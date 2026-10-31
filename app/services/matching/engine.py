"""Orchestration: filter -> score -> noise-adjust -> (optional) LLM re-rank -> persist."""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select, func, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload

from ...core.database import db
from ...models import JobDB, JobProfileDB, MatchDB
from .filters import passes_hard_filters
from .scoring import score_job
from .noise import apply_noise_adjustments
from .llm_rerank import rerank_top_matches

logger = logging.getLogger(__name__)

LLM_RERANK_TOP_N = 25
GHOST_JOB_WINDOW_DAYS = 7


def _job_to_dict(job: JobDB) -> dict:
    return {
        "id": job.id,
        "title": job.title,
        "normalized_title": job.normalized_title,
        "description": job.job_details.description if job.job_details else None,
        "company_name": job.company.name if job.company else None,
        "company_id": job.company_id,
        "city": job.city,
        "is_remote": job.is_remote,
        "remote_scope": job.remote_scope,
        "min_exp_years": job.min_exp_years,
        "max_exp_years": job.max_exp_years,
        "skills_extracted": job.skills_extracted or [],
        "salary_min": float(job.salary_min) if job.salary_min is not None else None,
        "salary_max": float(job.salary_max) if job.salary_max is not None else None,
        "salary_currency": job.salary_currency,
        "salary_period": job.salary_period,
        "salary_disclosed": job.salary_disclosed,
        "posted_date": job.posted_date,
        "first_seen_at": job.first_seen_at,
        "source_name": job.source.name if job.source else None,
        "apply_url": job.apply_url,
    }


def _profile_to_dict(profile: JobProfileDB, user_email: str) -> dict:
    return {
        "id": profile.id,
        "years_exp": float(profile.years_exp),
        "seniority_floor": profile.seniority_floor,
        "seniority_ceiling": profile.seniority_ceiling,
        "must_have_skills": profile.must_have_skills or [],
        "nice_to_have_skills": profile.nice_to_have_skills or [],
        "target_titles": profile.target_titles or [],
        "cities": profile.cities or [],
        "metro_cities": profile.metro_cities or [],
        "accepts_remote": profile.accepts_remote,
        "remote_only": profile.remote_only,
        "remote_scope": profile.remote_scope,
        "min_salary_inr": float(profile.min_salary_inr) if profile.min_salary_inr is not None else None,
        "exclude_companies": profile.exclude_companies or [],
        "exclude_keywords": profile.exclude_keywords or [],
        "include_staffing": profile.include_staffing,
        "domain_keywords": profile.domain_keywords or [],
        "no_cs_degree": profile.no_cs_degree,
        "user_email": user_email,
    }


async def _fetch_jobs(session, since: Optional[datetime]) -> List[JobDB]:
    query = select(JobDB).where(JobDB.status == "active").options(
        selectinload(JobDB.company),
        selectinload(JobDB.job_details),
        selectinload(JobDB.source),
    )
    if since is not None:
        query = query.where(JobDB.first_seen_at >= since)
    result = await session.execute(query)
    return list(result.scalars().all())


async def _fetch_repost_counts(session) -> Dict[tuple, int]:
    """(company_id, normalized_title) -> count of active postings first-seen
    in the trailing GHOST_JOB_WINDOW_DAYS days — a proxy for the "same job
    reposted weekly" ghost-job signal. Count includes the posting itself, so
    the engine subtracts 1 before treating it as a repost tally.
    """
    window_start = datetime.utcnow() - timedelta(days=GHOST_JOB_WINDOW_DAYS)
    result = await session.execute(
        select(JobDB.company_id, JobDB.normalized_title, func.count(JobDB.id))
        .where(
            JobDB.status == "active",
            JobDB.company_id.isnot(None),
            JobDB.normalized_title.isnot(None),
            JobDB.first_seen_at >= window_start,
        )
        .group_by(JobDB.company_id, JobDB.normalized_title)
    )
    return {(row[0], row[1]): row[2] for row in result.all()}


async def _persist_matches(session, job_profile_id: int, scored: List[dict]) -> None:
    if not scored:
        return
    rows = [
        {
            "job_profile_id": job_profile_id,
            "job_id": m["job"]["id"],
            "score": round(m["score"], 2),
            "reasons": m["breakdown"],
            "explanation": m.get("explanation"),
        }
        for m in scored
    ]
    stmt = pg_insert(MatchDB).values(rows)
    # Rescoring must never clobber state (new/seen/interested/applied/dismissed)
    # or surfaced_at — those belong to the user's interaction with the feed,
    # not to how fresh the score is.
    stmt = stmt.on_conflict_do_update(
        index_elements=["job_profile_id", "job_id"],
        set_={
            "score": stmt.excluded.score,
            "reasons": stmt.excluded.reasons,
            "explanation": stmt.excluded.explanation,
        },
    )
    await session.execute(stmt)


async def _prune_matches(session, job_profile_id: int, job_ids: List[int]) -> int:
    """Drop matches for jobs that no longer pass the hard filters.

    Without this, a job only ever leaves the feed by the user dismissing it —
    so when a job's data is corrected (Hirist stating 10-15 years on a job we
    had recorded as 5+), the stale match survives the rescore and keeps showing
    a job the filters would now reject. Only untouched rows are removed;
    anything the user has interested/applied/dismissed stays, because that is
    their history, not our scoring.
    """
    if not job_ids:
        return 0
    result = await session.execute(
        delete(MatchDB).where(
            MatchDB.job_profile_id == job_profile_id,
            MatchDB.job_id.in_(job_ids),
            MatchDB.state.in_(("new", "seen")),
        )
    )
    return result.rowcount or 0


async def run_matching(
    profile_ids: Optional[List[int]] = None,
    since: Optional[datetime] = None,
    llm_rerank: bool = True,
) -> Dict[int, dict]:
    """Score jobs against active profiles and persist matches.

    since=None means a full rescore (only run this after a profile edit —
    see REFERENCE 3.5). Otherwise only jobs first-seen on/after `since` are
    considered, for the normal post-ingest incremental run.
    """
    stats: Dict[int, dict] = {}

    async with db.get_session() as session:
        profile_query = select(JobProfileDB).where(JobProfileDB.is_active.is_(True)).options(
            selectinload(JobProfileDB.user)
        )
        if profile_ids:
            profile_query = profile_query.where(JobProfileDB.id.in_(profile_ids))
        profiles = list((await session.execute(profile_query)).scalars().all())

        if not profiles:
            logger.info("No active profiles to match against")
            return stats

        jobs = await _fetch_jobs(session, since)
        job_dicts = [_job_to_dict(j) for j in jobs]
        repost_counts = await _fetch_repost_counts(session)
        logger.info(f"Matching {len(job_dicts)} jobs against {len(profiles)} profile(s)")

        for profile_orm in profiles:
            profile = _profile_to_dict(profile_orm, profile_orm.user.email)
            scored = []
            rejected_ids: List[int] = []
            dropped = 0

            for job in job_dicts:
                passed, _reason = passes_hard_filters(job, profile)
                if not passed:
                    dropped += 1
                    rejected_ids.append(job["id"])
                    continue

                result = score_job(job, profile)
                repost_key = (job["company_id"], job["normalized_title"])
                repost_count = max(0, repost_counts.get(repost_key, 1) - 1)
                adjusted, noise_factors = apply_noise_adjustments(
                    result["total"], job, profile, repost_count
                )
                breakdown = {**result["breakdown"], **noise_factors}
                scored.append({"job": job, "score": adjusted, "breakdown": breakdown, "explanation": None})

            scored.sort(key=lambda m: m["score"], reverse=True)

            if llm_rerank:
                scored = await rerank_top_matches(scored, profile, top_n=LLM_RERANK_TOP_N)
                scored.sort(key=lambda m: m["score"], reverse=True)

            await _persist_matches(session, profile["id"], scored)
            pruned = await _prune_matches(session, profile["id"], rejected_ids)

            stats[profile["id"]] = {
                "jobs_considered": len(job_dicts),
                "matched": len(scored),
                "dropped": dropped,
                "pruned": pruned,
            }
            logger.info(
                f"Profile {profile['id']}: {len(scored)} matched, {dropped} dropped "
                f"of {len(job_dicts)} considered, {pruned} stale match(es) removed"
            )

        await session.commit()

    return stats
