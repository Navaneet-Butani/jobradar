"""Remotive job source integration."""

from .fetcher import RemotiveFetcher, FetchResult
from .config import setup_remotive_source, validate_remotive_config

__all__ = ["RemotiveFetcher", "FetchResult", "setup_remotive_source", "validate_remotive_config"]
