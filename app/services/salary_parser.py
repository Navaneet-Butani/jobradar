"""Salary parsing service with multi-currency support."""

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Optional, Dict, List, Tuple, Union
from dataclasses import dataclass

from ..models.job import SalaryInfo
from ..models.common import Currency, SalaryPeriod
from ..core.exceptions import ValidationError

logger = logging.getLogger(__name__)


@dataclass
class ParsedSalary:
    """Result of salary parsing with confidence and metadata."""
    min_salary: Optional[Decimal] = None
    max_salary: Optional[Decimal] = None
    currency: Currency = Currency.USD
    period: SalaryPeriod = SalaryPeriod.YEAR
    is_disclosed: bool = False
    is_negotiable: bool = False
    confidence: float = 0.0
    raw_salary: Optional[str] = None
    parsing_method: str = "unknown"
    parsing_notes: List[str] = None
    
    # Additional compensation info
    bonus_info: Optional[str] = None
    equity_info: Optional[str] = None
    benefits_mentioned: List[str] = None
    
    def __post_init__(self):
        if self.parsing_notes is None:
            self.parsing_notes = []
        if self.benefits_mentioned is None:
            self.benefits_mentioned = []


class SalaryParser:
    """Service for parsing salary information from various formats."""
    
    # Currency symbols and their codes
    CURRENCY_SYMBOLS = {
        '$': Currency.USD,
        '£': Currency.GBP,
        '€': Currency.EUR,
        '¥': Currency.JPY,
        '₹': Currency.INR,
        'C$': Currency.CAD,
        'A$': Currency.AUD,
        'S$': Currency.SGD,
        'CHF': Currency.CHF,
        'SEK': Currency.SEK,
        'NOK': Currency.NOK,
        'DKK': Currency.DKK,
    }
    
    # Currency names and codes
    CURRENCY_NAMES = {
        'usd': Currency.USD, 'dollar': Currency.USD, 'dollars': Currency.USD,
        'eur': Currency.EUR, 'euro': Currency.EUR, 'euros': Currency.EUR,
        'gbp': Currency.GBP, 'pound': Currency.GBP, 'pounds': Currency.GBP,
        'jpy': Currency.JPY, 'yen': Currency.JPY,
        'inr': Currency.INR, 'rupee': Currency.INR, 'rupees': Currency.INR,
        'cad': Currency.CAD, 'canadian': Currency.CAD,
        'aud': Currency.AUD, 'australian': Currency.AUD,
        'sgd': Currency.SGD, 'singapore': Currency.SGD,
        'chf': Currency.CHF, 'swiss': Currency.CHF,
        'sek': Currency.SEK, 'swedish': Currency.SEK,
        'nok': Currency.NOK, 'norwegian': Currency.NOK,
        'dkk': Currency.DKK, 'danish': Currency.DKK,
    }
    
    # Period indicators
    PERIOD_INDICATORS = {
        SalaryPeriod.HOUR: ['hour', 'hr', 'hourly', 'per hour', '/hr', '/hour'],
        SalaryPeriod.DAY: ['day', 'daily', 'per day', '/day'],
        SalaryPeriod.WEEK: ['week', 'weekly', 'per week', '/week', '/wk'],
        SalaryPeriod.MONTH: ['month', 'monthly', 'per month', '/month', '/mo'],
        SalaryPeriod.YEAR: ['year', 'yearly', 'annual', 'annually', 'per year', '/year', '/yr', 'pa', 'p.a.', 'per annum'],
    }
    
    # Salary range patterns (ordered by specificity)
    SALARY_PATTERNS = [
        # Range with currency symbols: $80,000 - $120,000
        r'([A-Z$£€¥₹]+)\s*([0-9,]+(?:\.[0-9]+)?)\s*[-–—to]\s*\1?\s*([0-9,]+(?:\.[0-9]+)?)',
        
        # Range with currency at end: 80,000 - 120,000 USD
        r'([0-9,]+(?:\.[0-9]+)?)\s*[-–—to]\s*([0-9,]+(?:\.[0-9]+)?)\s*([A-Z]{3}|dollars?|euros?|pounds?)',
        
        # Single amount with currency symbol: $80,000
        r'([A-Z$£€¥₹]+)\s*([0-9,]+(?:\.[0-9]+)?)',
        
        # Single amount with currency name: 80,000 USD
        r'([0-9,]+(?:\.[0-9]+)?)\s*([A-Z]{3}|dollars?|euros?|pounds?)',
        
        # Range without explicit currency: 80,000 - 120,000
        r'([0-9,]+(?:\.[0-9]+)?)\s*[-–—to]\s*([0-9,]+(?:\.[0-9]+)?)',
        
        # K notation ranges: 80k - 120k
        r'([0-9,]+(?:\.[0-9]+)?)\s*k\s*[-–—to]\s*([0-9,]+(?:\.[0-9]+)?)\s*k',
        
        # Single K notation: 80k
        r'([0-9,]+(?:\.[0-9]+)?)\s*k(?:\s|$)',
        
        # Salary with "up to": up to $80,000
        r'(?:up\s+to|upto|max|maximum)\s*([A-Z$£€¥₹]+)?\s*([0-9,]+(?:\.[0-9]+)?)',
        
        # Starting salary: starting at $60,000
        r'(?:starting\s+at|from|minimum)\s*([A-Z$£€¥₹]+)?\s*([0-9,]+(?:\.[0-9]+)?)',
        
        # Complex ranges: $60k-$80k per year
        r'([A-Z$£€¥₹]+)\s*([0-9,]+(?:\.[0-9]+)?)\s*k?\s*[-–—to]\s*\1?\s*([0-9,]+(?:\.[0-9]+)?)\s*k?',
    ]
    
    # Negotiable indicators
    NEGOTIABLE_KEYWORDS = [
        'negotiable', 'competitive', 'commensurate', 'doe', 'depending on experience',
        'based on experience', 'market rate', 'open', 'flexible', 'to be discussed'
    ]

    # India: not-disclosed indicators (Instahyre/Naukri-style listings commonly say this
    # instead of omitting the field entirely)
    NOT_DISCLOSED_KEYWORDS = [
        'not disclosed', 'undisclosed', 'confidential', 'best in industry'
    ]

    # India: lakh/crore notation. 1 lakh = 100,000; 1 crore = 10,000,000.
    # Range first (more specific), then single amount.
    INDIAN_NOTATION_MULTIPLIERS = {
        'lakh': Decimal('100000'), 'lakhs': Decimal('100000'),
        'lac': Decimal('100000'), 'lacs': Decimal('100000'),
        'l': Decimal('100000'), 'lpa': Decimal('100000'),
        'cr': Decimal('10000000'), 'crore': Decimal('10000000'), 'crores': Decimal('10000000'),
    }
    INDIAN_NOTATION_RANGE_PATTERN = re.compile(
        r'([0-9]+(?:\.[0-9]+)?)\s*[-–—]\s*([0-9]+(?:\.[0-9]+)?)\s*'
        r'(lakhs?|lacs?|lpa|cr|crores?)\b',
        re.IGNORECASE
    )
    INDIAN_NOTATION_SINGLE_PATTERN = re.compile(
        r'([0-9]+(?:\.[0-9]+)?)\s*(lakhs?|lacs?|lpa|cr|crores?|l)\b',
        re.IGNORECASE
    )
    
    # Bonus/equity indicators
    BONUS_KEYWORDS = [
        'bonus', 'performance bonus', 'annual bonus', 'signing bonus', 'retention bonus'
    ]
    
    EQUITY_KEYWORDS = [
        'equity', 'stock options', 'stocks', 'shares', 'rsu', 'restricted stock',
        'stock grants', 'employee stock', 'espp'
    ]
    
    # Benefits keywords
    BENEFITS_KEYWORDS = [
        'health insurance', 'medical', 'dental', 'vision', '401k', 'retirement',
        'pto', 'paid time off', 'vacation', 'sick leave', 'flexible hours',
        'remote work', 'gym', 'wellness', 'education', 'training'
    ]
    
    def __init__(self):
        """Initialize the salary parser."""
        self.logger = logging.getLogger(f"{__name__}")
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for better performance."""
        self.compiled_patterns = []
        for pattern in self.SALARY_PATTERNS:
            try:
                self.compiled_patterns.append(re.compile(pattern, re.IGNORECASE))
            except re.error as e:
                self.logger.warning(f"Failed to compile pattern {pattern}: {e}")
    
    async def parse_salary(self, salary_text: str, context: Optional[str] = None) -> ParsedSalary:
        """Parse salary information from text."""
        try:
            if not salary_text or not salary_text.strip():
                return ParsedSalary(
                    raw_salary=salary_text,
                    confidence=0.0,
                    parsing_notes=["Empty salary text"]
                )
            
            text = salary_text.strip()
            result = ParsedSalary(raw_salary=text)

            # "Not disclosed" is an explicit signal, not a parsing failure —
            # short-circuit with high confidence rather than falling through
            # to contextual number-guessing.
            if self._is_not_disclosed(text):
                return ParsedSalary(
                    raw_salary=text,
                    is_disclosed=False,
                    confidence=0.9,
                    parsing_method="not_disclosed",
                    parsing_notes=["Salary explicitly marked not disclosed"]
                )

            # Check for negotiable indicators first
            if self._is_negotiable(text):
                result.is_negotiable = True
                result.parsing_notes.append("Detected negotiable salary")

            # Try different parsing strategies
            parsing_strategies = [
                self._parse_indian_notation,  # tried first — "12-16 Lacs" would
                                               # otherwise match the generic bare-range
                                               # pattern and silently drop the multiplier
                self._parse_structured_salary,
                self._parse_range_salary,
                self._parse_single_amount,
                self._parse_k_notation,
                self._parse_contextual_salary
            ]
            
            best_result = None
            best_confidence = 0.0
            
            for strategy in parsing_strategies:
                try:
                    parsed = await strategy(text, context)
                    if parsed and parsed.confidence > best_confidence:
                        # Preserve original values
                        parsed.raw_salary = text
                        parsed.is_negotiable = result.is_negotiable
                        best_result = parsed
                        best_confidence = parsed.confidence
                except Exception as e:
                    self.logger.debug(f"Salary parsing strategy failed: {e}")
                    continue
            
            if best_result:
                # Extract additional compensation info
                best_result.bonus_info = self._extract_bonus_info(text)
                best_result.equity_info = self._extract_equity_info(text)
                best_result.benefits_mentioned = self._extract_benefits(text)
                
                # Validate and normalize the result
                best_result = self._validate_and_normalize(best_result)
                return best_result
            
            # Fallback result
            result.confidence = 0.1
            result.parsing_notes.append("Could not parse salary information")
            return result
            
        except Exception as e:
            self.logger.error(f"Error parsing salary '{salary_text}': {e}")
            return ParsedSalary(
                raw_salary=salary_text,
                confidence=0.0,
                parsing_notes=[f"Parsing error: {str(e)}"]
            )
    
    async def extract_salary_from_text(self, text: str) -> List[ParsedSalary]:
        """Extract all salary mentions from a longer text."""
        try:
            salaries = []
            
            # Look for salary patterns in the text
            for pattern in self.compiled_patterns:
                matches = pattern.finditer(text)
                for match in matches:
                    salary_text = match.group(0)
                    parsed = await self.parse_salary(salary_text, context=text)
                    if parsed.confidence > 0.5:  # Only include confident matches
                        salaries.append(parsed)
            
            # Remove duplicates and return best matches
            return self._deduplicate_salaries(salaries)
            
        except Exception as e:
            self.logger.error(f"Error extracting salaries from text: {e}")
            return []
    
    async def normalize_salary_to_annual(self, salary: ParsedSalary) -> ParsedSalary:
        """Convert salary to annual equivalent."""
        try:
            if not salary.min_salary and not salary.max_salary:
                return salary
            
            # Conversion factors to annual
            conversion_factors = {
                SalaryPeriod.HOUR: 2080,  # 40 hours/week * 52 weeks
                SalaryPeriod.DAY: 260,    # 5 days/week * 52 weeks
                SalaryPeriod.WEEK: 52,    # 52 weeks/year
                SalaryPeriod.MONTH: 12,   # 12 months/year
                SalaryPeriod.YEAR: 1      # Already annual
            }
            
            factor = conversion_factors.get(salary.period, 1)
            
            normalized = ParsedSalary(
                min_salary=salary.min_salary * factor if salary.min_salary else None,
                max_salary=salary.max_salary * factor if salary.max_salary else None,
                currency=salary.currency,
                period=SalaryPeriod.YEAR,
                is_disclosed=salary.is_disclosed,
                is_negotiable=salary.is_negotiable,
                confidence=salary.confidence,
                raw_salary=salary.raw_salary,
                parsing_method=f"{salary.parsing_method}_normalized",
                parsing_notes=salary.parsing_notes + [f"Converted from {salary.period.value} to annual"],
                bonus_info=salary.bonus_info,
                equity_info=salary.equity_info,
                benefits_mentioned=salary.benefits_mentioned
            )
            
            return normalized
            
        except Exception as e:
            self.logger.error(f"Error normalizing salary: {e}")
            return salary
    
    # Private parsing methods
    
    async def _parse_structured_salary(self, text: str, context: Optional[str]) -> Optional[ParsedSalary]:
        """Parse well-structured salary information."""
        # Look for range patterns first
        range_pattern = self.compiled_patterns[0]  # Most specific range pattern
        match = range_pattern.search(text)
        
        if match:
            groups = match.groups()
            if len(groups) >= 3:
                currency_symbol = groups[0]
                min_amount = groups[1]
                max_amount = groups[2]
                
                currency = self._detect_currency(currency_symbol)
                period = self._detect_period(text)
                
                try:
                    min_sal = self._parse_amount(min_amount)
                    max_sal = self._parse_amount(max_amount)
                    
                    if min_sal and max_sal and min_sal <= max_sal:
                        return ParsedSalary(
                            min_salary=min_sal,
                            max_salary=max_sal,
                            currency=currency,
                            period=period,
                            is_disclosed=True,
                            confidence=0.95,
                            parsing_method="structured_range"
                        )
                except Exception:
                    pass
        
        return None
    
    async def _parse_range_salary(self, text: str, context: Optional[str]) -> Optional[ParsedSalary]:
        """Parse salary ranges with various formats."""
        # Try different range patterns
        for i, pattern in enumerate(self.compiled_patterns[:4]):  # First 4 are range patterns
            match = pattern.search(text)
            if match:
                groups = match.groups()
                
                try:
                    if len(groups) == 3:
                        # Format: amount - amount currency
                        min_amount, max_amount, currency_indicator = groups
                        min_sal = self._parse_amount(min_amount)
                        max_sal = self._parse_amount(max_amount)
                        currency = self._detect_currency(currency_indicator)
                    elif len(groups) == 2:
                        # Format: currency amount - amount
                        currency_indicator, amount = groups[0], groups[1]
                        min_sal = self._parse_amount(amount)
                        max_sal = None
                        currency = self._detect_currency(currency_indicator)
                    else:
                        continue
                    
                    if min_sal and (max_sal is None or min_sal <= max_sal):
                        period = self._detect_period(text)
                        confidence = 0.9 - (i * 0.1)  # Higher confidence for more specific patterns
                        
                        return ParsedSalary(
                            min_salary=min_sal,
                            max_salary=max_sal,
                            currency=currency,
                            period=period,
                            is_disclosed=True,
                            confidence=max(0.5, confidence),
                            parsing_method=f"range_pattern_{i}"
                        )
                except Exception:
                    continue
        
        return None
    
    async def _parse_single_amount(self, text: str, context: Optional[str]) -> Optional[ParsedSalary]:
        """Parse single salary amounts."""
        # Look for single amount patterns
        for i, pattern in enumerate(self.compiled_patterns[4:8]):  # Single amount patterns
            match = pattern.search(text)
            if match:
                groups = match.groups()
                
                try:
                    if len(groups) == 2:
                        amount_str, currency_indicator = groups
                        amount = self._parse_amount(amount_str)
                        currency = self._detect_currency(currency_indicator)
                    else:
                        continue
                    
                    if amount:
                        period = self._detect_period(text)
                        confidence = 0.8 - (i * 0.1)
                        
                        # Determine if it's min or max based on context
                        is_max_salary = any(keyword in text.lower() for keyword in ['up to', 'maximum', 'max'])
                        is_min_salary = any(keyword in text.lower() for keyword in ['starting', 'from', 'minimum'])
                        
                        return ParsedSalary(
                            min_salary=amount if not is_max_salary else None,
                            max_salary=amount if is_max_salary else None,
                            currency=currency,
                            period=period,
                            is_disclosed=True,
                            confidence=max(0.5, confidence),
                            parsing_method=f"single_amount_{i}"
                        )
                except Exception:
                    continue
        
        return None
    
    async def _parse_k_notation(self, text: str, context: Optional[str]) -> Optional[ParsedSalary]:
        """Parse salary amounts with 'k' notation."""
        # K notation patterns
        k_patterns = [
            r'([0-9,]+(?:\.[0-9]+)?)\s*k\s*[-–—to]\s*([0-9,]+(?:\.[0-9]+)?)\s*k',  # Range: 80k - 120k
            r'([0-9,]+(?:\.[0-9]+)?)\s*k(?:\s|$)',  # Single: 80k
        ]
        
        for i, pattern_str in enumerate(k_patterns):
            pattern = re.compile(pattern_str, re.IGNORECASE)
            match = pattern.search(text)
            
            if match:
                groups = match.groups()
                
                try:
                    if len(groups) == 2 and groups[1]:  # Range
                        min_amount = self._parse_amount(groups[0]) * 1000
                        max_amount = self._parse_amount(groups[1]) * 1000
                    elif len(groups) >= 1:  # Single amount
                        amount = self._parse_amount(groups[0]) * 1000
                        min_amount = amount
                        max_amount = None
                    else:
                        continue
                    
                    currency = self._detect_currency_from_context(text, context)
                    period = self._detect_period(text)
                    confidence = 0.85 - (i * 0.1)
                    
                    return ParsedSalary(
                        min_salary=min_amount,
                        max_salary=max_amount,
                        currency=currency,
                        period=period,
                        is_disclosed=True,
                        confidence=confidence,
                        parsing_method=f"k_notation_{i}"
                    )
                except Exception:
                    continue
        
        return None
    
    async def _parse_contextual_salary(self, text: str, context: Optional[str]) -> Optional[ParsedSalary]:
        """Parse salary using contextual clues."""
        # Look for any numbers that might be salaries
        number_pattern = re.compile(r'([0-9,]+(?:\.[0-9]+)?)')
        numbers = number_pattern.findall(text)
        
        if not numbers:
            return None
        
        # Try to determine if these could be salary amounts
        potential_salaries = []
        for num_str in numbers:
            try:
                amount = self._parse_amount(num_str)
                if amount and self._is_reasonable_salary(amount):
                    potential_salaries.append(amount)
            except Exception:
                continue
        
        if potential_salaries:
            # Use the largest reasonable amount
            salary_amount = max(potential_salaries)
            currency = self._detect_currency_from_context(text, context)
            period = self._detect_period(text)
            
            return ParsedSalary(
                min_salary=salary_amount,
                currency=currency,
                period=period,
                is_disclosed=True,
                confidence=0.4,  # Low confidence for contextual parsing
                parsing_method="contextual",
                parsing_notes=["Extracted from context - low confidence"]
            )
        
        return None
    
    # Helper methods
    
    def _parse_amount(self, amount_str: str) -> Optional[Decimal]:
        """Parse amount string to Decimal."""
        try:
            # Remove commas and whitespace
            cleaned = re.sub(r'[,\s]', '', amount_str)
            
            # Handle decimal points
            if '.' in cleaned:
                return Decimal(cleaned)
            else:
                return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return None
    
    def _detect_currency(self, indicator: str) -> Currency:
        """Detect currency from symbol or name."""
        if not indicator:
            return Currency.USD  # Default
        
        indicator_clean = indicator.strip().lower()
        
        # Check symbols first
        for symbol, currency in self.CURRENCY_SYMBOLS.items():
            if symbol.lower() in indicator_clean:
                return currency
        
        # Check names
        for name, currency in self.CURRENCY_NAMES.items():
            if name in indicator_clean:
                return currency
        
        return Currency.USD  # Default fallback
    
    def _detect_currency_from_context(self, text: str, context: Optional[str]) -> Currency:
        """Detect currency from text context."""
        combined_text = f"{text} {context or ''}".lower()
        
        # Look for currency indicators in the combined text
        for symbol, currency in self.CURRENCY_SYMBOLS.items():
            if symbol.lower() in combined_text:
                return currency
        
        for name, currency in self.CURRENCY_NAMES.items():
            if name in combined_text:
                return currency
        
        return Currency.USD  # Default
    
    def _detect_period(self, text: str) -> SalaryPeriod:
        """Detect salary period from text."""
        text_lower = text.lower()
        
        # Check each period type
        for period, indicators in self.PERIOD_INDICATORS.items():
            for indicator in indicators:
                if indicator in text_lower:
                    return period
        
        return SalaryPeriod.YEAR  # Default to annual
    
    def _is_negotiable(self, text: str) -> bool:
        """Check if salary is marked as negotiable."""
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.NEGOTIABLE_KEYWORDS)

    def _is_not_disclosed(self, text: str) -> bool:
        """Check if salary is explicitly marked as not disclosed."""
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.NOT_DISCLOSED_KEYWORDS)

    async def _parse_indian_notation(self, text: str, context: Optional[str]) -> Optional[ParsedSalary]:
        """Parse Indian lakh/crore notation: '12-16 Lacs P.A.', '1-5 Cr', '8 LPA', '12L'."""
        range_match = self.INDIAN_NOTATION_RANGE_PATTERN.search(text)
        if range_match:
            min_str, max_str, unit = range_match.groups()
            multiplier = self.INDIAN_NOTATION_MULTIPLIERS.get(unit.lower())
            if multiplier:
                try:
                    min_sal = self._parse_amount(min_str) * multiplier
                    max_sal = self._parse_amount(max_str) * multiplier
                    if min_sal and max_sal:
                        return ParsedSalary(
                            min_salary=min_sal,
                            max_salary=max_sal,
                            currency=Currency.INR,
                            period=SalaryPeriod.YEAR,
                            is_disclosed=True,
                            confidence=0.97,
                            parsing_method="indian_notation_range"
                        )
                except Exception:
                    pass

        single_match = self.INDIAN_NOTATION_SINGLE_PATTERN.search(text)
        if single_match:
            amount_str, unit = single_match.groups()
            multiplier = self.INDIAN_NOTATION_MULTIPLIERS.get(unit.lower())
            if multiplier:
                try:
                    amount = self._parse_amount(amount_str) * multiplier
                    if amount:
                        return ParsedSalary(
                            min_salary=amount,
                            currency=Currency.INR,
                            period=SalaryPeriod.YEAR,
                            is_disclosed=True,
                            confidence=0.95,
                            parsing_method="indian_notation_single"
                        )
                except Exception:
                    pass

        return None
    
    def _is_reasonable_salary(self, amount: Decimal) -> bool:
        """Check if amount is a reasonable salary."""
        # Basic sanity checks for salary amounts
        return 1000 <= amount <= 10000000  # $1K to $10M range
    
    def _extract_bonus_info(self, text: str) -> Optional[str]:
        """Extract bonus information from text."""
        text_lower = text.lower()
        
        for keyword in self.BONUS_KEYWORDS:
            if keyword in text_lower:
                # Try to extract the bonus-related sentence
                sentences = text.split('.')
                for sentence in sentences:
                    if keyword in sentence.lower():
                        return sentence.strip()
        
        return None
    
    def _extract_equity_info(self, text: str) -> Optional[str]:
        """Extract equity information from text."""
        text_lower = text.lower()
        
        for keyword in self.EQUITY_KEYWORDS:
            if keyword in text_lower:
                # Try to extract the equity-related sentence
                sentences = text.split('.')
                for sentence in sentences:
                    if keyword in sentence.lower():
                        return sentence.strip()
        
        return None
    
    def _extract_benefits(self, text: str) -> List[str]:
        """Extract mentioned benefits from text."""
        benefits = []
        text_lower = text.lower()
        
        for benefit in self.BENEFITS_KEYWORDS:
            if benefit in text_lower:
                benefits.append(benefit.title())
        
        return benefits
    
    def _validate_and_normalize(self, salary: ParsedSalary) -> ParsedSalary:
        """Validate and normalize parsed salary."""
        try:
            # Ensure min <= max if both are present
            if (salary.min_salary and salary.max_salary and 
                salary.min_salary > salary.max_salary):
                # Swap them
                salary.min_salary, salary.max_salary = salary.max_salary, salary.min_salary
                salary.parsing_notes.append("Swapped min/max values")
            
            # Check for unreasonable amounts
            if salary.min_salary and not self._is_reasonable_salary(salary.min_salary):
                salary.confidence *= 0.5
                salary.parsing_notes.append("Min salary amount seems unreasonable")
            
            if salary.max_salary and not self._is_reasonable_salary(salary.max_salary):
                salary.confidence *= 0.5
                salary.parsing_notes.append("Max salary amount seems unreasonable")
            
            # Adjust confidence based on period detection
            if salary.period == SalaryPeriod.YEAR:
                salary.confidence = min(1.0, salary.confidence + 0.1)
            
            return salary
            
        except Exception as e:
            salary.parsing_notes.append(f"Validation error: {str(e)}")
            return salary
    
    def _deduplicate_salaries(self, salaries: List[ParsedSalary]) -> List[ParsedSalary]:
        """Remove duplicate salary entries."""
        if not salaries:
            return []
        
        # Sort by confidence descending
        salaries.sort(key=lambda x: x.confidence, reverse=True)
        
        # Keep only unique salaries (by amount and currency)
        seen = set()
        unique_salaries = []
        
        for salary in salaries:
            key = (salary.min_salary, salary.max_salary, salary.currency)
            if key not in seen:
                seen.add(key)
                unique_salaries.append(salary)
        
        return unique_salaries[:3]  # Return top 3 unique matches