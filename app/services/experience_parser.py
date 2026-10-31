"""Experience-range parsing service.

Most sources don't carry a structured experience field — the range lives in
free text ("6-10 Yrs", "5+ years") in the description, or has to be guessed
from a seniority word in the title ("Senior", "Fresher"). Mirrors
SalaryParser's strategy-list + confidence pattern.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ParsedExperience:
    """Result of experience-range parsing with confidence and metadata."""
    min_years: Optional[int] = None
    max_years: Optional[int] = None
    confidence: float = 0.0
    parsing_method: str = "unknown"


class ExperienceParser:
    """Service for parsing required-experience ranges from text."""

    # No human job asks for more than this. Without a ceiling, a stray "2014+
    # years" (a year that lost its separator when the source's HTML was
    # flattened) parses as a 2014-year floor and silently drops the job from
    # every feed, because the hard filters compare it against the profile.
    MAX_PLAUSIBLE_YEARS = 50

    # "6-10 Yrs", "2 to 4 years", "0-1 year" — numeric range, explicit separator.
    RANGE_PATTERN = re.compile(
        r'([0-9]+)\s*(?:-|–|—|to)\s*([0-9]+)\s*\+?\s*(?:years?|yrs?)\b',
        re.IGNORECASE
    )

    # "5+ years", "3+ yrs"
    PLUS_PATTERN = re.compile(
        r'([0-9]+)\s*\+\s*(?:years?|yrs?)\b',
        re.IGNORECASE
    )

    # "0 years", "1 yr" — bare single number, no "+" (treated as an exact floor).
    SINGLE_PATTERN = re.compile(
        r'\b([0-9]+)\s*(?:years?|yrs?)\b(?:\s*(?:of\s+)?experience)?',
        re.IGNORECASE
    )

    # Title/description seniority fallback when no explicit number is present.
    # Ordered most- to least-specific; first match wins.
    TITLE_LEVEL_PATTERNS = [
        ((0, 1), re.compile(r'\b(fresher|intern(?:ship)?|trainee|new\s*grad(?:uate)?)\b', re.IGNORECASE)),
        ((0, 3), re.compile(r'\b(junior|jr\.?|entry.?level)\b', re.IGNORECASE)),
        ((5, None), re.compile(r'\b(senior|sr\.?|lead|principal|staff|architect)\b', re.IGNORECASE)),
    ]

    def parse_experience(self, text: Optional[str], title: Optional[str] = None) -> ParsedExperience:
        """Parse an experience range from free text, falling back to a title-derived guess."""
        combined = " ".join(t for t in (text, title) if t).strip()
        if not combined:
            return ParsedExperience(confidence=0.0, parsing_method="empty")

        range_match = self.RANGE_PATTERN.search(combined)
        if range_match:
            lo, hi = self._to_years(range_match.group(1)), self._to_years(range_match.group(2))
            if lo is not None and hi is not None and lo > hi:
                lo, hi = hi, lo
            if lo is not None and hi is not None:
                return ParsedExperience(min_years=lo, max_years=hi, confidence=0.95, parsing_method="numeric_range")

        plus_match = self.PLUS_PATTERN.search(combined)
        if plus_match:
            lo = self._to_years(plus_match.group(1))
            if lo is not None:
                return ParsedExperience(min_years=lo, max_years=None, confidence=0.9, parsing_method="numeric_plus")

        single_match = self.SINGLE_PATTERN.search(combined)
        if single_match:
            lo = self._to_years(single_match.group(1))
            if lo is not None:
                return ParsedExperience(min_years=lo, max_years=lo, confidence=0.6, parsing_method="numeric_single")

        for (lo, hi), pattern in self.TITLE_LEVEL_PATTERNS:
            if pattern.search(combined):
                return ParsedExperience(min_years=lo, max_years=hi, confidence=0.5, parsing_method="title_level")

        return ParsedExperience(confidence=0.0, parsing_method="no_match")

    def _to_years(self, raw: str) -> Optional[int]:
        """Whole years, or None when the digits cannot be an experience figure.

        Rejects out-of-range values and leading-zero digit strings: no posting
        writes "014+ years", but a flattened "2014+" does, and 14 is plausible
        enough to sail through a range check unnoticed.
        """
        if len(raw) > 1 and raw.startswith("0"):
            return None
        years = int(raw)
        return years if 0 <= years <= self.MAX_PLAUSIBLE_YEARS else None
