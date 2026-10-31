"""Company service for name normalization and fuzzy matching."""

import logging
import re
from typing import Dict, List, Optional, Tuple
from rapidfuzz import fuzz, utils
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.company import CompanyInfo, CompanyMatch, CompanyNormalizationResult, CompanyCreate
from ..repositories.company_repository import CompanyRepository

company_repo = CompanyRepository()
from ..core.database import db

logger = logging.getLogger(__name__)


class CompanyService:
    """Service for company-related operations with normalization and fuzzy matching."""
    
    # Common corporate suffixes to remove during normalization
    CORPORATE_SUFFIXES = [
        'Inc', 'Inc.', 'Incorporated',
        'LLC', 'L.L.C', 'L.L.C.',
        'Ltd', 'Ltd.', 'Limited',
        'Corp', 'Corp.', 'Corporation',
        'Co', 'Co.', 'Company',
        'LLP', 'L.L.P', 'L.L.P.',
        'LP', 'L.P', 'L.P.',
        'PLC', 'P.L.C', 'P.L.C.',
        'SA', 'S.A', 'S.A.',
        'AB', 'A.B', 'A.B.',
        'GmbH', 'AG', 'SRL', 'BV', 'NV',
        'Pty', 'Pty.', 'Pvt', 'Pvt.'
    ]
    
    # Common replacements for normalization
    NORMALIZATION_RULES = {
        ' and ': ' & ',
        ' And ': ' & ',
        ' AND ': ' & ',
        'The ': '',
        'THE ': '',
        ' Group': '',
        ' GROUP': '',
        ' International': '',
        ' INTERNATIONAL': '',
        ' Worldwide': '',
        ' WORLDWIDE': '',
        ' Global': '',
        ' GLOBAL': ''
    }
    
    # Known company aliases/variations
    COMPANY_ALIASES = {
        'IBM': ['International Business Machines', 'IBM Corp', 'IBM Corporation'],
        'Microsoft': ['MS', 'MSFT', 'Microsoft Corp', 'Microsoft Corporation'],
        'Google': ['Alphabet', 'Alphabet Inc', 'Google LLC'],
        'Amazon': ['AMZN', 'Amazon.com', 'Amazon Web Services', 'AWS'],
        'Apple': ['Apple Inc', 'Apple Computer'],
        'Meta': ['Facebook', 'Meta Platforms', 'Meta Inc'],
        'Salesforce': ['Salesforce.com', 'SFDC'],
        'Oracle': ['Oracle Corporation', 'Oracle Corp'],
        'SAP': ['SAP SE', 'SAP AG'],
        'Adobe': ['Adobe Systems', 'Adobe Inc']
    }
    
    @classmethod
    async def normalize_company_name(cls, name: str) -> CompanyNormalizationResult:
        """
        Normalize company name by removing suffixes, standardizing format.
        
        Args:
            name: Raw company name
            
        Returns:
            CompanyNormalizationResult with original, normalized name and applied rules
        """
        if not name or not name.strip():
            return CompanyNormalizationResult(
                original_name=name or "",
                normalized_name="",
                removed_suffixes=[],
                applied_rules=[],
                aliases_found=[]
            )
            
        original_name = name.strip()
        normalized = original_name
        removed_suffixes = []
        applied_rules = []
        aliases_found = []
        
        # Remove extra whitespace and standardize spacing
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        if normalized != original_name:
            applied_rules.append("standardized_spacing")
            
        # Apply normalization rules
        for rule_from, rule_to in cls.NORMALIZATION_RULES.items():
            if rule_from in normalized:
                normalized = normalized.replace(rule_from, rule_to)
                applied_rules.append(f"replaced_{rule_from.strip()}")
                
        # Remove corporate suffixes
        for suffix in cls.CORPORATE_SUFFIXES:
            patterns = [
                f" {re.escape(suffix)}$",  # End of string
                f", {re.escape(suffix)}$",  # After comma at end
                f" {re.escape(suffix)} ",  # Middle of string
                f", {re.escape(suffix)} "   # After comma in middle
            ]
            
            for pattern in patterns:
                if re.search(pattern, normalized, re.IGNORECASE):
                    normalized = re.sub(pattern, ' ', normalized, flags=re.IGNORECASE)
                    removed_suffixes.append(suffix)
                    break
                    
        # Check for known aliases
        normalized_upper = normalized.upper()
        for canonical, aliases in cls.COMPANY_ALIASES.items():
            if normalized_upper == canonical.upper():
                aliases_found = aliases
                break
            elif any(normalized_upper == alias.upper() for alias in aliases):
                normalized = canonical
                aliases_found = aliases
                applied_rules.append("resolved_alias")
                break
                
        # Final cleanup
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        normalized = normalized.strip('.,')
        
        return CompanyNormalizationResult(
            original_name=original_name,
            normalized_name=normalized,
            removed_suffixes=removed_suffixes,
            applied_rules=applied_rules,
            aliases_found=aliases_found
        )
        
    @classmethod
    async def find_company_matches(
        cls, 
        company_name: str, 
        session: Optional[AsyncSession] = None,
        similarity_threshold: float = 0.8,
        max_results: int = 5
    ) -> List[CompanyMatch]:
        """
        Find matching companies using fuzzy matching.
        
        Args:
            company_name: Company name to search for
            session: Database session
            similarity_threshold: Minimum similarity score (0.0-1.0)
            max_results: Maximum number of results to return
            
        Returns:
            List of CompanyMatch objects sorted by confidence score
        """
        if session is None:
            session = db.session
            
        if not company_name or not company_name.strip():
            return []
            
        try:
            # Normalize the search name
            normalization_result = await cls.normalize_company_name(company_name)
            search_name = normalization_result.normalized_name
            
            # First, try exact match on normalized name
            exact_matches = await company_repo.search_by_name(search_name, limit=1, session=session)
            if exact_matches and exact_matches[0].confidence_score == 1.0:
                return exact_matches
                
            # Get potential matches using database fuzzy search
            db_matches = await company_repo.search_by_name(company_name, limit=max_results * 2, session=session)
            
            # Also search by normalized name patterns
            normalized_matches = await company_repo.find_by_normalized_name(
                search_name, session=session
            )
            
            # Combine and deduplicate matches
            all_candidates = {}
            for match in db_matches:
                if match.company_id not in all_candidates:
                    all_candidates[match.company_id] = match
                    
            for company in normalized_matches:
                if company.id not in all_candidates:
                    # Calculate similarity score using RapidFuzz
                    score = cls._calculate_similarity(search_name, company.name)
                    all_candidates[company.id] = CompanyMatch(
                        company_id=company.id,
                        confidence_score=score,
                        match_type="normalized",
                        matched_name=company.name
                    )
                    
            # Filter by threshold and sort by confidence
            filtered_matches = [
                match for match in all_candidates.values() 
                if match.confidence_score >= similarity_threshold
            ]
            
            filtered_matches.sort(key=lambda x: x.confidence_score, reverse=True)
            
            # Add alternative matches to top results
            final_matches = []
            for match in filtered_matches[:max_results]:
                # Find alternative matches with similar scores
                alternatives = [
                    {"company_id": alt.company_id, "name": alt.matched_name, "score": alt.confidence_score}
                    for alt in filtered_matches[max_results:max_results+3]
                    if alt.confidence_score >= match.confidence_score - 0.1
                ]
                
                match.alternative_matches = alternatives
                final_matches.append(match)
                
            return final_matches
        except Exception as e:
            logger.error(f"Error finding company matches for '{company_name}': {e}")
            return []
            
    @classmethod
    def _calculate_similarity(cls, name1: str, name2: str) -> float:
        """
        Calculate similarity score between two company names using multiple RapidFuzz metrics.
        
        Args:
            name1: First company name
            name2: Second company name
            
        Returns:
            Similarity score between 0.0 and 1.0
        """
        if not name1 or not name2:
            return 0.0
            
        # Preprocess names for better comparison
        proc_name1 = utils.default_process(name1)
        proc_name2 = utils.default_process(name2)
        
        if proc_name1 == proc_name2:
            return 1.0
            
        # Calculate multiple similarity metrics
        ratios = []
        
        # Basic ratio
        ratios.append(fuzz.ratio(proc_name1, proc_name2) / 100.0)
        
        # Partial ratio (good for substring matches)
        ratios.append(fuzz.partial_ratio(proc_name1, proc_name2) / 100.0)
        
        # Token sort ratio (good for reordered words)
        ratios.append(fuzz.token_sort_ratio(proc_name1, proc_name2) / 100.0)
        
        # Token set ratio (good for subset matches)
        ratios.append(fuzz.token_set_ratio(proc_name1, proc_name2) / 100.0)
        
        # Weighted ratio (combines multiple metrics)
        ratios.append(fuzz.WRatio(proc_name1, proc_name2) / 100.0)
        
        # Return the maximum score (best match)
        return max(ratios)
        
    @classmethod
    async def find_or_create_company(
        cls, 
        company_info: CompanyInfo, 
        session: Optional[AsyncSession] = None,
        auto_create: bool = True
    ) -> Tuple[int, bool]:
        """
        Find existing company or create new one.
        
        Args:
            company_info: Company information
            session: Database session
            auto_create: Whether to create company if not found
            
        Returns:
            Tuple of (company_id, was_created)
        """
        if session is None:
            session = db.session
            
        try:
            # Normalize company name
            normalization_result = await cls.normalize_company_name(company_info.name)
            
            # Try to find existing company
            matches = await cls.find_company_matches(
                company_info.name, 
                session=session, 
                similarity_threshold=0.9,  # High threshold for auto-matching
                max_results=1
            )
            
            if matches and matches[0].confidence_score >= 0.95:
                # High confidence match found
                logger.info(
                    f"Found existing company match: {company_info.name} -> "
                    f"{matches[0].matched_name} (score: {matches[0].confidence_score})"
                )
                return matches[0].company_id, False
                
            if not auto_create:
                return None, False
                
            # Create new company
            company_data = CompanyCreate(
                name=company_info.name,
                normalized_name=normalization_result.normalized_name,
                slug="",  # Will be generated in repository
                website=company_info.website,
                logo_url=company_info.logo_url,
                description=company_info.description,
                headquarters=company_info.location,
                industry=company_info.industry,
                founded_year=company_info.founded_year,
                employee_count=company_info.employee_count
            )
            
            new_company = await company_repo.create_with_slug(
                company_data.dict(exclude_none=True), 
                session=session
            )
            
            logger.info(f"Created new company: {company_info.name} (ID: {new_company.id})")
            return new_company.id, True
        except Exception as e:
            logger.error(f"Error in find_or_create_company for '{company_info.name}': {e}")
            raise
            
    @classmethod
    async def match_company(
        cls, 
        company_name: str, 
        session: Optional[AsyncSession] = None
    ) -> Optional[CompanyMatch]:
        """
        Find the best matching company for a name.
        
        Args:
            company_name: Company name to match
            session: Database session
            
        Returns:
            Best CompanyMatch or None if no good match found
        """
        matches = await cls.find_company_matches(
            company_name, 
            session=session, 
            similarity_threshold=0.7,  # Lower threshold for suggestions
            max_results=1
        )
        
        return matches[0] if matches else None
        
    @classmethod
    async def suggest_company_corrections(
        cls, 
        company_name: str, 
        session: Optional[AsyncSession] = None,
        max_suggestions: int = 5
    ) -> List[Dict[str, any]]:
        """
        Suggest corrections for a company name.
        
        Args:
            company_name: Potentially misspelled company name
            session: Database session
            max_suggestions: Maximum number of suggestions
            
        Returns:
            List of suggestions with company info and confidence scores
        """
        if session is None:
            session = db.session
            
        try:
            # Find matches with lower threshold for suggestions
            matches = await cls.find_company_matches(
                company_name, 
                session=session, 
                similarity_threshold=0.4,  # Low threshold for suggestions
                max_results=max_suggestions
            )
            
            suggestions = []
            for match in matches:
                # Get company details
                company = await company_repo.get_by_id(match.company_id, session)
                if company:
                    suggestions.append({
                        "company_id": company.id,
                        "name": company.name,
                        "normalized_name": match.matched_name,
                        "confidence_score": match.confidence_score,
                        "match_type": match.match_type,
                        "industry": company.industry,
                        "active_jobs": company.active_jobs_count,
                        "website": company.website
                    })
                    
            return suggestions
        except Exception as e:
            logger.error(f"Error getting company suggestions for '{company_name}': {e}")
            return []
            
    @classmethod
    async def validate_company_name(cls, company_name: str) -> Dict[str, any]:
        """
        Validate and analyze a company name.
        
        Args:
            company_name: Company name to validate
            
        Returns:
            Validation results with suggestions and normalization info
        """
        if not company_name or not company_name.strip():
            return {
                "is_valid": False,
                "issues": ["empty_name"],
                "normalized": "",
                "suggestions": []
            }
            
        issues = []
        
        # Check for common issues
        if len(company_name.strip()) < 2:
            issues.append("too_short")
            
        if len(company_name.strip()) > 255:
            issues.append("too_long")
            
        if re.search(r'^[0-9]+$', company_name.strip()):
            issues.append("numbers_only")
            
        if re.search(r'[<>{}[\]\\]', company_name):
            issues.append("invalid_characters")
            
        # Normalize the name
        normalization_result = await cls.normalize_company_name(company_name)
        
        # Check if it looks like a person's name instead of a company
        name_parts = company_name.split()
        if len(name_parts) == 2 and all(part.istitle() for part in name_parts):
            if not any(suffix in company_name for suffix in cls.CORPORATE_SUFFIXES):
                issues.append("possible_person_name")
                
        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
            "original_name": normalization_result.original_name,
            "normalized_name": normalization_result.normalized_name,
            "removed_suffixes": normalization_result.removed_suffixes,
            "applied_rules": normalization_result.applied_rules,
            "aliases_found": normalization_result.aliases_found
        }