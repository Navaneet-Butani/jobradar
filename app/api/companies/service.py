"""Company profile business logic."""

import logging
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.exceptions import NotFoundError
from ...models import CompanyDB, JobDB, JobSourceDB
from .schema import CompanyJobResponse, CompanyResponse

logger = logging.getLogger(__name__)

MAX_JOBS = 50


class CompaniesService:
    async def get_company(
        self, company_id: int, session: AsyncSession, job_limit: int = MAX_JOBS
    ) -> CompanyResponse:
        company = (
            await session.execute(select(CompanyDB).where(CompanyDB.id == company_id))
        ).scalar_one_or_none()
        if company is None:
            raise NotFoundError("Company not found")

        rows = (await session.execute(
            select(JobDB, JobSourceDB.name)
            .outerjoin(JobSourceDB, JobSourceDB.id == JobDB.source_id)
            .where(JobDB.company_id == company_id, JobDB.status == "active")
            .order_by(JobDB.posted_date.desc().nullslast(), JobDB.first_seen_at.desc())
            .limit(job_limit)
        )).all()

        active_jobs = (await session.execute(
            select(func.count())
            .select_from(JobDB)
            .where(JobDB.company_id == company_id, JobDB.status == "active")
        )).scalar_one()

        jobs = [
            CompanyJobResponse(
                id=job.id,
                title=job.title,
                city=job.city,
                is_remote=job.is_remote,
                remote_scope=job.remote_scope,
                min_exp_years=job.min_exp_years,
                max_exp_years=job.max_exp_years,
                salary_min=float(job.salary_min) if job.salary_min is not None else None,
                salary_max=float(job.salary_max) if job.salary_max is not None else None,
                salary_currency=job.salary_currency,
                salary_disclosed=job.salary_disclosed,
                posted_date=job.posted_date,
                first_seen_at=job.first_seen_at,
                source_name=source_name,
                apply_url=job.apply_url,
                poster_name=job.poster_name,
                source_applicant_count=job.source_applicant_count,
            )
            for job, source_name in rows
        ]

        return CompanyResponse(
            id=company.id,
            name=company.name,
            slug=company.slug,
            website=company.website,
            career_page_url=company.career_page_url,
            logo_url=company.logo_url,
            tagline=company.tagline,
            description=company.description,
            industry=company.industry,
            headquarters=company.headquarters,
            founded_year=company.founded_year,
            employee_count=company.employee_count,
            employee_range=company.employee_range,
            rating=float(company.rating) if company.rating is not None else None,
            rating_count=company.rating_count,
            rating_url=company.rating_url,
            rating_source=company.rating_source,
            ats_type=company.ats_type,
            contact_email=company.contact_email,
            active_jobs=active_jobs,
            # Which boards this employer's postings reached us through. Useful
            # context: a company that only ever appears via one aggregator is a
            # different proposition from one posting on its own ATS.
            sources=sorted({name for _, name in rows if name}),
            jobs=jobs,
        )
