"""Field extraction service for processing job data from various sources."""

import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Union, Tuple
from urllib.parse import urlparse

from ..models.source import FieldMapping, ExtractionRules, SourceConfig, RawJobData
from ..models.job import LocationInfo, SalaryInfo, SkillInfo
from ..models.common import EmploymentType, ExperienceLevel, Currency, SalaryPeriod
from ..core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class FieldExtractionResult:
    """Result of field extraction with confidence and metadata."""
    
    def __init__(self, value: Any, confidence: float = 1.0, source_field: Optional[str] = None, 
                 method: str = "direct", warnings: Optional[List[str]] = None):
        self.value = value
        self.confidence = confidence
        self.source_field = source_field
        self.method = method
        self.warnings = warnings or []


class FieldExtractor:
    """Service for extracting and normalizing fields from raw job data."""
    
    def __init__(self, source_config: SourceConfig):
        """Initialize with source configuration."""
        self.source_config = source_config
        self.field_mapping = source_config.field_mapping
        self.extraction_rules = source_config.extraction_rules
        self.logger = logging.getLogger(f"{__name__}.{source_config.name}")
        
    async def extract_all_fields(self, raw_job_data: RawJobData) -> Dict[str, FieldExtractionResult]:
        """Extract all fields from raw job data."""
        try:
            results = {}
            
            # Extract core fields
            results['title'] = await self.extract_title(raw_job_data)
            results['company'] = await self.extract_company(raw_job_data)
            results['location'] = await self.extract_location(raw_job_data)
            results['description'] = await self.extract_description(raw_job_data)
            
            # Extract salary information
            results['salary_info'] = await self.extract_salary_info(raw_job_data)
            
            # Extract job characteristics
            results['employment_type'] = await self.extract_employment_type(raw_job_data)
            results['experience_level'] = await self.extract_experience_level(raw_job_data)
            results['experience_years'] = await self.extract_experience_years(raw_job_data)
            results['department'] = await self.extract_department(raw_job_data)
            
            # Extract application details
            results['apply_url'] = await self.extract_apply_url(raw_job_data)
            results['apply_email'] = await self.extract_apply_email(raw_job_data)
            results['contact_emails'] = await self.extract_contact_emails(raw_job_data)
            results['posted_date'] = await self.extract_posted_date(raw_job_data)
            results['deadline'] = await self.extract_deadline(raw_job_data)
            
            # Extract skills and benefits
            results['skills_required'] = await self.extract_skills_required(raw_job_data)
            results['skills_preferred'] = await self.extract_skills_preferred(raw_job_data)
            results['benefits'] = await self.extract_benefits(raw_job_data)
            
            self.logger.info(f"Successfully extracted {len(results)} fields from job {raw_job_data.external_id}")
            return results
            
        except Exception as e:
            self.logger.error(f"Error extracting fields from job {raw_job_data.external_id}: {e}")
            raise ValidationError(f"Field extraction failed: {str(e)}")
    
    async def extract_title(self, raw_job_data: RawJobData) -> FieldExtractionResult:
        """Extract and normalize job title."""
        try:
            # Try mapped fields first
            title = self._extract_field_with_fallback(raw_job_data, 'title')
            
            if title:
                # Normalize title
                normalized_title = self._normalize_title(str(title))
                return FieldExtractionResult(
                    value=normalized_title,
                    confidence=0.95 if normalized_title != title else 1.0,
                    source_field=self._get_source_field(raw_job_data, 'title'),
                    method="mapped_field"
                )
            
            # Fallback: try to extract from description
            description = self._extract_field_with_fallback(raw_job_data, 'description')
            if description:
                extracted_title = self._extract_title_from_description(str(description))
                if extracted_title:
                    return FieldExtractionResult(
                        value=extracted_title,
                        confidence=0.7,
                        source_field="description",
                        method="description_extraction",
                        warnings=["Title extracted from description due to missing title field"]
                    )
            
            # Ultimate fallback
            return FieldExtractionResult(
                value="Position Available",
                confidence=0.1,
                method="default_fallback",
                warnings=["No title found, using default value"]
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting title: {e}")
            return FieldExtractionResult(
                value="Position Available",
                confidence=0.0,
                method="error_fallback",
                warnings=[f"Error during extraction: {str(e)}"]
            )
    
    async def extract_company(self, raw_job_data: RawJobData) -> FieldExtractionResult:
        """Extract company name."""
        try:
            company = self._extract_field_with_fallback(raw_job_data, 'company')
            
            if company:
                # Basic company name cleaning
                cleaned_company = self._clean_company_name(str(company))
                return FieldExtractionResult(
                    value=cleaned_company,
                    confidence=0.95,
                    source_field=self._get_source_field(raw_job_data, 'company'),
                    method="mapped_field"
                )
            
            # Fallback: extract from email domain or URL
            apply_url = self._extract_field_with_fallback(raw_job_data, 'apply_url')
            if apply_url:
                company_from_url = self._extract_company_from_url(str(apply_url))
                if company_from_url:
                    return FieldExtractionResult(
                        value=company_from_url,
                        confidence=0.6,
                        source_field="apply_url",
                        method="url_extraction",
                        warnings=["Company name extracted from URL"]
                    )
            
            return FieldExtractionResult(
                value="Unknown Company",
                confidence=0.1,
                method="default_fallback",
                warnings=["No company name found"]
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting company: {e}")
            return FieldExtractionResult(
                value="Unknown Company",
                confidence=0.0,
                method="error_fallback",
                warnings=[f"Error during extraction: {str(e)}"]
            )
    
    async def extract_location(self, raw_job_data: RawJobData) -> FieldExtractionResult:
        """Extract location information."""
        try:
            location = self._extract_field_with_fallback(raw_job_data, 'location')
            
            if location:
                # Check for remote indicators
                is_remote = self._detect_remote_work(str(location))
                
                return FieldExtractionResult(
                    value={
                        'raw_location': str(location),
                        'is_remote': is_remote
                    },
                    confidence=0.9,
                    source_field=self._get_source_field(raw_job_data, 'location'),
                    method="mapped_field"
                )
            
            # Check description for location/remote indicators
            description = self._extract_field_with_fallback(raw_job_data, 'description')
            if description:
                is_remote = self._detect_remote_work(str(description))
                if is_remote:
                    return FieldExtractionResult(
                        value={
                            'raw_location': "Remote",
                            'is_remote': True
                        },
                        confidence=0.7,
                        source_field="description",
                        method="description_extraction",
                        warnings=["Remote work detected from description"]
                    )
            
            return FieldExtractionResult(
                value={
                    'raw_location': "Location not specified",
                    'is_remote': False
                },
                confidence=0.1,
                method="default_fallback",
                warnings=["No location information found"]
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting location: {e}")
            return FieldExtractionResult(
                value={'raw_location': "Unknown", 'is_remote': False},
                confidence=0.0,
                method="error_fallback",
                warnings=[f"Error during extraction: {str(e)}"]
            )
    
    async def extract_description(self, raw_job_data: RawJobData) -> FieldExtractionResult:
        """Extract job description."""
        try:
            description = self._extract_field_with_fallback(raw_job_data, 'description')
            
            if description:
                # Clean and normalize description
                cleaned_description = self._clean_description(str(description))
                return FieldExtractionResult(
                    value=cleaned_description,
                    confidence=1.0,
                    source_field=self._get_source_field(raw_job_data, 'description'),
                    method="mapped_field"
                )
            
            # No description means no description. This used to store the
            # literal string "No description available" as the job's
            # description, which put 2,861 rows of fabricated body text in the
            # database, made every "does this job have a description?" check
            # answer yes, and gave the reader a sentence the employer never
            # wrote. An absent value is the honest answer.
            return FieldExtractionResult(
                value=None,
                confidence=0.1,
                method="default_fallback",
                warnings=["No description found"]
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting description: {e}")
            return FieldExtractionResult(
                value=None,
                confidence=0.0,
                method="error_fallback",
                warnings=[f"Error during extraction: {str(e)}"]
            )
    
    async def extract_salary_info(self, raw_job_data: RawJobData) -> FieldExtractionResult:
        """Extract salary information."""
        try:
            # Try specific salary fields first
            salary_data = {}
            
            # Check for structured salary fields
            min_salary = self._extract_field_with_fallback(raw_job_data, 'salary_min')
            max_salary = self._extract_field_with_fallback(raw_job_data, 'salary_max')
            currency = self._extract_field_with_fallback(raw_job_data, 'salary_currency')
            period = self._extract_field_with_fallback(raw_job_data, 'salary_period')
            
            if min_salary or max_salary:
                salary_data.update({
                    'min_salary': self._parse_salary_amount(min_salary) if min_salary else None,
                    'max_salary': self._parse_salary_amount(max_salary) if max_salary else None,
                    'currency': self._parse_currency(currency) if currency else Currency.USD,
                    'period': self._parse_salary_period(period) if period else SalaryPeriod.YEAR,
                    'is_disclosed': True
                })
                
                return FieldExtractionResult(
                    value=salary_data,
                    confidence=0.9,
                    source_field="salary_fields",
                    method="structured_data"
                )
            
            # Try general salary field
            salary = self._extract_field_with_fallback(raw_job_data, 'salary')
            if salary:
                parsed_salary = self._parse_salary_string(str(salary))
                if parsed_salary:
                    return FieldExtractionResult(
                        value=parsed_salary,
                        confidence=0.8,
                        source_field=self._get_source_field(raw_job_data, 'salary'),
                        method="salary_parsing"
                    )
            
            # Try extracting from description
            description = self._extract_field_with_fallback(raw_job_data, 'description')
            if description:
                extracted_salary = self._extract_salary_from_text(str(description))
                if extracted_salary:
                    return FieldExtractionResult(
                        value=extracted_salary,
                        confidence=0.6,
                        source_field="description",
                        method="text_extraction",
                        warnings=["Salary extracted from description"]
                    )
            
            return FieldExtractionResult(
                value={'is_disclosed': False},
                confidence=0.9,
                method="not_disclosed",
                warnings=["No salary information found"]
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting salary: {e}")
            return FieldExtractionResult(
                value={'is_disclosed': False},
                confidence=0.0,
                method="error_fallback",
                warnings=[f"Error during extraction: {str(e)}"]
            )
    
    async def extract_employment_type(self, raw_job_data: RawJobData) -> FieldExtractionResult:
        """Extract employment type."""
        try:
            employment_type = self._extract_field_with_fallback(raw_job_data, 'employment_type')
            
            if employment_type:
                parsed_type = self._parse_employment_type(str(employment_type))
                if parsed_type:
                    return FieldExtractionResult(
                        value=parsed_type,
                        confidence=0.9,
                        source_field=self._get_source_field(raw_job_data, 'employment_type'),
                        method="mapped_field"
                    )
            
            # Try extracting from title or description
            title = self._extract_field_with_fallback(raw_job_data, 'title')
            description = self._extract_field_with_fallback(raw_job_data, 'description')
            
            text_to_analyze = f"{title or ''} {description or ''}"
            if text_to_analyze:
                detected_type = self._detect_employment_type_from_text(text_to_analyze)
                if detected_type:
                    return FieldExtractionResult(
                        value=detected_type,
                        confidence=0.7,
                        source_field="text_analysis",
                        method="text_detection",
                        warnings=["Employment type detected from text analysis"]
                    )
            
            return FieldExtractionResult(
                value=None,
                confidence=0.1,
                method="not_found",
                warnings=["Employment type not specified"]
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting employment type: {e}")
            return FieldExtractionResult(
                value=None,
                confidence=0.0,
                method="error_fallback",
                warnings=[f"Error during extraction: {str(e)}"]
            )
    
    async def extract_experience_level(self, raw_job_data: RawJobData) -> FieldExtractionResult:
        """Extract experience level."""
        try:
            experience_level = self._extract_field_with_fallback(raw_job_data, 'experience_level')
            
            if experience_level:
                parsed_level = self._parse_experience_level(str(experience_level))
                if parsed_level:
                    return FieldExtractionResult(
                        value=parsed_level,
                        confidence=0.9,
                        source_field=self._get_source_field(raw_job_data, 'experience_level'),
                        method="mapped_field"
                    )
            
            # Try detecting from title and description
            title = self._extract_field_with_fallback(raw_job_data, 'title')
            description = self._extract_field_with_fallback(raw_job_data, 'description')
            
            text_to_analyze = f"{title or ''} {description or ''}"
            if text_to_analyze:
                detected_level = self._detect_experience_level_from_text(text_to_analyze)
                if detected_level:
                    return FieldExtractionResult(
                        value=detected_level,
                        confidence=0.8,
                        source_field="text_analysis",
                        method="pattern_detection",
                        warnings=["Experience level detected from text patterns"]
                    )
            
            return FieldExtractionResult(
                value=None,
                confidence=0.1,
                method="not_found",
                warnings=["Experience level not specified"]
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting experience level: {e}")
            return FieldExtractionResult(
                value=None,
                confidence=0.0,
                method="error_fallback",
                warnings=[f"Error during extraction: {str(e)}"]
            )
    
    async def extract_experience_years(self, raw_job_data: RawJobData) -> FieldExtractionResult:
        """Extract a stated years-of-experience range.

        Only sources that mapped `min_exp_years`/`max_exp_years` produce a value
        here. When they do it beats anything the text parser can infer later —
        Hirist states 10-15 years on a job whose title ("Principal Backend
        Engineer") the parser was reading as a bare 5+.
        """
        try:
            min_years = self._parse_years(self._extract_field_with_fallback(raw_job_data, 'min_exp_years'))
            max_years = self._parse_years(self._extract_field_with_fallback(raw_job_data, 'max_exp_years'))

            if min_years is not None and max_years is not None and min_years > max_years:
                min_years, max_years = max_years, min_years

            if min_years is None and max_years is None:
                return FieldExtractionResult(
                    value=None,
                    confidence=0.1,
                    method="not_found",
                    warnings=["Experience years not stated by source"]
                )

            return FieldExtractionResult(
                value={"min_years": min_years, "max_years": max_years},
                confidence=0.95,
                source_field=self._get_source_field(raw_job_data, 'min_exp_years'),
                method="mapped_field"
            )

        except Exception as e:
            self.logger.error(f"Error extracting experience years: {e}")
            return FieldExtractionResult(
                value=None,
                confidence=0.0,
                method="error_fallback",
                warnings=[f"Error during extraction: {str(e)}"]
            )

    async def extract_department(self, raw_job_data: RawJobData) -> FieldExtractionResult:
        """Extract department."""
        try:
            department = self._extract_field_with_fallback(raw_job_data, 'department')
            
            if department:
                return FieldExtractionResult(
                    value=str(department).strip(),
                    confidence=0.9,
                    source_field=self._get_source_field(raw_job_data, 'department'),
                    method="mapped_field"
                )
            
            return FieldExtractionResult(
                value=None,
                confidence=0.1,
                method="not_found",
                warnings=["Department not specified"]
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting department: {e}")
            return FieldExtractionResult(
                value=None,
                confidence=0.0,
                method="error_fallback",
                warnings=[f"Error during extraction: {str(e)}"]
            )
    
    async def extract_apply_url(self, raw_job_data: RawJobData) -> FieldExtractionResult:
        """Extract application URL."""
        try:
            apply_url = self._extract_field_with_fallback(raw_job_data, 'apply_url')
            
            if apply_url:
                url_str = str(apply_url).strip()
                if self._is_valid_url(url_str):
                    return FieldExtractionResult(
                        value=url_str,
                        confidence=1.0,
                        source_field=self._get_source_field(raw_job_data, 'apply_url'),
                        method="mapped_field"
                    )
                else:
                    # Try to fix common URL issues
                    fixed_url = self._fix_url(url_str)
                    if fixed_url and self._is_valid_url(fixed_url):
                        return FieldExtractionResult(
                            value=fixed_url,
                            confidence=0.8,
                            source_field=self._get_source_field(raw_job_data, 'apply_url'),
                            method="url_fixing",
                            warnings=["URL was auto-corrected"]
                        )
            
            # Fallback to source URL if available
            if raw_job_data.source_url:
                return FieldExtractionResult(
                    value=raw_job_data.source_url,
                    confidence=0.6,
                    source_field="source_url",
                    method="source_url_fallback",
                    warnings=["Using source URL as apply URL"]
                )
            
            return FieldExtractionResult(
                value=f"https://example.com/apply/{raw_job_data.external_id}",
                confidence=0.1,
                method="placeholder",
                warnings=["No valid apply URL found, using placeholder"]
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting apply URL: {e}")
            return FieldExtractionResult(
                value=f"https://example.com/apply/{raw_job_data.external_id}",
                confidence=0.0,
                method="error_fallback",
                warnings=[f"Error during extraction: {str(e)}"]
            )
    
    async def extract_apply_email(self, raw_job_data: RawJobData) -> FieldExtractionResult:
        """Extract application email."""
        try:
            apply_email = self._extract_field_with_fallback(raw_job_data, 'apply_email')
            
            if apply_email:
                email_str = str(apply_email).strip()
                if self._is_valid_email(email_str):
                    return FieldExtractionResult(
                        value=email_str,
                        confidence=1.0,
                        source_field=self._get_source_field(raw_job_data, 'apply_email'),
                        method="mapped_field"
                    )
            
            # Try extracting email from description
            description = self._extract_field_with_fallback(raw_job_data, 'description')
            if description:
                extracted_email = self._extract_email_from_text(str(description))
                if extracted_email:
                    return FieldExtractionResult(
                        value=extracted_email,
                        confidence=0.8,
                        source_field="description",
                        method="text_extraction",
                        warnings=["Email extracted from description"]
                    )
            
            return FieldExtractionResult(
                value=None,
                confidence=0.1,
                method="not_found",
                warnings=["No application email found"]
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting apply email: {e}")
            return FieldExtractionResult(
                value=None,
                confidence=0.0,
                method="error_fallback",
                warnings=[f"Error during extraction: {str(e)}"]
            )
    
    async def extract_contact_emails(self, raw_job_data: RawJobData) -> FieldExtractionResult:
        """Harvest role-based contact emails (careers@, hr@, jobs@, talent@)
        from the description. Used by Phase 3's application-packet generator
        to address the packet without external enrichment services."""
        try:
            description = self._extract_field_with_fallback(raw_job_data, 'description')
            if description:
                emails = self._extract_contact_emails_from_text(str(description))
                if emails:
                    return FieldExtractionResult(
                        value=emails,
                        confidence=0.9,
                        source_field="description",
                        method="regex_extraction"
                    )

            return FieldExtractionResult(
                value=[],
                confidence=0.1,
                method="not_found",
                warnings=["No role-based contact emails found"]
            )

        except Exception as e:
            self.logger.error(f"Error extracting contact emails: {e}")
            return FieldExtractionResult(
                value=[],
                confidence=0.0,
                method="error_fallback",
                warnings=[f"Error during extraction: {str(e)}"]
            )

    async def extract_posted_date(self, raw_job_data: RawJobData) -> FieldExtractionResult:
        """Extract posted date."""
        try:
            posted_date = self._extract_field_with_fallback(raw_job_data, 'posted_date')
            
            if posted_date:
                parsed_date = self._parse_date(posted_date)
                if parsed_date:
                    return FieldExtractionResult(
                        value=parsed_date,
                        confidence=0.9,
                        source_field=self._get_source_field(raw_job_data, 'posted_date'),
                        method="mapped_field"
                    )
            
            # Fallback to fetch date
            return FieldExtractionResult(
                value=raw_job_data.fetched_at,
                confidence=0.5,
                source_field="fetched_at",
                method="fetch_date_fallback",
                warnings=["Using fetch date as posted date"]
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting posted date: {e}")
            return FieldExtractionResult(
                value=raw_job_data.fetched_at,
                confidence=0.0,
                method="error_fallback",
                warnings=[f"Error during extraction: {str(e)}"]
            )
    
    async def extract_deadline(self, raw_job_data: RawJobData) -> FieldExtractionResult:
        """Extract application deadline."""
        try:
            deadline = self._extract_field_with_fallback(raw_job_data, 'deadline')
            
            if deadline:
                parsed_deadline = self._parse_date(deadline)
                if parsed_deadline:
                    return FieldExtractionResult(
                        value=parsed_deadline,
                        confidence=0.9,
                        source_field=self._get_source_field(raw_job_data, 'deadline'),
                        method="mapped_field"
                    )
            
            return FieldExtractionResult(
                value=None,
                confidence=0.1,
                method="not_found",
                warnings=["No application deadline found"]
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting deadline: {e}")
            return FieldExtractionResult(
                value=None,
                confidence=0.0,
                method="error_fallback",
                warnings=[f"Error during extraction: {str(e)}"]
            )
    
    async def extract_skills_required(self, raw_job_data: RawJobData) -> FieldExtractionResult:
        """Extract required skills."""
        try:
            skills = self._extract_field_with_fallback(raw_job_data, 'skills_required')
            
            if skills:
                parsed_skills = self._parse_skills_list(skills)
                return FieldExtractionResult(
                    value=parsed_skills,
                    confidence=0.9,
                    source_field=self._get_source_field(raw_job_data, 'skills_required'),
                    method="mapped_field"
                )
            
            # Try extracting from description
            description = self._extract_field_with_fallback(raw_job_data, 'description')
            if description:
                extracted_skills = self._extract_skills_from_text(str(description), required=True)
                if extracted_skills:
                    return FieldExtractionResult(
                        value=extracted_skills,
                        confidence=0.7,
                        source_field="description",
                        method="text_extraction",
                        warnings=["Skills extracted from description"]
                    )
            
            return FieldExtractionResult(
                value=[],
                confidence=0.1,
                method="not_found",
                warnings=["No required skills found"]
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting required skills: {e}")
            return FieldExtractionResult(
                value=[],
                confidence=0.0,
                method="error_fallback",
                warnings=[f"Error during extraction: {str(e)}"]
            )
    
    async def extract_skills_preferred(self, raw_job_data: RawJobData) -> FieldExtractionResult:
        """Extract preferred skills."""
        try:
            skills = self._extract_field_with_fallback(raw_job_data, 'skills_preferred')
            
            if skills:
                parsed_skills = self._parse_skills_list(skills)
                return FieldExtractionResult(
                    value=parsed_skills,
                    confidence=0.9,
                    source_field=self._get_source_field(raw_job_data, 'skills_preferred'),
                    method="mapped_field"
                )
            
            # Try extracting from description
            description = self._extract_field_with_fallback(raw_job_data, 'description')
            if description:
                extracted_skills = self._extract_skills_from_text(str(description), required=False)
                if extracted_skills:
                    return FieldExtractionResult(
                        value=extracted_skills,
                        confidence=0.7,
                        source_field="description",
                        method="text_extraction",
                        warnings=["Skills extracted from description"]
                    )
            
            return FieldExtractionResult(
                value=[],
                confidence=0.1,
                method="not_found",
                warnings=["No preferred skills found"]
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting preferred skills: {e}")
            return FieldExtractionResult(
                value=[],
                confidence=0.0,
                method="error_fallback",
                warnings=[f"Error during extraction: {str(e)}"]
            )
    
    async def extract_benefits(self, raw_job_data: RawJobData) -> FieldExtractionResult:
        """Extract benefits."""
        try:
            benefits = self._extract_field_with_fallback(raw_job_data, 'benefits')
            
            if benefits:
                parsed_benefits = self._parse_benefits_list(benefits)
                return FieldExtractionResult(
                    value=parsed_benefits,
                    confidence=0.9,
                    source_field=self._get_source_field(raw_job_data, 'benefits'),
                    method="mapped_field"
                )
            
            # Try extracting from description
            description = self._extract_field_with_fallback(raw_job_data, 'description')
            if description:
                extracted_benefits = self._extract_benefits_from_text(str(description))
                if extracted_benefits:
                    return FieldExtractionResult(
                        value=extracted_benefits,
                        confidence=0.7,
                        source_field="description",
                        method="text_extraction",
                        warnings=["Benefits extracted from description"]
                    )
            
            return FieldExtractionResult(
                value=[],
                confidence=0.1,
                method="not_found",
                warnings=["No benefits found"]
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting benefits: {e}")
            return FieldExtractionResult(
                value=[],
                confidence=0.0,
                method="error_fallback",
                warnings=[f"Error during extraction: {str(e)}"]
            )
    
    # Helper methods for field extraction
    
    def _extract_field_with_fallback(self, raw_job_data: RawJobData, field_name: str) -> Optional[Any]:
        """Extract field using mapping with fallback strategies."""
        try:
            # Get possible field names for this field
            possible_keys = getattr(self.field_mapping, field_name, [])
            
            for key in possible_keys:
                # Support nested keys with dot notation
                if '.' in key:
                    value = self._get_nested_value(raw_job_data.raw_data, key.split('.'))
                else:
                    value = raw_job_data.raw_data.get(key)
                
                # Return first non-empty value
                if value is not None and str(value).strip():
                    return value
            
            return None
            
        except Exception as e:
            self.logger.warning(f"Error extracting field {field_name}: {e}")
            return None
    
    def _get_nested_value(self, data: Dict[str, Any], keys: List[str]) -> Optional[Any]:
        """Get value from nested dictionary using key path."""
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            elif isinstance(current, list) and key.isdigit() and int(key) < len(current):
                current = current[int(key)]
            else:
                return None
        return current
    
    def _get_source_field(self, raw_job_data: RawJobData, field_name: str) -> Optional[str]:
        """Get the actual source field name that contained the data."""
        possible_keys = getattr(self.field_mapping, field_name, [])
        
        for key in possible_keys:
            if '.' in key:
                value = self._get_nested_value(raw_job_data.raw_data, key.split('.'))
            else:
                value = raw_job_data.raw_data.get(key)
                
            if value is not None and str(value).strip():
                return key
        
        return None
    
    # Text processing and normalization methods
    
    def _normalize_title(self, title: str) -> str:
        """Normalize job title."""
        # Remove extra whitespace
        title = re.sub(r'\s+', ' ', title.strip())
        
        # Basic capitalization fixes
        title = title.title()
        
        # Fix common abbreviations
        title = re.sub(r'\bIt\b', 'IT', title)
        title = re.sub(r'\bUi\b', 'UI', title)
        title = re.sub(r'\bUx\b', 'UX', title)
        title = re.sub(r'\bApi\b', 'API', title)
        title = re.sub(r'\bSql\b', 'SQL', title)
        
        return title
    
    def _clean_company_name(self, company: str) -> str:
        """Basic company name cleaning."""
        # Remove extra whitespace
        company = re.sub(r'\s+', ' ', company.strip())
        
        # Remove common prefixes/suffixes that might be noise
        company = re.sub(r'^(Job at|Hiring at|Position at)\s+', '', company, flags=re.IGNORECASE)
        
        return company
    
    def _clean_description(self, description: str) -> str:
        """Clean job description."""
        # Remove extra whitespace and normalize line breaks
        description = re.sub(r'\s+', ' ', description.strip())
        description = re.sub(r'\n\s*\n', '\n\n', description)
        
        # Remove HTML tags if present
        description = re.sub(r'<[^>]+>', '', description)
        
        # Remove common noise patterns
        description = re.sub(r'^\s*Job Description:?\s*', '', description, flags=re.IGNORECASE)
        
        return description.strip()
    
    def _detect_remote_work(self, text: str) -> bool:
        """Detect if job is remote work."""
        text_lower = text.lower()
        
        for keyword in self.extraction_rules.remote_keywords:
            if keyword.lower() in text_lower:
                return True
        
        return False
    
    def _extract_title_from_description(self, description: str) -> Optional[str]:
        """Try to extract title from description."""
        # Look for common title patterns
        patterns = [
            r'(?:position|role|job)\s*:?\s*([^\n]{10,50})',
            r'(?:we are looking for|seeking)\s+(?:a|an)?\s*([^\n]{10,50})',
            r'(?:hiring|recruiting)\s+(?:a|an)?\s*([^\n]{10,50})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                title = match.group(1).strip()
                if len(title) > 5 and not title.endswith('.'):
                    return self._normalize_title(title)
        
        return None
    
    def _extract_company_from_url(self, url: str) -> Optional[str]:
        """Extract company name from URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Remove www. prefix
            domain = re.sub(r'^www\.', '', domain)
            
            # Extract company name from domain
            parts = domain.split('.')
            if len(parts) >= 2:
                company = parts[0]
                
                # Skip common subdomains
                if company in ['jobs', 'careers', 'apply', 'hiring']:
                    if len(parts) >= 3:
                        company = parts[1]
                
                # Capitalize and clean
                company = company.replace('-', ' ').replace('_', ' ').title()
                return company
        
        except Exception:
            pass
        
        return None
    
    # Parsing methods for specific data types
    
    def _parse_salary_amount(self, value: Any) -> Optional[Decimal]:
        """Parse salary amount from various formats."""
        if value is None:
            return None
        
        try:
            # Convert to string and clean
            salary_str = str(value).strip()
            
            # Remove currency symbols and common separators
            salary_str = re.sub(r'[$£€¥,\s]', '', salary_str)
            
            # Handle 'k' notation (e.g., "80k" -> "80000")
            if salary_str.lower().endswith('k'):
                salary_str = salary_str[:-1]
                multiplier = 1000
            else:
                multiplier = 1
            
            # Parse as decimal
            amount = Decimal(salary_str) * multiplier
            
            # Validate reasonable range
            if 1000 <= amount <= 10000000:  # $1K to $10M
                return amount
            
        except (ValueError, InvalidOperation):
            pass
        
        return None
    
    def _parse_currency(self, value: Any) -> Currency:
        """Parse currency from value."""
        if not value:
            return Currency.USD
        
        currency_str = str(value).upper().strip()
        
        # Map common currency symbols and codes
        currency_map = {
            '$': Currency.USD,
            'USD': Currency.USD,
            'DOLLAR': Currency.USD,
            '€': Currency.EUR,
            'EUR': Currency.EUR,
            'EURO': Currency.EUR,
            '£': Currency.GBP,
            'GBP': Currency.GBP,
            'POUND': Currency.GBP,
            '¥': Currency.JPY,
            'JPY': Currency.JPY,
            'YEN': Currency.JPY,
        }
        
        for symbol, currency in currency_map.items():
            if symbol in currency_str:
                return currency
        
        return Currency.USD  # Default
    
    def _parse_salary_period(self, value: Any) -> SalaryPeriod:
        """Parse salary period from value."""
        if not value:
            return SalaryPeriod.YEAR
        
        period_str = str(value).lower().strip()
        
        if any(word in period_str for word in ['hour', 'hr', 'hourly']):
            return SalaryPeriod.HOUR
        elif any(word in period_str for word in ['month', 'monthly']):
            return SalaryPeriod.MONTH
        elif any(word in period_str for word in ['year', 'yearly', 'annual', 'annually']):
            return SalaryPeriod.YEAR
        
        return SalaryPeriod.YEAR  # Default
    
    def _parse_salary_string(self, salary_str: str) -> Optional[Dict[str, Any]]:
        """Parse salary information from free-form text."""
        for pattern in self.extraction_rules.salary_patterns:
            match = re.search(pattern, salary_str, re.IGNORECASE)
            if match:
                groups = match.groups()
                
                if len(groups) >= 2 and groups[1]:
                    # Range format
                    min_sal = self._parse_salary_amount(groups[0])
                    max_sal = self._parse_salary_amount(groups[1])
                    
                    if min_sal and max_sal:
                        return {
                            'min_salary': min_sal,
                            'max_salary': max_sal,
                            'currency': self._parse_currency(salary_str),
                            'is_disclosed': True
                        }
                elif len(groups) >= 1:
                    # Single amount
                    amount = self._parse_salary_amount(groups[0])
                    if amount:
                        return {
                            'min_salary': amount,
                            'currency': self._parse_currency(salary_str),
                            'is_disclosed': True
                        }
        
        return None
    
    def _extract_salary_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract salary information from text."""
        return self._parse_salary_string(text)
    
    def _parse_employment_type(self, value: str) -> Optional[EmploymentType]:
        """Parse employment type from string."""
        value_lower = value.lower().strip()
        
        for emp_type, keywords in self.extraction_rules.employment_type_keywords.items():
            for keyword in keywords:
                if keyword in value_lower:
                    try:
                        return EmploymentType(emp_type)
                    except ValueError:
                        continue
        
        return None
    
    def _detect_employment_type_from_text(self, text: str) -> Optional[EmploymentType]:
        """Detect employment type from text analysis."""
        return self._parse_employment_type(text)
    
    def _parse_experience_level(self, value: str) -> Optional[ExperienceLevel]:
        """Parse experience level from string."""
        value_lower = value.lower().strip()
        
        # Direct keyword mapping
        if any(word in value_lower for word in ['senior', 'sr.', 'sr']):
            return ExperienceLevel.SENIOR
        elif any(word in value_lower for word in ['junior', 'jr.', 'jr']):
            return ExperienceLevel.JUNIOR
        elif any(word in value_lower for word in ['lead', 'leader', 'principal']):
            return ExperienceLevel.LEAD
        elif any(word in value_lower for word in ['entry', 'entry-level', 'graduate', 'trainee']):
            return ExperienceLevel.ENTRY_LEVEL
        elif any(word in value_lower for word in ['mid', 'middle', 'intermediate']):
            return ExperienceLevel.MID_LEVEL
        
        return None
    
    def _parse_years(self, value: Any) -> Optional[int]:
        """Coerce a source's experience figure to whole years, or None.

        Bounded at 50 so a source that quietly starts sending months, or a
        sentinel like 99, cannot poison the matching filters.
        """
        if value is None:
            return None
        try:
            years = int(float(str(value).strip()))
        except (TypeError, ValueError):
            return None
        return years if 0 <= years <= 50 else None

    def _detect_experience_level_from_text(self, text: str) -> Optional[ExperienceLevel]:
        """Detect experience level from text patterns."""
        # Try parsing as experience level first
        result = self._parse_experience_level(text)
        if result:
            return result
        
        # Look for years of experience patterns
        for pattern in self.extraction_rules.experience_patterns:
            if pattern.startswith(r'\b(\d+)'):
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    try:
                        years = int(matches[0][0]) if matches[0][0] else int(matches[0][1])
                        
                        if years <= 2:
                            return ExperienceLevel.JUNIOR
                        elif years <= 5:
                            return ExperienceLevel.MID_LEVEL
                        else:
                            return ExperienceLevel.SENIOR
                    except (ValueError, IndexError):
                        continue
        
        return None
    
    def _parse_skills_list(self, value: Any) -> List[str]:
        """Parse skills from various formats."""
        if not value:
            return []
        
        if isinstance(value, list):
            return [str(skill).strip() for skill in value if str(skill).strip()]
        
        # Parse comma-separated or other delimited strings
        skills_str = str(value)
        
        # Try different delimiters
        for delimiter in [',', ';', '|', '\n']:
            if delimiter in skills_str:
                skills = [skill.strip() for skill in skills_str.split(delimiter)]
                return [skill for skill in skills if skill and len(skill) > 1]
        
        # Return as single skill if no delimiters found
        return [skills_str.strip()] if skills_str.strip() else []
    
    def _extract_skills_from_text(self, text: str, required: bool = True) -> List[str]:
        """Extract skills from text using pattern matching."""
        # This is a simplified implementation
        # In practice, you'd use NLP libraries and skill databases
        
        skills = []
        text_lower = text.lower()
        
        # Common programming languages and technologies
        common_skills = [
            'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'php', 'ruby', 'go',
            'react', 'angular', 'vue', 'node.js', 'express', 'django', 'flask', 'spring',
            'sql', 'mysql', 'postgresql', 'mongodb', 'redis', 'elasticsearch',
            'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'git', 'linux', 'jenkins'
        ]
        
        for skill in common_skills:
            if skill in text_lower:
                skills.append(skill.title())
        
        return skills[:10]  # Limit to top 10 to avoid noise
    
    def _parse_benefits_list(self, value: Any) -> List[str]:
        """Parse benefits from various formats."""
        return self._parse_skills_list(value)  # Same logic as skills
    
    def _extract_benefits_from_text(self, text: str) -> List[str]:
        """Extract benefits from text."""
        benefits = []
        text_lower = text.lower()
        
        # Common benefits
        common_benefits = [
            'health insurance', 'dental insurance', 'vision insurance',
            '401k', 'retirement plan', 'pension',
            'paid time off', 'pto', 'vacation', 'sick leave',
            'remote work', 'work from home', 'flexible hours',
            'stock options', 'equity', 'bonus',
            'professional development', 'training', 'conference',
            'gym membership', 'wellness program'
        ]
        
        for benefit in common_benefits:
            if benefit in text_lower:
                benefits.append(benefit.title())
        
        return benefits[:5]  # Limit to avoid noise
    
    # Validation helper methods
    
    def _is_valid_url(self, url: str) -> bool:
        """Check if URL is valid."""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
    
    def _fix_url(self, url: str) -> Optional[str]:
        """Try to fix common URL issues."""
        # Add https:// if missing protocol
        if not url.startswith(('http://', 'https://')):
            return f"https://{url}"
        
        return None
    
    def _is_valid_email(self, email: str) -> bool:
        """Check if email is valid."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def _extract_email_from_text(self, text: str) -> Optional[str]:
        """Extract email from text."""
        pattern = r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b'
        matches = re.findall(pattern, text)
        
        if matches:
            # Return first valid email
            for email in matches:
                if self._is_valid_email(email):
                    return email
        
        return None
    
    CONTACT_EMAIL_PATTERN = re.compile(
        r'\b(careers|hr|jobs|talent)[a-zA-Z0-9._%+-]*@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b',
        re.IGNORECASE
    )

    def _extract_contact_emails_from_text(self, text: str) -> List[str]:
        """Find careers@/hr@/jobs@/talent@-prefixed emails, deduped and lowercased."""
        seen = []
        for match in self.CONTACT_EMAIL_PATTERN.finditer(text):
            email = match.group(0).lower()
            if self._is_valid_email(email) and email not in seen:
                seen.append(email)
        return seen

    def _parse_date(self, value: Any) -> Optional[datetime]:
        """Parse date from various formats."""
        if not value:
            return None
        
        if isinstance(value, datetime):
            return value
        
        # Try to parse string dates
        date_str = str(value).strip()
        
        # Common date formats
        formats = [
            '%Y-%m-%d',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%d %H:%M:%S',
            '%m/%d/%Y',
            '%d/%m/%Y',
            '%Y/%m/%d',
            '%d-%m-%Y',
            '%B %d, %Y',
            '%b %d, %Y',
            '%d %B %Y',
            '%d %b %Y'
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        return None