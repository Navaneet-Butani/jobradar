"""Location parsing and normalization service."""

import logging
import re
from typing import Optional, Dict, List, Tuple, Set
from dataclasses import dataclass

from ..models.job import LocationInfo
from ..models.common import WorkArrangement
from ..core.exceptions import ValidationError

logger = logging.getLogger(__name__)


@dataclass
class ParsedLocation:
    """Result of location parsing with confidence."""
    city: Optional[str] = None
    state_province: Optional[str] = None
    country: str = "Unknown"
    country_code: Optional[str] = None
    is_remote: bool = False
    work_arrangement: Optional[WorkArrangement] = None
    confidence: float = 0.0
    raw_location: Optional[str] = None
    parsing_notes: List[str] = None
    
    def __post_init__(self):
        if self.parsing_notes is None:
            self.parsing_notes = []


class LocationParser:
    """Service for parsing and normalizing job locations."""
    
    # Remote work indicators
    REMOTE_KEYWORDS = {
        'remote', 'work from home', 'wfh', 'distributed', 'anywhere', 
        'telecommute', 'virtual', 'home-based', 'location independent',
        'fully remote', 'remote work', 'remote position', 'remote job',
        'work remotely', 'home office', 'telework', 'distance work'
    }
    
    # Hybrid work indicators
    HYBRID_KEYWORDS = {
        'hybrid', 'flexible', 'mix of remote', 'part remote', 'semi-remote',
        'remote/office', 'office/remote', 'flexible location', 'hybrid work'
    }
    
    # On-site indicators
    ONSITE_KEYWORDS = {
        'on-site', 'onsite', 'in-office', 'office-based', 'on location',
        'on premises', 'in person', 'at office', 'office required'
    }
    
    # Country mappings and codes
    COUNTRY_MAPPINGS = {
        # Major countries with common variations
        'united states': {'country': 'United States', 'code': 'US', 'aliases': ['usa', 'us', 'america', 'united states of america']},
        'canada': {'country': 'Canada', 'code': 'CA', 'aliases': ['can', 'ca']},
        'united kingdom': {'country': 'United Kingdom', 'code': 'GB', 'aliases': ['uk', 'gb', 'great britain', 'england', 'britain']},
        'germany': {'country': 'Germany', 'code': 'DE', 'aliases': ['de', 'deutschland']},
        'france': {'country': 'France', 'code': 'FR', 'aliases': ['fr']},
        'australia': {'country': 'Australia', 'code': 'AU', 'aliases': ['au', 'aus']},
        'india': {'country': 'India', 'code': 'IN', 'aliases': ['in', 'ind']},
        'netherlands': {'country': 'Netherlands', 'code': 'NL', 'aliases': ['nl', 'holland']},
        'singapore': {'country': 'Singapore', 'code': 'SG', 'aliases': ['sg']},
        'japan': {'country': 'Japan', 'code': 'JP', 'aliases': ['jp']},
        'south korea': {'country': 'South Korea', 'code': 'KR', 'aliases': ['korea', 'kr']},
        'brazil': {'country': 'Brazil', 'code': 'BR', 'aliases': ['br', 'brasil']},
        'mexico': {'country': 'Mexico', 'code': 'MX', 'aliases': ['mx']},
        'spain': {'country': 'Spain', 'code': 'ES', 'aliases': ['es', 'espana']},
        'italy': {'country': 'Italy', 'code': 'IT', 'aliases': ['it', 'italia']},
        'switzerland': {'country': 'Switzerland', 'code': 'CH', 'aliases': ['ch', 'schweiz']},
        'sweden': {'country': 'Sweden', 'code': 'SE', 'aliases': ['se']},
        'norway': {'country': 'Norway', 'code': 'NO', 'aliases': ['no']},
        'denmark': {'country': 'Denmark', 'code': 'DK', 'aliases': ['dk']},
        'ireland': {'country': 'Ireland', 'code': 'IE', 'aliases': ['ie']},
        'new zealand': {'country': 'New Zealand', 'code': 'NZ', 'aliases': ['nz']},
    }
    
    # US States with abbreviations
    US_STATES = {
        'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR', 'california': 'CA',
        'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE', 'florida': 'FL', 'georgia': 'GA',
        'hawaii': 'HI', 'idaho': 'ID', 'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA',
        'kansas': 'KS', 'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
        'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS',
        'missouri': 'MO', 'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV', 'new hampshire': 'NH',
        'new jersey': 'NJ', 'new mexico': 'NM', 'new york': 'NY', 'north carolina': 'NC',
        'north dakota': 'ND', 'ohio': 'OH', 'oklahoma': 'OK', 'oregon': 'OR', 'pennsylvania': 'PA',
        'rhode island': 'RI', 'south carolina': 'SC', 'south dakota': 'SD', 'tennessee': 'TN',
        'texas': 'TX', 'utah': 'UT', 'vermont': 'VT', 'virginia': 'VA', 'washington': 'WA',
        'west virginia': 'WV', 'wisconsin': 'WI', 'wyoming': 'WY'
    }
    
    # Major cities for context
    MAJOR_CITIES = {
        # US Cities
        'new york': {'country': 'United States', 'state': 'New York', 'aliases': ['nyc', 'new york city', 'manhattan']},
        'los angeles': {'country': 'United States', 'state': 'California', 'aliases': ['la', 'los angeles']},
        'chicago': {'country': 'United States', 'state': 'Illinois', 'aliases': ['chi']},
        'houston': {'country': 'United States', 'state': 'Texas', 'aliases': []},
        'phoenix': {'country': 'United States', 'state': 'Arizona', 'aliases': []},
        'philadelphia': {'country': 'United States', 'state': 'Pennsylvania', 'aliases': ['philly']},
        'san antonio': {'country': 'United States', 'state': 'Texas', 'aliases': []},
        'san diego': {'country': 'United States', 'state': 'California', 'aliases': []},
        'dallas': {'country': 'United States', 'state': 'Texas', 'aliases': []},
        'san jose': {'country': 'United States', 'state': 'California', 'aliases': []},
        'austin': {'country': 'United States', 'state': 'Texas', 'aliases': []},
        'san francisco': {'country': 'United States', 'state': 'California', 'aliases': ['sf', 'san fran']},
        'seattle': {'country': 'United States', 'state': 'Washington', 'aliases': []},
        'denver': {'country': 'United States', 'state': 'Colorado', 'aliases': []},
        'boston': {'country': 'United States', 'state': 'Massachusetts', 'aliases': []},
        'atlanta': {'country': 'United States', 'state': 'Georgia', 'aliases': []},
        'miami': {'country': 'United States', 'state': 'Florida', 'aliases': []},
        
        # International Cities
        'london': {'country': 'United Kingdom', 'state': None, 'aliases': []},
        'paris': {'country': 'France', 'state': None, 'aliases': []},
        'berlin': {'country': 'Germany', 'state': None, 'aliases': []},
        'tokyo': {'country': 'Japan', 'state': None, 'aliases': []},
        'sydney': {'country': 'Australia', 'state': 'New South Wales', 'aliases': []},
        'toronto': {'country': 'Canada', 'state': 'Ontario', 'aliases': []},
        'vancouver': {'country': 'Canada', 'state': 'British Columbia', 'aliases': []},
        'amsterdam': {'country': 'Netherlands', 'state': None, 'aliases': []},
        'zurich': {'country': 'Switzerland', 'state': None, 'aliases': []},
        'singapore': {'country': 'Singapore', 'state': None, 'aliases': []},
        'bangalore': {'country': 'India', 'state': 'Karnataka', 'aliases': ['bengaluru']},
        'mumbai': {'country': 'India', 'state': 'Maharashtra', 'aliases': ['bombay']},
        'delhi': {'country': 'India', 'state': 'Delhi', 'aliases': ['new delhi']},
        'hyderabad': {'country': 'India', 'state': 'Telangana', 'aliases': []},
        'pune': {'country': 'India', 'state': 'Maharashtra', 'aliases': []},
        'chennai': {'country': 'India', 'state': 'Tamil Nadu', 'aliases': ['madras']},

        # Gujarat. Aliases include local-area names
        # commonly used in place of the city itself in job postings.
        'ahmedabad': {'country': 'India', 'state': 'Gujarat', 'aliases': [
            'ahmadabad', 'amdavad', 'sg highway', 'prahlad nagar', 'bodakdev',
            'vastrapur', 'bopal', 'science city', 'sanand',
        ]},
        'gandhinagar': {'country': 'India', 'state': 'Gujarat', 'aliases': [
            'gandhi nagar', 'gift city', 'infocity', 'adalaj',
        ]},
        'surat': {'country': 'India', 'state': 'Gujarat', 'aliases': []},
        'vadodara': {'country': 'India', 'state': 'Gujarat', 'aliases': ['baroda']},
        'rajkot': {'country': 'India', 'state': 'Gujarat', 'aliases': []},
    }

    # Reject signals for India-based users on "remote" listings — a remote
    # job scoped to another region is noise, not a match. Checked against
    # location text + description combined.
    REMOTE_SCOPE_SIGNALS = {
        'us_only': [
            r'authorized to work in the (?:us|u\.s\.|united states)',
            r'\bus\s*citizens?\s*only\b',
            r'\bus[- ]based candidates?\s*only\b',
            r'\best\s*timezone required\b',
            r'\bpst\s*timezone required\b',
            r'\bus remote\b',
            r'\busa only\b',
        ],
        'eu_only': [
            r'\beu residents?\s*only\b',
            r'must be based in (?:the )?eu\b',
            r'\bcet\s*timezone required\b',
            r'\beu work authorization\b',
        ],
        'uk_only': [
            r'\buk[- ]based candidates?\s*only\b',
            r'must be eligible to work in the uk\b',
            r'\bgmt\s*timezone required\b',
            r'\buk remote\b',
        ],
        'india_only': [
            r'\bindia only\b',
            r'must be based in india\b',
            r'\bpan[- ]india\b',
            r'\bindia remote\b',
        ],
    }
    
    def __init__(self):
        """Initialize the location parser."""
        self.logger = logging.getLogger(f"{__name__}")
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for location parsing."""
        # Pattern for city, state/province format
        self.city_state_pattern = re.compile(
            r'^([^,]+),\s*([A-Z]{2}|[A-Za-z\s]+)(?:,\s*([A-Za-z\s]+))?$'
        )
        
        # Pattern for postal codes
        self.postal_code_patterns = {
            'US': re.compile(r'\b\d{5}(?:-\d{4})?\b'),  # US ZIP codes
            'CA': re.compile(r'\b[A-Z]\d[A-Z]\s*\d[A-Z]\d\b'),  # Canadian postal codes
            'UK': re.compile(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b'),  # UK postcodes
        }
        
        # Pattern for coordinates
        self.coordinate_pattern = re.compile(
            r'(-?\d+\.?\d*),\s*(-?\d+\.?\d*)'
        )
    
    async def parse_location(self, raw_location: str) -> ParsedLocation:
        """Parse a raw location string into structured location information."""
        try:
            if not raw_location or not raw_location.strip():
                return ParsedLocation(
                    raw_location=raw_location,
                    confidence=0.0,
                    parsing_notes=["Empty location string"]
                )
            
            location = raw_location.strip()
            result = ParsedLocation(raw_location=location)
            
            # Step 1: Check for remote work indicators
            work_arrangement = self._detect_work_arrangement(location)
            result.work_arrangement = work_arrangement
            result.is_remote = (work_arrangement == WorkArrangement.REMOTE)
            
            if result.is_remote:
                result.country = "Remote"
                result.confidence = 0.9
                result.parsing_notes.append("Detected as remote work")
                return result
            
            # Step 2: Clean and normalize the location string
            cleaned_location = self._clean_location_string(location)
            
            # Step 3: Try different parsing strategies
            parsing_strategies = [
                self._parse_city_state_country,
                self._parse_known_cities,
                self._parse_country_only,
                self._parse_partial_location
            ]
            
            best_result = None
            best_confidence = 0.0
            
            for strategy in parsing_strategies:
                try:
                    parsed = await strategy(cleaned_location)
                    if parsed and parsed.confidence > best_confidence:
                        best_result = parsed
                        best_confidence = parsed.confidence
                except Exception as e:
                    self.logger.debug(f"Parsing strategy failed: {e}")
                    continue
            
            if best_result:
                # Preserve original raw location and work arrangement
                best_result.raw_location = location
                best_result.work_arrangement = work_arrangement
                best_result.is_remote = result.is_remote
                return best_result
            
            # Fallback result
            result.confidence = 0.1
            result.parsing_notes.append("Could not parse location")
            return result
            
        except Exception as e:
            self.logger.error(f"Error parsing location '{raw_location}': {e}")
            return ParsedLocation(
                raw_location=raw_location,
                confidence=0.0,
                parsing_notes=[f"Parsing error: {str(e)}"]
            )
    
    async def normalize_city_name(self, city: str) -> str:
        """Normalize city name to standard format."""
        if not city:
            return ""
        
        # Basic normalization
        normalized = city.strip().title()
        
        # Handle common abbreviations and variations
        city_variations = {
            'Nyc': 'New York',
            'La': 'Los Angeles',
            'Sf': 'San Francisco',
            'Philly': 'Philadelphia',
            'Chi': 'Chicago',
            'Dc': 'Washington',
            'Bengaluru': 'Bangalore',
            'Bombay': 'Mumbai',
            'Madras': 'Chennai',
            'Baroda': 'Vadodara',
            'Ahmadabad': 'Ahmedabad',
            'Amdavad': 'Ahmedabad',
            'Gandhi Nagar': 'Gandhinagar',
        }
        
        return city_variations.get(normalized, normalized)
    
    async def detect_remote_indicators(self, text: str) -> bool:
        """Detect if text contains remote work indicators."""
        if not text:
            return False
        
        text_lower = text.lower()
        
        # Check for remote keywords
        for keyword in self.REMOTE_KEYWORDS:
            if keyword in text_lower:
                return True
        
        return False
    
    async def classify_remote_scope(self, is_remote: bool, location_text: Optional[str] = None,
                                     description_text: Optional[str] = None) -> Optional[str]:
        """Classify which region a remote job is actually open to.

        Returns None for non-remote jobs. For remote jobs: 'india_only',
        'us_only', 'eu_only', 'uk_only', or 'global' if no region-restricting
        signal is found. A US-only remote job is noise for India-based users —
        without this, remote boards flood the feed with unreachable listings.
        """
        if not is_remote:
            return None

        combined = f"{location_text or ''} {description_text or ''}".lower()
        if not combined.strip():
            return 'global'

        for scope, patterns in self.REMOTE_SCOPE_SIGNALS.items():
            for pattern in patterns:
                if re.search(pattern, combined, re.IGNORECASE):
                    return scope

        # USD salary mentioned with no India context is a soft signal the
        # role is scoped to US candidates even without an explicit statement.
        if 'india' not in combined and ('usd' in combined or '$' in combined):
            return 'us_only'

        if 'india' in combined:
            return 'india_only'

        return 'global'

    async def extract_coordinates(self, location_text: str) -> Optional[Tuple[float, float]]:
        """Extract latitude/longitude coordinates from text."""
        if not location_text:
            return None
        
        match = self.coordinate_pattern.search(location_text)
        if match:
            try:
                lat = float(match.group(1))
                lng = float(match.group(2))
                
                # Validate coordinate ranges
                if -90 <= lat <= 90 and -180 <= lng <= 180:
                    return (lat, lng)
            except ValueError:
                pass
        
        return None
    
    def _detect_work_arrangement(self, location: str) -> Optional[WorkArrangement]:
        """Detect work arrangement from location string."""
        location_lower = location.lower()
        
        # Check for remote indicators
        for keyword in self.REMOTE_KEYWORDS:
            if keyword in location_lower:
                return WorkArrangement.REMOTE
        
        # Check for hybrid indicators
        for keyword in self.HYBRID_KEYWORDS:
            if keyword in location_lower:
                return WorkArrangement.HYBRID
        
        # Check for on-site indicators
        for keyword in self.ONSITE_KEYWORDS:
            if keyword in location_lower:
                return WorkArrangement.ON_SITE
        
        return None
    
    def _clean_location_string(self, location: str) -> str:
        """Clean and normalize location string for parsing."""
        # Remove common prefixes/suffixes
        cleaned = location.strip()
        
        # Remove work arrangement indicators for parsing
        for keyword in self.REMOTE_KEYWORDS | self.HYBRID_KEYWORDS | self.ONSITE_KEYWORDS:
            cleaned = re.sub(rf'\b{re.escape(keyword)}\b', '', cleaned, flags=re.IGNORECASE)
        
        # Remove parentheses content that might contain remote info
        cleaned = re.sub(r'\([^)]*\)', '', cleaned)
        
        # Remove extra whitespace and punctuation
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        cleaned = cleaned.strip(',').strip()
        
        return cleaned
    
    async def _parse_city_state_country(self, location: str) -> Optional[ParsedLocation]:
        """Parse location in City, State, Country format."""
        if not location:
            return None
        
        # Try different comma-separated formats
        parts = [part.strip() for part in location.split(',')]
        
        if len(parts) == 1:
            # Single part - might be city or country
            return await self._parse_single_part(parts[0])
        elif len(parts) == 2:
            # City, State/Country format
            return await self._parse_city_state(parts[0], parts[1])
        elif len(parts) >= 3:
            # City, State, Country format
            return await self._parse_city_state_country_parts(parts[0], parts[1], parts[2])
        
        return None
    
    async def _parse_known_cities(self, location: str) -> Optional[ParsedLocation]:
        """Parse location using known cities database."""
        location_lower = location.lower().strip()
        
        # Check exact matches first
        if location_lower in self.MAJOR_CITIES:
            city_info = self.MAJOR_CITIES[location_lower]
            return ParsedLocation(
                city=location.title(),
                state_province=city_info['state'],
                country=city_info['country'],
                country_code=self._get_country_code(city_info['country']),
                confidence=0.95,
                parsing_notes=["Matched known city"]
            )
        
        # Check aliases
        for city, info in self.MAJOR_CITIES.items():
            for alias in info['aliases']:
                if alias.lower() == location_lower:
                    return ParsedLocation(
                        city=city.title(),
                        state_province=info['state'],
                        country=info['country'],
                        country_code=self._get_country_code(info['country']),
                        confidence=0.9,
                        parsing_notes=["Matched city alias"]
                    )
        
        return None
    
    async def _parse_country_only(self, location: str) -> Optional[ParsedLocation]:
        """Parse location that contains only country information."""
        location_lower = location.lower().strip()
        
        # Check direct country matches
        for country, info in self.COUNTRY_MAPPINGS.items():
            if location_lower == country:
                return ParsedLocation(
                    country=info['country'],
                    country_code=info['code'],
                    confidence=0.8,
                    parsing_notes=["Matched country name"]
                )
            
            # Check aliases
            for alias in info['aliases']:
                if location_lower == alias:
                    return ParsedLocation(
                        country=info['country'],
                        country_code=info['code'],
                        confidence=0.75,
                        parsing_notes=["Matched country alias"]
                    )
        
        return None
    
    async def _parse_partial_location(self, location: str) -> Optional[ParsedLocation]:
        """Parse partial or incomplete location information."""
        if not location or len(location) < 2:
            return None
        
        # Try to extract any recognizable parts
        words = location.lower().split()
        
        found_country = None
        found_state = None
        found_city = None
        confidence = 0.0
        notes = []
        
        # Look for country mentions
        for word in words:
            for country, info in self.COUNTRY_MAPPINGS.items():
                if word in info['aliases'] or word == country:
                    found_country = info['country']
                    confidence += 0.3
                    notes.append(f"Found country: {found_country}")
                    break
        
        # Look for US states
        if not found_country or found_country == "United States":
            for word in words:
                if word in self.US_STATES:
                    found_state = word.title()
                    found_country = "United States"
                    confidence += 0.3
                    notes.append(f"Found US state: {found_state}")
                    break
                
                # Check state abbreviations
                word_upper = word.upper()
                for state_name, abbrev in self.US_STATES.items():
                    if word_upper == abbrev:
                        found_state = state_name.title()
                        found_country = "United States"
                        confidence += 0.3
                        notes.append(f"Found US state abbreviation: {found_state}")
                        break
        
        # If we found something, create a result
        if found_country or found_state:
            return ParsedLocation(
                city=found_city,
                state_province=found_state,
                country=found_country or "Unknown",
                country_code=self._get_country_code(found_country) if found_country else None,
                confidence=min(0.7, confidence),
                parsing_notes=notes
            )
        
        return None
    
    async def _parse_single_part(self, part: str) -> Optional[ParsedLocation]:
        """Parse a single location part."""
        # Try as known city first
        city_result = await self._parse_known_cities(part)
        if city_result:
            return city_result
        
        # Try as country
        country_result = await self._parse_country_only(part)
        if country_result:
            return country_result
        
        # Try as partial location
        return await self._parse_partial_location(part)
    
    async def _parse_city_state(self, city_part: str, state_part: str) -> Optional[ParsedLocation]:
        """Parse city and state/country parts."""
        city = city_part.strip()
        state_or_country = state_part.strip()
        
        # Check if state_part is a known country
        country_result = await self._parse_country_only(state_or_country)
        if country_result:
            return ParsedLocation(
                city=self._normalize_city_string(city),
                country=country_result.country,
                country_code=country_result.country_code,
                confidence=0.8,
                parsing_notes=["Parsed as City, Country"]
            )
        
        # Check if it's a US state
        state_lower = state_or_country.lower()
        if state_lower in self.US_STATES:
            return ParsedLocation(
                city=self._normalize_city_string(city),
                state_province=state_or_country.title(),
                country="United States",
                country_code="US",
                confidence=0.85,
                parsing_notes=["Parsed as City, US State"]
            )
        
        # Check US state abbreviations
        state_upper = state_or_country.upper()
        for state_name, abbrev in self.US_STATES.items():
            if state_upper == abbrev:
                return ParsedLocation(
                    city=self._normalize_city_string(city),
                    state_province=state_name.title(),
                    country="United States",
                    country_code="US",
                    confidence=0.85,
                    parsing_notes=["Parsed as City, US State (abbreviation)"]
                )
        
        # Fallback: treat as city, region
        return ParsedLocation(
            city=self._normalize_city_string(city),
            state_province=state_or_country.title(),
            confidence=0.6,
            parsing_notes=["Parsed as City, Region (unspecified country)"]
        )
    
    async def _parse_city_state_country_parts(self, city_part: str, state_part: str, country_part: str) -> Optional[ParsedLocation]:
        """Parse city, state, and country parts."""
        city = self._normalize_city_string(city_part.strip())
        state = state_part.strip()
        
        # Parse country
        country_result = await self._parse_country_only(country_part)
        if not country_result:
            return None
        
        return ParsedLocation(
            city=city,
            state_province=state.title() if state else None,
            country=country_result.country,
            country_code=country_result.country_code,
            confidence=0.9,
            parsing_notes=["Parsed as City, State, Country"]
        )
    
    def _normalize_city_string(self, city: str) -> str:
        """Normalize city string."""
        if not city:
            return ""
        
        # Basic normalization
        normalized = city.strip().title()
        
        # Remove common prefixes
        normalized = re.sub(r'^(City of|Town of)\s+', '', normalized, flags=re.IGNORECASE)
        
        return normalized
    
    def _get_country_code(self, country_name: str) -> Optional[str]:
        """Get ISO country code for a country name."""
        if not country_name:
            return None
        
        country_lower = country_name.lower()
        
        for country, info in self.COUNTRY_MAPPINGS.items():
            if (country_lower == country or 
                country_lower == info['country'].lower() or
                country_lower in [alias.lower() for alias in info['aliases']]):
                return info['code']
        
        return None