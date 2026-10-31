"""Company repository for database operations."""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, text
from sqlalchemy.orm import selectinload

from .base import BaseRepository, CacheableRepositoryMixin
from ..models import CompanyDB, CompanySizeDB
from ..models.company import CompanySearchCriteria, CompanyMatch
from ..core.database import db
from ..core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class CompanyRepository(BaseRepository[CompanyDB], CacheableRepositoryMixin):
    """Repository for company-related database operations."""
    
    def __init__(self):
        super().__init__(CompanyDB)
        CacheableRepositoryMixin.__init__(self, cache_ttl=1800)  # 30 minutes
        
    async def get_by_name(
        self, 
        name: str, 
        session: Optional[AsyncSession] = None
    ) -> Optional[CompanyDB]:
        """Get company by exact name match."""
        if session is None:
            session = db.session
            
        # Check cache first
        cache_key = self._get_cache_key("company_name", name.lower())
        cached_company = await self._get_from_cache(cache_key)
        if cached_company:
            return cached_company
            
        try:
            result = await session.execute(
                select(CompanyDB)
                .where(func.lower(CompanyDB.name) == name.lower())
                .options(selectinload(CompanyDB.size))
            )
            company = result.scalar_one_or_none()
            
            if company:
                await self._set_cache(cache_key, company)
                
            return company
        except Exception as e:
            logger.error(f"Error fetching company by name {name}: {e}")
            raise
            
    async def get_by_slug(
        self, 
        slug: str, 
        session: Optional[AsyncSession] = None
    ) -> Optional[CompanyDB]:
        """Get company by slug."""
        if session is None:
            session = db.session
            
        cache_key = self._get_cache_key("company_slug", slug)
        cached_company = await self._get_from_cache(cache_key)
        if cached_company:
            return cached_company
            
        try:
            result = await session.execute(
                select(CompanyDB)
                .where(CompanyDB.slug == slug)
                .options(selectinload(CompanyDB.size))
            )
            company = result.scalar_one_or_none()
            
            if company:
                await self._set_cache(cache_key, company)
                
            return company
        except Exception as e:
            logger.error(f"Error fetching company by slug {slug}: {e}")
            raise
            
    async def search_by_name(
        self, 
        name: str, 
        limit: int = 10,
        session: Optional[AsyncSession] = None
    ) -> List[CompanyMatch]:
        """Search companies by name with fuzzy matching."""
        if session is None:
            session = db.session
            
        try:
            # First try exact matches
            exact_matches = await session.execute(
                select(CompanyDB)
                .where(func.lower(CompanyDB.name) == name.lower())
                .options(selectinload(CompanyDB.size))
                .limit(limit)
            )
            
            matches = []
            for company in exact_matches.scalars().all():
                matches.append(CompanyMatch(
                    company_id=company.id,
                    confidence_score=1.0,
                    match_type="exact",
                    matched_name=company.name
                ))
                
            # If we don't have enough exact matches, try fuzzy matching
            if len(matches) < limit:
                remaining_limit = limit - len(matches)
                fuzzy_matches = await session.execute(
                    text("""
                    SELECT id, name, similarity(name, :search_name) as sim_score
                    FROM companies 
                    WHERE similarity(name, :search_name) > 0.3
                    AND lower(name) != lower(:search_name)
                    ORDER BY sim_score DESC
                    LIMIT :limit
                    """).bindparams(
                        search_name=name,
                        limit=remaining_limit
                    )
                )
                
                for row in fuzzy_matches.all():
                    matches.append(CompanyMatch(
                        company_id=row.id,
                        confidence_score=float(row.sim_score),
                        match_type="fuzzy",
                        matched_name=row.name
                    ))
                    
            return matches
        except Exception as e:
            logger.error(f"Error searching companies by name {name}: {e}")
            raise
            
    async def find_by_normalized_name(
        self, 
        normalized_name: str, 
        session: Optional[AsyncSession] = None
    ) -> List[CompanyDB]:
        """Find companies by normalized name patterns."""
        if session is None:
            session = db.session
            
        try:
            # Create variations of the normalized name
            name_variations = [
                normalized_name,
                normalized_name.replace(" ", ""),
                normalized_name.replace("-", " "),
                normalized_name.replace("_", " ")
            ]
            
            # Search for companies with similar patterns
            conditions = []
            for variation in name_variations:
                conditions.extend([
                    func.lower(CompanyDB.name).contains(variation.lower()),
                    func.similarity(func.lower(CompanyDB.name), variation.lower()) > 0.6
                ])
                
            result = await session.execute(
                select(CompanyDB)
                .where(or_(*conditions))
                .options(selectinload(CompanyDB.size))
                .order_by(desc(CompanyDB.data_quality_score))
                .limit(20)
            )
            
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error finding companies by normalized name {normalized_name}: {e}")
            raise
            
    async def create_with_slug(
        self, 
        company_data: Dict[str, Any], 
        session: Optional[AsyncSession] = None
    ) -> CompanyDB:
        """Create company with auto-generated slug."""
        if session is None:
            session = db.session
            
        try:
            # Generate slug from name
            base_slug = self._generate_slug(company_data['name'])
            slug = base_slug
            counter = 1
            
            # Ensure slug uniqueness
            while await self.get_by_slug(slug, session):
                slug = f"{base_slug}-{counter}"
                counter += 1
                
            company_data['slug'] = slug
            # normalized_name is a CompanyCreate/matching-logic concept, not a CompanyDB column.
            company_data.pop('normalized_name', None)
            try:
                company = await self.create(company_data, session)
            except ValidationError:
                # Concurrent insert of the same company (same slug) — the other
                # request won the race, so fetch what it created instead of failing.
                existing = await self.get_by_name(company_data['name'], session)
                if existing:
                    return existing
                raise

            # Invalidate cache
            await self._invalidate_cache("company_*")

            return company
        except Exception as e:
            logger.error(f"Error creating company with slug: {e}")
            raise
            
    def _generate_slug(self, name: str) -> str:
        """Generate URL-friendly slug from company name."""
        import re
        
        # Convert to lowercase and replace spaces with hyphens
        slug = name.lower().strip()
        slug = re.sub(r'[^\w\s-]', '', slug)  # Remove special characters
        slug = re.sub(r'[-\s]+', '-', slug)   # Replace spaces and multiple hyphens
        slug = slug.strip('-')                # Remove leading/trailing hyphens
        
        return slug[:100]  # Limit length
        
    async def search_companies(
        self, 
        criteria: CompanySearchCriteria, 
        offset: int = 0,
        limit: int = 50,
        session: Optional[AsyncSession] = None
    ) -> Tuple[List[CompanyDB], int]:
        """Search companies with advanced filtering."""
        if session is None:
            session = db.session
            
        try:
            # Build base query
            query = select(CompanyDB).options(selectinload(CompanyDB.size))
            
            # Apply filters
            filters = []
            
            # Name search
            if criteria.name:
                search_term = f"%{criteria.name.lower()}%"
                filters.append(func.lower(CompanyDB.name).contains(search_term))
                
            # Industry filter
            if criteria.industry:
                filters.append(func.lower(CompanyDB.industry) == criteria.industry.lower())
                
            # Size filter
            if criteria.size:
                query = query.join(CompanySizeDB, CompanyDB.size_id == CompanySizeDB.id)
                filters.append(CompanySizeDB.name == criteria.size.value)
                
            # Location filter
            if criteria.location:
                location_term = f"%{criteria.location.lower()}%"
                filters.append(func.lower(CompanyDB.headquarters).contains(location_term))
                
            # Employee count filters
            if criteria.min_employees is not None:
                filters.append(CompanyDB.employee_count >= criteria.min_employees)
                
            if criteria.max_employees is not None:
                filters.append(CompanyDB.employee_count <= criteria.max_employees)
                
            # Active jobs filter
            if criteria.has_jobs:
                filters.append(CompanyDB.active_jobs_count > 0)
                
            # Quality filter
            if criteria.min_quality_score is not None:
                filters.append(CompanyDB.data_quality_score >= criteria.min_quality_score)
                
            # Apply all filters
            if filters:
                query = query.where(and_(*filters))
                
            # Get total count
            count_query = select(func.count()).select_from(query.subquery())
            total_count = await session.execute(count_query)
            total = total_count.scalar()
            
            # Apply ordering and pagination
            query = query.order_by(
                desc(CompanyDB.active_jobs_count),
                desc(CompanyDB.data_quality_score)
            ).offset(offset).limit(limit)
            
            # Execute query
            result = await session.execute(query)
            companies = list(result.scalars().all())
            
            return companies, total
        except Exception as e:
            logger.error(f"Error searching companies: {e}")
            raise
            
    async def update_job_counts(
        self, 
        company_id: int, 
        session: Optional[AsyncSession] = None
    ) -> bool:
        """Update job counts for a company."""
        if session is None:
            session = db.session
            
        try:
            # Update active jobs count and total jobs posted
            await session.execute(
                text("""
                UPDATE companies 
                SET 
                    active_jobs_count = (
                        SELECT COUNT(*) FROM jobs 
                        WHERE company_id = :company_id AND status = 'active'
                    ),
                    total_jobs_posted = (
                        SELECT COUNT(*) FROM jobs 
                        WHERE company_id = :company_id
                    ),
                    last_job_posted_at = (
                        SELECT MAX(posted_date) FROM jobs 
                        WHERE company_id = :company_id
                    ),
                    updated_at = NOW()
                WHERE id = :company_id
                """).bindparams(company_id=company_id)
            )
            await session.commit()
            
            # Invalidate cache
            await self._invalidate_cache(f"company_*")
            
            return True
        except Exception as e:
            await session.rollback()
            logger.error(f"Error updating job counts for company {company_id}: {e}")
            raise
            
    async def get_ats_enabled_companies(
        self,
        session: Optional[AsyncSession] = None
    ) -> List[CompanyDB]:
        """Get companies with a known, active ATS board to poll."""
        if session is None:
            session = db.session

        try:
            result = await session.execute(
                select(CompanyDB).where(
                    and_(
                        CompanyDB.ats_type.isnot(None),
                        CompanyDB.ats_slug.isnot(None),
                        CompanyDB.ats_is_active.is_(True),
                    )
                )
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error fetching ATS-enabled companies: {e}")
            raise

    async def get_companies_without_ats_discovery(
        self,
        limit: int = 50,
        cooldown_days: int = 30,
        session: Optional[AsyncSession] = None
    ) -> List[CompanyDB]:
        """Get companies never probed for an ATS board, or not probed in `cooldown_days`.

        Discovery must not become a crawler (docs/sources.md) —
        this is the query that enforces the 30-day re-probe cooldown.
        """
        if session is None:
            session = db.session

        try:
            cutoff = datetime.utcnow() - timedelta(days=cooldown_days)
            result = await session.execute(
                select(CompanyDB).where(
                    and_(
                        CompanyDB.ats_type.is_(None),
                        or_(
                            CompanyDB.ats_discovery_attempted_at.is_(None),
                            CompanyDB.ats_discovery_attempted_at < cutoff,
                        ),
                    )
                ).limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error fetching companies without ATS discovery: {e}")
            raise

    async def get_top_companies(
        self,
        limit: int = 20,
        by_jobs: bool = True,
        session: Optional[AsyncSession] = None
    ) -> List[CompanyDB]:
        """Get top companies by job count or other metrics."""
        if session is None:
            session = db.session
            
        cache_key = self._get_cache_key("top_companies", limit, by_jobs)
        cached_companies = await self._get_from_cache(cache_key)
        if cached_companies:
            return cached_companies
            
        try:
            query = select(CompanyDB).options(selectinload(CompanyDB.size))
            
            if by_jobs:
                query = query.where(CompanyDB.active_jobs_count > 0).order_by(
                    desc(CompanyDB.active_jobs_count),
                    desc(CompanyDB.data_quality_score)
                )
            else:
                query = query.order_by(
                    desc(CompanyDB.data_quality_score),
                    desc(CompanyDB.total_jobs_posted)
                )
                
            query = query.limit(limit)
            
            result = await session.execute(query)
            companies = list(result.scalars().all())
            
            # Cache results for 1 hour
            await self._set_cache(cache_key, companies, ttl=3600)
            
            return companies
        except Exception as e:
            logger.error(f"Error fetching top companies: {e}")
            raise
            
    async def get_companies_by_industry(
        self, 
        industry: str, 
        limit: int = 50,
        session: Optional[AsyncSession] = None
    ) -> List[CompanyDB]:
        """Get companies in a specific industry."""
        if session is None:
            session = db.session
            
        cache_key = self._get_cache_key("industry_companies", industry, limit)
        cached_companies = await self._get_from_cache(cache_key)
        if cached_companies:
            return cached_companies
            
        try:
            result = await session.execute(
                select(CompanyDB)
                .where(func.lower(CompanyDB.industry) == industry.lower())
                .options(selectinload(CompanyDB.size))
                .order_by(
                    desc(CompanyDB.active_jobs_count),
                    desc(CompanyDB.data_quality_score)
                )
                .limit(limit)
            )
            
            companies = list(result.scalars().all())
            
            # Cache for 2 hours
            await self._set_cache(cache_key, companies, ttl=7200)
            
            return companies
        except Exception as e:
            logger.error(f"Error fetching companies by industry {industry}: {e}")
            raise
            
    async def get_company_statistics(
        self, 
        company_id: int, 
        session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """Get detailed statistics for a company."""
        if session is None:
            session = db.session
            
        try:
            # Get basic company info with job stats
            result = await session.execute(
                text("""
                SELECT 
                    c.*,
                    COUNT(j.id) as total_jobs,
                    COUNT(CASE WHEN j.status = 'active' THEN 1 END) as active_jobs,
                    AVG(j.quality_score) as avg_quality_score,
                    MIN(j.salary_min) as min_salary_offered,
                    MAX(j.salary_max) as max_salary_offered,
                    COUNT(DISTINCT j.city) as cities_count,
                    COUNT(CASE WHEN j.is_remote = true THEN 1 END) as remote_jobs
                FROM companies c
                LEFT JOIN jobs j ON c.id = j.company_id
                WHERE c.id = :company_id
                GROUP BY c.id
                """).bindparams(company_id=company_id)
            )
            
            row = result.first()
            if not row:
                return {}
                
            # Get top skills for this company's jobs
            skills_result = await session.execute(
                text("""
                SELECT skill, COUNT(*) as count
                FROM (
                    SELECT jsonb_array_elements_text(skills_extracted) as skill
                    FROM jobs 
                    WHERE company_id = :company_id AND status = 'active'
                    UNION ALL
                    SELECT jsonb_path_query_array(skills_required, '$[*].name')::text as skill
                    FROM jobs 
                    WHERE company_id = :company_id AND status = 'active'
                ) skills
                WHERE skill IS NOT NULL AND skill != 'null'
                GROUP BY skill
                ORDER BY count DESC
                LIMIT 10
                """).bindparams(company_id=company_id)
            )
            
            top_skills = [{"skill": row.skill, "count": row.count} for row in skills_result.all()]
            
            statistics = {
                "company_id": company_id,
                "total_jobs_posted": row.total_jobs or 0,
                "active_jobs_count": row.active_jobs or 0,
                "avg_quality_score": float(row.avg_quality_score) if row.avg_quality_score else 0,
                "salary_range": {
                    "min": float(row.min_salary_offered) if row.min_salary_offered else None,
                    "max": float(row.max_salary_offered) if row.max_salary_offered else None
                },
                "geographic_reach": {
                    "cities_count": row.cities_count or 0,
                    "remote_jobs": row.remote_jobs or 0
                },
                "top_skills": top_skills
            }
            
            return statistics
        except Exception as e:
            logger.error(f"Error fetching company statistics for {company_id}: {e}")
            raise
            
    async def batch_update_quality_scores(
        self, 
        score_updates: List[Dict[str, Any]], 
        session: Optional[AsyncSession] = None
    ) -> int:
        """Update data quality scores for multiple companies."""
        if session is None:
            session = db.session
            
        try:
            updated_count = 0
            for update in score_updates:
                if 'company_id' not in update or 'quality_score' not in update:
                    continue
                    
                await session.execute(
                    text("""
                    UPDATE companies 
                    SET data_quality_score = :quality_score,
                        updated_at = NOW()
                    WHERE id = :company_id
                    """).bindparams(
                        company_id=update['company_id'],
                        quality_score=update['quality_score']
                    )
                )
                updated_count += 1
                
            await session.commit()
            
            # Invalidate cache
            await self._invalidate_cache("company_*")
            
            return updated_count
        except Exception as e:
            await session.rollback()
            logger.error(f"Error batch updating company quality scores: {e}")
            raise