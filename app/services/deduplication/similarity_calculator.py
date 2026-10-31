"""Advanced similarity calculation engine with configurable algorithms."""

import re
import logging
from typing import Dict, List, Tuple, Optional
from decimal import Decimal
from datetime import datetime, timedelta

try:
    from rapidfuzz import fuzz, process
except ImportError:
    # Fallback for environments without rapidfuzz
    class FuzzFallback:
        @staticmethod
        def ratio(s1, s2): return 0.0
        @staticmethod
        def partial_ratio(s1, s2): return 0.0
        @staticmethod
        def token_sort_ratio(s1, s2): return 0.0
        @staticmethod
        def token_set_ratio(s1, s2): return 0.0
    fuzz = FuzzFallback()

from ...config.deduplication_config import get_dedup_config
from ...services.company_service import CompanyService
from ...utils.text_processing import TextNormalizer

logger = logging.getLogger(__name__)


class SimilarityCalculator:
    """
    Advanced similarity calculation with multiple algorithms and configurable weights.

    Features:
    - Multi-factor weighted scoring
    - Configurable similarity thresholds
    - Advanced text normalization
    - Company-aware matching
    - Location intelligence
    - Temporal proximity scoring
    """

    def __init__(self, company_service: CompanyService = None, environment: str = "development"):
        self.company_service = company_service
        self.text_normalizer = TextNormalizer()

        # Load configuration
        self.config = get_dedup_config(environment)
        self.weights = self.config.similarity_weights
        self.thresholds = self.config.similarity_thresholds
        # No "advanced" field on DeduplicationConfig — every consumer below
        # already falls back to a sensible default via .get(key, default).
        self.advanced_config = {}

        # Title similarity synonyms
        self.title_synonyms = self._load_title_synonyms()

    async def calculate_comprehensive_similarity(self, job1: dict, job2: dict) -> Dict[str, float]:
        """
        Calculate comprehensive similarity between two jobs.

        Returns detailed similarity breakdown with individual scores.
        """
        try:
            scores = {}
            factors = {}

            # 1. Title Similarity (35% weight)
            title_result = await self._calculate_title_similarity(
                job1.get('title', ''), job2.get('title', '')
            )
            scores['title'] = title_result['score']
            factors['title'] = title_result['factors']

            # 2. Company Similarity (25% weight)
            company_result = await self._calculate_company_similarity(
                job1.get('company_name', ''), job2.get('company_name', '')
            )
            scores['company'] = company_result['score']
            factors['company'] = company_result['factors']

            # 3. Location Similarity (20% weight)
            location_result = await self._calculate_location_similarity(
                job1.get('location', ''), job2.get('location', '')
            )
            scores['location'] = location_result['score']
            factors['location'] = location_result['factors']

            # 4. Salary Similarity (10% weight)
            salary_result = await self._calculate_salary_similarity(
                job1.get('salary', {}), job2.get('salary', {})
            )
            scores['salary'] = salary_result['score']
            factors['salary'] = salary_result['factors']

            # 5. Date Proximity (5% weight)
            date_result = await self._calculate_date_proximity(
                job1.get('posted_date'), job2.get('posted_date')
            )
            scores['date'] = date_result['score']
            factors['date'] = date_result['factors']

            # 6. Description Similarity (5% weight)
            description_result = await self._calculate_description_similarity(
                job1.get('description', ''), job2.get('description', '')
            )
            scores['description'] = description_result['score']
            factors['description'] = description_result['factors']

            # Calculate weighted total
            total_score = sum(
                scores[key] * self.weights.get(key, 0)
                for key in scores
            )

            # Apply boost factors
            boosted_score = self._apply_similarity_boosts(total_score, scores, factors)

            return {
                'total_score': boosted_score,
                'individual_scores': scores,
                'match_factors': factors,
                'confidence': self._calculate_confidence(scores, factors)
            }

        except Exception as e:
            logger.error(f"Error calculating similarity: {e}")
            return {'total_score': 0.0, 'individual_scores': {}, 'match_factors': {}}

    async def _calculate_title_similarity(self, title1: str, title2: str) -> Dict:
        """Advanced title similarity with synonym handling."""
        if not title1 or not title2:
            return {'score': 0.0, 'factors': {'reason': 'missing_title'}}

        # Normalize titles
        norm_title1 = self.text_normalizer.normalize_job_title(title1)
        norm_title2 = self.text_normalizer.normalize_job_title(title2)

        factors = {
            'original_1': title1,
            'original_2': title2,
            'normalized_1': norm_title1,
            'normalized_2': norm_title2
        }

        # 1. Exact match after normalization
        if norm_title1 == norm_title2:
            factors['match_type'] = 'exact_normalized'
            return {'score': 1.0, 'factors': factors}

        # 2. Synonym-aware matching (if enabled)
        if self.advanced_config.get('enable_synonym_matching', True):
            synonym_score = self._calculate_synonym_similarity(norm_title1, norm_title2)
            if synonym_score > 0.9:
                factors['match_type'] = 'synonym_match'
                factors['synonym_score'] = synonym_score
                return {'score': synonym_score, 'factors': factors}

        # 3. Multiple similarity algorithms
        algorithm_weights = self.advanced_config.get('algorithm_weights', {}).get('title_algorithms', {
            'ratio': 0.25, 'partial_ratio': 0.30, 'token_sort': 0.25, 'token_set': 0.20
        })

        ratio_score = fuzz.ratio(norm_title1, norm_title2) / 100.0
        partial_score = fuzz.partial_ratio(norm_title1, norm_title2) / 100.0
        token_sort_score = fuzz.token_sort_ratio(norm_title1, norm_title2) / 100.0
        token_set_score = fuzz.token_set_ratio(norm_title1, norm_title2) / 100.0

        # Use configured weights
        scores = [
            (ratio_score, algorithm_weights.get('ratio', 0.25)),
            (partial_score, algorithm_weights.get('partial_ratio', 0.30)),
            (token_sort_score, algorithm_weights.get('token_sort', 0.25)),
            (token_set_score, algorithm_weights.get('token_set', 0.20))
        ]

        weighted_score = sum(score * weight for score, weight in scores)

        factors.update({
            'match_type': 'fuzzy_algorithms',
            'ratio_score': ratio_score,
            'partial_score': partial_score,
            'token_sort_score': token_sort_score,
            'token_set_score': token_set_score,
            'weighted_score': weighted_score
        })

        return {'score': weighted_score, 'factors': factors}

    async def _calculate_company_similarity(self, company1: str, company2: str) -> Dict:
        """Enhanced company similarity using company service."""
        if not company1 or not company2:
            return {'score': 0.5, 'factors': {'reason': 'missing_company'}}

        factors = {
            'company_1': company1,
            'company_2': company2
        }

        try:
            # Use company service for advanced matching if available
            if self.company_service:
                matches = await self.company_service.find_company_matches(
                    company1, similarity_threshold=0.3, max_results=5
                )

                # Check if company2 is in the matches
                for match in matches:
                    if self._normalize_company_name(match.matched_name) == self._normalize_company_name(company2):
                        factors.update({
                            'match_type': 'company_service',
                            'service_score': match.similarity_score,
                            'normalized_match': True
                        })
                        return {'score': match.similarity_score, 'factors': factors}

            # Fallback to string similarity with company-specific rules
            norm_company1 = self._normalize_company_name(company1)
            norm_company2 = self._normalize_company_name(company2)

            if norm_company1 == norm_company2:
                factors['match_type'] = 'exact_normalized'
                return {'score': 1.0, 'factors': factors}

            # Check for company aliases (if enabled)
            if self.advanced_config.get('enable_company_aliases', True):
                if self._are_company_aliases(norm_company1, norm_company2):
                    factors['match_type'] = 'known_aliases'
                    return {'score': 0.95, 'factors': factors}

            # String similarity
            similarity = fuzz.token_set_ratio(norm_company1, norm_company2) / 100.0

            factors.update({
                'match_type': 'string_similarity',
                'normalized_1': norm_company1,
                'normalized_2': norm_company2,
                'string_score': similarity
            })

            return {'score': similarity, 'factors': factors}

        except Exception as e:
            logger.error(f"Error in company similarity: {e}")
            # Fallback to basic string matching
            basic_score = fuzz.ratio(company1.lower(), company2.lower()) / 100.0
            factors['match_type'] = 'fallback_basic'
            factors['error'] = str(e)
            return {'score': basic_score, 'factors': factors}

    async def _calculate_location_similarity(self, location1: str, location2: str) -> Dict:
        """Intelligent location similarity with remote work detection."""
        factors = {
            'location_1': location1,
            'location_2': location2
        }

        if not location1 or not location2:
            return {'score': 0.5, 'factors': factors}

        # Normalize locations
        norm_loc1 = self.text_normalizer.normalize_location(location1)
        norm_loc2 = self.text_normalizer.normalize_location(location2)

        # Remote work detection
        is_remote1 = self.text_normalizer.is_remote_location(norm_loc1)
        is_remote2 = self.text_normalizer.is_remote_location(norm_loc2)

        if is_remote1 and is_remote2:
            factors['match_type'] = 'both_remote'
            return {'score': 1.0, 'factors': factors}

        if is_remote1 or is_remote2:
            factors['match_type'] = 'mixed_remote_local'
            return {'score': 0.6, 'factors': factors}

        # Geographic similarity
        geo_score = self._calculate_geographic_similarity(norm_loc1, norm_loc2)

        factors.update({
            'match_type': 'geographic',
            'normalized_1': norm_loc1,
            'normalized_2': norm_loc2,
            'geographic_score': geo_score
        })

        return {'score': geo_score, 'factors': factors}

    async def _calculate_salary_similarity(self, salary1: dict, salary2: dict) -> Dict:
        """Advanced salary similarity with currency and range handling."""
        factors = {
            'salary_1': salary1,
            'salary_2': salary2
        }

        # Both have no salary information
        if not salary1 and not salary2:
            factors['match_type'] = 'both_undisclosed'
            return {'score': 0.8, 'factors': factors}

        # One has salary, other doesn't
        if not salary1 or not salary2:
            factors['match_type'] = 'mixed_disclosure'
            return {'score': 0.4, 'factors': factors}

        try:
            # Extract salary ranges
            range1 = self._extract_salary_range(salary1)
            range2 = self._extract_salary_range(salary2)

            if not range1 or not range2:
                factors['match_type'] = 'extraction_failed'
                return {'score': 0.5, 'factors': factors}

            # Calculate overlap
            overlap_score = self._calculate_range_overlap(range1, range2)

            factors.update({
                'match_type': 'range_comparison',
                'range_1': range1,
                'range_2': range2,
                'overlap_score': overlap_score
            })

            return {'score': overlap_score, 'factors': factors}

        except Exception as e:
            logger.error(f"Error calculating salary similarity: {e}")
            factors['match_type'] = 'error'
            factors['error'] = str(e)
            return {'score': 0.5, 'factors': factors}

    async def _calculate_date_proximity(self, date1, date2) -> Dict:
        """Calculate temporal proximity score."""
        factors = {
            'date_1': str(date1) if date1 else None,
            'date_2': str(date2) if date2 else None
        }

        if not date1 or not date2:
            factors['match_type'] = 'missing_date'
            return {'score': 0.5, 'factors': factors}

        try:
            # Convert to datetime if needed
            if isinstance(date1, str):
                date1 = datetime.fromisoformat(date1.replace('Z', '+00:00'))
            if isinstance(date2, str):
                date2 = datetime.fromisoformat(date2.replace('Z', '+00:00'))

            # Calculate days difference
            days_diff = abs((date1 - date2).days)
            max_days = self.advanced_config.get('date_window_days', 14)

            # Proximity scoring based on configured window
            if days_diff == 0:
                score = 1.0
            elif days_diff <= 1:
                score = 0.9
            elif days_diff <= 3:
                score = 0.8
            elif days_diff <= 7:
                score = 0.6
            elif days_diff <= max_days:
                score = 0.4
            elif days_diff <= max_days * 2:
                score = 0.2
            else:
                score = 0.1

            factors.update({
                'match_type': 'temporal_proximity',
                'days_difference': days_diff,
                'proximity_score': score,
                'max_window_days': max_days
            })

            return {'score': score, 'factors': factors}

        except Exception as e:
            logger.error(f"Error calculating date proximity: {e}")
            factors['match_type'] = 'error'
            return {'score': 0.5, 'factors': factors}

    async def _calculate_description_similarity(self, desc1: str, desc2: str) -> Dict:
        """Calculate description similarity using advanced text analysis."""
        factors = {
            'desc_1_length': len(desc1) if desc1 else 0,
            'desc_2_length': len(desc2) if desc2 else 0
        }

        if not desc1 or not desc2:
            factors['match_type'] = 'missing_description'
            return {'score': 0.5, 'factors': factors}

        # Normalize descriptions
        norm_desc1 = self.text_normalizer.normalize_description(desc1)
        norm_desc2 = self.text_normalizer.normalize_description(desc2)

        # Calculate similarity
        token_set_score = fuzz.token_set_ratio(norm_desc1, norm_desc2) / 100.0

        # Boost for length similarity
        length_ratio = min(len(norm_desc1), len(norm_desc2)) / max(len(norm_desc1), len(norm_desc2)) if max(len(norm_desc1), len(norm_desc2)) > 0 else 0
        length_boost = length_ratio * 0.1

        final_score = min(1.0, token_set_score + length_boost)

        factors.update({
            'match_type': 'text_analysis',
            'token_set_score': token_set_score,
            'length_ratio': length_ratio,
            'length_boost': length_boost,
            'final_score': final_score
        })

        return {'score': final_score, 'factors': factors}

    def _apply_similarity_boosts(self, base_score: float, scores: Dict, factors: Dict) -> float:
        """Apply contextual boosts to similarity score."""
        boosted_score = base_score

        # Cross-source boost (different sources, high similarity)
        cross_source_boost = self.advanced_config.get('cross_source_boost', 0.05)
        if self._is_cross_source_match(factors):
            boosted_score += cross_source_boost

        # High confidence boost
        if scores.get('title', 0) > 0.95 and scores.get('company', 0) > 0.9:
            boosted_score += 0.02

        # Recent posting boost
        if scores.get('date', 0) > 0.8:
            boosted_score += 0.01

        return min(1.0, boosted_score)

    def _calculate_confidence(self, scores: Dict, factors: Dict) -> float:
        """Calculate confidence in the similarity assessment."""
        # Base confidence from score distribution
        score_values = list(scores.values())
        if not score_values:
            return 0.0

        avg_score = sum(score_values) / len(score_values)
        score_variance = sum((s - avg_score) ** 2 for s in score_values) / len(score_values)

        # High variance means conflicting signals, lower confidence
        variance_penalty = min(0.3, score_variance * 2)

        base_confidence = avg_score - variance_penalty

        # Boost confidence for strong signals
        strong_factors = sum(1 for score in score_values if score > 0.8)
        confidence_boost = min(0.2, strong_factors * 0.05)

        return min(1.0, max(0.0, base_confidence + confidence_boost))

    # Helper methods for advanced processing

    def _load_title_synonyms(self) -> Dict[str, List[str]]:
        """Load job title synonyms for better matching."""
        return {
            'software engineer': ['software developer', 'programmer', 'software dev', 'coder'],
            'senior': ['sr', 'senior level', 'lead', 'principal'],
            'junior': ['jr', 'entry level', 'junior level', 'associate'],
            'full stack': ['fullstack', 'full-stack', 'frontend backend'],
            'front end': ['frontend', 'front-end', 'ui developer'],
            'back end': ['backend', 'back-end', 'server side'],
            'devops': ['dev ops', 'development operations', 'site reliability'],
            'ui/ux': ['ui ux', 'user interface user experience', 'product designer'],
            'qa': ['quality assurance', 'tester', 'test engineer', 'qe'],
            'data scientist': ['data analyst', 'machine learning engineer', 'ml engineer'],
            'product manager': ['pm', 'product owner', 'product lead'],
            'engineering manager': ['em', 'tech lead', 'development manager']
        }

    def _calculate_synonym_similarity(self, title1: str, title2: str) -> float:
        """Calculate similarity considering synonyms."""
        words1 = set(title1.lower().split())
        words2 = set(title2.lower().split())

        # Check for synonym matches
        for base_term, synonyms in self.title_synonyms.items():
            if base_term in title1.lower():
                for synonym in synonyms:
                    if synonym in title2.lower():
                        return 0.95
            if base_term in title2.lower():
                for synonym in synonyms:
                    if synonym in title1.lower():
                        return 0.95

        return fuzz.token_set_ratio(title1, title2) / 100.0

    def _normalize_company_name(self, company: str) -> str:
        """Advanced company name normalization."""
        return self.text_normalizer.normalize_company_name(company)

    def _are_company_aliases(self, company1: str, company2: str) -> bool:
        """Check if companies are known aliases."""
        aliases = {
            'google': ['alphabet', 'google cloud', 'youtube'],
            'meta': ['facebook', 'instagram', 'whatsapp'],
            'amazon': ['aws', 'amazon web services', 'twitch'],
            'microsoft': ['msft', 'xbox', 'linkedin'],
            'apple': ['apple inc'],
            'alphabet': ['google', 'youtube'],
            'bytedance': ['tiktok']
        }

        for main_company, company_aliases in aliases.items():
            if main_company in company1 and any(alias in company2 for alias in company_aliases):
                return True
            if main_company in company2 and any(alias in company1 for alias in company_aliases):
                return True

        return False

    def _calculate_geographic_similarity(self, loc1: str, loc2: str) -> float:
        """Calculate geographic similarity."""
        # Exact match
        if loc1 == loc2:
            return 1.0

        # Same city detection (basic)
        major_cities = ['san francisco', 'new york', 'los angeles', 'chicago', 'boston', 'seattle', 'austin', 'denver']
        for city in major_cities:
            if city in loc1 and city in loc2:
                return 0.9

        # Fuzzy location matching
        return fuzz.ratio(loc1, loc2) / 100.0

    def _extract_salary_range(self, salary: dict) -> Optional[Tuple[float, float]]:
        """Extract salary range with currency normalization."""
        try:
            min_sal = salary.get('min_salary') or salary.get('minimum')
            max_sal = salary.get('max_salary') or salary.get('maximum')

            if min_sal and max_sal:
                return (float(min_sal), float(max_sal))
            elif min_sal:
                return (float(min_sal), float(min_sal) * 1.2)
            elif max_sal:
                return (float(max_sal) * 0.8, float(max_sal))

            return None

        except (ValueError, TypeError):
            return None

    def _calculate_range_overlap(self, range1: Tuple[float, float], range2: Tuple[float, float]) -> float:
        """Calculate percentage overlap between two salary ranges."""
        min1, max1 = range1
        min2, max2 = range2

        overlap_start = max(min1, min2)
        overlap_end = min(max1, max2)

        if overlap_start >= overlap_end:
            return 0.0

        overlap_size = overlap_end - overlap_start
        range1_size = max1 - min1
        range2_size = max2 - min2
        avg_range_size = (range1_size + range2_size) / 2

        return min(1.0, overlap_size / avg_range_size) if avg_range_size > 0 else 1.0

    def _is_cross_source_match(self, factors: Dict) -> bool:
        """Detect if this is a cross-source duplicate."""
        # This would check source information in the factors
        # Implementation depends on how source info is passed
        return False