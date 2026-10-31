"""Cross-source duplicate detection with intelligent source prioritization."""

import logging
import hashlib
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import urlparse

from ...models.job import StandardJob
from ...repositories.job_repository import JobRepository
from ...services.deduplication.similarity_calculator import SimilarityCalculator
from ...config.deduplication_config import get_dedup_config

logger = logging.getLogger(__name__)


# Phase 1 Task 5 — apply-link precedence, best first. Matched on the URL host so
# it works regardless of which adapter produced the row.
APPLY_URL_PRECEDENCE = (
    # 1. The employer's own ATS — straight to the hiring team, never a ghost job
    ("greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com",
     "workable.com", "recruitee.com", "smartrecruiters.com", "bamboohr.com"),
    # 2. Instahyre
    ("instahyre.com",),
    # 3. LinkedIn
    ("linkedin.com",),
    # 4. Indeed
    ("indeed.com",),
    # 5. Everything else that is still an aggregator
    ("hirist.tech", "naukri.com", "monsterindia.com", "shine.com", "timesjobs.com",
     "glassdoor.com", "ziprecruiter.com", "monster.com",
     "remoteok.com", "arbeitnow.com", "remotive.com", "himalayas.app"),
)

# A company-owned careers page isn't in the table above but beats every
# aggregator, so it sits just behind a real ATS.
_UNKNOWN_HOST_RANK = 1


def apply_url_rank(url: Optional[str]) -> int:
    """Lower is better. Unknown hosts are treated as company-owned careers pages."""
    if not url:
        return len(APPLY_URL_PRECEDENCE) + 1

    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return len(APPLY_URL_PRECEDENCE) + 1

    if not host:
        return len(APPLY_URL_PRECEDENCE) + 1

    for rank, hosts in enumerate(APPLY_URL_PRECEDENCE):
        if any(host == h or host.endswith("." + h) for h in hosts):
            return rank

    return _UNKNOWN_HOST_RANK


class CrossSourceDuplicateMatch:
    """Represents a cross-source duplicate match."""

    def __init__(self, job_id: int, source_id: int, similarity_score: float,
                 match_factors: Dict, source_priority: int):
        self.job_id = job_id
        self.source_id = source_id
        self.similarity_score = similarity_score
        self.match_factors = match_factors
        self.source_priority = source_priority


class CrossSourceDetector:
    """
    Advanced cross-source duplicate detection engine.

    Features:
    - Multi-source duplicate identification
    - Source priority-based resolution
    - Temporal window optimization
    - Company-based clustering
    - Intelligent merge strategies
    """

    def __init__(self, job_repository: JobRepository, similarity_calculator: SimilarityCalculator, environment: str = "development"):
        self.job_repository = job_repository
        self.similarity_calculator = similarity_calculator

        # Load configuration
        self.config = get_dedup_config(environment)
        self.source_priorities = self.config.cross_source.get('source_priorities', {})
        self.cross_source_threshold = self.config.similarity_thresholds.get('medium', 0.85)
        self.temporal_window_days = self.config.cross_source.get('temporal_window_days', 21)
        self.merge_preferences = {}  # no dedicated field on DeduplicationConfig; unused downstream

    async def find_cross_source_duplicates(self, job: StandardJob,
                                         exclude_source_id: Optional[int] = None) -> List[CrossSourceDuplicateMatch]:
        """
        Find duplicates across different job sources.

        Args:
            job: The job to check for cross-source duplicates
            exclude_source_id: Source ID to exclude from search (typically current job's source)

        Returns:
            List of cross-source duplicate matches sorted by priority and similarity
        """
        try:
            logger.info(f"Searching for cross-source duplicates: {job.title} at {job.company_name}")

            # Strategy 1: Company-based search (most efficient)
            company_matches = await self._find_company_based_matches(job, exclude_source_id)

            # Strategy 2: Title-based search (broader search)
            if len(company_matches) < 3:
                title_matches = await self._find_title_based_matches(job, exclude_source_id)
                company_matches.extend(title_matches)

            # Strategy 3: Content hash search (exact matches)
            hash_matches = await self._find_hash_based_matches(job, exclude_source_id)
            company_matches.extend(hash_matches)

            # Deduplicate matches and calculate final scores
            unique_matches = self._deduplicate_matches(company_matches)

            # Sort by source priority and similarity
            sorted_matches = self._prioritize_matches(unique_matches)

            logger.info(f"Found {len(sorted_matches)} cross-source duplicate candidates")
            return sorted_matches

        except Exception as e:
            logger.error(f"Error finding cross-source duplicates: {e}")
            return []

    async def resolve_cross_source_conflicts(self, matches: List[CrossSourceDuplicateMatch],
                                           new_job: StandardJob) -> Dict:
        """
        Resolve conflicts when the same job exists across multiple sources.

        Returns resolution strategy with preferred job and merge actions.
        """
        try:
            if not matches:
                return {'action': 'create_new', 'reason': 'no_conflicts'}

            # Analyze source priorities and job quality
            resolution = await self._analyze_source_conflicts(matches, new_job)

            logger.info(f"Cross-source conflict resolution: {resolution['action']}")
            return resolution

        except Exception as e:
            logger.error(f"Error resolving cross-source conflicts: {e}")
            return {'action': 'create_new', 'reason': 'resolution_error', 'error': str(e)}

    async def merge_cross_source_information(self, primary_job_id: int,
                                           secondary_matches: List[CrossSourceDuplicateMatch]) -> Dict:
        """
        Merge information from secondary sources into primary job.

        Returns merge result with updated fields and statistics.
        """
        try:
            # Get primary job
            primary_job = await self.job_repository.get_job_by_id(primary_job_id)

            if not primary_job:
                return {'success': False, 'error': 'Primary job not found'}

            merge_updates = {}
            source_tracking = []

            for match in secondary_matches:
                secondary_job = await self.job_repository.get_job_by_id(match.job_id)

                if secondary_job:
                    # Merge fields based on quality and completeness
                    field_updates = await self._merge_job_fields(primary_job, secondary_job)
                    merge_updates.update(field_updates)

                    # Track source information
                    source_tracking.append({
                        'source_id': match.source_id,
                        'job_id': match.job_id,
                        'similarity_score': match.similarity_score,
                        'found_at': datetime.utcnow().isoformat()
                    })

            # Apply updates to primary job
            if merge_updates:
                await self.job_repository.update_job(primary_job_id, merge_updates)

            # Update source tracking metadata
            merge_updates['cross_source_metadata'] = {
                'sources': source_tracking,
                'last_merge': datetime.utcnow().isoformat(),
                'merge_count': len(secondary_matches)
            }

            logger.info(f"Merged {len(secondary_matches)} cross-source jobs into primary {primary_job_id}")

            return {
                'success': True,
                'primary_job_id': primary_job_id,
                'merged_sources': len(secondary_matches),
                'updated_fields': list(merge_updates.keys()),
                'source_tracking': source_tracking
            }

        except Exception as e:
            logger.error(f"Error merging cross-source information: {e}")
            return {'success': False, 'error': str(e)}

    # Private implementation methods

    async def _find_company_based_matches(self, job: StandardJob, exclude_source_id: Optional[int]) -> List[CrossSourceDuplicateMatch]:
        """Find matches based on company and title similarity."""
        try:
            # Calculate search window
            posted_date = getattr(job, 'posted_date', None) or datetime.utcnow()
            search_start = posted_date - timedelta(days=self.temporal_window_days)
            search_end = posted_date + timedelta(days=self.temporal_window_days)

            # Search for jobs from same company in different sources
            candidates = await self.job_repository.find_jobs_by_company_and_timeframe(
                company_name=job.company_name,
                start_date=search_start,
                end_date=search_end,
                exclude_source_id=exclude_source_id,
                limit=50
            )

            matches = []
            for candidate in candidates:
                # Calculate similarity
                similarity_result = await self.similarity_calculator.calculate_comprehensive_similarity(
                    self._job_to_dict(job), self._job_to_dict(candidate)
                )

                similarity_score = similarity_result['total_score']

                # Apply cross-source threshold (typically higher than same-source)
                if similarity_score >= self.cross_source_threshold:
                    source_id = getattr(candidate, 'source_id', 999)
                    source_priority = self.source_priorities.get(source_id, 999)

                    matches.append(CrossSourceDuplicateMatch(
                        job_id=candidate.id,
                        source_id=source_id,
                        similarity_score=similarity_score,
                        match_factors=similarity_result['match_factors'],
                        source_priority=source_priority
                    ))

            return matches

        except Exception as e:
            logger.error(f"Error in company-based search: {e}")
            return []

    async def _find_title_based_matches(self, job: StandardJob, exclude_source_id: Optional[int]) -> List[CrossSourceDuplicateMatch]:
        """Find matches based on title similarity across sources."""
        try:
            # Extract key terms from job title
            title_keywords = self._extract_title_keywords(job.title)

            # Search across sources
            candidates = await self.job_repository.search_jobs_by_title_keywords(
                keywords=title_keywords,
                exclude_source_id=exclude_source_id,
                posted_within_days=self.temporal_window_days,
                limit=30
            )

            matches = []
            for candidate in candidates:
                # Calculate similarity
                similarity_result = await self.similarity_calculator.calculate_comprehensive_similarity(
                    self._job_to_dict(job), self._job_to_dict(candidate)
                )

                similarity_score = similarity_result['total_score']

                # Higher threshold for title-based matching
                if similarity_score >= (self.cross_source_threshold + 0.05):
                    source_id = getattr(candidate, 'source_id', 999)
                    source_priority = self.source_priorities.get(source_id, 999)

                    matches.append(CrossSourceDuplicateMatch(
                        job_id=candidate.id,
                        source_id=source_id,
                        similarity_score=similarity_score,
                        match_factors=similarity_result['match_factors'],
                        source_priority=source_priority
                    ))

            return matches

        except Exception as e:
            logger.error(f"Error in title-based search: {e}")
            return []

    async def _find_hash_based_matches(self, job: StandardJob, exclude_source_id: Optional[int]) -> List[CrossSourceDuplicateMatch]:
        """Find exact matches based on content hash."""
        try:
            # Generate content hash for exact matching
            content_hash = await self._generate_cross_source_hash(job)

            # Find jobs with same hash from different sources
            candidates = await self.job_repository.find_jobs_by_content_hash(
                content_hash=content_hash,
                exclude_source_id=exclude_source_id
            )

            matches = []
            for candidate in candidates:
                source_id = getattr(candidate, 'source_id', 999)
                source_priority = self.source_priorities.get(source_id, 999)

                matches.append(CrossSourceDuplicateMatch(
                    job_id=candidate.id,
                    source_id=source_id,
                    similarity_score=1.0,  # Exact match
                    match_factors={'match_type': 'exact_hash', 'content_hash': content_hash},
                    source_priority=source_priority
                ))

            return matches

        except Exception as e:
            logger.error(f"Error in hash-based search: {e}")
            return []

    def _deduplicate_matches(self, matches: List[CrossSourceDuplicateMatch]) -> List[CrossSourceDuplicateMatch]:
        """Remove duplicate matches from the list."""
        seen_jobs = set()
        unique_matches = []

        for match in matches:
            if match.job_id not in seen_jobs:
                seen_jobs.add(match.job_id)
                unique_matches.append(match)

        return unique_matches

    def _prioritize_matches(self, matches: List[CrossSourceDuplicateMatch]) -> List[CrossSourceDuplicateMatch]:
        """Sort matches by source priority and similarity score."""
        return sorted(matches, key=lambda m: (m.source_priority, -m.similarity_score))

    async def _analyze_source_conflicts(self, matches: List[CrossSourceDuplicateMatch],
                                      new_job: StandardJob) -> Dict:
        """Analyze conflicts and determine resolution strategy."""
        if not matches:
            return {'action': 'create_new', 'reason': 'no_matches'}

        # Get best match by priority and similarity
        best_match = matches[0]

        # Source priority rules
        new_job_source_priority = self.source_priorities.get(getattr(new_job, 'source_id', 999), 999)

        if new_job_source_priority < best_match.source_priority:
            # New job has higher priority source
            return {
                'action': 'replace_existing',
                'primary_job_id': None,
                'replace_job_id': best_match.job_id,
                'reason': 'higher_priority_source',
                'new_source_priority': new_job_source_priority,
                'existing_source_priority': best_match.source_priority
            }

        elif new_job_source_priority == best_match.source_priority:
            # Same priority, use quality and completeness
            try:
                existing_job = await self.job_repository.get_job_by_id(best_match.job_id)

                if existing_job and await self._is_better_quality(new_job, existing_job):
                    return {
                        'action': 'replace_existing',
                        'primary_job_id': None,
                        'replace_job_id': best_match.job_id,
                        'reason': 'better_quality'
                    }
                else:
                    return {
                        'action': 'merge_into_existing',
                        'primary_job_id': best_match.job_id,
                        'reason': 'existing_better_quality'
                    }
            except Exception as e:
                logger.error(f"Error comparing job quality: {e}")
                return {
                    'action': 'merge_into_existing',
                    'primary_job_id': best_match.job_id,
                    'reason': 'quality_comparison_failed'
                }

        else:
            # Existing job has higher priority
            return {
                'action': 'merge_into_existing',
                'primary_job_id': best_match.job_id,
                'reason': 'existing_higher_priority',
                'existing_source_priority': best_match.source_priority,
                'new_source_priority': new_job_source_priority
            }

    async def _merge_job_fields(self, primary_job, secondary_job) -> Dict:
        """Determine which fields to merge from secondary to primary job."""
        merge_updates = {}

        # Salary information (prefer disclosed over undisclosed)
        if self._should_merge_salary(getattr(primary_job, 'salary', None), getattr(secondary_job, 'salary', None)):
            merge_updates['salary_min'] = getattr(secondary_job, 'salary_min', None)
            merge_updates['salary_max'] = getattr(secondary_job, 'salary_max', None)
            merge_updates['salary_currency'] = getattr(secondary_job, 'salary_currency', None)

        # Description (prefer longer, more detailed)
        primary_desc = getattr(primary_job, 'description', None)
        secondary_desc = getattr(secondary_job, 'description', None)
        if self._should_merge_description(primary_desc, secondary_desc):
            merge_updates['description'] = secondary_desc

        # Apply URL (prefer direct company links)
        primary_url = getattr(primary_job, 'apply_url', None)
        secondary_url = getattr(secondary_job, 'apply_url', None)
        if self._should_merge_apply_url(primary_url, secondary_url):
            merge_updates['apply_url'] = secondary_url

        # Benefits (merge both)
        primary_benefits = getattr(primary_job, 'benefits', None)
        secondary_benefits = getattr(secondary_job, 'benefits', None)
        if secondary_benefits and secondary_benefits != primary_benefits:
            merged_benefits = self._merge_benefits(primary_benefits, secondary_benefits)
            if merged_benefits != primary_benefits:
                merge_updates['benefits'] = merged_benefits

        # Skills (union of both)
        primary_skills = getattr(primary_job, 'skills', None)
        secondary_skills = getattr(secondary_job, 'skills', None)
        if secondary_skills and secondary_skills != primary_skills:
            merged_skills = self._merge_skills(primary_skills, secondary_skills)
            if merged_skills != primary_skills:
                merge_updates['skills'] = merged_skills

        return merge_updates

    def _should_merge_salary(self, primary_salary, secondary_salary) -> bool:
        """Determine if secondary salary should replace primary."""
        if not secondary_salary:
            return False

        if not primary_salary:
            return True

        # Prefer disclosed salary
        primary_disclosed = getattr(primary_salary, 'is_disclosed', False)
        secondary_disclosed = getattr(secondary_salary, 'is_disclosed', False)

        return secondary_disclosed and not primary_disclosed

    def _should_merge_description(self, primary_desc: str, secondary_desc: str) -> bool:
        """Determine if secondary description should replace primary."""
        if not secondary_desc:
            return False

        if not primary_desc:
            return True

        # Prefer longer, more detailed descriptions
        return len(secondary_desc) > len(primary_desc) * 1.5

    def _should_merge_apply_url(self, primary_url: str, secondary_url: str) -> bool:
        """Determine if secondary URL should replace primary.

        Phase 1 Task 5: when the same job arrives from several sources, keep the
        highest-precedence apply link. Applying at the employer's own ATS
        converts better than applying through an aggregator, and it's the link
        the application packet surfaces.
        """
        if not secondary_url:
            return False

        if not primary_url:
            return True

        return apply_url_rank(secondary_url) < apply_url_rank(primary_url)

    def _merge_benefits(self, primary_benefits, secondary_benefits) -> List[str]:
        """Merge benefits from both jobs."""
        if not primary_benefits:
            return secondary_benefits or []

        if not secondary_benefits:
            return primary_benefits

        # Union of benefits
        primary_set = set(primary_benefits)
        secondary_set = set(secondary_benefits)

        return list(primary_set.union(secondary_set))

    def _merge_skills(self, primary_skills, secondary_skills) -> List[str]:
        """Merge skills from both jobs."""
        if not primary_skills:
            return secondary_skills or []

        if not secondary_skills:
            return primary_skills

        # Union of skills (case-insensitive)
        primary_lower = [skill.lower() for skill in primary_skills]
        merged_skills = list(primary_skills)

        for skill in secondary_skills:
            if skill.lower() not in primary_lower:
                merged_skills.append(skill)

        return merged_skills

    async def _is_better_quality(self, job1: StandardJob, job2) -> bool:
        """Compare job quality to determine which is better."""
        # Simple quality scoring based on completeness
        score1 = self._calculate_job_completeness_score(job1)
        score2 = self._calculate_job_completeness_score(job2)

        return score1 > score2

    def _calculate_job_completeness_score(self, job) -> float:
        """Calculate job completeness score."""
        score = 0.0

        # Required fields
        if getattr(job, 'title', None):
            score += 0.2
        if getattr(job, 'company_name', None):
            score += 0.2
        if getattr(job, 'description', None) and len(job.description) > 100:
            score += 0.2

        # Optional but valuable fields
        if getattr(job, 'salary_min', None) or getattr(job, 'salary_max', None):
            score += 0.15
        if getattr(job, 'benefits', None):
            score += 0.1
        if getattr(job, 'skills', None):
            score += 0.1
        if getattr(job, 'apply_url', None) and 'example.com' not in str(job.apply_url):
            score += 0.05

        return score

    def _extract_title_keywords(self, title: str) -> List[str]:
        """Extract key terms from job title for searching."""
        if not title:
            return []

        # Remove common noise words
        noise_words = {'job', 'position', 'role', 'opening', 'opportunity'}
        words = [word.lower() for word in title.split() if word.lower() not in noise_words and len(word) > 2]

        # Return top 3 most meaningful words
        return words[:3]

    async def _generate_cross_source_hash(self, job: StandardJob) -> str:
        """Generate hash for cross-source matching (less strict than content hash)."""
        # Use title + company for cross-source hash (location may vary)
        hash_components = [
            job.title.lower().strip() if job.title else '',
            job.company_name.lower().strip() if job.company_name else ''
        ]

        content_string = "|".join(filter(None, hash_components))

        return hashlib.sha256(content_string.encode('utf-8')).hexdigest()

    def _job_to_dict(self, job) -> dict:
        """Convert job object to dictionary for similarity calculator."""
        return {
            'title': getattr(job, 'title', ''),
            'company_name': getattr(job, 'company_name', ''),
            'location': getattr(job, 'location', None),
            'salary': getattr(job, 'salary', None),
            'posted_date': getattr(job, 'posted_date', None),
            'description': getattr(job, 'description', ''),
            'source_id': getattr(job, 'source_id', None)
        }