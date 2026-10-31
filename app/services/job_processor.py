"""Main job processing pipeline orchestrator."""

import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from ..models.source import RawJobData, SourceConfig
from ..monitoring import get_job_metrics, timed, timer
from ..models.job import StandardJob, ProcessedJob, LocationInfo, SalaryInfo
from ..models.base import ProcessingStats, ValidationResult, DeduplicationResult
from ..models.common import JobStatus, ProcessingStatus
from ..models.company import CompanyInfo
from ..repositories.job_repository import JobRepository
from ..repositories.company_repository import CompanyRepository
from ..repositories.source_repository import SourceRepository
from ..services.field_extractor import FieldExtractor
from ..services.location_parser import LocationParser
from ..services.salary_parser import SalaryParser
from ..services.experience_parser import ExperienceParser
from ..services.skill_extractor import SkillExtractor
from ..services.company_service import CompanyService
from ..services.deduplication_service import DeduplicationService
from ..services.validation_service import ValidationService
from ..core.exceptions import ValidationError, ProcessingError
from ..core.database import db

logger = logging.getLogger(__name__)

# Storage-size guardrail: Supabase free tier is 500 MB and descriptions
# dominate usage (~5 KB x 50k jobs ~= 250 MB uncapped).
MAX_DESCRIPTION_BYTES = 4096


@dataclass
class ProcessingResult:
    """Result of processing a single job."""
    success: bool = False
    job_id: Optional[int] = None
    is_duplicate: bool = False
    duplicate_of: Optional[int] = None
    processing_time_ms: int = 0
    validation_result: Optional[ValidationResult] = None
    deduplication_result: Optional[DeduplicationResult] = None
    errors: List[str] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


@dataclass
class BatchProcessingResult:
    """Result of processing a batch of jobs."""
    total_jobs: int = 0
    successful_jobs: int = 0
    failed_jobs: int = 0
    duplicate_jobs: int = 0
    new_jobs_added: int = 0
    existing_jobs_updated: int = 0
    processing_time_ms: int = 0
    errors: List[str] = None
    warnings: List[str] = None
    job_results: List[ProcessingResult] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []
        if self.job_results is None:
            self.job_results = []


class JobProcessor:
    """Main service for processing raw job data through the complete pipeline."""
    
    def __init__(self, 
                 job_repository: JobRepository,
                 company_repository: CompanyRepository,
                 company_service: CompanyService,
                 location_parser: LocationParser,
                 salary_parser: SalaryParser,
                 skill_extractor: SkillExtractor,
                 deduplication_service: DeduplicationService,
                 validation_service: ValidationService):
        """Initialize with all required services."""
        self.job_repository = job_repository
        self.source_repository = SourceRepository()
        self.company_repository = company_repository
        self.company_service = company_service
        self.location_parser = location_parser
        self.salary_parser = salary_parser
        self.experience_parser = ExperienceParser()
        self.skill_extractor = skill_extractor
        self.deduplication_service = deduplication_service
        self.validation_service = validation_service
        self.logger = logging.getLogger(f"{__name__}")
        
        # Initialize metrics
        self.job_metrics = get_job_metrics()
    
    @timed("job_processing_total_duration", {"pipeline": "complete"})
    async def process_raw_job(self, raw_job: RawJobData, source_config: SourceConfig) -> ProcessingResult:
        """Process a single raw job through the complete pipeline."""
        start_time = datetime.utcnow()
        result = ProcessingResult()
        
        try:
            self.logger.info(f"Processing job {raw_job.external_id} from source {raw_job.source_id}")
            
            # Record processing attempt
            self.job_metrics.record_rate("job_processing_attempts", 1, {"source": raw_job.source_id})
            
            # Step 1: Extract fields from raw data
            extractor = FieldExtractor(source_config)
            extracted_fields = await extractor.extract_all_fields(raw_job)
            
            # Step 2: Convert to StandardJob
            standard_job = await self._create_standard_job(extracted_fields, raw_job)
            if not standard_job:
                result.errors.append("Failed to create standard job from extracted fields")
                return result
            
            # Step 3: Enhanced processing (location, salary, company)
            enhanced_job = await self._enhance_job_data(standard_job)
            
            # Step 4: Validation
            validation_result = await self.validation_service.validate_job(enhanced_job)
            result.validation_result = validation_result
            
            if not validation_result.is_valid:
                # Still process invalid jobs but mark them appropriately
                result.warnings.extend(validation_result.issues)
            
            # Step 5: Deduplication
            deduplication_result = await self.deduplication_service.process_deduplication(enhanced_job)
            result.deduplication_result = deduplication_result
            
            if deduplication_result.is_duplicate:
                # Handle duplicate job
                duplicate_job_id = await self._handle_duplicate_job(
                    enhanced_job, deduplication_result, raw_job.source_id, raw_job.raw_data
                )
                result.is_duplicate = True
                result.duplicate_of = duplicate_job_id
                result.success = True
                self.logger.info(f"Job {raw_job.external_id} identified as duplicate of job {duplicate_job_id}")
            else:
                # Process as new job
                processed_job = await self._create_processed_job(enhanced_job, raw_job, validation_result, deduplication_result)
                created = await self._create_or_get_existing_job(processed_job, raw_data=raw_job.raw_data)
                job_id = created.id
                result.job_id = job_id
                result.success = True
                self.logger.info(f"Job {raw_job.external_id} processed successfully as new job {job_id}")
            
        except Exception as e:
            error_msg = f"Error processing job {raw_job.external_id}: {str(e)}"
            self.logger.error(error_msg)
            result.errors.append(error_msg)
            result.success = False
        
        finally:
            # Calculate processing time
            end_time = datetime.utcnow()
            result.processing_time_ms = int((end_time - start_time).total_seconds() * 1000)
        
        return result
    
    async def process_job_batch(self, raw_jobs: List[RawJobData], source_config: SourceConfig, 
                              batch_size: int = 50, max_concurrent: int = 10) -> BatchProcessingResult:
        """Process a batch of raw jobs with concurrency control."""
        start_time = datetime.utcnow()
        batch_result = BatchProcessingResult(total_jobs=len(raw_jobs))
        
        try:
            self.logger.info(f"Processing batch of {len(raw_jobs)} jobs from source {source_config.source_id}")
            
            # Process jobs in chunks to control concurrency
            for i in range(0, len(raw_jobs), batch_size):
                chunk = raw_jobs[i:i + batch_size]
                
                # Create semaphore for concurrency control
                semaphore = asyncio.Semaphore(max_concurrent)
                
                async def process_with_semaphore(raw_job):
                    async with semaphore:
                        try:
                            return await self.process_raw_job(raw_job, source_config)
                        finally:
                            await db.release_task_session()
                
                # Process chunk concurrently
                chunk_tasks = [process_with_semaphore(job) for job in chunk]
                chunk_results = await asyncio.gather(*chunk_tasks, return_exceptions=True)
                
                # Process results
                for raw_job, chunk_result in zip(chunk, chunk_results):
                    if isinstance(chunk_result, Exception):
                        # Handle exception
                        error_result = ProcessingResult(
                            success=False,
                            errors=[f"Exception processing job {raw_job.external_id}: {str(chunk_result)}"]
                        )
                        batch_result.job_results.append(error_result)
                        batch_result.failed_jobs += 1
                    else:
                        # Handle successful processing
                        batch_result.job_results.append(chunk_result)
                        
                        if chunk_result.success:
                            batch_result.successful_jobs += 1
                            
                            if chunk_result.is_duplicate:
                                batch_result.duplicate_jobs += 1
                                batch_result.existing_jobs_updated += 1
                            else:
                                batch_result.new_jobs_added += 1
                        else:
                            batch_result.failed_jobs += 1
                            batch_result.errors.extend(chunk_result.errors)
                
                # Log progress
                processed_so_far = min(i + batch_size, len(raw_jobs))
                self.logger.info(f"Processed {processed_so_far}/{len(raw_jobs)} jobs")
            
            # Aggregate warnings
            for job_result in batch_result.job_results:
                batch_result.warnings.extend(job_result.warnings)
            
        except Exception as e:
            error_msg = f"Error processing job batch: {str(e)}"
            self.logger.error(error_msg)
            batch_result.errors.append(error_msg)
        
        finally:
            # Calculate total processing time
            end_time = datetime.utcnow()
            batch_result.processing_time_ms = int((end_time - start_time).total_seconds() * 1000)
            
            self.logger.info(f"Batch processing completed: {batch_result.successful_jobs}/{batch_result.total_jobs} successful, "
                           f"{batch_result.duplicate_jobs} duplicates, {batch_result.failed_jobs} failed, "
                           f"took {batch_result.processing_time_ms}ms")
        
        return batch_result

    async def process_standard_job(self, standard_job: StandardJob) -> ProcessingResult:
        """Process a job that's already been parsed into StandardJob form.

        For sources (like RemoteOK) that run their own parser instead of the
        generic FieldExtractor/FieldMapping path. Mirrors process_raw_job
        starting from the enhance step — skips raw extraction/standardization.
        """
        start_time = datetime.utcnow()
        result = ProcessingResult()

        try:
            self.logger.info(f"Processing job {standard_job.external_id} from source {standard_job.source_id}")
            self.job_metrics.record_rate("job_processing_attempts", 1, {"source": standard_job.source_id})

            enhanced_job = await self._enhance_job_data(standard_job)

            validation_result = await self.validation_service.validate_job(enhanced_job)
            result.validation_result = validation_result
            if not validation_result.is_valid:
                result.warnings.extend(validation_result.issues)

            deduplication_result = await self.deduplication_service.process_deduplication(enhanced_job)
            result.deduplication_result = deduplication_result

            if deduplication_result.is_duplicate:
                duplicate_job_id = await self._handle_duplicate_job(
                    enhanced_job, deduplication_result, standard_job.source_id, None
                )
                result.is_duplicate = True
                result.duplicate_of = duplicate_job_id
                result.success = True
                self.logger.info(f"Job {standard_job.external_id} identified as duplicate of job {duplicate_job_id}")
            else:
                processed_job = ProcessedJob(
                    **enhanced_job.dict(exclude={'quality_score'}),
                    status=JobStatus.ACTIVE,
                    first_seen_at=datetime.utcnow(),
                    last_seen_at=datetime.utcnow(),
                    validation_result=validation_result,
                    deduplication_result=deduplication_result,
                    spam_score=min(100.0, max(0.0, validation_result.quality_metrics.get('spam_likelihood_score', 0) if validation_result.quality_metrics else 0)),
                    quality_score=min(100.0, max(0.0, validation_result.quality_metrics.get('overall_quality_score', 0) if validation_result.quality_metrics else 0)),
                    is_valid_link=await self.validation_service.validate_url(enhanced_job.apply_url)
                )
                created = await self._create_or_get_existing_job(processed_job)
                job_id = created.id
                result.job_id = job_id
                result.success = True
                self.logger.info(f"Job {standard_job.external_id} processed successfully as new job {job_id}")

        except Exception as e:
            error_msg = f"Error processing job {standard_job.external_id}: {str(e)}"
            self.logger.error(error_msg)
            result.errors.append(error_msg)
            result.success = False

        finally:
            end_time = datetime.utcnow()
            result.processing_time_ms = int((end_time - start_time).total_seconds() * 1000)

        return result

    async def process_standard_job_batch(self, standard_jobs: List[StandardJob],
                                        batch_size: int = 50, max_concurrent: int = 10) -> BatchProcessingResult:
        """Process a batch of already-parsed StandardJob objects with concurrency control."""
        start_time = datetime.utcnow()
        batch_result = BatchProcessingResult(total_jobs=len(standard_jobs))

        try:
            for i in range(0, len(standard_jobs), batch_size):
                chunk = standard_jobs[i:i + batch_size]
                semaphore = asyncio.Semaphore(max_concurrent)

                async def process_with_semaphore(standard_job):
                    async with semaphore:
                        try:
                            return await self.process_standard_job(standard_job)
                        finally:
                            await db.release_task_session()

                chunk_tasks = [process_with_semaphore(job) for job in chunk]
                chunk_results = await asyncio.gather(*chunk_tasks, return_exceptions=True)

                for standard_job, chunk_result in zip(chunk, chunk_results):
                    if isinstance(chunk_result, Exception):
                        error_result = ProcessingResult(
                            success=False,
                            errors=[f"Exception processing job {standard_job.external_id}: {str(chunk_result)}"]
                        )
                        batch_result.job_results.append(error_result)
                        batch_result.failed_jobs += 1
                    else:
                        batch_result.job_results.append(chunk_result)

                        if chunk_result.success:
                            batch_result.successful_jobs += 1
                            if chunk_result.is_duplicate:
                                batch_result.duplicate_jobs += 1
                                batch_result.existing_jobs_updated += 1
                            else:
                                batch_result.new_jobs_added += 1
                        else:
                            batch_result.failed_jobs += 1
                            batch_result.errors.extend(chunk_result.errors)

                self.logger.info(f"Processed {min(i + batch_size, len(standard_jobs))}/{len(standard_jobs)} jobs")

            for job_result in batch_result.job_results:
                batch_result.warnings.extend(job_result.warnings)

        except Exception as e:
            error_msg = f"Error processing job batch: {str(e)}"
            self.logger.error(error_msg)
            batch_result.errors.append(error_msg)

        finally:
            end_time = datetime.utcnow()
            batch_result.processing_time_ms = int((end_time - start_time).total_seconds() * 1000)
            self.logger.info(f"Batch processing completed: {batch_result.successful_jobs}/{batch_result.total_jobs} successful, "
                           f"{batch_result.duplicate_jobs} duplicates, {batch_result.failed_jobs} failed, "
                           f"took {batch_result.processing_time_ms}ms")

        return batch_result

    async def reprocess_existing_jobs(self, job_ids: List[int], source_config: SourceConfig) -> BatchProcessingResult:
        """Reprocess existing jobs (e.g., after algorithm improvements)."""
        try:
            self.logger.info(f"Reprocessing {len(job_ids)} existing jobs")
            
            # Fetch existing jobs
            existing_jobs = await self.job_repository.get_jobs_by_ids(job_ids)
            
            # Convert back to raw format for reprocessing
            raw_jobs = []
            for job in existing_jobs:
                # Create pseudo raw job data from existing job
                raw_job = RawJobData(
                    source_id=job.source_id,
                    external_id=job.external_id,
                    raw_data=await self._convert_job_to_raw_data(job),
                    source_url=getattr(job, 'source_url', None),
                    fetched_at=job.created_at
                )
                raw_jobs.append(raw_job)
            
            # Process as batch
            return await self.process_job_batch(raw_jobs, source_config)
            
        except Exception as e:
            error_msg = f"Error reprocessing jobs: {str(e)}"
            self.logger.error(error_msg)
            return BatchProcessingResult(
                total_jobs=len(job_ids),
                failed_jobs=len(job_ids),
                errors=[error_msg]
            )
    
    async def get_processing_stats(self, source_id: Optional[int] = None, 
                                 days: int = 7) -> ProcessingStats:
        """Get processing statistics for monitoring."""
        try:
            # This would typically query the database for processing metrics
            # For now, return a basic structure
            return ProcessingStats(
                total_jobs_processed=0,
                successful_jobs=0,
                failed_jobs=0,
                duplicate_jobs=0,
                average_processing_time_ms=0,
                quality_score_average=0.0,
                spam_detection_rate=0.0
            )
        except Exception as e:
            self.logger.error(f"Error getting processing stats: {e}")
            raise ProcessingError(f"Failed to get processing stats: {str(e)}")
    
    # Private helper methods
    
    async def _create_standard_job(self, extracted_fields: Dict[str, Any], raw_job: RawJobData) -> Optional[StandardJob]:
        """Create StandardJob from extracted fields."""
        try:
            # Extract basic required fields
            title_result = extracted_fields.get('title')
            company_result = extracted_fields.get('company')
            apply_url_result = extracted_fields.get('apply_url')
            
            if not all([title_result, company_result, apply_url_result]):
                self.logger.warning(f"Missing required fields for job {raw_job.external_id}")
                return None
            
            # Create StandardJob with extracted data
            standard_job = StandardJob(
                title=title_result.value,
                company_name=company_result.value,
                apply_url=apply_url_result.value
            )
            
            # Add optional fields if available
            location_result = extracted_fields.get('location')
            if location_result and location_result.value:
                standard_job.location = LocationInfo(**location_result.value)
            
            description_result = extracted_fields.get('description')
            if description_result and description_result.value:
                standard_job.description = description_result.value
            
            posted_date_result = extracted_fields.get('posted_date')
            if posted_date_result and posted_date_result.value:
                standard_job.posted_date = posted_date_result.value

            contact_emails_result = extracted_fields.get('contact_emails')
            if contact_emails_result and contact_emails_result.value:
                standard_job.contact_emails = contact_emails_result.value
            
            employment_type_result = extracted_fields.get('employment_type')
            if employment_type_result and employment_type_result.value:
                standard_job.employment_type = employment_type_result.value
            
            experience_level_result = extracted_fields.get('experience_level')
            if experience_level_result and experience_level_result.value:
                standard_job.experience_level = experience_level_result.value

            experience_years_result = extracted_fields.get('experience_years')
            if experience_years_result and experience_years_result.value:
                standard_job.min_exp_years = experience_years_result.value.get('min_years')
                standard_job.max_exp_years = experience_years_result.value.get('max_years')

            # Handle salary info
            salary_result = extracted_fields.get('salary_info')
            if salary_result and salary_result.value:
                standard_job.salary = SalaryInfo(**salary_result.value)
            
            # Handle skills
            skills_required_result = extracted_fields.get('skills_required')
            if skills_required_result and skills_required_result.value:
                standard_job.skills_extracted = skills_required_result.value
            
            return standard_job
            
        except Exception as e:
            self.logger.error(f"Error creating standard job: {e}")
            return None
    
    async def _enhance_job_data(self, job: StandardJob) -> StandardJob:
        """Enhance job data using specialized services."""
        try:
            # Enhance location information
            if job.location and hasattr(job.location, 'raw_location'):
                enhanced_location = await self.location_parser.parse_location(job.location.raw_location)
                if enhanced_location.confidence > 0.5:
                    # Update location with parsed information
                    job.location.city = enhanced_location.city
                    job.location.state_province = enhanced_location.state_province
                    job.location.country = enhanced_location.country
                    job.location.country_code = enhanced_location.country_code
                    job.location.is_remote = enhanced_location.is_remote
                    job.location.work_arrangement = enhanced_location.work_arrangement

                if job.location.is_remote:
                    job.location.remote_scope = await self.location_parser.classify_remote_scope(
                        is_remote=True,
                        location_text=job.location.raw_location,
                        description_text=getattr(job, 'description', None),
                    )
            
            # Enhance salary information
            if job.salary and hasattr(job.salary, 'raw_salary') and job.salary.raw_salary:
                enhanced_salary = await self.salary_parser.parse_salary(
                    job.salary.raw_salary, 
                    context=getattr(job, 'description', None)
                )
                if enhanced_salary.confidence > 0.5:
                    # Update salary with parsed information
                    if enhanced_salary.min_salary:
                        job.salary.min_salary = enhanced_salary.min_salary
                    if enhanced_salary.max_salary:
                        job.salary.max_salary = enhanced_salary.max_salary
                    job.salary.currency = enhanced_salary.currency
                    job.salary.period = enhanced_salary.period
                    job.salary.is_disclosed = enhanced_salary.is_disclosed
                    job.salary.is_negotiable = enhanced_salary.is_negotiable
            
            # Enhance experience range — most sources have no structured field,
            # so parse from description text, falling back to a title-derived guess.
            # Skipped entirely when the source stated the range itself: a guess
            # off the title read "Principal ..." as 5+ on jobs Hirist labels 10-15.
            if job.min_exp_years is None and job.max_exp_years is None:
                experience_result = self.experience_parser.parse_experience(
                    getattr(job, 'description', None), job.title
                )
                if experience_result.confidence > 0.0:
                    job.min_exp_years = experience_result.min_years
                    job.max_exp_years = experience_result.max_years

            # Enhance company information
            company_result = await self.company_service.normalize_company_name(job.company_name)
            if company_result:
                # Update with normalized company name
                job.company_name = company_result.normalized_name
            
            # Skills: merge the source's own curated labels (e.g. Instahyre's
            # `keywords` array, already sitting in skills_extracted from field
            # extraction) with skills regex-extracted from description/requirements.
            # Curated labels are trusted over regex guesses on the same skill name.
            curated_skills = self.skill_extractor.canonicalize_skill_names(job.skills_extracted or [])
            regex_result = await self.skill_extractor.extract_from_job(job)

            merged_by_name = {s.name: s for s in regex_result.skills}
            for skill in curated_skills:
                merged_by_name[skill.name] = skill

            if merged_by_name:
                job.skills_required = list(merged_by_name.values())
                job.skills_extracted = list(merged_by_name.keys())
            
            # Generate content hash for deduplication
            job.content_hash = await self.deduplication_service.generate_content_hash(job)
            
            return job
            
        except Exception as e:
            self.logger.warning(f"Error enhancing job data: {e}")
            return job  # Return original job if enhancement fails
    
    # Apply-URL precedence for dedup merges — applying at the source converts
    # better than applying through an aggregator. Lower number wins.
    _SOURCE_PRECEDENCE = {'ats': 1, 'instahyre': 2}

    def _source_precedence(self, source_name: Optional[str], raw_data: Optional[Dict[str, Any]]) -> int:
        """Resolve a source (+ optional raw payload, for JobSpy's LinkedIn/Indeed
        split) to its apply_url precedence tier: 1 ATS direct, 2 Instahyre,
        3 LinkedIn, 4 Indeed, 5 remote boards (everything else)."""
        name = (source_name or '').lower()
        if name in self._SOURCE_PRECEDENCE:
            return self._SOURCE_PRECEDENCE[name]
        if name == 'jobspy':
            site = str((raw_data or {}).get('site', '')).lower()
            return 3 if 'linkedin' in site else 4
        return 5

    async def _handle_duplicate_job(self, job: StandardJob, dedup_result: DeduplicationResult,
                                    source_id: Optional[int] = None,
                                    raw_data: Optional[Dict[str, Any]] = None) -> Optional[int]:
        """Handle a duplicate job by updating the existing one.

        Also applies dedup source precedence: if the incoming job's source
        outranks the stored job's source, the existing row's apply_url is
        replaced with the incoming (better) one.
        """
        try:
            if not dedup_result.duplicate_job_ids:
                return None

            # Get the best matching existing job
            existing_job_id = dedup_result.duplicate_job_ids[0]
            existing_job = await self.job_repository.get_by_id(existing_job_id)

            if not existing_job:
                return None

            update_data = {'last_seen_at': datetime.utcnow()}

            if source_id is not None and job.apply_url:
                try:
                    incoming_source = await self.source_repository.get_by_id(source_id)
                    existing_source = await self.source_repository.get_by_id(existing_job.source_id)
                    if incoming_source and existing_source:
                        incoming_precedence = self._source_precedence(incoming_source.name, raw_data)
                        existing_detail = await self.job_repository.get_job_detail(existing_job_id)
                        existing_raw = existing_detail.raw_data if existing_detail else None
                        existing_precedence = self._source_precedence(existing_source.name, existing_raw)
                        if incoming_precedence < existing_precedence:
                            update_data['apply_url'] = job.apply_url
                except Exception as e:
                    self.logger.warning(
                        f"Could not resolve source precedence for dedup merge of job {existing_job_id}: {e}"
                    )

            await self.job_repository.update(existing_job_id, update_data)
            return existing_job_id

        except Exception as e:
            self.logger.error(f"Error handling duplicate job: {e}")
            return None
    
    async def _create_processed_job(self, standard_job: StandardJob, raw_job: RawJobData,
                                  validation_result: ValidationResult, 
                                  dedup_result: DeduplicationResult) -> ProcessedJob:
        """Create ProcessedJob from StandardJob with all metadata."""
        try:
            # Convert StandardJob to ProcessedJob
            processed_job = ProcessedJob(
                # Copy all fields from StandardJob
                **standard_job.dict(exclude={'quality_score', 'source_id', 'external_id'}),

                # Add processing metadata
                source_id=raw_job.source_id,
                external_id=raw_job.external_id,
                status=JobStatus.ACTIVE,
                first_seen_at=datetime.utcnow(),
                last_seen_at=datetime.utcnow(),
                validation_result=validation_result,
                deduplication_result=dedup_result,
                
                # Quality metrics
                spam_score=min(100.0, max(0.0, validation_result.quality_metrics.get('spam_likelihood_score', 0) if validation_result.quality_metrics else 0)),
                quality_score=min(100.0, max(0.0, validation_result.quality_metrics.get('overall_quality_score', 0) if validation_result.quality_metrics else 0)),

                # URL validation
                is_valid_link=await self.validation_service.validate_url(standard_job.apply_url)
            )
            
            return processed_job
            
        except Exception as e:
            self.logger.error(f"Error creating processed job: {e}")
            raise ProcessingError(f"Failed to create processed job: {str(e)}")

    async def _processed_job_to_db_data(self, processed_job: ProcessedJob) -> Dict[str, Any]:
        """Flatten a ProcessedJob (Pydantic, nested) into JobDB (SQLAlchemy, flat) column data.

        employment_type_id/experience_level_id/work_arrangement_id are left
        unset (nullable FKs) — resolving StandardJob's enum values to lookup
        table rows isn't implemented anywhere in the codebase yet.
        """
        company_id = None
        if processed_job.company_name:
            try:
                company_id, _ = await self.company_service.find_or_create_company(
                    CompanyInfo(name=processed_job.company_name)
                )
            except Exception as e:
                self.logger.warning(f"Could not resolve company '{processed_job.company_name}': {e}")

        location = processed_job.location
        salary = processed_job.salary

        return {
            'source_id': processed_job.source_id,
            'external_id': processed_job.external_id,
            'company_id': company_id,
            'title': processed_job.title,
            'normalized_title': processed_job.normalized_title,
            'location_raw': location.raw_location if location else None,
            'city': location.city if location else None,
            'state_province': location.state_province if location else None,
            'country': location.country if location else "Unknown",
            'is_remote': location.is_remote if location else processed_job.is_remote,
            'remote_scope': location.remote_scope if location else None,
            'min_exp_years': processed_job.min_exp_years,
            'max_exp_years': processed_job.max_exp_years,
            'salary_min': salary.min_salary if salary else None,
            'salary_max': salary.max_salary if salary else None,
            'salary_currency': salary.currency.value if salary else "USD",
            'salary_period': salary.period.value if salary else "year",
            # A salary is only "disclosed" if we actually came away with a number.
            # Several sources set the flag from the presence of a salary *field*
            # rather than a parsed value, which left rows claiming disclosure with
            # NULL min/max — and Phase 2 scoring reads that as "disclosed but below
            # your floor" (0 pts), ranking them beneath genuinely-undisclosed jobs
            # (2 pts). Enforce the invariant here, at the one place the row is built.
            'salary_disclosed': bool(
                salary and salary.is_disclosed and (salary.min_salary or salary.max_salary)
            ),
            'apply_url': processed_job.apply_url,
            'apply_email': processed_job.apply_email,
            # `context` is the window of surrounding words the regex extractor
            # captured to score its own confidence (skill_extractor.py). It is
            # never read back — but persisting it stored a slice of the
            # description ~7x per job, 19 MB across the corpus. Drop it here,
            # at the one place skills become a row.
            'skills_required': [s.dict(exclude={'context'}) for s in processed_job.skills_required],
            'skills_preferred': [s.dict(exclude={'context'}) for s in processed_job.skills_preferred],
            'skills_extracted': processed_job.skills_extracted,
            'posted_date': processed_job.posted_date,
            'application_deadline': processed_job.application_deadline,
            'first_seen_at': processed_job.first_seen_at,
            'last_seen_at': processed_job.last_seen_at,
            'last_updated_at': processed_job.last_updated_at,
            'status': processed_job.status.value,
            'is_valid_link': processed_job.is_valid_link,
            'quality_score': processed_job.quality_score,
            'spam_score': processed_job.spam_score,
            'content_hash': processed_job.content_hash,
            'benefits': processed_job.benefits,
        }

    @staticmethod
    def _truncate_bytes(text: Optional[str], max_bytes: int) -> Optional[str]:
        """Truncate to a UTF-8 byte budget without splitting a multi-byte char."""
        if not text:
            return text
        encoded = text.encode('utf-8')
        if len(encoded) <= max_bytes:
            return text
        return encoded[:max_bytes].decode('utf-8', errors='ignore')

    async def _create_or_get_existing_job(self, processed_job: ProcessedJob,
                                          raw_data: Optional[Dict[str, Any]] = None):
        """Insert the job (plus its job_details row), or return the existing
        row if we've already ingested it.

        Dedup only checks content_hash/fuzzy similarity, not (source_id,
        external_id) directly — so re-ingesting the exact same source item
        (e.g. a repeat sync) can reach here even though a row already
        exists, and hits the DB's unique constraint. Treat that as success,
        not failure.
        """
        db_data = await self._processed_job_to_db_data(processed_job)
        try:
            job = await self.job_repository.create(db_data)
        except ValidationError:
            existing = await self.job_repository.get_by_external_id(
                processed_job.source_id, processed_job.external_id
            )
            if not existing:
                raise
            job = existing

        try:
            await self.job_repository.upsert_job_detail(job.id, {
                'description': self._truncate_bytes(processed_job.description, MAX_DESCRIPTION_BYTES),
                'requirements': processed_job.requirements,
                'responsibilities': processed_job.responsibilities,
                'company_benefits': '; '.join(processed_job.benefits) if processed_job.benefits else None,
                'raw_data': raw_data,
                'contact_emails': processed_job.contact_emails or None,
            })
        except Exception as e:
            # job_details is supplementary — don't fail the whole job over it.
            self.logger.warning(f"Failed to store job_details for job {job.id}: {e}")

        return job

    async def _convert_job_to_raw_data(self, job) -> Dict[str, Any]:
        """Convert existing job back to raw data format for reprocessing."""
        # This is a simplified conversion - in practice you'd want to preserve
        # as much original raw data as possible
        return {
            'title': job.title,
            'company': job.company_name,
            'location': str(job.location) if job.location else None,
            'description': getattr(job, 'description', None),
            'apply_url': job.apply_url,
            'posted_date': job.posted_date.isoformat() if job.posted_date else None,
            'salary': str(job.salary) if job.salary else None,
            'employment_type': str(job.employment_type) if job.employment_type else None,
            'experience_level': str(job.experience_level) if job.experience_level else None
        }