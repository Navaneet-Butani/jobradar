"""Which role categories the scrapers are currently allowed to collect.

Stored as one row in `system_settings` rather than in a new table: that table
already exists as a typed key/value store, and this is a single JSON list for
a small self-hosted deployment. Read on every ATS poll, written from the UI.
"""

import json
import logging
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import SystemSettingDB
from .role_filter import DEFAULT_ENABLED, ROLE_CATEGORIES

logger = logging.getLogger(__name__)

SETTING_KEY = "scrape_role_categories"
_DESCRIPTION = "Role categories the scrapers collect; see app/services/role_filter.py"


async def get_enabled_categories(session: AsyncSession) -> List[str]:
    """Enabled category keys, falling back to all of them.

    Falls back rather than raising: a missing or corrupt row must not stop an
    ingest run, and collecting everything is the pre-configuration behaviour.
    """
    result = await session.execute(
        select(SystemSettingDB).where(SystemSettingDB.key == SETTING_KEY)
    )
    row = result.scalar_one_or_none()
    if row is None or not row.value:
        return list(DEFAULT_ENABLED)
    try:
        stored = json.loads(row.value)
    except (TypeError, ValueError):
        logger.warning("%s is not valid JSON; collecting every category", SETTING_KEY)
        return list(DEFAULT_ENABLED)
    if not isinstance(stored, list):
        logger.warning("%s is not a list; collecting every category", SETTING_KEY)
        return list(DEFAULT_ENABLED)
    # Drop keys that no longer exist so a renamed category cannot silently
    # disable scraping entirely.
    return [k for k in stored if k in ROLE_CATEGORIES]


async def set_enabled_categories(session: AsyncSession, keys: List[str]) -> List[str]:
    """Replace the enabled set. Unknown keys are rejected by the caller."""
    clean = [k for k in dict.fromkeys(keys) if k in ROLE_CATEGORIES]
    result = await session.execute(
        select(SystemSettingDB).where(SystemSettingDB.key == SETTING_KEY)
    )
    row = result.scalar_one_or_none()
    if row is None:
        session.add(SystemSettingDB(
            key=SETTING_KEY, value=json.dumps(clean), value_type="json",
            description=_DESCRIPTION,
        ))
    else:
        row.value = json.dumps(clean)
        row.value_type = "json"
    await session.commit()
    logger.info("scrape_role_categories set to %s", clean)
    return clean
