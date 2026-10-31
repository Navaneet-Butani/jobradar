"""Job deduplication service using hash-based and fuzzy matching."""

import hashlib
import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any, Tuple, Set
from rapidfuzz import fuzz, process

from ..models.job import StandardJob, ProcessedJob, JobSearchCriteria
from ..models.base import DeduplicationResult, ValidationResult
from ..repositories.job_repository import JobRepository
from ..core.exceptions import ValidationError
from ..services.company_service import CompanyService
from .deduplication.bloom_filter import DuplicationBloomFilter
from .deduplication.similarity_calculator import SimilarityCalculator
from .deduplication.cross_source_detector import CrossSourceDetector
from .deduplication.group_manager import DuplicateGroupsManager
from ..repositories.duplicate_group_repository import DuplicateGroupRepository

logger = logging.getLogger(__name__)


class DuplicateMatch:
    """Represents a potential duplicate match."""
    
    def __init__(self, job_id: int, similarity_score: float, match_type: str, 
                 match_factors: Dict[str, Any], confidence: float = 0.0):
        self.job_id = job_id
        self.similarity_score = similarity_score
        self.match_type = match_type
        self.match_factors = match_factors
        self.confidence = confidence


class DeduplicationService:
    """Service for detecting and handling duplicate job postings."""
    
    # Similarity thresholds for different match types
    EXACT_HASH_THRESHOLD = 1.0  # 100% match
    HIGH_SIMILARITY_THRESHOLD = 0.95  # 95%+ likely duplicate
    MEDIUM_SIMILARITY_THRESHOLD = 0.85  # 85%+ possible duplicate  
    LOW_SIMILARITY_THRESHOLD = 0.75  # 75%+ worth investigating
    
    # Content hash weights for different fields
    HASH_WEIGHTS = {
        'title': 0.3,
        'company': 0.25, 
        'location': 0.2,
        'posted_date': 0.15,
        'salary': 0.1
    }
    
    def __init__(self, job_repository: JobRepository, company_service: CompanyService):
        """Initialize with required dependencies."""
        self.job_repository = job_repository
        self.company_service = company_service
        self.logger = logging.getLogger(f"{__name__}")

        # Initialize bloom filter for performance optimization
        self.bloom_filter = None
        self._bloom_filter_initialized = False

        # Initialize enhanced similarity calculator
        self.similarity_calculator = SimilarityCalculator(company_service)

        # Initialize cross-source detector
        self.cross_source_detector = CrossSourceDetector(
            job_repository=self.job_repository,
            similarity_calculator=self.similarity_calculator
        )

        # Initialize group manager
        self.group_repository = DuplicateGroupRepository()
        self.group_manager = DuplicateGroupsManager(
            job_repository=self.job_repository,
            group_repository=self.group_repository,
            similarity_calculator=self.similarity_calculator
        )
    
    async def _ensure_bloom_filter_initialized(self) -> None:
        """Ensure bloom filter is initialized."""
        if not self._bloom_filter_initialized:
            try:
                self.bloom_filter = DuplicationBloomFilter()
                await self.bloom_filter.initialize()
                self._bloom_filter_initialized = True
                self.logger.info("Bloom filter initialized successfully")
            except Exception as e:
                self.logger.warning(f"Failed to initialize bloom filter: {e}")
                self.bloom_filter = None
                self._bloom_filter_initialized = True  # Set to true to avoid repeated attempts

    async def find_duplicates(self, job: StandardJob,
                            search_window_days: int = 30) -> List[DuplicateMatch]:
        """Find potential duplicates for a job using multiple strategies with bloom filter optimization."""
        try:
            duplicates = []

            # Ensure bloom filter is initialized
            await self._ensure_bloom_filter_initialized()

            # Generate content hash for exact matching
            content_hash = await self.generate_content_hash(job)

            # STEP 1: Bloom filter check (fast negative check)
            if self.bloom_filter:
                might_exist = await self.bloom_filter.check_hash(content_hash)

                if not might_exist:
                    # Definitely no duplicates, skip expensive database queries
                    self.logger.debug(f"Bloom filter negative check: no duplicates for {content_hash[:12]}...")
                    return []
                else:
                    self.logger.debug(f"Bloom filter positive check: checking database for {content_hash[:12]}...")

            # STEP 2: Database checks (bloom filter indicates possible match or bloom filter unavailable)
            # Strategy 1: Exact hash match (fastest)
            exact_matches = await self._find_exact_hash_matches(content_hash)
            duplicates.extend(exact_matches)
            
            # Strategy 2: High similarity fuzzy matching
            if not exact_matches:  # Only if no exact matches found
                fuzzy_matches = await self._find_fuzzy_matches(
                    job, search_window_days, min_similarity=self.HIGH_SIMILARITY_THRESHOLD
                )
                duplicates.extend(fuzzy_matches)
            
            # Strategy 3: Medium similarity for investigation
            if len(duplicates) < 3:  # Get more candidates if needed
                medium_matches = await self._find_fuzzy_matches(
                    job, search_window_days, 
                    min_similarity=self.MEDIUM_SIMILARITY_THRESHOLD,
                    max_results=5
                )
                # Add only if not already found
                existing_ids = {dup.job_id for dup in duplicates}
                for match in medium_matches:
                    if match.job_id not in existing_ids:
                        duplicates.append(match)
            
            # Sort by similarity score descending
            duplicates.sort(key=lambda x: x.similarity_score, reverse=True)
            
            self.logger.info(f"Found {len(duplicates)} potential duplicates for job")
            return duplicates[:10]  # Limit to top 10 matches
            
        except Exception as e:
            self.logger.error(f"Error finding duplicates: {e}")
            return []
    
    async def generate_content_hash(self, job: StandardJob) -> str:
        """Generate a content hash for deduplication."""
        try:
            # Normalize key fields for hashing
            normalized_title = self._normalize_for_hash(job.title)
            normalized_company = await self._normalize_company_for_hash(job.company_name)
            normalized_location = self._normalize_location_for_hash(job.location)
            
            # Create deterministic date string (day precision)
            date_str = ""
            if job.posted_date:
                date_str = job.posted_date.strftime("%Y-%m-%d")
            
            # Create salary string for hashing
            salary_str = self._normalize_salary_for_hash(job.salary)
            
            # Combine fields in consistent order
            hash_components = [
                normalized_title,
                normalized_company, 
                normalized_location,
                date_str,
                salary_str
            ]
            
            # Create hash string
            content_string = "|".join(filter(None, hash_components))
            
            # Generate SHA-256 hash
            content_hash = hashlib.sha256(content_string.encode('utf-8')).hexdigest()
            
            self.logger.debug(f"Generated content hash: {content_hash[:12]}... from: {content_string}")
            return content_hash
            
        except Exception as e:
            self.logger.error(f"Error generating content hash: {e}")
            # Return a fallback hash based on basic fields
            fallback_string = f"{job.title}|{job.company_name}"
            return hashlib.md5(fallback_string.encode('utf-8')).hexdigest()
    
    async def calculate_similarity(self, job1: StandardJob, job2: StandardJob) -> float:
        """Calculate similarity score between two jobs."""
        try:
            scores = {}
            weights = {
                'title': 0.35,
                'company': 0.25,
                'location': 0.15,
                'salary': 0.15,
                'description': 0.10
            }
            
            # Title similarity
            scores['title'] = self._calculate_text_similarity(job1.title, job2.title)
            
            # Company similarity (use fuzzy matching)
            scores['company'] = await self._calculate_company_similarity(
                job1.company_name, job2.company_name
            )
            
            # Location similarity
            location1 = self._get_location_string(job1.location)
            location2 = self._get_location_string(job2.location)
            scores['location'] = self._calculate_location_similarity(location1, location2)
            
            # Salary similarity
            scores['salary'] = self._calculate_salary_similarity(job1.salary, job2.salary)
            
            # Description similarity (if available)
            if hasattr(job1, 'description') and hasattr(job2, 'description'):
                scores['description'] = self._calculate_description_similarity(
                    job1.description, job2.description
                )
            else:
                scores['description'] = 0.5  # Neutral score if no description
                weights['description'] = 0.0  # Don't count it
                # Redistribute description weight to other factors
                for key in ['title', 'company', 'location']:
                    weights[key] += 0.033
            
            # Calculate weighted average
            total_score = sum(scores[key] * weights[key] for key in scores)
            
            self.logger.debug(f"Similarity scores: {scores}, Total: {total_score:.3f}")
            return total_score
            
        except Exception as e:
            self.logger.error(f"Error calculating similarity: {e}")
            return 0.0
    
    async def merge_duplicate_info(self, existing_job: ProcessedJob, 
                                 new_job: StandardJob) -> ProcessedJob:
        """Merge information from a duplicate job into existing job."""
        try:
            # Update last seen timestamp
            existing_job.last_seen_at = datetime.utcnow()
            
            # Merge source information if from different sources
            if hasattr(new_job, 'source_id') and new_job.source_id != existing_job.source_id:
                # Track additional sources (implementation depends on schema)
                self.logger.info(f"Job found in additional source: {new_job.source_id}")
            
            # Update with more complete information if available
            merge_updates = {}
            
            # Use more detailed description if current one is short
            if (hasattr(new_job, 'description') and new_job.description and 
                len(new_job.description) > len(existing_job.description or "")):
                merge_updates['description'] = new_job.description
            
            # Use disclosed salary if current job doesn't have one
            if (new_job.salary and new_job.salary.is_disclosed and 
                (not existing_job.salary or not existing_job.salary.is_disclosed)):
                merge_updates['salary'] = new_job.salary
            
            # Update apply URL if current one is broken or placeholder
            if (new_job.apply_url and 
                (not existing_job.apply_url or 'example.com' in existing_job.apply_url)):
                merge_updates['apply_url'] = new_job.apply_url
            
            # Apply updates
            for field, value in merge_updates.items():
                setattr(existing_job, field, value)
            
            # Update deduplication result
            existing_job.deduplication_result = DeduplicationResult(
                is_duplicate=True,
                duplicate_count=existing_job.deduplication_result.duplicate_count + 1 if existing_job.deduplication_result else 1,
                last_duplicate_found=datetime.utcnow(),
                duplicate_sources=[new_job.source_id] if hasattr(new_job, 'source_id') else []
            )
            
            self.logger.info(f"Merged duplicate job information, updates: {list(merge_updates.keys())}")
            return existing_job
            
        except Exception as e:
            self.logger.error(f"Error merging duplicate info: {e}")
            return existing_job
    
    async def process_new_job(self, job: StandardJob) -> DeduplicationResult:
        """Process new job and add to bloom filter if not duplicate."""
        # Process deduplication
        result = await self.process_deduplication(job)

        # Add to bloom filter for future checks if not a duplicate
        if not result.is_duplicate and self.bloom_filter:
            try:
                content_hash = await self.generate_content_hash(job)
                await self.bloom_filter.add_hash(content_hash)
                self.logger.debug(f"Added hash to bloom filter: {content_hash[:12]}...")
            except Exception as e:
                self.logger.warning(f"Failed to add hash to bloom filter: {e}")

        return result

    async def process_cross_source_deduplication(self, job: StandardJob) -> Dict:
        """Process cross-source deduplication for a new job."""
        try:
            # Find cross-source duplicates
            cross_source_matches = await self.cross_source_detector.find_cross_source_duplicates(
                job, exclude_source_id=getattr(job, 'source_id', None)
            )

            if not cross_source_matches:
                return {
                    'action': 'create_new',
                    'cross_source_duplicates': 0,
                    'resolution': 'no_duplicates_found'
                }

            # Resolve conflicts
            resolution = await self.cross_source_detector.resolve_cross_source_conflicts(
                cross_source_matches, job
            )

            self.logger.info(f"Cross-source resolution: {resolution['action']} for {len(cross_source_matches)} matches")

            return {
                'action': resolution['action'],
                'cross_source_duplicates': len(cross_source_matches),
                'resolution': resolution,
                'matches': cross_source_matches[:5]  # Limit for logging
            }

        except Exception as e:
            self.logger.error(f"Error in cross-source deduplication: {e}")
            return {
                'action': 'create_new',
                'cross_source_duplicates': 0,
                'resolution': 'error',
                'error': str(e)
            }

    async def process_group_management(self, duplicates: List[DuplicateMatch]) -> Dict:
        """Process duplicate group management for found duplicates."""
        try:
            if len(duplicates) < 2:
                return {
                    'action': 'no_group_created',
                    'reason': 'insufficient_duplicates',
                    'duplicate_count': len(duplicates)
                }

            # Extract job IDs and similarity scores
            job_ids = [dup.job_id for dup in duplicates]
            similarity_scores = {dup.job_id: dup.similarity_score for dup in duplicates}

            # Check if any jobs are already in groups
            existing_groups = set()
            for job_id in job_ids:
                mapping = await self.group_repository.get_job_mapping(job_id)
                if mapping:
                    existing_groups.add(mapping.group_id)

            if existing_groups:
                # Add to existing group or merge groups
                return await self._handle_existing_groups(job_ids, similarity_scores, existing_groups)
            else:
                # Create new group
                group_id = await self.group_manager.create_duplicate_group(job_ids, similarity_scores)

                if group_id:
                    return {
                        'action': 'group_created',
                        'group_id': group_id,
                        'member_count': len(job_ids),
                        'primary_job_id': await self._get_group_primary_job(group_id)
                    }
                else:
                    return {
                        'action': 'group_creation_failed',
                        'reason': 'unknown_error',
                        'job_ids': job_ids
                    }

        except Exception as e:
            self.logger.error(f"Error in group management: {e}")
            return {
                'action': 'group_management_error',
                'error': str(e)
            }

    async def _handle_existing_groups(self, job_ids: List[int],
                                    similarity_scores: Dict[int, float],
                                    existing_groups: Set[int]) -> Dict:
        """Handle cases where some jobs are already in groups."""
        try:
            if len(existing_groups) == 1:
                # Add new jobs to existing group
                group_id = list(existing_groups)[0]
                added_count = 0

                for job_id in job_ids:
                    mapping = await self.group_repository.get_job_mapping(job_id)
                    if not mapping:  # Only add if not already in group
                        success = await self.group_manager.add_job_to_group(
                            group_id, job_id, similarity_scores.get(job_id, 0.0)
                        )
                        if success:
                            added_count += 1

                return {
                    'action': 'jobs_added_to_group',
                    'group_id': group_id,
                    'jobs_added': added_count
                }

            elif len(existing_groups) > 1:
                # Multiple groups found - consider merging
                group_list = list(existing_groups)
                primary_group = group_list[0]

                # Try to merge groups
                for secondary_group in group_list[1:]:
                    merged_group = await self.group_manager.merge_groups(primary_group, secondary_group)
                    if merged_group:
                        primary_group = merged_group

                return {
                    'action': 'groups_merged',
                    'primary_group_id': primary_group,
                    'merged_groups': len(group_list) - 1
                }

            return {
                'action': 'no_action_taken',
                'reason': 'complex_group_situation'
            }

        except Exception as e:
            self.logger.error(f"Error handling existing groups: {e}")
            return {
                'action': 'existing_groups_error',
                'error': str(e)
            }

    async def _get_group_primary_job(self, group_id: int) -> Optional[int]:
        """Get the primary job ID for a group."""
        try:
            group = await self.group_repository.get_group(group_id)
            return group.primary_job_id if group else None
        except Exception:
            return None

    async def process_deduplication(self, job: StandardJob) -> DeduplicationResult:
        """Process deduplication for a job and return result."""
        try:
            # Find potential duplicates
            duplicates = await self.find_duplicates(job)

            if not duplicates:
                return DeduplicationResult(
                    is_duplicate=False,
                    duplicate_count=0,
                    confidence_score=1.0,
                    match_type="no_duplicates"
                )
            
            # Get the best match
            best_match = duplicates[0]
            
            # Determine if it's a duplicate based on similarity
            is_duplicate = best_match.similarity_score >= self.HIGH_SIMILARITY_THRESHOLD
            
            # Determine match type
            if best_match.similarity_score >= self.EXACT_HASH_THRESHOLD:
                match_type = "exact_hash"
            elif best_match.similarity_score >= self.HIGH_SIMILARITY_THRESHOLD:
                match_type = "high_similarity"
            elif best_match.similarity_score >= self.MEDIUM_SIMILARITY_THRESHOLD:
                match_type = "medium_similarity"
            else:
                match_type = "low_similarity"
            
            return DeduplicationResult(
                is_duplicate=is_duplicate,
                duplicate_count=len(duplicates),
                confidence_score=best_match.similarity_score,
                match_type=match_type,
                duplicate_job_ids=[d.job_id for d in duplicates[:5]],
                match_factors=best_match.match_factors,
                processing_notes=[f"Found {len(duplicates)} potential matches"] if duplicates else []
            )
            
        except Exception as e:
            self.logger.error(f"Error processing deduplication: {e}")
            return DeduplicationResult(
                is_duplicate=False,
                duplicate_count=0,
                confidence_score=0.0,
                match_type="error",
                processing_notes=[f"Deduplication error: {str(e)}"]
            )
    
    # Private helper methods
    
    async def _find_exact_hash_matches(self, content_hash: str) -> List[DuplicateMatch]:
        """Find jobs with exact hash matches."""
        try:
            # Query database for jobs with same content hash
            matching_job = await self.job_repository.get_by_content_hash(content_hash)
            matching_jobs = [matching_job] if matching_job else []

            matches = []
            for job in matching_jobs:
                matches.append(DuplicateMatch(
                    job_id=job.id,
                    similarity_score=1.0,
                    match_type="exact_hash",
                    match_factors={"content_hash": content_hash},
                    confidence=1.0
                ))
            
            return matches
            
        except Exception as e:
            self.logger.error(f"Error finding exact hash matches: {e}")
            return []
    
    async def _find_fuzzy_matches(self, job: StandardJob, search_window_days: int,
                                min_similarity: float = 0.75, max_results: int = 10) -> List[DuplicateMatch]:
        """Find jobs using fuzzy similarity matching."""
        try:
            # Get candidate jobs from recent timeframe
            cutoff_date = datetime.utcnow() - timedelta(days=search_window_days)
            
            # Search for jobs with similar title and company
            search_criteria = JobSearchCriteria(
                title=job.title,
                company=job.company_name,
                posted_after=cutoff_date,
                limit=100  # Get reasonable number of candidates
            )

            candidate_jobs, _ = await self.job_repository.search_jobs(search_criteria)
            
            matches = []
            for candidate in candidate_jobs:
                # Convert to StandardJob for comparison
                candidate_standard = await self._convert_to_standard_job(candidate)
                
                # Calculate enhanced similarity using new calculator
                similarity_result = await self.similarity_calculator.calculate_comprehensive_similarity(
                    self._job_to_dict(job),
                    self._job_to_dict(candidate_standard)
                )
                similarity = similarity_result['total_score']
                
                if similarity >= min_similarity:
                    # Use enhanced match factors from similarity calculator
                    match_factors = similarity_result.get('match_factors', {})
                    confidence = similarity_result.get('confidence', similarity)

                    matches.append(DuplicateMatch(
                        job_id=candidate.id,
                        similarity_score=similarity,
                        match_type="enhanced_fuzzy_match",
                        match_factors=match_factors,
                        confidence=confidence
                    ))
            
            # Sort by similarity and return top matches
            matches.sort(key=lambda x: x.similarity_score, reverse=True)
            return matches[:max_results]
            
        except Exception as e:
            self.logger.error(f"Error finding fuzzy matches: {e}")
            return []
    
    def _normalize_for_hash(self, text: str) -> str:
        """Normalize text for consistent hashing."""
        if not text:
            return ""
        
        # Convert to lowercase
        normalized = text.lower().strip()
        
        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Remove common punctuation and special characters
        normalized = re.sub(r'[^\w\s]', '', normalized)
        
        # Remove common job title noise words
        noise_words = {'job', 'position', 'role', 'opening', 'opportunity', 'hiring'}
        words = normalized.split()
        words = [w for w in words if w not in noise_words]
        
        return ' '.join(words)
    
    async def _normalize_company_for_hash(self, company_name: str) -> str:
        """Normalize company name for hashing."""
        if not company_name:
            return ""
        
        # Use company service normalization
        result = await self.company_service.normalize_company_name(company_name)
        return result.normalized_name.lower()
    
    def _normalize_location_for_hash(self, location) -> str:
        """Normalize location for hashing."""
        if not location:
            return ""
        
        if hasattr(location, 'city') and hasattr(location, 'country'):
            # Use structured location
            parts = []
            if location.city:
                parts.append(location.city.lower())
            if location.country:
                parts.append(location.country.lower())
            return ','.join(parts)
        elif hasattr(location, 'raw_location'):
            # Use raw location string
            return self._normalize_for_hash(location.raw_location)
        else:
            # Assume it's a string
            return self._normalize_for_hash(str(location))
    
    def _normalize_salary_for_hash(self, salary) -> str:
        """Normalize salary for hashing."""
        if not salary:
            return ""
        
        if hasattr(salary, 'min_salary') and hasattr(salary, 'max_salary'):
            # Use structured salary
            parts = []
            if salary.min_salary:
                parts.append(str(int(salary.min_salary)))
            if salary.max_salary:
                parts.append(str(int(salary.max_salary)))
            if hasattr(salary, 'currency'):
                parts.append(str(salary.currency).lower())
            return '-'.join(parts)
        else:
            # Try to extract numbers from string
            salary_str = str(salary)
            numbers = re.findall(r'\d+', salary_str)
            return '-'.join(numbers)
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two text strings."""
        if not text1 or not text2:
            return 0.0
        
        # Use multiple similarity metrics and take the best
        ratio = fuzz.ratio(text1.lower(), text2.lower()) / 100.0
        partial_ratio = fuzz.partial_ratio(text1.lower(), text2.lower()) / 100.0
        token_sort = fuzz.token_sort_ratio(text1.lower(), text2.lower()) / 100.0
        
        # Return the highest similarity score
        return max(ratio, partial_ratio, token_sort)
    
    async def _calculate_company_similarity(self, company1: str, company2: str) -> float:
        """Calculate similarity between company names."""
        if not company1 or not company2:
            return 0.0
        
        # Use company service for advanced matching
        try:
            matches = await self.company_service.find_company_matches(
                company1, threshold=0.5, limit=5
            )
            
            # Check if company2 is in the matches
            for match in matches:
                if match.name.lower() == company2.lower():
                    return match.similarity_score
            
            # Fallback to basic fuzzy matching
            return self._calculate_text_similarity(company1, company2)
            
        except Exception:
            # Fallback to basic fuzzy matching
            return self._calculate_text_similarity(company1, company2)
    
    def _calculate_location_similarity(self, location1: str, location2: str) -> float:
        """Calculate similarity between locations."""
        if not location1 or not location2:
            return 0.0
        
        # Exact match for remote work
        if 'remote' in location1.lower() and 'remote' in location2.lower():
            return 1.0
        
        # Use fuzzy matching for location strings
        return self._calculate_text_similarity(location1, location2)
    
    def _calculate_salary_similarity(self, salary1, salary2) -> float:
        """Calculate similarity between salary ranges."""
        try:
            # Both must have salary info to compare
            if not salary1 or not salary2:
                return 0.5  # Neutral score
            
            # If both don't disclose salary, consider similar
            if (hasattr(salary1, 'is_disclosed') and hasattr(salary2, 'is_disclosed') and
                not salary1.is_disclosed and not salary2.is_disclosed):
                return 0.8
            
            # Extract salary ranges
            range1 = self._extract_salary_range(salary1)
            range2 = self._extract_salary_range(salary2)
            
            if not range1 or not range2:
                return 0.5
            
            # Calculate overlap percentage
            overlap = self._calculate_range_overlap(range1, range2)
            return overlap
            
        except Exception:
            return 0.5  # Neutral score on error
    
    def _calculate_description_similarity(self, desc1: str, desc2: str) -> float:
        """Calculate similarity between job descriptions."""
        if not desc1 or not desc2:
            return 0.5
        
        # Use token-based similarity for longer texts
        return fuzz.token_set_ratio(desc1.lower(), desc2.lower()) / 100.0
    
    def _get_location_string(self, location) -> str:
        """Extract location string from location object."""
        if not location:
            return ""
        
        if hasattr(location, 'raw_location'):
            return location.raw_location or ""
        elif isinstance(location, dict):
            return location.get('raw_location', '')
        else:
            return str(location)
    
    def _extract_keywords(self, text: str, max_keywords: int = 3) -> str:
        """Extract key words from text for searching."""
        if not text:
            return ""
        
        # Remove common words and extract meaningful terms
        words = text.lower().split()
        
        # Filter out common stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'about', 'is', 'are', 'was', 'were', 'job', 'position', 'role'}
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        
        return ' '.join(keywords[:max_keywords])
    
    async def _convert_to_standard_job(self, job_data) -> StandardJob:
        """Convert database job to StandardJob for comparison."""
        # This is a simplified conversion - in practice you'd map all fields
        try:
            return StandardJob(
                title=job_data.title,
                company_name=job_data.company_name,
                location=job_data.location,
                apply_url=job_data.apply_url,
                posted_date=job_data.posted_date,
                salary=job_data.salary,
                description=getattr(job_data, 'description', None)
            )
        except Exception:
            # Fallback with minimal data
            return StandardJob(
                title=getattr(job_data, 'title', 'Unknown'),
                company_name=getattr(job_data, 'company_name', 'Unknown'),
                apply_url=getattr(job_data, 'apply_url', 'https://example.com')
            )
    
    async def _analyze_match_factors(self, job1: StandardJob, job2: StandardJob) -> Dict[str, Any]:
        """Analyze what factors contributed to the match."""
        factors = {}
        
        # Title similarity
        title_sim = self._calculate_text_similarity(job1.title, job2.title)
        factors['title_similarity'] = title_sim
        
        # Company similarity
        company_sim = await self._calculate_company_similarity(job1.company_name, job2.company_name)
        factors['company_similarity'] = company_sim
        
        # Location match
        location1 = self._get_location_string(job1.location)
        location2 = self._get_location_string(job2.location)
        factors['location_similarity'] = self._calculate_location_similarity(location1, location2)
        
        # Date proximity
        if job1.posted_date and job2.posted_date:
            date_diff = abs((job1.posted_date - job2.posted_date).days)
            factors['date_proximity'] = max(0, 1 - (date_diff / 30))  # Normalized by 30 days
        
        return factors
    
    def _calculate_match_confidence(self, similarity: float, match_factors: Dict[str, Any]) -> float:
        """Calculate confidence in the match based on factors."""
        base_confidence = similarity
        
        # Boost confidence if multiple factors are strong
        strong_factors = sum(1 for score in match_factors.values() if isinstance(score, float) and score > 0.8)
        confidence_boost = min(0.1, strong_factors * 0.03)
        
        return min(1.0, base_confidence + confidence_boost)
    
    def _extract_salary_range(self, salary) -> Optional[Tuple[float, float]]:
        """Extract salary range as tuple (min, max)."""
        try:
            if hasattr(salary, 'min_salary') and hasattr(salary, 'max_salary'):
                min_sal = float(salary.min_salary) if salary.min_salary else None
                max_sal = float(salary.max_salary) if salary.max_salary else None
                
                if min_sal and max_sal:
                    return (min_sal, max_sal)
                elif min_sal:
                    return (min_sal, min_sal * 1.2)  # Estimate max as 20% higher
                elif max_sal:
                    return (max_sal * 0.8, max_sal)  # Estimate min as 20% lower
            
            return None
            
        except Exception:
            return None
    
    def _calculate_range_overlap(self, range1: Tuple[float, float], range2: Tuple[float, float]) -> float:
        """Calculate overlap percentage between two ranges."""
        min1, max1 = range1
        min2, max2 = range2
        
        # Calculate overlap
        overlap_start = max(min1, min2)
        overlap_end = min(max1, max2)
        
        if overlap_start >= overlap_end:
            return 0.0  # No overlap
        
        overlap_size = overlap_end - overlap_start
        range1_size = max1 - min1
        range2_size = max2 - min2
        
        # Calculate overlap as percentage of average range size
        avg_range_size = (range1_size + range2_size) / 2
        
        if avg_range_size == 0:
            return 1.0  # Both are point values and equal
        
        return min(1.0, overlap_size / avg_range_size)

    def _job_to_dict(self, job: StandardJob) -> dict:
        """Convert StandardJob to dictionary for similarity calculator."""
        return {
            'title': job.title,
            'company_name': job.company_name,
            'location': getattr(job, 'location', None),
            'salary': getattr(job, 'salary', None),
            'posted_date': getattr(job, 'posted_date', None),
            'description': getattr(job, 'description', None),
            'source_id': getattr(job, 'source_id', None)
        }