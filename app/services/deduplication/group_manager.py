"""Duplicate groups management system for handling job clusters."""

import logging
import hashlib
from typing import List, Dict, Optional, Tuple, Set
from datetime import datetime, timedelta
from decimal import Decimal

from ...models.job import StandardJob
from ...repositories.job_repository import JobRepository
from ...repositories.duplicate_group_repository import DuplicateGroupRepository
from ...services.deduplication.similarity_calculator import SimilarityCalculator
from ...config.deduplication_config import get_dedup_config

logger = logging.getLogger(__name__)


class DuplicateGroupsManager:
    """
    Manages clusters of duplicate jobs with intelligent grouping and optimization.

    Features:
    - Automatic duplicate group creation
    - Primary job selection based on quality metrics
    - Group merging for related clusters
    - Group splitting for incorrectly grouped jobs
    - Performance optimization for large groups
    """

    def __init__(self, job_repository: JobRepository,
                 group_repository: DuplicateGroupRepository,
                 similarity_calculator: SimilarityCalculator,
                 environment: str = "development"):
        self.job_repository = job_repository
        self.group_repository = group_repository
        self.similarity_calculator = similarity_calculator

        # Configuration
        self.config = get_dedup_config(environment)
        self.max_group_size = self.config.group_management.get('max_group_size', 50)
        self.group_quality_threshold = self.config.group_management.get('quality_threshold', 0.8)
        self.primary_selection_weights = self.config.group_management.get('primary_selection_weights', {})

    async def create_duplicate_group(self, job_ids: List[int],
                                   similarity_scores: Dict[int, float]) -> Optional[int]:
        """
        Create a new duplicate group from a list of job IDs.

        Args:
            job_ids: List of job IDs to group together
            similarity_scores: Mapping of job_id to similarity score

        Returns:
            Group ID if successful, None if failed
        """
        try:
            if len(job_ids) < 2:
                logger.warning("Cannot create group with less than 2 jobs")
                return None

            # Select primary job
            primary_job_id = await self._select_primary_job(job_ids, similarity_scores)

            if not primary_job_id:
                logger.error("Failed to select primary job for group")
                return None

            # Generate group hash
            group_hash = await self._generate_group_hash(job_ids)

            # Check if group already exists
            existing_group = await self.group_repository.get_groups_by_hash(group_hash)
            if existing_group:
                logger.info(f"Group with hash {group_hash} already exists: {existing_group.id}")
                return existing_group.id

            # Calculate group quality score
            quality_score = await self._calculate_group_quality(job_ids, similarity_scores)

            # Create duplicate group
            group_data = {
                'primary_job_id': primary_job_id,
                'group_hash': group_hash,
                'member_count': len(job_ids),
                'quality_score': quality_score
            }

            group_id = await self.group_repository.create_group(group_data)

            if not group_id:
                logger.error("Failed to create duplicate group")
                return None

            # Create mappings for all jobs
            mapping_success = await self._create_group_mappings(
                group_id, job_ids, primary_job_id, similarity_scores
            )

            if not mapping_success:
                # Rollback group creation
                await self.group_repository.delete_group(group_id)
                return None

            # Merge information into primary job
            await self._merge_group_information(group_id, primary_job_id, job_ids)

            logger.info(f"Created duplicate group {group_id} with {len(job_ids)} jobs, primary: {primary_job_id}")
            return group_id

        except Exception as e:
            logger.error(f"Error creating duplicate group: {e}")
            return None

    async def add_job_to_group(self, group_id: int, job_id: int,
                             similarity_score: float) -> bool:
        """Add a job to an existing duplicate group."""
        try:
            # Get group information
            group = await self.group_repository.get_group(group_id)
            if not group:
                logger.error(f"Group {group_id} not found")
                return False

            # Check if group is at capacity
            if group.member_count >= self.max_group_size:
                logger.warning(f"Group {group_id} at maximum capacity ({self.max_group_size})")
                return False

            # Check if job already in a group
            existing_mapping = await self.group_repository.get_job_mapping(job_id)
            if existing_mapping:
                logger.warning(f"Job {job_id} already in group {existing_mapping.group_id}")
                return False

            # Create mapping
            mapping_data = {
                'job_id': job_id,
                'group_id': group_id,
                'similarity_score': similarity_score,
                'detection_method': 'group_addition',
                'is_primary': False,
                'metadata': {'added_at': datetime.utcnow().isoformat()}
            }

            mapping_id = await self.group_repository.create_mapping(mapping_data)

            if mapping_id:
                # Update group member count
                await self.group_repository.update_group(group_id, {
                    'member_count': group.member_count + 1,
                    'updated_at': datetime.utcnow()
                })

                # Check if new job should be primary
                await self._reassess_primary_job(group_id)

                logger.info(f"Added job {job_id} to group {group_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Error adding job to group: {e}")
            return False

    async def remove_job_from_group(self, job_id: int) -> bool:
        """Remove a job from its duplicate group."""
        try:
            # Get job mapping
            mapping = await self.group_repository.get_job_mapping(job_id)
            if not mapping:
                logger.warning(f"Job {job_id} not in any group")
                return False

            group_id = mapping.group_id
            was_primary = mapping.is_primary

            # Remove mapping
            await self.group_repository.delete_mapping(mapping.id)

            # Update group
            group = await self.group_repository.get_group(group_id)
            new_member_count = group.member_count - 1

            if new_member_count <= 1:
                # Dissolve group if only one member left
                await self._dissolve_group(group_id)
            else:
                # Update member count
                await self.group_repository.update_group(group_id, {
                    'member_count': new_member_count,
                    'updated_at': datetime.utcnow()
                })

                # Select new primary if removed job was primary
                if was_primary:
                    await self._reassess_primary_job(group_id)

            logger.info(f"Removed job {job_id} from group {group_id}")
            return True

        except Exception as e:
            logger.error(f"Error removing job from group: {e}")
            return False

    async def merge_groups(self, group1_id: int, group2_id: int) -> Optional[int]:
        """Merge two duplicate groups into one."""
        try:
            # Get both groups
            group1 = await self.group_repository.get_group(group1_id)
            group2 = await self.group_repository.get_group(group2_id)

            if not group1 or not group2:
                logger.error("One or both groups not found for merging")
                return None

            # Check combined size
            total_size = group1.member_count + group2.member_count
            if total_size > self.max_group_size:
                logger.warning(f"Merged group would exceed maximum size: {total_size}")
                return None

            # Determine which group to keep (higher quality)
            primary_group_id = group1_id if group1.quality_score >= group2.quality_score else group2_id
            secondary_group_id = group2_id if primary_group_id == group1_id else group1_id

            # Get all mappings from secondary group
            secondary_mappings = await self.group_repository.get_group_mappings(secondary_group_id)

            # Move mappings to primary group
            for mapping in secondary_mappings:
                await self.group_repository.update_mapping(mapping.id, {
                    'group_id': primary_group_id,
                    'is_primary': False  # Will be reassessed
                })

            # Update primary group
            await self.group_repository.update_group(primary_group_id, {
                'member_count': total_size,
                'quality_score': max(group1.quality_score, group2.quality_score),
                'updated_at': datetime.utcnow()
            })

            # Delete secondary group
            await self.group_repository.delete_group(secondary_group_id)

            # Reassess primary job
            await self._reassess_primary_job(primary_group_id)

            logger.info(f"Merged groups {group1_id} and {group2_id} into {primary_group_id}")
            return primary_group_id

        except Exception as e:
            logger.error(f"Error merging groups: {e}")
            return None

    async def split_group(self, group_id: int, job_ids_to_split: List[int]) -> Optional[int]:
        """Split jobs from an existing group into a new group."""
        try:
            if len(job_ids_to_split) < 2:
                logger.warning("Need at least 2 jobs to create new group")
                return None

            # Verify all jobs are in the group
            for job_id in job_ids_to_split:
                mapping = await self.group_repository.get_job_mapping(job_id)
                if not mapping or mapping.group_id != group_id:
                    logger.error(f"Job {job_id} not in group {group_id}")
                    return None

            # Calculate similarity scores for new group
            similarity_scores = {}
            for job_id in job_ids_to_split:
                mapping = await self.group_repository.get_job_mapping(job_id)
                similarity_scores[job_id] = float(mapping.similarity_score)

            # Remove jobs from original group
            for job_id in job_ids_to_split:
                await self.remove_job_from_group(job_id)

            # Create new group
            new_group_id = await self.create_duplicate_group(job_ids_to_split, similarity_scores)

            if new_group_id:
                logger.info(f"Split {len(job_ids_to_split)} jobs from group {group_id} into new group {new_group_id}")

            return new_group_id

        except Exception as e:
            logger.error(f"Error splitting group: {e}")
            return None

    async def get_group_jobs(self, group_id: int, include_primary_only: bool = False) -> List[Dict]:
        """Get all jobs in a duplicate group."""
        try:
            mappings = await self.group_repository.get_group_mappings(group_id)

            if include_primary_only:
                mappings = [m for m in mappings if m.is_primary]

            job_ids = [m.job_id for m in mappings]
            jobs = await self.job_repository.get_jobs_by_ids(job_ids)

            # Combine job data with mapping info
            result = []
            for job in jobs:
                mapping = next((m for m in mappings if m.job_id == job.id), None)
                if mapping:
                    result.append({
                        'job': job,
                        'mapping': mapping,
                        'is_primary': mapping.is_primary,
                        'similarity_score': float(mapping.similarity_score)
                    })

            return result

        except Exception as e:
            logger.error(f"Error getting group jobs: {e}")
            return []

    async def find_related_groups(self, group_id: int, similarity_threshold: float = 0.8) -> List[int]:
        """Find other groups that might be related to the given group."""
        try:
            # Get primary job from the group
            group = await self.group_repository.get_group(group_id)
            if not group:
                return []

            primary_job = await self.job_repository.get_job_by_id(group.primary_job_id)
            if not primary_job:
                return []

            # Find other groups with similar primary jobs
            company_id = getattr(primary_job, 'company_id', None)
            if not company_id:
                return []

            other_groups = await self.group_repository.get_groups_by_company(
                company_id, exclude_group_id=group_id
            )

            related_groups = []
            for other_group in other_groups:
                other_primary = await self.job_repository.get_job_by_id(other_group.primary_job_id)

                if other_primary:
                    similarity_result = await self.similarity_calculator.calculate_comprehensive_similarity(
                        self._job_to_dict(primary_job), self._job_to_dict(other_primary)
                    )

                    if similarity_result['total_score'] >= similarity_threshold:
                        related_groups.append(other_group.id)

            return related_groups

        except Exception as e:
            logger.error(f"Error finding related groups: {e}")
            return []

    async def run_group_maintenance(self) -> Dict[str, int]:
        """Run maintenance tasks on duplicate groups."""
        try:
            maintenance_results = {
                'orphaned_mappings_cleaned': 0,
                'low_quality_groups_dissolved': 0,
                'groups_merged': 0,
                'primary_jobs_reassessed': 0
            }

            # Clean up orphaned mappings
            orphaned_count = await self.group_repository.cleanup_orphaned_mappings()
            maintenance_results['orphaned_mappings_cleaned'] = orphaned_count

            # Dissolve low-quality groups
            low_quality_groups = await self.group_repository.get_groups_needing_review(0.5)
            for group in low_quality_groups:
                if group.member_count <= 2:  # Only dissolve very small, low-quality groups
                    await self._dissolve_group(group.id)
                    maintenance_results['low_quality_groups_dissolved'] += 1

            # Find and merge related groups
            all_groups = await self.group_repository.get_groups_by_quality_range(0.8, 1.0)
            merge_threshold = self.config.get('group_merge_candidate_threshold', 0.85)

            for group in all_groups:
                related_groups = await self.find_related_groups(group.id, merge_threshold)
                for related_id in related_groups[:1]:  # Only merge with one related group at a time
                    merged_id = await self.merge_groups(group.id, related_id)
                    if merged_id:
                        maintenance_results['groups_merged'] += 1
                        break

            logger.info(f"Group maintenance completed: {maintenance_results}")
            return maintenance_results

        except Exception as e:
            logger.error(f"Error in group maintenance: {e}")
            return {}

    # Private helper methods

    async def _select_primary_job(self, job_ids: List[int],
                                similarity_scores: Dict[int, float]) -> Optional[int]:
        """Select the best job to be primary for the group."""
        try:
            jobs = await self.job_repository.get_jobs_by_ids(job_ids)

            if not jobs:
                return None

            best_job_id = None
            best_score = -1

            for job in jobs:
                score = await self._calculate_primary_selection_score(job, similarity_scores.get(job.id, 0))

                if score > best_score:
                    best_score = score
                    best_job_id = job.id

            return best_job_id

        except Exception as e:
            logger.error(f"Error selecting primary job: {e}")
            return None

    async def _calculate_primary_selection_score(self, job, similarity_score: float) -> float:
        """Calculate score for primary job selection."""
        weights = self.primary_selection_weights

        # Base scoring factors
        completeness_score = self._calculate_job_completeness(job)
        quality_score = getattr(job, 'quality_score', 0.5)
        freshness_score = self._calculate_freshness_score(getattr(job, 'posted_date', None))
        source_priority_score = self._get_source_priority_score(getattr(job, 'source_id', 999))

        # Weighted total
        total_score = (
            completeness_score * weights.get('completeness', 0.3) +
            quality_score * weights.get('quality', 0.3) +
            freshness_score * weights.get('freshness', 0.2) +
            source_priority_score * weights.get('source_priority', 0.2)
        )

        return total_score

    def _calculate_job_completeness(self, job) -> float:
        """Calculate how complete a job posting is."""
        score = 0.0

        # Required fields
        if getattr(job, 'title', None):
            score += 0.2
        if getattr(job, 'company_id', None):
            score += 0.2

        # Valuable fields
        description = getattr(job, 'description', None)
        if description and len(description) > 100:
            score += 0.2
        if getattr(job, 'salary_min', None) or getattr(job, 'salary_max', None):
            score += 0.15
        apply_url = getattr(job, 'apply_url', None)
        if apply_url and 'example.com' not in str(apply_url):
            score += 0.1
        if getattr(job, 'skills', None):
            score += 0.1
        if getattr(job, 'benefits', None):
            score += 0.05

        return score

    def _calculate_freshness_score(self, posted_date) -> float:
        """Calculate freshness score based on posting date."""
        if not posted_date:
            return 0.5

        try:
            if isinstance(posted_date, str):
                posted_date = datetime.fromisoformat(posted_date.replace('Z', '+00:00'))

            days_old = (datetime.utcnow() - posted_date).days

            if days_old <= 1:
                return 1.0
            elif days_old <= 3:
                return 0.9
            elif days_old <= 7:
                return 0.7
            elif days_old <= 14:
                return 0.5
            elif days_old <= 30:
                return 0.3
            else:
                return 0.1
        except Exception:
            return 0.5

    def _get_source_priority_score(self, source_id: int) -> float:
        """Get normalized score based on source priority."""
        source_priorities = self.config.get('source_priorities', {})
        priority = source_priorities.get(source_id, 999)

        # Normalize to 0-1 scale (lower priority number = higher score)
        max_priority = max(source_priorities.values()) if source_priorities else 999
        return 1.0 - (priority / max_priority) if max_priority > 0 else 0.0

    async def _generate_group_hash(self, job_ids: List[int]) -> str:
        """Generate unique hash for the group."""
        # Sort job IDs for consistent hash
        sorted_ids = sorted(job_ids)
        content = '|'.join(map(str, sorted_ids))

        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]

    async def _calculate_group_quality(self, job_ids: List[int],
                                     similarity_scores: Dict[int, float]) -> float:
        """Calculate overall quality score for the group."""
        if not similarity_scores:
            return 0.5

        # Average similarity score
        avg_similarity = sum(similarity_scores.values()) / len(similarity_scores)

        # Job quality factor
        jobs = await self.job_repository.get_jobs_by_ids(job_ids)
        job_qualities = [getattr(job, 'quality_score', 0.5) for job in jobs]
        avg_job_quality = sum(job_qualities) / len(job_qualities) if job_qualities else 0.5

        # Combined score
        return (avg_similarity * 0.6) + (avg_job_quality * 0.4)

    async def _create_group_mappings(self, group_id: int, job_ids: List[int],
                                   primary_job_id: int, similarity_scores: Dict[int, float]) -> bool:
        """Create mappings for all jobs in the group."""
        try:
            for job_id in job_ids:
                mapping_data = {
                    'job_id': job_id,
                    'group_id': group_id,
                    'similarity_score': similarity_scores.get(job_id, 0.0),
                    'detection_method': 'group_creation',
                    'is_primary': job_id == primary_job_id,
                    'metadata': {
                        'created_at': datetime.utcnow().isoformat(),
                        'initial_group': True
                    }
                }

                mapping_id = await self.group_repository.create_mapping(mapping_data)
                if not mapping_id:
                    logger.error(f"Failed to create mapping for job {job_id}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Error creating group mappings: {e}")
            return False

    async def _merge_group_information(self, group_id: int, primary_job_id: int,
                                     all_job_ids: List[int]) -> bool:
        """Merge information from all jobs into the primary job."""
        try:
            # Get all jobs
            jobs = await self.job_repository.get_jobs_by_ids(all_job_ids)
            primary_job = next((job for job in jobs if job.id == primary_job_id), None)
            secondary_jobs = [job for job in jobs if job.id != primary_job_id]

            if not primary_job:
                return False

            merge_updates = {}

            # Merge information from each secondary job
            for secondary_job in secondary_jobs:
                updates = await self._merge_job_fields(primary_job, secondary_job)
                merge_updates.update(updates)

            # Apply updates if any
            if merge_updates:
                await self.job_repository.update_job(primary_job_id, merge_updates)

            # Update group metadata
            group_metadata = {
                'source_count': len(set(getattr(job, 'source_id', 0) for job in jobs)),
                'total_jobs': len(all_job_ids),
                'last_merge': datetime.utcnow().isoformat()
            }

            merge_updates['group_metadata'] = group_metadata

            return True

        except Exception as e:
            logger.error(f"Error merging group information: {e}")
            return False

    async def _merge_job_fields(self, primary_job, secondary_job) -> Dict:
        """Merge fields from secondary job into primary job."""
        merge_updates = {}

        # Basic field merging logic
        # Prefer more complete information
        if not getattr(primary_job, 'description', None) and getattr(secondary_job, 'description', None):
            merge_updates['description'] = secondary_job.description

        # Prefer disclosed salary over undisclosed
        primary_salary = getattr(primary_job, 'salary_min', None) or getattr(primary_job, 'salary_max', None)
        secondary_salary = getattr(secondary_job, 'salary_min', None) or getattr(secondary_job, 'salary_max', None)

        if not primary_salary and secondary_salary:
            if getattr(secondary_job, 'salary_min', None):
                merge_updates['salary_min'] = secondary_job.salary_min
            if getattr(secondary_job, 'salary_max', None):
                merge_updates['salary_max'] = secondary_job.salary_max

        return merge_updates

    async def _reassess_primary_job(self, group_id: int) -> bool:
        """Reassess and update the primary job for a group."""
        try:
            # Get all mappings
            mappings = await self.group_repository.get_group_mappings(group_id)
            job_ids = [m.job_id for m in mappings]

            # Calculate similarity scores
            similarity_scores = {m.job_id: float(m.similarity_score) for m in mappings}

            # Select new primary
            new_primary_id = await self._select_primary_job(job_ids, similarity_scores)

            if not new_primary_id:
                return False

            # Update mappings
            for mapping in mappings:
                is_primary = mapping.job_id == new_primary_id
                await self.group_repository.update_mapping(mapping.id, {
                    'is_primary': is_primary
                })

            # Update group
            await self.group_repository.update_group(group_id, {
                'primary_job_id': new_primary_id,
                'updated_at': datetime.utcnow()
            })

            return True

        except Exception as e:
            logger.error(f"Error reassessing primary job: {e}")
            return False

    async def _dissolve_group(self, group_id: int) -> bool:
        """Dissolve a group when it has too few members."""
        try:
            # Delete all mappings
            await self.group_repository.delete_group_mappings(group_id)

            # Delete group
            await self.group_repository.delete_group(group_id)

            logger.info(f"Dissolved group {group_id}")
            return True

        except Exception as e:
            logger.error(f"Error dissolving group: {e}")
            return False

    def _job_to_dict(self, job) -> dict:
        """Convert job object to dictionary."""
        return {
            'title': getattr(job, 'title', ''),
            'company_name': getattr(job, 'company_name', ''),
            'location': getattr(job, 'location', None),
            'salary': getattr(job, 'salary', None),
            'posted_date': getattr(job, 'posted_date', None),
            'description': getattr(job, 'description', ''),
            'source_id': getattr(job, 'source_id', None)
        }