"""IT job filtering service for RemoteOK jobs."""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Set, Optional, NamedTuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class FilterResult(Enum):
    """Result of job filtering."""
    INCLUDED = "included"
    EXCLUDED_TAGS = "excluded_tags"
    EXCLUDED_TITLE = "excluded_title"
    EXCLUDED_DESCRIPTION = "excluded_description"
    EXCLUDED_OLD = "excluded_old"
    EXCLUDED_QUALITY = "excluded_quality"
    EXCLUDED_UNKNOWN = "excluded_unknown"


@dataclass
class FilterStats:
    """Statistics from job filtering operation."""
    total_jobs: int = 0
    included_jobs: int = 0
    excluded_by_tags: int = 0
    excluded_by_title: int = 0
    excluded_by_description: int = 0
    excluded_by_age: int = 0
    excluded_by_quality: int = 0
    excluded_unknown: int = 0

    def get_inclusion_rate(self) -> float:
        """Get percentage of jobs included."""
        if self.total_jobs == 0:
            return 0.0
        return (self.included_jobs / self.total_jobs) * 100

    def get_summary(self) -> Dict[str, Any]:
        """Get filtering summary."""
        return {
            'total_jobs': self.total_jobs,
            'included_jobs': self.included_jobs,
            'inclusion_rate': self.get_inclusion_rate(),
            'exclusions': {
                'tags': self.excluded_by_tags,
                'title': self.excluded_by_title,
                'description': self.excluded_by_description,
                'age': self.excluded_by_age,
                'quality': self.excluded_by_quality,
                'unknown': self.excluded_unknown
            }
        }


class JobClassification(NamedTuple):
    """Classification result for a job."""
    is_it_job: bool
    confidence_score: float
    matched_tags: List[str]
    matched_title_keywords: List[str]
    matched_description_keywords: List[str]
    quality_score: float
    filter_result: FilterResult
    reason: str


class RemoteOKFilter:
    """Filter for identifying IT-related jobs from RemoteOK."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize RemoteOK filter.

        Args:
            config: Filter configuration dictionary
        """
        self.config = config or self._get_default_config()

        # Convert lists to sets for faster lookup
        self.include_tags = set(tag.lower() for tag in self.config.get('include_tags', []))
        self.exclude_tags = set(tag.lower() for tag in self.config.get('exclude_tags', []))

        # IT job indicators in titles
        self.it_title_keywords = {
            'developer', 'engineer', 'programmer', 'dev', 'software',
            'frontend', 'backend', 'fullstack', 'full-stack', 'full stack',
            'devops', 'sre', 'platform', 'infrastructure', 'cloud',
            'data scientist', 'data engineer', 'ml engineer', 'ai engineer',
            'mobile developer', 'ios developer', 'android developer',
            'qa engineer', 'test engineer', 'automation engineer',
            'security engineer', 'cybersecurity', 'infosec',
            'architect', 'tech lead', 'technical lead', 'cto', 'vp engineering'
        }

        # Non-IT job indicators in titles
        self.non_it_title_keywords = {
            'sales', 'marketing', 'designer', 'design', 'hr', 'human resources',
            'customer support', 'support specialist', 'account manager',
            'business development', 'bd', 'copywriter', 'content writer',
            'social media', 'seo specialist', 'operations', 'admin',
            'recruiter', 'talent acquisition', 'finance', 'accounting',
            'legal', 'lawyer', 'attorney', 'paralegal'
        }

        # Compile regex patterns for efficiency
        self.title_patterns = self._compile_title_patterns()
        self.description_patterns = self._compile_description_patterns()

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default filter configuration."""
        return {
            'include_tags': [
                # Backend
                'dev', 'developer', 'engineer', 'engineering',
                'python', 'javascript', 'java', 'golang', 'go', 'rust',
                'node', 'nodejs', 'django', 'flask', 'rails', 'laravel',
                'php', 'ruby', 'csharp', 'dotnet', '.net', 'scala',
                # Frontend
                'frontend', 'front-end', 'react', 'angular', 'vue', 'vuejs',
                'html', 'css', 'sass', 'scss', 'typescript', 'ts',
                # DevOps/Cloud
                'devops', 'cloud', 'aws', 'azure', 'gcp', 'kubernetes',
                'docker', 'terraform', 'ansible', 'jenkins', 'cicd',
                # Data
                'data', 'ml', 'ai', 'machine learning', 'data science',
                'sql', 'nosql', 'mongodb', 'postgresql', 'mysql',
                # Mobile
                'ios', 'android', 'mobile', 'react native', 'flutter'
            ],
            'exclude_tags': [
                'sales', 'marketing', 'design', 'hr', 'customer support',
                'writing', 'content', 'copywriting', 'seo', 'social media'
            ],
            'max_age_days': 30,
            'min_quality_score': 0.5
        }

    def _compile_title_patterns(self) -> List[re.Pattern]:
        """Compile regex patterns for title matching."""
        patterns = []

        # IT role patterns
        it_patterns = [
            r'\b(?:senior|junior|lead|principal|staff)\s+(?:software|backend|frontend|fullstack|full.stack)\s+(?:engineer|developer)\b',
            r'\b(?:software|backend|frontend|fullstack|full.stack)\s+(?:engineer|developer)\b',
            r'\b(?:devops|sre|platform|cloud|infrastructure)\s+engineer\b',
            r'\b(?:data|ml|ai|machine\s+learning)\s+(?:engineer|scientist)\b',
            r'\b(?:mobile|ios|android)\s+developer\b',
            r'\b(?:qa|test|automation)\s+engineer\b',
            r'\btech(?:nical)?\s+lead\b',
            r'\bsoftware\s+architect\b'
        ]

        for pattern in it_patterns:
            patterns.append(re.compile(pattern, re.IGNORECASE))

        return patterns

    def _compile_description_patterns(self) -> List[re.Pattern]:
        """Compile regex patterns for description matching."""
        patterns = []

        # Technical skill patterns
        tech_patterns = [
            r'\b(?:python|javascript|java|golang|rust|php|ruby|scala)\b',
            r'\b(?:react|angular|vue|django|flask|rails|laravel)\b',
            r'\b(?:aws|azure|gcp|kubernetes|docker|terraform)\b',
            r'\b(?:sql|nosql|mongodb|postgresql|mysql|redis)\b',
            r'\b(?:git|github|gitlab|ci/cd|jenkins|github actions)\b'
        ]

        for pattern in tech_patterns:
            patterns.append(re.compile(pattern, re.IGNORECASE))

        return patterns

    def classify_job(self, job: Dict[str, Any]) -> JobClassification:
        """
        Classify a job as IT or non-IT.

        Args:
            job: RemoteOK job dictionary

        Returns:
            JobClassification with detailed analysis
        """
        # Extract job fields
        title = job.get('position', '').lower()
        company = job.get('company', '').lower()
        tags = [tag.lower() for tag in job.get('tags', [])]
        description = job.get('description', '').lower()

        # Initialize classification
        matched_tags = []
        matched_title_keywords = []
        matched_description_keywords = []
        confidence_score = 0.0
        quality_score = self._calculate_quality_score(job)

        # Check for excluded tags first
        excluded_found = self.exclude_tags.intersection(set(tags))
        if excluded_found:
            return JobClassification(
                is_it_job=False,
                confidence_score=0.0,
                matched_tags=list(excluded_found),
                matched_title_keywords=[],
                matched_description_keywords=[],
                quality_score=quality_score,
                filter_result=FilterResult.EXCLUDED_TAGS,
                reason=f"Contains excluded tags: {', '.join(excluded_found)}"
            )

        # Check for non-IT keywords in title
        non_it_in_title = [keyword for keyword in self.non_it_title_keywords
                          if keyword in title]
        if non_it_in_title:
            return JobClassification(
                is_it_job=False,
                confidence_score=0.0,
                matched_tags=[],
                matched_title_keywords=non_it_in_title,
                matched_description_keywords=[],
                quality_score=quality_score,
                filter_result=FilterResult.EXCLUDED_TITLE,
                reason=f"Non-IT keywords in title: {', '.join(non_it_in_title)}"
            )

        # Primary filter: Check tags for IT technologies
        included_found = self.include_tags.intersection(set(tags))
        if included_found:
            matched_tags = list(included_found)
            confidence_score += 0.7  # High confidence from tags

        # Secondary filter: Check title for IT keywords
        it_in_title = [keyword for keyword in self.it_title_keywords
                      if keyword in title]
        if it_in_title:
            matched_title_keywords = it_in_title
            confidence_score += 0.5

        # Check title patterns
        for pattern in self.title_patterns:
            if pattern.search(title):
                confidence_score += 0.3
                break

        # Tertiary filter: Check description for technical terms
        for pattern in self.description_patterns:
            matches = pattern.findall(description)
            if matches:
                matched_description_keywords.extend(matches)
                confidence_score += 0.1

        # Normalize confidence score
        confidence_score = min(confidence_score, 1.0)

        # Make decision based on confidence
        is_it_job = confidence_score >= 0.3  # Threshold for IT classification

        if is_it_job:
            filter_result = FilterResult.INCLUDED
            reason = f"IT job (confidence: {confidence_score:.2f})"
        else:
            filter_result = FilterResult.EXCLUDED_UNKNOWN
            reason = f"Insufficient IT indicators (confidence: {confidence_score:.2f})"

        return JobClassification(
            is_it_job=is_it_job,
            confidence_score=confidence_score,
            matched_tags=matched_tags,
            matched_title_keywords=matched_title_keywords,
            matched_description_keywords=matched_description_keywords,
            quality_score=quality_score,
            filter_result=filter_result,
            reason=reason
        )

    def _calculate_quality_score(self, job: Dict[str, Any]) -> float:
        """Calculate quality score for a job posting."""
        score = 0.0

        # Required fields present (40%)
        required_fields = ['position', 'company', 'description']
        present_fields = sum(1 for field in required_fields if job.get(field))
        score += (present_fields / len(required_fields)) * 0.4

        # Description length (20%)
        description = job.get('description', '')
        if description:
            # Good description is 200-2000 characters
            desc_length = len(description)
            if 200 <= desc_length <= 2000:
                score += 0.2
            elif desc_length > 100:
                score += 0.1

        # Salary disclosed (20%)
        if job.get('salary_min') or job.get('salary_max'):
            score += 0.2

        # Company information (20%)
        company = job.get('company', '')
        if company and len(company) > 2:
            score += 0.2

        return min(score, 1.0)

    def filter_jobs(self, jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Filter jobs for IT positions.

        Args:
            jobs: List of RemoteOK job dictionaries

        Returns:
            Dictionary with filtered jobs and statistics
        """
        stats = FilterStats()
        included_jobs = []
        excluded_jobs = []

        max_age_days = self.config.get('max_age_days', 30)
        min_quality_score = self.config.get('min_quality_score', 0.5)
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=max_age_days)

        for job in jobs:
            stats.total_jobs += 1

            # Check job age
            posted_date = self._parse_job_date(job)
            if posted_date and posted_date < cutoff_date:
                stats.excluded_by_age += 1
                excluded_jobs.append({
                    'job': job,
                    'reason': 'Too old',
                    'classification': None
                })
                continue

            # Classify job
            classification = self.classify_job(job)

            # Apply quality filter
            if classification.quality_score < min_quality_score:
                stats.excluded_by_quality += 1
                excluded_jobs.append({
                    'job': job,
                    'reason': f'Low quality score: {classification.quality_score:.2f}',
                    'classification': classification
                })
                continue

            # Apply IT classification filter
            if classification.is_it_job:
                stats.included_jobs += 1
                included_jobs.append({
                    'job': job,
                    'classification': classification
                })
            else:
                # Track exclusion reasons
                if classification.filter_result == FilterResult.EXCLUDED_TAGS:
                    stats.excluded_by_tags += 1
                elif classification.filter_result == FilterResult.EXCLUDED_TITLE:
                    stats.excluded_by_title += 1
                elif classification.filter_result == FilterResult.EXCLUDED_DESCRIPTION:
                    stats.excluded_by_description += 1
                else:
                    stats.excluded_unknown += 1

                excluded_jobs.append({
                    'job': job,
                    'reason': classification.reason,
                    'classification': classification
                })

        logger.info(f"RemoteOK filter results: {stats.included_jobs}/{stats.total_jobs} "
                   f"jobs included ({stats.get_inclusion_rate():.1f}%)")

        return {
            'included_jobs': included_jobs,
            'excluded_jobs': excluded_jobs,
            'stats': stats,
            'filter_config': self.config
        }

    def filter_recent_jobs(self, jobs: List[Dict[str, Any]], days: int = 30) -> List[Dict[str, Any]]:
        """
        Filter jobs posted within N days.

        Args:
            jobs: List of job dictionaries
            days: Number of days to look back

        Returns:
            List of recent jobs
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        recent_jobs = []

        for job in jobs:
            posted_date = self._parse_job_date(job)
            if posted_date and posted_date >= cutoff_date:
                recent_jobs.append(job)

        logger.debug(f"Filtered {len(recent_jobs)}/{len(jobs)} recent jobs (within {days} days)")
        return recent_jobs

    def _parse_job_date(self, job: Dict[str, Any]) -> Optional[datetime]:
        """Parse job posting date from various formats."""
        date_str = job.get('date') or job.get('epoch')

        if not date_str:
            return None

        try:
            # Try epoch timestamp
            if isinstance(date_str, (int, float)):
                return datetime.fromtimestamp(date_str, tz=timezone.utc)

            # Try ISO format
            if isinstance(date_str, str):
                # Handle various ISO formats
                for fmt in ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d']:
                    try:
                        dt = datetime.strptime(date_str, fmt)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        return dt
                    except ValueError:
                        continue

        except Exception as e:
            logger.warning(f"Failed to parse job date '{date_str}': {e}")

        return None

    def get_filter_stats(self) -> Dict[str, Any]:
        """Get filter configuration and statistics."""
        return {
            'config': self.config,
            'include_tags_count': len(self.include_tags),
            'exclude_tags_count': len(self.exclude_tags),
            'it_title_keywords_count': len(self.it_title_keywords),
            'non_it_title_keywords_count': len(self.non_it_title_keywords),
            'title_patterns_count': len(self.title_patterns),
            'description_patterns_count': len(self.description_patterns)
        }