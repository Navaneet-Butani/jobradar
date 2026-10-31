"""Common enums and types used across job data models."""

from enum import Enum
from typing import Literal


class EmploymentType(str, Enum):
    """Employment type enumeration."""
    
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract" 
    FREELANCE = "freelance"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"
    VOLUNTEER = "volunteer"
    OTHER = "other"


class ExperienceLevel(str, Enum):
    """Experience level enumeration.

    Some members alias the same value (e.g. ENTRY == ENTRY_LEVEL) because
    call sites across the pipeline/search code use both spellings.
    """

    ENTRY_LEVEL = "entry_level"
    ENTRY = "entry_level"
    JUNIOR = "junior"
    MID_LEVEL = "mid_level"
    MID = "mid_level"
    SENIOR = "senior"
    SENIOR_LEVEL = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"
    EXECUTIVE = "executive"
    DIRECTOR = "director"
    VP = "vp"
    C_LEVEL = "c_level"
    OTHER = "other"


class WorkArrangement(str, Enum):
    """Work arrangement enumeration."""
    
    ON_SITE = "on_site"
    REMOTE = "remote"
    HYBRID = "hybrid"
    FLEXIBLE = "flexible"


class SalaryPeriod(str, Enum):
    """Salary period enumeration."""
    
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class Currency(str, Enum):
    """Supported currency codes."""
    
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    CAD = "CAD"
    AUD = "AUD"
    JPY = "JPY"
    CHF = "CHF"
    CNY = "CNY"
    INR = "INR"
    SGD = "SGD"
    SEK = "SEK"
    NOK = "NOK"
    DKK = "DKK"


class JobStatus(str, Enum):
    """Job status enumeration."""
    
    ACTIVE = "active"
    EXPIRED = "expired"
    FILLED = "filled"
    INVALID = "invalid"
    PENDING_REVIEW = "pending_review"


class ProcessingStatus(str, Enum):
    """Processing status enumeration."""
    
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class SkillCategory(str, Enum):
    """Skill category enumeration.

    Some members alias the same value (e.g. PROGRAMMING == PROGRAMMING_LANGUAGE)
    because call sites across sources/normalizers use both spellings.
    """

    PROGRAMMING_LANGUAGE = "programming_language"
    PROGRAMMING = "programming_language"
    FRAMEWORK = "framework"
    FRONTEND = "frontend"
    BACKEND = "backend"
    DATABASE = "database"
    DATA = "data"
    CLOUD_PLATFORM = "cloud_platform"
    CLOUD = "cloud_platform"
    DEVOPS = "devops"
    METHODOLOGY = "methodology"
    SOFT_SKILL = "soft_skill"
    DOMAIN_KNOWLEDGE = "domain_knowledge"
    TOOL = "tool"
    CERTIFICATION = "certification"
    OTHER = "other"


class ProficiencyLevel(str, Enum):
    """Skill proficiency level enumeration."""
    
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class CompanySize(str, Enum):
    """Company size enumeration."""
    
    STARTUP = "startup"  # 1-10
    SMALL = "small"      # 11-50
    MEDIUM = "medium"    # 51-200
    LARGE = "large"      # 201-1000
    ENTERPRISE = "enterprise"  # 1000+


class AlertFrequency(str, Enum):
    """Job alert frequency enumeration."""
    
    INSTANT = "instant"
    DAILY = "daily"
    WEEKLY = "weekly"


class QualityIssue(str, Enum):
    """Quality issue types."""

    BROKEN_LINK = "broken_link"
    SPAM = "spam"
    OUTDATED = "outdated"
    INAPPROPRIATE = "inappropriate"
    DUPLICATE = "duplicate"
    INCOMPLETE = "incomplete"
    MISLEADING = "misleading"


class ApplicationStatus(str, Enum):
    """Application status enumeration — the tracker's pipeline."""
    APPLIED = "applied"
    SCREENING = "screening"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    GHOSTED = "ghosted"


class ApplicationMethod(str, Enum):
    """Application method enumeration."""
    DIRECT = "direct"
    PORTAL = "portal"
    EMAIL = "email"
    REFERRAL = "referral"
    ATS_FORM = "ats_form"


# Type aliases for better code readability
JobId = int
CompanyId = int
UserId = int
SourceId = int
SkillId = int
ApplicationId = int