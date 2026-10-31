"""Business logic for the scraping configuration API."""

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from ...services.role_filter import ROLE_CATEGORIES
from ...services.scraping_config import get_enabled_categories, set_enabled_categories
from .schema import RoleCategoryResponse

# Concrete titles per category, so the settings page shows what a checkbox
# actually does rather than making the reader guess from a label.
_EXAMPLES = {
    "backend": ["Backend Developer", "Node.js Engineer", "Python Developer"],
    "frontend": ["React Developer", "Frontend Engineer", "UI Developer"],
    "fullstack": ["Full Stack Developer", "Senior Software Engineer", "SDE II"],
    "mobile": ["Android Developer", "iOS Engineer", "Flutter Developer"],
    "qa": ["QA Automation Engineer", "SDET", "Test Engineer"],
    "devops": ["DevOps Engineer", "Site Reliability Engineer", "Cloud Engineer"],
    "data": ["Data Engineer", "ML Engineer", "Data Scientist"],
    "security": ["Security Engineer", "Cybersecurity Analyst"],
    "design": ["UI/UX Designer", "Graphic Designer", "Product Designer"],
    "it_support": ["IT Support Specialist", "System Administrator", "DBA"],
    "architect": ["Solutions Architect", "Tech Lead", "Principal Engineer"],
    "embedded": ["Embedded Engineer", "Firmware Developer"],
    "product_tech": ["Technical Program Manager", "Solutions Engineer"],
}


class ScrapingService:
    """Reads and updates which role categories the scrapers collect."""

    @staticmethod
    async def list_categories(session: AsyncSession) -> List[RoleCategoryResponse]:
        enabled = set(await get_enabled_categories(session))
        return [
            RoleCategoryResponse(
                key=key,
                label=meta["label"],
                enabled=key in enabled,
                examples=_EXAMPLES.get(key, []),
            )
            for key, meta in ROLE_CATEGORIES.items()
        ]

    @staticmethod
    def unknown_keys(keys: List[str]) -> List[str]:
        """Keys the caller sent that do not exist — rejected rather than ignored,
        so a typo in the UI cannot silently disable a category."""
        return [k for k in keys if k not in ROLE_CATEGORIES]

    @staticmethod
    async def update_categories(session: AsyncSession, keys: List[str]) -> List[RoleCategoryResponse]:
        await set_enabled_categories(session, keys)
        return await ScrapingService.list_categories(session)
