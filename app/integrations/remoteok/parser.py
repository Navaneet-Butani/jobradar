"""RemoteOK API response parser for transforming job data to standard format."""

import asyncio
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple, NamedTuple, Set
from urllib.parse import urlparse
from html import unescape
import html2text

from ...models.job import StandardJob, LocationInfo, SalaryInfo, SkillInfo
from ...models.common import (
    EmploymentType, ExperienceLevel, WorkArrangement,
    SalaryPeriod, Currency, SkillCategory
)
from ...services.location_parser import LocationParser
from ...services.salary_parser import SalaryParser
from ...core.exceptions import ValidationError, ProcessingError
from ...utils.text_processing import TextProcessor

logger = logging.getLogger(__name__)


class ParsingStats:
    """Statistics for tracking parsing success and issues."""

    def __init__(self):
        self.total_jobs = 0
        self.successfully_parsed = 0
        self.parsing_errors = 0
        self.validation_errors = 0
        self.missing_fields = {}
        self.remote_jobs_detected = 0
        self.salary_parsed = 0
        self.skills_extracted = 0
        self.html_cleaned = 0

    def add_missing_field(self, field_name: str):
        """Track missing field occurrences."""
        self.missing_fields[field_name] = self.missing_fields.get(field_name, 0) + 1

    @property
    def success_rate(self) -> float:
        """Calculate parsing success rate."""
        if self.total_jobs == 0:
            return 0.0
        return (self.successfully_parsed / self.total_jobs) * 100

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics."""
        return {
            'total_jobs': self.total_jobs,
            'successfully_parsed': self.successfully_parsed,
            'parsing_errors': self.parsing_errors,
            'validation_errors': self.validation_errors,
            'success_rate': round(self.success_rate, 2),
            'remote_jobs_detected': self.remote_jobs_detected,
            'salary_parsed': self.salary_parsed,
            'skills_extracted': self.skills_extracted,
            'html_cleaned': self.html_cleaned,
            'missing_fields': dict(self.missing_fields)
        }


class AttributionInfo(NamedTuple):
    """Attribution information for RemoteOK jobs."""
    source_name: str
    source_url: str
    attribution_text: str
    backlink_required: bool


class RemoteOKParser:
    """Parser for transforming RemoteOK API responses to StandardJob format."""

    # RemoteOK uses USD for all salary information
    DEFAULT_CURRENCY = Currency.USD

    # Remote work indicators (RemoteOK jobs are remote by default)
    REMOTE_INDICATORS = {
        'remote', 'work from home', 'wfh', 'telecommute', 'telework',
        'distributed', 'home office', 'anywhere', 'location independent',
        'virtual', 'remote work', 'remote job', 'work remotely', 'nomad'
    }

    # Employment type keywords
    EMPLOYMENT_TYPE_PATTERNS = {
        EmploymentType.FULL_TIME: {
            'full time', 'full-time', 'permanent', 'regular', 'ft', 'fulltime'
        },
        EmploymentType.PART_TIME: {
            'part time', 'part-time', 'pt', 'casual', 'parttime'
        },
        EmploymentType.CONTRACT: {
            'contract', 'contractor', 'freelance', 'temporary', 'temp',
            'consulting', 'consultant', 'project', 'fixed term', 'gig'
        },
        EmploymentType.INTERNSHIP: {
            'intern', 'internship', 'graduate', 'trainee', 'apprentice'
        }
    }

    # Experience level patterns
    EXPERIENCE_LEVEL_PATTERNS = {
        ExperienceLevel.ENTRY_LEVEL: {
            'entry level', 'junior', 'graduate', 'trainee', 'intern',
            'beginner', '0-2 years', 'recent graduate', 'jr'
        },
        ExperienceLevel.MID_LEVEL: {
            'mid level', 'middle', 'intermediate', '2-5 years',
            '3-5 years', 'experienced', 'regular'
        },
        ExperienceLevel.SENIOR_LEVEL: {
            'senior', 'sr', 'lead', 'principal', '5+ years',
            'expert', 'advanced', 'staff', 'senior level'
        },
        ExperienceLevel.EXECUTIVE: {
            'director', 'manager', 'head of', 'chief', 'vp',
            'vice president', 'executive', 'c-level'
        }
    }

    # Technology to skill category mapping
    SKILL_CATEGORIES = {
        SkillCategory.PROGRAMMING: {
            'python', 'javascript', 'java', 'go', 'golang', 'rust', 'php',
            'ruby', 'scala', 'kotlin', 'swift', 'typescript', 'csharp',
            'cpp', 'c++', 'c#', '.net', 'dotnet'
        },
        SkillCategory.FRONTEND: {
            'react', 'angular', 'vue', 'vuejs', 'html', 'css', 'sass',
            'scss', 'less', 'bootstrap', 'tailwind', 'jquery', 'webpack',
            'babel', 'next', 'nextjs', 'nuxt', 'gatsby'
        },
        SkillCategory.BACKEND: {
            'django', 'flask', 'fastapi', 'rails', 'laravel', 'express',
            'nodejs', 'node', 'spring', 'gin', 'echo', 'actix'
        },
        SkillCategory.DATABASE: {
            'sql', 'mysql', 'postgresql', 'postgres', 'mongodb', 'redis',
            'elasticsearch', 'cassandra', 'dynamodb', 'sqlite', 'mariadb'
        },
        SkillCategory.CLOUD: {
            'aws', 'azure', 'gcp', 'kubernetes', 'docker', 'terraform',
            'ansible', 'jenkins', 'gitlab', 'github actions', 'circleci'
        },
        SkillCategory.DATA: {
            'spark', 'hadoop', 'kafka', 'airflow', 'pandas', 'numpy',
            'tensorflow', 'pytorch', 'scikit-learn', 'jupyter'
        }
    }

    def __init__(self,
                 location_parser: Optional[LocationParser] = None,
                 salary_parser: Optional[SalaryParser] = None):
        """
        Initialize RemoteOK parser.

        Args:
            location_parser: Location parser service
            salary_parser: Salary parser service
        """
        self.location_parser = location_parser
        self.salary_parser = salary_parser
        self.html_converter = html2text.HTML2Text()
        self.html_converter.ignore_links = True
        self.html_converter.ignore_images = True
        self.html_converter.body_width = 0  # Don't wrap lines

    async def parse_job(self, raw_job: Dict[str, Any]) -> StandardJob:
        """
        Parse a single RemoteOK job to StandardJob format.

        Args:
            raw_job: Raw job data from RemoteOK API

        Returns:
            StandardJob instance
        """
        try:
            # Extract basic fields
            title = self._extract_title(raw_job)
            company_name = self._extract_company(raw_job)
            description = await self._extract_description(raw_job)

            # Parse location (mostly remote)
            location = await self._parse_location(raw_job)

            # Parse salary
            salary = await self._parse_salary(raw_job)

            # Extract skills
            skills = self._extract_skills(raw_job, description)

            # Parse dates
            posted_date = self._parse_posted_date(raw_job)

            # Determine employment type and experience level
            employment_type = self._determine_employment_type(title, description)
            experience_level = self._determine_experience_level(title, description)

            # Generate apply URL and source URL
            apply_url = self._extract_apply_url(raw_job)
            source_url = self._extract_source_url(raw_job)

            # Add attribution
            attribution = self._get_attribution_info(raw_job)

            # Create StandardJob
            job = StandardJob(
                external_id=str(raw_job.get('id', '')),
                title=title,
                normalized_title=self._normalize_title(title),
                company_name=company_name,
                location=location,
                is_remote=location.is_remote if location else True,  # RemoteOK defaults to remote
                employment_type=employment_type,
                experience_level=experience_level,
                salary=salary,
                description=description,
                skills_extracted=skills,
                posted_date=posted_date,
                apply_url=apply_url,
                # Add attribution information
                source_url=source_url,
                quality_score=self._calculate_quality_score(raw_job, description, salary, skills),
                confidence_score=0.9  # High confidence for well-structured RemoteOK data
            )

            return job

        except Exception as e:
            logger.error(f"Error parsing RemoteOK job {raw_job.get('id', 'unknown')}: {e}")
            raise ProcessingError(f"Failed to parse job: {e}")

    def _extract_title(self, job: Dict[str, Any]) -> str:
        """Extract and clean job title."""
        title = job.get('position') or job.get('title', '')
        if not title:
            raise ValidationError("Job title is required")

        # Clean and normalize title
        title = unescape(title).strip()
        return title[:500]  # Limit length

    def _extract_company(self, job: Dict[str, Any]) -> str:
        """Extract and clean company name."""
        company = job.get('company', '').strip()
        if not company:
            raise ValidationError("Company name is required")

        # Clean company name
        company = unescape(company)
        return company[:255]  # Limit length

    async def _extract_description(self, job: Dict[str, Any]) -> str:
        """Extract and clean job description from HTML."""
        raw_description = job.get('description', '')
        if not raw_description:
            return ''

        try:
            # Convert HTML to markdown/text
            clean_description = self.html_converter.handle(raw_description)

            # Clean up the text
            clean_description = self._clean_description_text(clean_description)

            return clean_description[:5000]  # Reasonable limit

        except Exception as e:
            logger.warning(f"Error cleaning HTML description: {e}")
            # Fallback: strip HTML tags with regex
            clean_text = re.sub(r'<[^>]+>', '', raw_description)
            return unescape(clean_text).strip()[:5000]

    def _clean_description_text(self, text: str) -> str:
        """Clean and normalize description text."""
        if not text:
            return ''

        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)

        # Remove markdown artifacts
        text = re.sub(r'[*_`#]+', '', text)

        # Clean up line breaks
        text = text.replace('\n\n\n', '\n\n')

        return text.strip()

    async def _parse_location(self, job: Dict[str, Any]) -> Optional[LocationInfo]:
        """Parse location information."""
        raw_location = job.get('location', '')

        # RemoteOK jobs are typically remote, but let's parse what we have
        if self.location_parser and raw_location:
            try:
                location = await self.location_parser.parse_location(raw_location)
                return location
            except Exception as e:
                logger.warning(f"Error parsing location '{raw_location}': {e}")

        # Default RemoteOK location (remote work)
        is_remote = self._detect_remote_work(job)
        return LocationInfo(
            raw_location=raw_location or 'Remote',
            country='Unknown',
            is_remote=is_remote,
            work_arrangement=WorkArrangement.REMOTE if is_remote else WorkArrangement.ON_SITE
        )

    def _detect_remote_work(self, job: Dict[str, Any]) -> bool:
        """Detect if job is remote work."""
        # RemoteOK specializes in remote work, so default to True
        text_to_check = f"{job.get('position', '')} {job.get('description', '')}".lower()

        # Check for remote indicators
        for indicator in self.REMOTE_INDICATORS:
            if indicator in text_to_check:
                return True

        # RemoteOK default
        return True

    async def _parse_salary(self, job: Dict[str, Any]) -> Optional[SalaryInfo]:
        """Parse salary information."""
        salary_min = job.get('salary_min')
        salary_max = job.get('salary_max')

        # Convert to Decimal if present
        min_decimal = None
        max_decimal = None

        if salary_min and salary_min > 0:
            min_decimal = Decimal(str(salary_min))

        if salary_max and salary_max > 0:
            max_decimal = Decimal(str(salary_max))

        if min_decimal or max_decimal:
            return SalaryInfo(
                min_salary=min_decimal,
                max_salary=max_decimal,
                currency=self.DEFAULT_CURRENCY,
                period=SalaryPeriod.YEAR,
                is_disclosed=True
            )

        # Try to parse from description if not in structured fields
        description = job.get('description', '')
        if self.salary_parser and description:
            try:
                return await self.salary_parser.parse_salary(description)
            except Exception as e:
                logger.debug(f"Could not parse salary from description: {e}")

        return None

    def _extract_skills(self, job: Dict[str, Any], description: str) -> List[str]:
        """Extract skills from tags and description."""
        skills = set()

        # Extract from tags (primary source)
        tags = job.get('tags', [])
        if isinstance(tags, list):
            skills.update(tag.lower().strip() for tag in tags if tag)

        # Extract additional technical skills from description
        if description:
            technical_skills = self._extract_technical_skills(description)
            skills.update(technical_skills)

        # Clean and deduplicate skills
        cleaned_skills = []
        for skill in skills:
            if skill and len(skill) > 1 and skill not in cleaned_skills:
                # Normalize skill name
                normalized_skill = self._normalize_skill_name(skill)
                if normalized_skill:
                    cleaned_skills.append(normalized_skill)

        return sorted(list(set(cleaned_skills)))  # Remove duplicates and sort

    def _extract_technical_skills(self, text: str) -> Set[str]:
        """Extract technical skills from text."""
        technical_skills = set()
        text_lower = text.lower()

        # Check all skill categories
        for category, skills in self.SKILL_CATEGORIES.items():
            for skill in skills:
                # Use word boundaries to match whole words
                pattern = r'\b' + re.escape(skill) + r'\b'
                if re.search(pattern, text_lower, re.IGNORECASE):
                    technical_skills.add(skill)

        return technical_skills

    def _normalize_skill_name(self, skill: str) -> Optional[str]:
        """Normalize skill name."""
        if not skill:
            return None

        skill = skill.strip().lower()

        # Skip very short or very long skills
        if len(skill) < 2 or len(skill) > 50:
            return None

        # Skip common non-skill words
        stop_words = {'and', 'or', 'the', 'of', 'to', 'in', 'for', 'with', 'on'}
        if skill in stop_words:
            return None

        # Normalize common variations
        normalizations = {
            'js': 'javascript',
            'ts': 'typescript',
            'k8s': 'kubernetes',
            'tf': 'tensorflow',
            'ml': 'machine learning',
            'ai': 'artificial intelligence'
        }

        return normalizations.get(skill, skill)

    def _parse_posted_date(self, job: Dict[str, Any]) -> Optional[datetime]:
        """Parse job posting date."""
        date_value = job.get('date') or job.get('epoch')

        if not date_value:
            return None

        try:
            # Handle epoch timestamp
            if isinstance(date_value, (int, float)):
                return datetime.fromtimestamp(date_value, tz=timezone.utc)

            # Handle ISO string
            if isinstance(date_value, str):
                # Try different formats
                for fmt in ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d']:
                    try:
                        dt = datetime.strptime(date_value, fmt)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        return dt
                    except ValueError:
                        continue

        except Exception as e:
            logger.warning(f"Failed to parse date '{date_value}': {e}")

        return None

    def _determine_employment_type(self, title: str, description: str) -> Optional[EmploymentType]:
        """Determine employment type from title and description."""
        text = f"{title} {description}".lower()

        # Check patterns
        for emp_type, patterns in self.EMPLOYMENT_TYPE_PATTERNS.items():
            for pattern in patterns:
                if pattern in text:
                    return emp_type

        # Default for RemoteOK (mostly full-time positions)
        return EmploymentType.FULL_TIME

    def _determine_experience_level(self, title: str, description: str) -> Optional[ExperienceLevel]:
        """Determine experience level from title and description."""
        text = f"{title} {description}".lower()

        # Check patterns
        for level, patterns in self.EXPERIENCE_LEVEL_PATTERNS.items():
            for pattern in patterns:
                if pattern in text:
                    return level

        # Default to mid-level if unclear
        return ExperienceLevel.MID_LEVEL

    def _normalize_title(self, title: str) -> str:
        """Normalize job title for matching."""
        if not title:
            return ''

        # Convert to lowercase and remove extra spaces
        normalized = re.sub(r'\s+', ' ', title.lower().strip())

        # Remove common prefixes/suffixes
        patterns_to_remove = [
            r'^remote\s+',
            r'^work\s+from\s+home\s+',
            r'\s+\(remote\)$',
            r'\s+remote$'
        ]

        for pattern in patterns_to_remove:
            normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)

        return normalized.strip()

    def _extract_apply_url(self, job: Dict[str, Any]) -> str:
        """Extract apply URL."""
        apply_url = job.get('apply_url') or job.get('url', '')
        if not apply_url:
            # Generate RemoteOK URL from job ID
            job_id = job.get('id')
            if job_id:
                apply_url = f"https://remoteok.io/l/{job_id}"
            else:
                raise ValidationError("No apply URL available")

        return apply_url

    def _extract_source_url(self, job: Dict[str, Any]) -> str:
        """Extract source URL (RemoteOK job page)."""
        # RemoteOK job URL
        job_id = job.get('id')
        if job_id:
            return f"https://remoteok.io/l/{job_id}"

        return job.get('url', '')

    def _get_attribution_info(self, job: Dict[str, Any]) -> AttributionInfo:
        """Get attribution information for RemoteOK."""
        return AttributionInfo(
            source_name="RemoteOK",
            source_url="https://remoteok.io",
            attribution_text="Jobs sourced from RemoteOK.io",
            backlink_required=True
        )

    def _calculate_quality_score(self,
                                job: Dict[str, Any],
                                description: str,
                                salary: Optional[SalaryInfo],
                                skills: List[str]) -> float:
        """Calculate quality score for the job."""
        score = 0.0

        # Required fields present (30%)
        required_fields = ['position', 'company', 'description']
        present_fields = sum(1 for field in required_fields if job.get(field))
        score += (present_fields / len(required_fields)) * 0.3

        # Description quality (25%)
        if description:
            desc_length = len(description)
            if desc_length >= 200:
                score += 0.25
            elif desc_length >= 100:
                score += 0.15
            elif desc_length >= 50:
                score += 0.1

        # Salary disclosed (20%)
        if salary and salary.is_disclosed:
            score += 0.2

        # Skills extracted (15%)
        if skills:
            skill_score = min(len(skills) / 5, 1.0)  # Up to 5 skills for full score
            score += skill_score * 0.15

        # Additional details (10%)
        if job.get('company_logo'):
            score += 0.05
        if job.get('apply_url'):
            score += 0.05

        return min(score * 100, 100.0)  # Convert to 0-100 scale


async def parse_remoteok_jobs(
    jobs: List[Dict[str, Any]],
    location_parser: Optional[LocationParser] = None,
    salary_parser: Optional[SalaryParser] = None
) -> Tuple[List[StandardJob], ParsingStats]:
    """
    Parse a batch of RemoteOK jobs.

    Args:
        jobs: List of raw RemoteOK job data
        location_parser: Optional location parser
        salary_parser: Optional salary parser

    Returns:
        Tuple of (parsed_jobs, parsing_stats)
    """
    parser = RemoteOKParser(location_parser, salary_parser)
    stats = ParsingStats()
    parsed_jobs = []

    for job in jobs:
        stats.total_jobs += 1

        try:
            parsed_job = await parser.parse_job(job)
            parsed_jobs.append(parsed_job)
            stats.successfully_parsed += 1

            # Update specific stats
            if parsed_job.is_remote:
                stats.remote_jobs_detected += 1
            if parsed_job.salary:
                stats.salary_parsed += 1
            if parsed_job.skills_extracted:
                stats.skills_extracted += 1

        except ValidationError as e:
            logger.warning(f"Validation error for job {job.get('id', 'unknown')}: {e}")
            stats.validation_errors += 1
        except ProcessingError as e:
            logger.error(f"Processing error for job {job.get('id', 'unknown')}: {e}")
            stats.parsing_errors += 1
        except Exception as e:
            logger.error(f"Unexpected error parsing job {job.get('id', 'unknown')}: {e}")
            stats.parsing_errors += 1

    logger.info(f"RemoteOK parsing completed: {stats.successfully_parsed}/{stats.total_jobs} "
               f"jobs parsed successfully ({stats.success_rate:.1f}%)")

    return parsed_jobs, stats