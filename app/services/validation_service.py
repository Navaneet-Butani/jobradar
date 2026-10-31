"""Data validation and quality scoring service."""

import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any, Set, Tuple
from urllib.parse import urlparse
from dataclasses import dataclass

from ..models.job import StandardJob, ProcessedJob
from ..models.base import ValidationResult
from ..core.exceptions import ValidationError

logger = logging.getLogger(__name__)


@dataclass
class QualityMetrics:
    """Quality metrics for a job posting."""
    completeness_score: float = 0.0  # 0-100
    content_quality_score: float = 0.0  # 0-100
    spam_likelihood_score: float = 0.0  # 0-100
    overall_quality_score: float = 0.0  # 0-100
    
    # Detailed scores
    field_completeness: Dict[str, bool] = None
    content_flags: List[str] = None
    spam_indicators: List[str] = None
    quality_notes: List[str] = None
    
    def __post_init__(self):
        if self.field_completeness is None:
            self.field_completeness = {}
        if self.content_flags is None:
            self.content_flags = []
        if self.spam_indicators is None:
            self.spam_indicators = []
        if self.quality_notes is None:
            self.quality_notes = []


class ValidationService:
    """Service for validating job data quality and detecting spam."""
    
    # Spam indicators
    SPAM_KEYWORDS = {
        'urgent', 'immediate', 'hurry', 'fast cash', 'easy money', 'work from home',
        'make money fast', 'no experience required', 'guaranteed income', 'unlimited earning',
        'pyramid', 'mlm', 'multi-level marketing', 'get rich quick', 'investment opportunity',
        'earn $$$', 'secret method', 'exclusive offer', 'limited time', 'act now'
    }
    
    SPAM_PATTERNS = [
        r'\$\$\$+',  # Multiple dollar signs
        r'[!]{3,}',  # Multiple exclamation marks
        r'[A-Z]{10,}',  # Long strings of capitals
        r'earn\s*\$\d+\s*per\s*(day|hour)',  # Earn $X per day/hour
        r'work\s*from\s*home.*\$\d+',  # Work from home $X
        r'no\s*experience.*\$\d+',  # No experience $X
    ]
    
    # Suspicious domains
    SPAM_DOMAINS = {
        'spam-site.com', 'fake-jobs.net', 'scam-alerts.org',
        # Add more known spam domains
    }
    
    # Quality indicators
    QUALITY_KEYWORDS = {
        'benefits', 'competitive salary', 'health insurance', 'career growth',
        'professional development', 'team environment', 'company culture',
        'equal opportunity', 'diversity', 'inclusion'
    }
    
    # Required fields for quality scoring
    REQUIRED_FIELDS = [
        'title', 'company_name', 'location', 'description', 'apply_url'
    ]
    
    OPTIONAL_FIELDS = [
        'salary', 'employment_type', 'experience_level', 'skills_required',
        'benefits', 'department'
    ]
    
    # Field weights for completeness scoring
    FIELD_WEIGHTS = {
        'title': 0.2,
        'company_name': 0.15,
        'location': 0.1,
        'description': 0.25,
        'apply_url': 0.1,
        'salary': 0.15,
        'employment_type': 0.05,
        'experience_level': 0.05,
        'skills_required': 0.1,
        'benefits': 0.05
    }
    
    def __init__(self):
        """Initialize the validation service."""
        self.logger = logging.getLogger(f"{__name__}")
        self._compile_spam_patterns()
    
    def _compile_spam_patterns(self):
        """Compile spam detection patterns."""
        self.compiled_spam_patterns = []
        for pattern in self.SPAM_PATTERNS:
            try:
                self.compiled_spam_patterns.append(re.compile(pattern, re.IGNORECASE))
            except re.error as e:
                self.logger.warning(f"Failed to compile spam pattern {pattern}: {e}")
    
    async def validate_job(self, job: StandardJob) -> ValidationResult:
        """Validate a job posting and return validation result."""
        try:
            validation_issues = []
            warnings = []
            
            # Required field validation
            required_issues = self._validate_required_fields(job)
            validation_issues.extend(required_issues)
            
            # URL validation
            url_issues = await self._validate_urls(job)
            validation_issues.extend(url_issues)
            
            # Date validation
            date_issues = self._validate_dates(job)
            validation_issues.extend(date_issues)
            
            # Salary validation
            salary_issues = self._validate_salary(job)
            validation_issues.extend(salary_issues)
            
            # Content validation
            content_issues = self._validate_content(job)
            validation_issues.extend(content_issues)
            
            # Calculate quality metrics
            quality_metrics = await self.calculate_quality_score(job)
            
            # Determine overall validation status
            is_valid = len(validation_issues) == 0
            confidence = 1.0 - (len(validation_issues) * 0.1)  # Reduce confidence per issue
            
            return ValidationResult(
                is_valid=is_valid,
                confidence=max(0.0, confidence),
                issues=validation_issues,
                warnings=warnings,
                quality_metrics=quality_metrics.__dict__,
                validation_timestamp=datetime.utcnow()
            )
            
        except Exception as e:
            self.logger.error(f"Error validating job: {e}")
            return ValidationResult(
                is_valid=False,
                confidence=0.0,
                issues=[f"Validation error: {str(e)}"],
                warnings=[],
                quality_metrics={},
                validation_timestamp=datetime.utcnow()
            )
    
    async def calculate_quality_score(self, job: StandardJob) -> QualityMetrics:
        """Calculate comprehensive quality score for a job."""
        try:
            metrics = QualityMetrics()
            
            # 1. Field completeness score (40% of overall)
            completeness = self._calculate_completeness_score(job)
            metrics.completeness_score = completeness['score']
            metrics.field_completeness = completeness['field_status']
            
            # 2. Content quality score (40% of overall)  
            content_quality = self._calculate_content_quality_score(job)
            metrics.content_quality_score = content_quality['score']
            metrics.content_flags = content_quality['flags']
            
            # 3. Spam likelihood score (20% of overall, inverted)
            spam_analysis = await self.detect_spam(job)
            metrics.spam_likelihood_score = spam_analysis['spam_score']
            metrics.spam_indicators = spam_analysis['indicators']
            
            # Calculate overall quality score
            quality_from_spam = 100 - metrics.spam_likelihood_score
            metrics.overall_quality_score = (
                metrics.completeness_score * 0.4 +
                metrics.content_quality_score * 0.4 +
                quality_from_spam * 0.2
            )
            
            # Add quality notes
            metrics.quality_notes = self._generate_quality_notes(metrics)
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"Error calculating quality score: {e}")
            return QualityMetrics(
                completeness_score=0.0,
                content_quality_score=0.0,
                spam_likelihood_score=100.0,
                overall_quality_score=0.0,
                quality_notes=[f"Quality calculation error: {str(e)}"]
            )
    
    async def detect_spam(self, job: StandardJob) -> Dict[str, Any]:
        """Detect spam indicators in job posting."""
        try:
            spam_score = 0.0
            indicators = []
            
            # Combine text for analysis
            text_to_analyze = self._get_combined_text(job)
            
            # 1. Keyword-based detection (30 points max)
            keyword_score = self._detect_spam_keywords(text_to_analyze)
            spam_score += keyword_score
            if keyword_score > 0:
                indicators.append(f"Contains spam keywords (score: {keyword_score})")
            
            # 2. Pattern-based detection (25 points max)
            pattern_score = self._detect_spam_patterns(text_to_analyze)
            spam_score += pattern_score
            if pattern_score > 0:
                indicators.append(f"Matches spam patterns (score: {pattern_score})")
            
            # 3. URL analysis (20 points max)
            url_score = await self._analyze_url_spam(job.apply_url)
            spam_score += url_score
            if url_score > 0:
                indicators.append(f"Suspicious URL (score: {url_score})")
            
            # 4. Salary analysis (15 points max)
            salary_score = self._analyze_salary_spam(job)
            spam_score += salary_score
            if salary_score > 0:
                indicators.append(f"Unrealistic salary claims (score: {salary_score})")
            
            # 5. Content structure analysis (10 points max)
            structure_score = self._analyze_content_structure(text_to_analyze)
            spam_score += structure_score
            if structure_score > 0:
                indicators.append(f"Poor content structure (score: {structure_score})")
            
            return {
                'spam_score': min(100.0, spam_score),
                'indicators': indicators,
                'analysis_method': 'comprehensive'
            }
            
        except Exception as e:
            self.logger.error(f"Error detecting spam: {e}")
            return {
                'spam_score': 50.0,  # Medium score on error
                'indicators': [f"Spam detection error: {str(e)}"],
                'analysis_method': 'error_fallback'
            }
    
    async def validate_url(self, url: str) -> bool:
        """Validate if URL is accessible and not suspicious."""
        try:
            if not url:
                return False
            
            # Basic URL format validation
            parsed = urlparse(url)
            if not all([parsed.scheme, parsed.netloc]):
                return False
            
            # Check against known spam domains
            domain = parsed.netloc.lower()
            if domain in self.SPAM_DOMAINS:
                return False
            
            # Check for suspicious URL patterns
            suspicious_patterns = [
                r'bit\.ly',  # URL shorteners can be suspicious
                r'tinyurl',
                r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}',  # IP addresses
                r'[a-z0-9]{20,}',  # Very long random strings
            ]
            
            for pattern in suspicious_patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    return False
            
            return True
            
        except Exception as e:
            self.logger.warning(f"Error validating URL {url}: {e}")
            return False
    
    # Private validation methods
    
    def _validate_required_fields(self, job: StandardJob) -> List[str]:
        """Validate required fields are present."""
        issues = []
        
        for field in self.REQUIRED_FIELDS:
            value = getattr(job, field, None)
            if not value or (isinstance(value, str) and not value.strip()):
                issues.append(f"Missing required field: {field}")
        
        return issues
    
    async def _validate_urls(self, job: StandardJob) -> List[str]:
        """Validate URLs in the job posting."""
        issues = []
        
        # Validate apply URL
        if not await self.validate_url(job.apply_url):
            issues.append("Invalid or suspicious apply URL")
        
        return issues
    
    def _validate_dates(self, job: StandardJob) -> List[str]:
        """Validate date fields."""
        issues = []
        
        # Check posted date
        if job.posted_date:
            # Posted date shouldn't be in the future
            if job.posted_date > datetime.utcnow():
                issues.append("Posted date is in the future")
            
            # Posted date shouldn't be too old (more than 1 year)
            one_year_ago = datetime.utcnow() - timedelta(days=365)
            if job.posted_date < one_year_ago:
                issues.append("Posted date is more than 1 year old")
        
        # Check application deadline
        if hasattr(job, 'application_deadline') and job.application_deadline:
            if job.application_deadline < datetime.utcnow():
                issues.append("Application deadline has passed")
        
        return issues
    
    def _validate_salary(self, job: StandardJob) -> List[str]:
        """Validate salary information."""
        issues = []
        
        if job.salary:
            # Check for reasonable salary ranges
            if hasattr(job.salary, 'min_salary') and job.salary.min_salary:
                if job.salary.min_salary < 1000:
                    issues.append("Minimum salary seems unreasonably low")
                elif job.salary.min_salary > 10000000:
                    issues.append("Minimum salary seems unreasonably high")
            
            if hasattr(job.salary, 'max_salary') and job.salary.max_salary:
                if job.salary.max_salary < 1000:
                    issues.append("Maximum salary seems unreasonably low")
                elif job.salary.max_salary > 10000000:
                    issues.append("Maximum salary seems unreasonably high")
            
            # Check salary range consistency
            if (hasattr(job.salary, 'min_salary') and hasattr(job.salary, 'max_salary') and
                job.salary.min_salary and job.salary.max_salary):
                if job.salary.min_salary > job.salary.max_salary:
                    issues.append("Minimum salary is greater than maximum salary")
        
        return issues
    
    def _validate_content(self, job: StandardJob) -> List[str]:
        """Validate content quality."""
        issues = []
        
        # Check description length
        if hasattr(job, 'description') and job.description:
            if len(job.description) < 50:
                issues.append("Job description is too short (less than 50 characters)")
            elif len(job.description) > 10000:
                issues.append("Job description is extremely long (over 10,000 characters)")
        
        # Check title length and content
        if len(job.title) < 5:
            issues.append("Job title is too short")
        elif len(job.title) > 200:
            issues.append("Job title is too long")
        
        # Check for placeholder content
        placeholder_patterns = [
            r'lorem\s+ipsum',
            r'placeholder',
            r'insert\s+text\s+here',
            r'todo',
            r'xxx+',
        ]
        
        combined_text = self._get_combined_text(job)
        for pattern in placeholder_patterns:
            if re.search(pattern, combined_text, re.IGNORECASE):
                issues.append("Contains placeholder or template text")
                break
        
        return issues
    
    def _calculate_completeness_score(self, job: StandardJob) -> Dict[str, Any]:
        """Calculate field completeness score."""
        field_status = {}
        weighted_score = 0.0
        
        for field, weight in self.FIELD_WEIGHTS.items():
            value = getattr(job, field, None)
            
            # Determine if field is complete
            is_complete = False
            if value is not None:
                if isinstance(value, str):
                    is_complete = bool(value.strip())
                elif isinstance(value, list):
                    is_complete = len(value) > 0
                elif hasattr(value, '__dict__'):  # Object with attributes
                    is_complete = True
                else:
                    is_complete = True
            
            field_status[field] = is_complete
            if is_complete:
                weighted_score += weight * 100
        
        return {
            'score': weighted_score,
            'field_status': field_status
        }
    
    def _calculate_content_quality_score(self, job: StandardJob) -> Dict[str, Any]:
        """Calculate content quality score."""
        score = 0.0
        flags = []
        
        # Description quality (40 points)
        if hasattr(job, 'description') and job.description:
            desc_score, desc_flags = self._analyze_description_quality(job.description)
            score += desc_score
            flags.extend(desc_flags)
        
        # Title quality (20 points)
        title_score, title_flags = self._analyze_title_quality(job.title)
        score += title_score
        flags.extend(title_flags)
        
        # Company information quality (15 points)
        company_score = self._analyze_company_quality(job.company_name)
        score += company_score
        
        # Professional language and tone (15 points)
        text = self._get_combined_text(job)
        language_score, language_flags = self._analyze_language_quality(text)
        score += language_score
        flags.extend(language_flags)
        
        # Quality indicators bonus (10 points)
        quality_score = self._detect_quality_indicators(text)
        score += quality_score
        
        return {
            'score': min(100.0, score),
            'flags': flags
        }
    
    def _analyze_description_quality(self, description: str) -> Tuple[float, List[str]]:
        """Analyze job description quality."""
        score = 0.0
        flags = []
        
        if not description:
            return 0.0, ["No description provided"]
        
        # Length scoring
        length = len(description)
        if length >= 200:
            score += 15  # Good length
        elif length >= 100:
            score += 10  # Adequate length
        else:
            score += 5   # Too short
            flags.append("Description is quite short")
        
        # Structure scoring
        sentences = description.split('.')
        if len(sentences) >= 3:
            score += 10  # Good structure
        else:
            flags.append("Description lacks detail")
        
        # Content variety scoring
        if any(word in description.lower() for word in ['responsibilities', 'requirements', 'qualifications']):
            score += 10  # Good structure
        
        # Professional tone
        if re.search(r'[a-zA-Z]+', description):  # Contains letters
            score += 5
        
        return score, flags
    
    def _analyze_title_quality(self, title: str) -> Tuple[float, List[str]]:
        """Analyze job title quality."""
        score = 0.0
        flags = []
        
        # Length check
        if 10 <= len(title) <= 100:
            score += 10
        else:
            flags.append("Title length not optimal")
        
        # Professional title indicators
        professional_indicators = ['engineer', 'developer', 'manager', 'analyst', 'specialist', 'coordinator']
        if any(indicator in title.lower() for indicator in professional_indicators):
            score += 5
        
        # Avoid excessive punctuation
        if title.count('!') <= 1 and title.count('?') == 0:
            score += 5
        else:
            flags.append("Excessive punctuation in title")
        
        return score, flags
    
    def _analyze_company_quality(self, company_name: str) -> float:
        """Analyze company name quality."""
        if not company_name or company_name.lower() in ['unknown', 'n/a', 'tbd']:
            return 0.0
        
        # Basic checks
        if len(company_name) >= 3 and company_name.strip():
            return 15.0
        
        return 5.0
    
    def _analyze_language_quality(self, text: str) -> Tuple[float, List[str]]:
        """Analyze language and tone quality."""
        score = 0.0
        flags = []
        
        text_lower = text.lower()
        
        # Check for professional language
        professional_terms = ['experience', 'skills', 'requirements', 'qualifications', 'team', 'company']
        professional_count = sum(1 for term in professional_terms if term in text_lower)
        score += min(10, professional_count * 2)
        
        # Penalize excessive caps
        caps_ratio = sum(1 for c in text if c.isupper()) / max(1, len(text))
        if caps_ratio > 0.3:
            flags.append("Excessive use of capital letters")
        else:
            score += 5
        
        return score, flags
    
    def _detect_quality_indicators(self, text: str) -> float:
        """Detect positive quality indicators."""
        text_lower = text.lower()
        
        quality_count = sum(1 for keyword in self.QUALITY_KEYWORDS if keyword in text_lower)
        return min(10.0, quality_count * 2)
    
    def _detect_spam_keywords(self, text: str) -> float:
        """Detect spam keywords."""
        text_lower = text.lower()
        
        spam_count = sum(1 for keyword in self.SPAM_KEYWORDS if keyword in text_lower)
        return min(30.0, spam_count * 5)
    
    def _detect_spam_patterns(self, text: str) -> float:
        """Detect spam patterns."""
        pattern_count = 0
        
        for pattern in self.compiled_spam_patterns:
            if pattern.search(text):
                pattern_count += 1
        
        return min(25.0, pattern_count * 5)
    
    async def _analyze_url_spam(self, url: str) -> float:
        """Analyze URL for spam indicators."""
        if not url:
            return 0.0
        
        spam_score = 0.0
        
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Check against known spam domains
            if domain in self.SPAM_DOMAINS:
                spam_score += 20
            
            # Check for suspicious patterns
            if re.search(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}', domain):
                spam_score += 10  # IP address instead of domain
            
            if len(domain) > 50:
                spam_score += 5  # Unusually long domain
            
            # Check for suspicious URL structure
            if parsed.path.count('/') > 5:
                spam_score += 5  # Deep URL structure
                
        except Exception:
            spam_score += 5  # Malformed URL
        
        return min(20.0, spam_score)
    
    def _analyze_salary_spam(self, job: StandardJob) -> float:
        """Analyze salary for spam indicators."""
        if not job.salary:
            return 0.0
        
        spam_score = 0.0
        
        # Check for unrealistic salaries
        if hasattr(job.salary, 'min_salary') and job.salary.min_salary:
            if job.salary.min_salary > 1000000:  # Over $1M
                spam_score += 10
        
        if hasattr(job.salary, 'max_salary') and job.salary.max_salary:
            if job.salary.max_salary > 2000000:  # Over $2M
                spam_score += 10
        
        # Check salary text for spam patterns
        if hasattr(job.salary, 'raw_salary') and job.salary.raw_salary:
            text = job.salary.raw_salary.lower()
            if any(phrase in text for phrase in ['easy money', 'fast cash', 'unlimited earning']):
                spam_score += 15
        
        return min(15.0, spam_score)
    
    def _analyze_content_structure(self, text: str) -> float:
        """Analyze content structure for spam indicators."""
        spam_score = 0.0
        
        # Check for excessive repetition
        words = text.lower().split()
        if len(words) > 10:
            unique_words = set(words)
            repetition_ratio = len(words) / len(unique_words)
            if repetition_ratio > 3:  # High repetition
                spam_score += 5
        
        # Check for excessive punctuation
        punctuation_count = sum(1 for c in text if c in '!?')
        if punctuation_count > len(text) * 0.05:  # More than 5% punctuation
            spam_score += 5
        
        return min(10.0, spam_score)
    
    def _get_combined_text(self, job: StandardJob) -> str:
        """Get combined text from all job fields for analysis."""
        text_parts = [job.title, job.company_name]
        
        if hasattr(job, 'description') and job.description:
            text_parts.append(job.description)
        
        if hasattr(job, 'location') and job.location:
            if hasattr(job.location, 'raw_location'):
                text_parts.append(job.location.raw_location)
            else:
                text_parts.append(str(job.location))
        
        return ' '.join(filter(None, text_parts))
    
    def _generate_quality_notes(self, metrics: QualityMetrics) -> List[str]:
        """Generate quality improvement notes."""
        notes = []
        
        if metrics.completeness_score < 70:
            notes.append("Job posting is missing important information")
        
        if metrics.content_quality_score < 60:
            notes.append("Content quality could be improved")
        
        if metrics.spam_likelihood_score > 30:
            notes.append("Contains potential spam indicators")
        
        if metrics.overall_quality_score >= 80:
            notes.append("High quality job posting")
        elif metrics.overall_quality_score >= 60:
            notes.append("Good quality job posting")
        else:
            notes.append("Job posting needs improvement")
        
        return notes