"""Instahyre job source integration."""

from .fetcher import InstahyreFetcher, FetchResult
from .config import setup_instahyre_source, validate_instahyre_config

__all__ = ["InstahyreFetcher", "FetchResult", "setup_instahyre_source", "validate_instahyre_config"]
