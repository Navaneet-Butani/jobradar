"""Advanced query builder for job search with PostgreSQL full-text search."""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime, timedelta
from sqlalchemy import text, and_, or_, func, desc, asc
from sqlalchemy.sql import Select
from sqlalchemy.orm import selectinload

from ...models import JobDB, JobDetailDB, CompanyDB, EmploymentTypeDB, ExperienceLevelDB
from ...models.job import JobSearchCriteria
from ...models.common import EmploymentType, ExperienceLevel, Currency

logger = logging.getLogger(__name__)


class SearchQueryBuilder:
    """Advanced query builder for job search with full-text search and security."""

    def __init__(self):
        self.conditions = []
        self.params = {}
        self.joins = set()
        self.order_clauses = []
        self.param_counter = 0

    def _get_param_name(self, prefix: str = "param") -> str:
        """Generate unique parameter name."""
        self.param_counter += 1
        return f"{prefix}_{self.param_counter}"

    def add_text_search(self, query: str, weight_factor: float = 1.0) -> "SearchQueryBuilder":
        """
        Add PostgreSQL full-text search with proper relevance ranking.

        Args:
            query: Search query string
            weight_factor: Factor to adjust text search importance
        """
        if not query or not query.strip():
            return self

        # Clean and prepare the search query
        cleaned_query = query.strip().replace("'", "''")  # Escape single quotes

        # Create parameters for the query
        query_param = self._get_param_name("search_query")
        self.params[query_param] = cleaned_query

        # Build full-text search condition with ranking
        # Search in both main job fields and job details
        fts_condition = text(f"""
            (
                j.search_vector @@ plainto_tsquery('job_search', :{query_param})
                OR jd.details_search_vector @@ plainto_tsquery('job_search', :{query_param})
            )
        """)

        self.conditions.append(fts_condition)

        # Add job_details join if not already added
        self.joins.add("job_details")

        # Add relevance scoring for ordering
        relevance_score = text(f"""
            (
                COALESCE(
                    ts_rank(j.search_vector, plainto_tsquery('job_search', :{query_param})), 0
                ) +
                COALESCE(
                    ts_rank(jd.details_search_vector, plainto_tsquery('job_search', :{query_param})) * 0.5, 0
                )
            ) * {weight_factor}
        """)

        # Store for later use in ordering
        self._text_relevance_score = relevance_score

        return self

    def add_location_filter(self, location: str) -> "SearchQueryBuilder":
        """
        Add location filter with multiple matching strategies.

        Args:
            location: Location search term
        """
        if not location or not location.strip():
            return self

        location_param = self._get_param_name("location")
        self.params[location_param] = f"%{location.strip().lower()}%"

        # Handle "Remote" keyword specially
        if "remote" in location.lower():
            remote_condition = text("j.is_remote = true")
            location_condition = or_(
                text(f"LOWER(j.location_raw) LIKE :{location_param}"),
                text(f"LOWER(j.city) LIKE :{location_param}"),
                text(f"LOWER(j.country) LIKE :{location_param}"),
                remote_condition
            )
        else:
            location_condition = or_(
                text(f"LOWER(j.city) LIKE :{location_param}"),
                text(f"LOWER(j.state_province) LIKE :{location_param}"),
                text(f"LOWER(j.country) LIKE :{location_param}"),
                text(f"LOWER(j.location_raw) LIKE :{location_param}")
            )

        self.conditions.append(location_condition)
        return self

    def add_company_filter(self, company: str) -> "SearchQueryBuilder":
        """
        Add company filter with exact and fuzzy matching.

        Args:
            company: Company name to search for
        """
        if not company or not company.strip():
            return self

        company_param = self._get_param_name("company")
        self.params[company_param] = f"%{company.strip().lower()}%"

        # Join with companies table if not already joined
        self.joins.add("company")

        # Use both exact and fuzzy matching
        company_condition = text(f"LOWER(c.name) LIKE :{company_param}")
        self.conditions.append(company_condition)

        return self

    def add_salary_filter(
        self,
        min_salary: Optional[float] = None,
        max_salary: Optional[float] = None,
        currency: Optional[Currency] = None
    ) -> "SearchQueryBuilder":
        """
        Add salary range filter with proper NULL handling.

        Args:
            min_salary: Minimum salary requirement
            max_salary: Maximum salary limit
            currency: Salary currency filter
        """
        salary_conditions = []

        if min_salary is not None:
            min_param = self._get_param_name("min_salary")
            self.params[min_param] = min_salary

            # Include jobs where either min or max salary meets the requirement
            salary_conditions.append(or_(
                text(f"j.salary_min >= :{min_param}"),
                text(f"j.salary_max >= :{min_param}")
            ))

        if max_salary is not None:
            max_param = self._get_param_name("max_salary")
            self.params[max_param] = max_salary

            # Only include jobs where salary range is within limit
            salary_conditions.append(and_(
                text(f"j.salary_min <= :{max_param}"),
                text(f"j.salary_max <= :{max_param}")
            ))

        if currency:
            currency_param = self._get_param_name("currency")
            self.params[currency_param] = currency.value
            salary_conditions.append(text(f"j.salary_currency = :{currency_param}"))

        if salary_conditions:
            self.conditions.extend(salary_conditions)

        return self

    def add_employment_type_filter(self, employment_types: List[EmploymentType]) -> "SearchQueryBuilder":
        """Add employment type filter."""
        if not employment_types:
            return self

        # Map enum values to database IDs (this would need actual mapping)
        type_mapping = {
            EmploymentType.FULL_TIME: 1,
            EmploymentType.PART_TIME: 2,
            EmploymentType.CONTRACT: 3,
            EmploymentType.FREELANCE: 4,
            EmploymentType.INTERNSHIP: 5
        }

        type_ids = [type_mapping.get(et) for et in employment_types if et in type_mapping]

        if type_ids:
            types_param = self._get_param_name("employment_types")
            self.params[types_param] = tuple(type_ids)
            self.conditions.append(text(f"j.employment_type_id = ANY(:{types_param})"))

        return self

    def add_experience_level_filter(self, experience_levels: List[ExperienceLevel]) -> "SearchQueryBuilder":
        """Add experience level filter."""
        if not experience_levels:
            return self

        # Map enum values to database IDs
        level_mapping = {
            ExperienceLevel.ENTRY: 1,
            ExperienceLevel.JUNIOR: 2,
            ExperienceLevel.MID: 3,
            ExperienceLevel.SENIOR: 4,
            ExperienceLevel.LEAD: 5,
            ExperienceLevel.EXECUTIVE: 6
        }

        level_ids = [level_mapping.get(el) for el in experience_levels if el in level_mapping]

        if level_ids:
            levels_param = self._get_param_name("experience_levels")
            self.params[levels_param] = tuple(level_ids)
            self.conditions.append(text(f"j.experience_level_id = ANY(:{levels_param})"))

        return self

    def add_remote_filter(self, is_remote: bool) -> "SearchQueryBuilder":
        """Add remote work filter."""
        remote_param = self._get_param_name("is_remote")
        self.params[remote_param] = is_remote
        self.conditions.append(text(f"j.is_remote = :{remote_param}"))
        return self

    def add_skills_filter(
        self,
        required_skills: Optional[List[str]] = None,
        preferred_skills: Optional[List[str]] = None
    ) -> "SearchQueryBuilder":
        """
        Add skills filter using JSONB operations.

        Args:
            required_skills: All of these skills must be present
            preferred_skills: At least one of these skills should be present
        """
        if required_skills:
            for i, skill in enumerate(required_skills):
                skill_param = self._get_param_name(f"req_skill")
                self.params[skill_param] = skill

                # Check if skill exists in either required or extracted skills
                skill_condition = or_(
                    text(f"j.skills_required @> :[{skill_param}]"),
                    text(f"j.skills_extracted @> :[{skill_param}]")
                )
                self.conditions.append(skill_condition)

        if preferred_skills:
            pref_conditions = []
            for skill in preferred_skills:
                skill_param = self._get_param_name(f"pref_skill")
                self.params[skill_param] = skill

                pref_conditions.append(or_(
                    text(f"j.skills_preferred @> :[{skill_param}]"),
                    text(f"j.skills_extracted @> :[{skill_param}]")
                ))

            if pref_conditions:
                # At least one preferred skill should match
                self.conditions.append(or_(*pref_conditions))

        return self

    def add_date_filter(
        self,
        posted_after: Optional[datetime] = None,
        posted_before: Optional[datetime] = None
    ) -> "SearchQueryBuilder":
        """Add date range filter."""
        if posted_after:
            after_param = self._get_param_name("posted_after")
            self.params[after_param] = posted_after
            self.conditions.append(text(f"j.posted_date >= :{after_param}"))

        if posted_before:
            before_param = self._get_param_name("posted_before")
            self.params[before_param] = posted_before
            self.conditions.append(text(f"j.posted_date <= :{before_param}"))

        return self

    def add_quality_filter(
        self,
        min_quality_score: Optional[float] = None,
        exclude_spam: bool = True
    ) -> "SearchQueryBuilder":
        """Add quality and spam filters."""
        if min_quality_score is not None:
            quality_param = self._get_param_name("min_quality")
            self.params[quality_param] = min_quality_score
            self.conditions.append(text(f"j.quality_score >= :{quality_param}"))

        if exclude_spam:
            spam_param = self._get_param_name("spam_threshold")
            self.params[spam_param] = 70.0  # Configurable spam threshold
            self.conditions.append(text(f"j.spam_score < :{spam_param}"))

        return self

    def add_sorting(self, sort_by: str, sort_order: str = "desc") -> "SearchQueryBuilder":
        """
        Add sorting with support for relevance, date, salary, and quality.

        Args:
            sort_by: Field to sort by (relevance, posted_date, salary, quality)
            sort_order: Sort direction (asc, desc)
        """
        order_func = desc if sort_order.lower() == "desc" else asc

        if sort_by == "relevance" and hasattr(self, '_text_relevance_score'):
            # Use text relevance score combined with other factors
            relevance_formula = text(f"""
                calculate_job_relevance(
                    {self._text_relevance_score},
                    j.quality_score,
                    j.posted_date,
                    j.salary_disclosed
                )
            """)
            self.order_clauses.append(order_func(relevance_formula))

        elif sort_by == "posted_date":
            self.order_clauses.append(order_func(text("j.posted_date")))

        elif sort_by == "salary":
            # Sort by max salary, handle NULLs last
            if sort_order.lower() == "desc":
                self.order_clauses.append(text("j.salary_max DESC NULLS LAST"))
            else:
                self.order_clauses.append(text("j.salary_max ASC NULLS LAST"))

        elif sort_by == "quality":
            self.order_clauses.append(order_func(text("j.quality_score")))

        else:
            # Default to posted_date
            self.order_clauses.append(desc(text("j.posted_date")))

        return self

    def add_pagination(self, page: int, limit: int) -> "SearchQueryBuilder":
        """Add pagination with limit and offset."""
        self.limit = max(1, min(limit, 100))  # Limit between 1 and 100
        self.offset = max(0, (page - 1) * self.limit)
        return self

    def build_select_query(self, include_details: bool = False) -> Tuple[str, Dict[str, Any]]:
        """
        Build the complete SELECT query with all conditions.

        Args:
            include_details: Whether to include job details in the query

        Returns:
            Tuple of (query_string, parameters)
        """
        # Base SELECT with all necessary fields
        select_fields = [
            "j.id", "j.uuid", "j.title", "j.normalized_title",
            "j.company_id", "j.location_raw", "j.city", "j.state_province",
            "j.country", "j.is_remote", "j.employment_type_id",
            "j.experience_level_id", "j.work_arrangement_id",
            "j.salary_min", "j.salary_max", "j.salary_currency",
            "j.salary_disclosed", "j.apply_url", "j.skills_required",
            "j.skills_preferred", "j.posted_date", "j.first_seen_at",
            "j.last_seen_at", "j.status", "j.quality_score",
            "j.views_count", "j.clicks_count"
        ]

        # Company fields, always. This used to be conditional on a company
        # filter being active, which meant an ordinary search returned rows with
        # no employer at all and every result card read "Unknown". It is a LEFT
        # JOIN on an indexed FK against a 5.8k-row table — the cost is noise.
        select_fields.extend([
            "c.name as company_name", "c.logo_url as company_logo",
            "c.website as company_website", "c.industry as company_industry",
            "c.headquarters as company_headquarters", "c.slug as company_slug",
            "c.rating as company_rating", "c.rating_count as company_rating_count",
            "c.rating_url as company_rating_url", "c.rating_source as company_rating_source",
        ])

        # Add job details if requested
        if include_details or "job_details" in self.joins:
            select_fields.extend([
                "jd.description", "jd.requirements", "jd.responsibilities",
                "jd.company_benefits"
            ])

        # Add relevance score if available
        if hasattr(self, '_text_relevance_score'):
            select_fields.append(f"({self._text_relevance_score}) as text_relevance_score")

        query_parts = [
            f"SELECT {', '.join(select_fields)}",
            "FROM jobs j"
        ]

        # Add joins. companies is unconditional to match the select list above.
        query_parts.append("LEFT JOIN companies c ON j.company_id = c.id")

        if "job_details" in self.joins or include_details:
            query_parts.append("LEFT JOIN job_details jd ON j.id = jd.job_id")

        # Add WHERE clause
        if self.conditions:
            # Always include active status
            all_conditions = [text("j.status = 'active'")] + self.conditions
            where_clause = "WHERE " + " AND ".join([str(cond) for cond in all_conditions])
            query_parts.append(where_clause)
        else:
            query_parts.append("WHERE j.status = 'active'")

        # Add ORDER BY
        if self.order_clauses:
            order_clause = "ORDER BY " + ", ".join([str(clause) for clause in self.order_clauses])
            query_parts.append(order_clause)

        # Add pagination
        if hasattr(self, 'limit'):
            query_parts.append(f"LIMIT {self.limit}")
        if hasattr(self, 'offset'):
            query_parts.append(f"OFFSET {self.offset}")

        query = " ".join(query_parts)
        return query, self.params

    def build_count_query(self) -> Tuple[str, Dict[str, Any]]:
        """Build count query for pagination."""
        query_parts = [
            "SELECT COUNT(*)",
            "FROM jobs j"
        ]

        # Add joins — job_details is needed too when the WHERE clause
        # references jd (e.g. full-text search matches against job_details).
        if "company" in self.joins:
            query_parts.append("LEFT JOIN companies c ON j.company_id = c.id")

        if "job_details" in self.joins:
            query_parts.append("LEFT JOIN job_details jd ON j.id = jd.job_id")

        # Add WHERE clause
        if self.conditions:
            all_conditions = [text("j.status = 'active'")] + self.conditions
            where_clause = "WHERE " + " AND ".join([str(cond) for cond in all_conditions])
            query_parts.append(where_clause)
        else:
            query_parts.append("WHERE j.status = 'active'")

        query = " ".join(query_parts)
        return query, self.params

    @classmethod
    def from_criteria(cls, criteria: JobSearchCriteria) -> "SearchQueryBuilder":
        """
        Create query builder from search criteria.

        Args:
            criteria: Job search criteria object

        Returns:
            Configured SearchQueryBuilder instance
        """
        builder = cls()

        # Text search
        if criteria.query:
            builder.add_text_search(criteria.query)

        if criteria.title:
            builder.add_text_search(criteria.title, weight_factor=1.5)  # Higher weight for title

        # Location
        if criteria.location:
            builder.add_location_filter(criteria.location)

        # Company
        if criteria.company:
            builder.add_company_filter(criteria.company)

        # Employment characteristics
        if criteria.employment_types:
            builder.add_employment_type_filter(criteria.employment_types)

        if criteria.experience_levels:
            builder.add_experience_level_filter(criteria.experience_levels)

        if criteria.is_remote is not None:
            builder.add_remote_filter(criteria.is_remote)

        # Salary
        builder.add_salary_filter(
            criteria.min_salary,
            criteria.max_salary,
            criteria.salary_currency
        )

        # Skills
        builder.add_skills_filter(
            criteria.required_skills,
            criteria.preferred_skills
        )

        # Date filters
        builder.add_date_filter(
            criteria.posted_after,
            criteria.posted_before
        )

        # Quality filters
        builder.add_quality_filter(
            criteria.min_quality_score,
            criteria.exclude_spam
        )

        # Sorting and pagination
        builder.add_sorting(criteria.sort_by, criteria.sort_order)
        builder.add_pagination(
            (criteria.offset // criteria.limit) + 1,  # Convert offset to page
            criteria.limit
        )

        return builder