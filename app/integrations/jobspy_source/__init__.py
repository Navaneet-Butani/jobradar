"""JobSpy (Indeed + LinkedIn) job source integration."""

from .fetcher import JobSpyFetcher, JobSpyFetchResult
from .config import setup_jobspy_source

__all__ = ["JobSpyFetcher", "JobSpyFetchResult", "setup_jobspy_source"]
