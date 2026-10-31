"""ATS (Greenhouse/Lever/Ashby) job source integration."""

from .fetcher import ATSFetcher, ATSFetchResult
from .config import setup_ats_source
from .discovery import discover_ats, slug_variants

__all__ = ["ATSFetcher", "ATSFetchResult", "setup_ats_source", "discover_ats", "slug_variants"]
