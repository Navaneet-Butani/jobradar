"""Text processing utilities for job data processing."""

import re
import string
import unicodedata
from typing import List, Dict, Set, Optional, Tuple, Any
from collections import Counter


class TextProcessor:
    """Utility class for text processing operations."""
    
    # Common stop words for text analysis
    STOP_WORDS = {
        'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
        'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the',
        'to', 'was', 'were', 'will', 'with', 'would', 'you', 'your',
        'job', 'position', 'role', 'work', 'company', 'team', 'we', 'our'
    }
    
    # Common abbreviations and their expansions
    ABBREVIATIONS = {
        'jr': 'junior',
        'sr': 'senior',
        'mgr': 'manager',
        'dev': 'developer',
        'eng': 'engineer',
        'admin': 'administrator',
        'coord': 'coordinator',
        'spec': 'specialist',
        'assoc': 'associate',
        'asst': 'assistant',
        'dir': 'director',
        'vp': 'vice president',
        'ceo': 'chief executive officer',
        'cto': 'chief technology officer',
        'cfo': 'chief financial officer',
        'hr': 'human resources',
        'it': 'information technology',
        'ai': 'artificial intelligence',
        'ml': 'machine learning',
        'ui': 'user interface',
        'ux': 'user experience',
        'api': 'application programming interface',
        'sql': 'structured query language',
        'aws': 'amazon web services',
        'gcp': 'google cloud platform'
    }
    
    @staticmethod
    def normalize_text(text: str, 
                      lowercase: bool = True,
                      remove_punctuation: bool = False,
                      remove_extra_whitespace: bool = True,
                      expand_abbreviations: bool = False) -> str:
        """Normalize text with various options."""
        if not text:
            return ""
        
        # Unicode normalization
        normalized = unicodedata.normalize('NFKD', text)
        
        # Convert to lowercase
        if lowercase:
            normalized = normalized.lower()
        
        # Expand abbreviations
        if expand_abbreviations:
            normalized = TextProcessor._expand_abbreviations(normalized)
        
        # Remove punctuation
        if remove_punctuation:
            normalized = normalized.translate(str.maketrans('', '', string.punctuation))
        
        # Remove extra whitespace
        if remove_extra_whitespace:
            normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    @staticmethod
    def clean_job_title(title: str) -> str:
        """Clean and normalize job title."""
        if not title:
            return ""
        
        cleaned = title.strip()
        
        # Remove common noise patterns
        noise_patterns = [
            r'^\s*[-•]\s*',  # Leading dashes or bullets
            r'\s*[-•]\s*$',  # Trailing dashes or bullets
            r'^\s*(job|position|role|opening):\s*',  # Prefixes like "Job: "
            r'\s*\(.*?\)\s*$',  # Trailing parentheses content
            r'\s*#\d+\s*$',  # Job numbers like "#123"
            r'\s*-\s*(urgent|immediate|asap)\s*$'  # Urgency indicators
        ]
        
        for pattern in noise_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Normalize whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        # Basic capitalization
        if cleaned.islower() or cleaned.isupper():
            cleaned = cleaned.title()
        
        # Fix common title patterns
        cleaned = re.sub(r'\bIt\b', 'IT', cleaned)
        cleaned = re.sub(r'\bUi\b', 'UI', cleaned)
        cleaned = re.sub(r'\bUx\b', 'UX', cleaned)
        cleaned = re.sub(r'\bApi\b', 'API', cleaned)
        cleaned = re.sub(r'\bSql\b', 'SQL', cleaned)
        cleaned = re.sub(r'\bAi\b', 'AI', cleaned)
        cleaned = re.sub(r'\bMl\b', 'ML', cleaned)
        
        return cleaned
    
    @staticmethod
    def clean_company_name(company_name: str) -> str:
        """Clean and normalize company name."""
        if not company_name:
            return ""
        
        cleaned = company_name.strip()
        
        # Remove common prefixes that might be noise
        prefixes_to_remove = [
            r'^(hiring\s+at|jobs?\s+at|careers?\s+at|position\s+at)\s+',
            r'^(work\s+for|join\s+our\s+team\s+at)\s+'
        ]
        
        for prefix in prefixes_to_remove:
            cleaned = re.sub(prefix, '', cleaned, flags=re.IGNORECASE)
        
        # Remove extra whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned
    
    @staticmethod
    def extract_keywords(text: str, 
                        min_length: int = 3,
                        max_keywords: int = 10,
                        exclude_stop_words: bool = True) -> List[str]:
        """Extract meaningful keywords from text."""
        if not text:
            return []
        
        # Normalize text
        normalized = TextProcessor.normalize_text(text, lowercase=True, remove_punctuation=True)
        
        # Split into words
        words = normalized.split()
        
        # Filter words
        filtered_words = []
        for word in words:
            if len(word) >= min_length:
                if not exclude_stop_words or word not in TextProcessor.STOP_WORDS:
                    filtered_words.append(word)
        
        # Count word frequency and return most common
        word_counts = Counter(filtered_words)
        keywords = [word for word, count in word_counts.most_common(max_keywords)]
        
        return keywords
    
    @staticmethod
    def extract_skills_mentions(text: str, skills_database: Set[str]) -> List[Tuple[str, int]]:
        """Extract skill mentions from text with counts."""
        if not text or not skills_database:
            return []
        
        text_lower = text.lower()
        skill_mentions = []
        
        for skill in skills_database:
            skill_lower = skill.lower()
            
            # Count exact matches (word boundaries)
            pattern = r'\b' + re.escape(skill_lower) + r'\b'
            matches = re.findall(pattern, text_lower)
            
            if matches:
                skill_mentions.append((skill, len(matches)))
        
        # Sort by mention count (descending)
        skill_mentions.sort(key=lambda x: x[1], reverse=True)
        
        return skill_mentions
    
    @staticmethod
    def calculate_text_similarity(text1: str, text2: str, method: str = 'jaccard') -> float:
        """Calculate similarity between two texts."""
        if not text1 or not text2:
            return 0.0
        
        # Normalize texts
        norm1 = TextProcessor.normalize_text(text1, remove_punctuation=True)
        norm2 = TextProcessor.normalize_text(text2, remove_punctuation=True)
        
        # Convert to word sets
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        
        if method == 'jaccard':
            # Jaccard similarity
            intersection = words1.intersection(words2)
            union = words1.union(words2)
            return len(intersection) / len(union) if union else 0.0
        
        elif method == 'overlap':
            # Overlap coefficient
            intersection = words1.intersection(words2)
            return len(intersection) / min(len(words1), len(words2)) if words1 and words2 else 0.0
        
        elif method == 'cosine':
            # Simple cosine similarity based on word counts
            all_words = words1.union(words2)
            if not all_words:
                return 0.0
            
            # Create vectors
            vec1 = [1 if word in words1 else 0 for word in all_words]
            vec2 = [1 if word in words2 else 0 for word in all_words]
            
            # Calculate cosine similarity
            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            magnitude1 = sum(a * a for a in vec1) ** 0.5
            magnitude2 = sum(b * b for b in vec2) ** 0.5
            
            if magnitude1 == 0 or magnitude2 == 0:
                return 0.0
            
            return dot_product / (magnitude1 * magnitude2)
        
        else:
            raise ValueError(f"Unknown similarity method: {method}")
    
    @staticmethod
    def detect_language_patterns(text: str) -> Dict[str, Any]:
        """Detect various language patterns in text."""
        if not text:
            return {}
        
        patterns = {}
        
        # Character composition
        total_chars = len(text)
        if total_chars > 0:
            patterns['uppercase_ratio'] = sum(1 for c in text if c.isupper()) / total_chars
            patterns['digit_ratio'] = sum(1 for c in text if c.isdigit()) / total_chars
            patterns['punctuation_ratio'] = sum(1 for c in text if c in string.punctuation) / total_chars
        
        # Word patterns
        words = text.split()
        if words:
            patterns['average_word_length'] = sum(len(word) for word in words) / len(words)
            patterns['long_words_ratio'] = sum(1 for word in words if len(word) > 8) / len(words)
        
        # Sentence patterns
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if sentences:
            patterns['average_sentence_length'] = sum(len(s.split()) for s in sentences) / len(sentences)
            patterns['sentence_count'] = len(sentences)
        
        # Special patterns
        patterns['exclamation_count'] = text.count('!')
        patterns['question_count'] = text.count('?')
        patterns['all_caps_words'] = len(re.findall(r'\b[A-Z]{2,}\b', text))
        patterns['email_count'] = len(re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text))
        patterns['url_count'] = len(re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text))
        
        return patterns
    
    @staticmethod
    def split_into_sentences(text: str) -> List[str]:
        """Split text into sentences."""
        if not text:
            return []
        
        # Simple sentence splitting
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        return sentences
    
    @staticmethod
    def extract_phrases(text: str, min_words: int = 2, max_words: int = 4) -> List[str]:
        """Extract meaningful phrases from text."""
        if not text:
            return []
        
        # Normalize text
        normalized = TextProcessor.normalize_text(text, remove_punctuation=True)
        words = normalized.split()
        
        phrases = []
        
        # Extract n-grams
        for n in range(min_words, max_words + 1):
            for i in range(len(words) - n + 1):
                phrase = ' '.join(words[i:i + n])
                
                # Filter out phrases with stop words only
                phrase_words = phrase.split()
                non_stop_words = [w for w in phrase_words if w not in TextProcessor.STOP_WORDS]
                
                if len(non_stop_words) >= min_words - 1:  # At least some meaningful words
                    phrases.append(phrase)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_phrases = []
        for phrase in phrases:
            if phrase not in seen:
                seen.add(phrase)
                unique_phrases.append(phrase)
        
        return unique_phrases
    
    @staticmethod
    def _expand_abbreviations(text: str) -> str:
        """Expand common abbreviations in text."""
        words = text.split()
        expanded_words = []
        
        for word in words:
            # Remove punctuation for lookup
            clean_word = word.strip(string.punctuation).lower()
            
            if clean_word in TextProcessor.ABBREVIATIONS:
                # Preserve original case and punctuation
                expanded = TextProcessor.ABBREVIATIONS[clean_word]
                if word.isupper():
                    expanded = expanded.upper()
                elif word.istitle():
                    expanded = expanded.title()
                
                # Add back punctuation
                if word != clean_word:
                    trailing_punct = word[len(clean_word):]
                    expanded += trailing_punct
                
                expanded_words.append(expanded)
            else:
                expanded_words.append(word)
        
        return ' '.join(expanded_words)


class HTMLProcessor:
    """Utility class for processing HTML content."""
    
    @staticmethod
    def strip_html_tags(html: str) -> str:
        """Remove HTML tags from text."""
        if not html:
            return ""
        
        # Remove HTML tags
        clean_text = re.sub(r'<[^>]+>', '', html)
        
        # Decode HTML entities
        html_entities = {
            '&amp;': '&',
            '&lt;': '<',
            '&gt;': '>',
            '&quot;': '"',
            '&#39;': "'",
            '&nbsp;': ' ',
            '&ndash;': '–',
            '&mdash;': '—',
            '&hellip;': '…'
        }
        
        for entity, char in html_entities.items():
            clean_text = clean_text.replace(entity, char)
        
        # Clean up whitespace
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        return clean_text
    
    @staticmethod
    def extract_text_from_html(html: str, preserve_structure: bool = False) -> str:
        """Extract clean text from HTML with optional structure preservation."""
        if not html:
            return ""
        
        text = html
        
        if preserve_structure:
            # Replace block elements with line breaks
            block_elements = ['div', 'p', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li']
            for element in block_elements:
                text = re.sub(f'<{element}[^>]*>', '\n', text, flags=re.IGNORECASE)
                text = re.sub(f'</{element}>', '\n', text, flags=re.IGNORECASE)
        
        # Remove all HTML tags
        text = HTMLProcessor.strip_html_tags(text)
        
        if preserve_structure:
            # Clean up line breaks
            text = re.sub(r'\n\s*\n', '\n\n', text)  # Normalize double line breaks
            text = re.sub(r'\n{3,}', '\n\n', text)   # Limit to double line breaks
        
        return text.strip()


# Utility functions for common operations
def normalize_whitespace(text: str) -> str:
    """Normalize whitespace in text."""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()


def remove_non_printable(text: str) -> str:
    """Remove non-printable characters from text."""
    if not text:
        return ""
    return ''.join(char for char in text if char.isprintable() or char.isspace())


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text to maximum length with optional suffix."""
    if not text or len(text) <= max_length:
        return text
    
    if len(suffix) >= max_length:
        return text[:max_length]
    
    truncated = text[:max_length - len(suffix)]
    
    # Try to break at word boundary
    last_space = truncated.rfind(' ')
    if last_space > max_length * 0.8:  # If we can break reasonably close to the limit
        truncated = truncated[:last_space]
    
    return truncated + suffix


def count_words(text: str) -> int:
    """Count words in text."""
    if not text:
        return 0
    return len(text.split())


def count_sentences(text: str) -> int:
    """Count sentences in text."""
    if not text:
        return 0
    sentences = re.split(r'[.!?]+', text)
    return len([s for s in sentences if s.strip()])


def extract_numbers(text: str) -> List[float]:
    """Extract all numbers from text."""
    if not text:
        return []
    
    # Pattern to match numbers (including decimals)
    number_pattern = r'-?\d+(?:\.\d+)?'
    matches = re.findall(number_pattern, text)
    
    numbers = []
    for match in matches:
        try:
            numbers.append(float(match))
        except ValueError:
            continue
    
    return numbers


def extract_emails(text: str) -> List[str]:
    """Extract email addresses from text."""
    if not text:
        return []
    
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    return re.findall(email_pattern, text)


def extract_urls(text: str) -> List[str]:
    """Extract URLs from text."""
    if not text:
        return []

    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    return re.findall(url_pattern, text)


class TextNormalizer:
    """Advanced text normalization for job data."""

    def __init__(self):
        self.stop_words = self._load_stop_words()
        self.job_noise_words = self._load_job_noise_words()

    def normalize_job_title(self, title: str) -> str:
        """Normalize job title for comparison."""
        if not title:
            return ""

        # Convert to lowercase
        normalized = title.lower().strip()

        # Remove company names in parentheses
        normalized = re.sub(r'\([^)]*\)', '', normalized)

        # Remove location suffixes
        normalized = re.sub(r'[,-]\s*[a-z\s]+(?:, [a-z]{2})?$', '', normalized)

        # Standardize abbreviations
        abbreviations = {
            r'\bsr\.?\b': 'senior',
            r'\bjr\.?\b': 'junior',
            r'\bmgr\.?\b': 'manager',
            r'\bdev\.?\b': 'developer',
            r'\beng\.?\b': 'engineer',
            r'\bqa\.?\b': 'quality assurance',
            r'\bui/ux\b': 'user interface user experience',
            r'\bfull\s*stack\b': 'fullstack',
            r'\bfront\s*end\b': 'frontend',
            r'\bback\s*end\b': 'backend',
            r'\bdev\s*ops\b': 'devops',
            r'\bml\b': 'machine learning',
            r'\bai\b': 'artificial intelligence',
        }

        for pattern, replacement in abbreviations.items():
            normalized = re.sub(pattern, replacement, normalized)

        # Remove noise words
        words = normalized.split()
        words = [w for w in words if w not in self.job_noise_words]

        # Remove punctuation and extra spaces
        normalized = ' '.join(words)
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        return normalized

    def normalize_description(self, description: str) -> str:
        """Normalize job description for comparison."""
        if not description:
            return ""

        # Convert to lowercase and remove HTML
        normalized = re.sub(r'<[^>]+>', '', description.lower())

        # Remove URLs
        normalized = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', normalized)

        # Remove email addresses
        normalized = re.sub(r'\S+@\S+', '', normalized)

        # Remove phone numbers
        normalized = re.sub(r'[\d\s\-\(\)\.]{10,}', '', normalized)

        # Remove excessive punctuation
        normalized = re.sub(r'[^\w\s]', ' ', normalized)

        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        # Remove stop words
        words = normalized.split()
        words = [w for w in words if w not in self.stop_words and len(w) > 2]

        return ' '.join(words[:200])  # Limit to first 200 words

    def normalize_company_name(self, company: str) -> str:
        """Advanced company name normalization."""
        if not company:
            return ""

        normalized = company.lower().strip()

        # Remove common suffixes and legal entities
        suffixes = [
            r'\binc\.?\b', r'\bcorp\.?\b', r'\bcorporation\b',
            r'\bllc\b', r'\bltd\.?\b', r'\blimited\b',
            r'\bco\.?\b', r'\bcompany\b', r'\bgroup\b',
            r'\bholdings?\b', r'\benterprise\b', r'\bsolutions?\b'
        ]

        for suffix in suffixes:
            normalized = re.sub(suffix, '', normalized)

        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        return normalized

    def normalize_location(self, location: str) -> str:
        """Normalize location string."""
        if not location:
            return ""

        normalized = location.lower().strip()

        # Location abbreviations
        abbreviations = {
            r'\bsf\b': 'san francisco',
            r'\bnyc\b': 'new york city',
            r'\bla\b': 'los angeles',
            r'\bdc\b': 'washington dc',
            r'\bchicago\b': 'chicago',
            r'\bboston\b': 'boston',
            r'\bseattle\b': 'seattle',
            r'\baustin\b': 'austin',
            r'\bdenver\b': 'denver',
            r'\bportland\b': 'portland'
        }

        for abbr_pattern, full_name in abbreviations.items():
            normalized = re.sub(abbr_pattern, full_name, normalized)

        # Remove common location suffixes
        normalized = re.sub(r',?\s*(usa?|united states|america)$', '', normalized)
        normalized = re.sub(r',?\s*[a-z]{2}$', '', normalized)  # Remove state codes

        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        return normalized

    def extract_skills_keywords(self, text: str) -> List[str]:
        """Extract potential skills and keywords from job text."""
        if not text:
            return []

        # Common technical skills and keywords
        tech_keywords = {
            # Programming languages
            'python', 'java', 'javascript', 'typescript', 'go', 'rust', 'c++', 'c#', 'php', 'ruby', 'swift', 'kotlin',

            # Frameworks and libraries
            'react', 'angular', 'vue', 'django', 'flask', 'spring', 'nodejs', 'express', 'fastapi',

            # Databases
            'postgresql', 'mysql', 'mongodb', 'redis', 'elasticsearch', 'cassandra', 'oracle',

            # Cloud platforms
            'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'terraform',

            # Other technologies
            'git', 'jenkins', 'nginx', 'apache', 'linux', 'unix', 'agile', 'scrum'
        }

        text_lower = text.lower()
        found_keywords = []

        for keyword in tech_keywords:
            if keyword in text_lower:
                found_keywords.append(keyword)

        return found_keywords[:10]  # Return top 10 keywords

    def is_remote_location(self, location: str) -> bool:
        """Detect if location indicates remote work."""
        if not location:
            return False

        remote_indicators = [
            'remote', 'work from home', 'wfh', 'telecommute',
            'anywhere', 'distributed', 'virtual', 'home office',
            'remote work', 'remote-first', 'fully remote'
        ]

        location_lower = location.lower()
        return any(indicator in location_lower for indicator in remote_indicators)

    def calculate_text_similarity_score(self, text1: str, text2: str) -> float:
        """Calculate basic text similarity score using multiple methods."""
        if not text1 or not text2:
            return 0.0

        # Normalize both texts
        norm_text1 = self._normalize_for_comparison(text1)
        norm_text2 = self._normalize_for_comparison(text2)

        if norm_text1 == norm_text2:
            return 1.0

        # Word-based similarity
        words1 = set(norm_text1.split())
        words2 = set(norm_text2.split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))

        jaccard_similarity = intersection / union if union > 0 else 0.0

        return jaccard_similarity

    def _normalize_for_comparison(self, text: str) -> str:
        """Normalize text for similarity comparison."""
        if not text:
            return ""

        # Convert to lowercase
        normalized = text.lower()

        # Remove punctuation
        normalized = re.sub(r'[^\w\s]', ' ', normalized)

        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        # Remove stop words
        words = normalized.split()
        words = [w for w in words if w not in self.stop_words and len(w) > 2]

        return ' '.join(words)

    def _load_stop_words(self) -> Set[str]:
        """Load stop words for text processing."""
        return {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'about', 'is', 'are', 'was', 'were',
            'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
            'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can',
            'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it',
            'we', 'they', 'me', 'him', 'her', 'us', 'them', 'my', 'your',
            'his', 'her', 'its', 'our', 'their', 'am', 'if', 'then', 'else',
            'when', 'where', 'why', 'how', 'all', 'any', 'both', 'each',
            'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor',
            'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very'
        }

    def _load_job_noise_words(self) -> Set[str]:
        """Load job-specific noise words."""
        return {
            'job', 'position', 'role', 'opening', 'opportunity', 'career',
            'work', 'employment', 'hiring', 'wanted', 'seeking', 'looking',
            'apply', 'join', 'team', 'company', 'organization', 'firm',
            'workplace', 'office', 'department', 'division', 'staff',
            'employee', 'candidate', 'applicant', 'professional', 'individual',
            'person', 'people', 'talent', 'resource', 'human', 'full', 'time',
            'part', 'contract', 'temporary', 'permanent', 'immediate', 'urgent'
        }


# Create a global instance for easy import
text_normalizer = TextNormalizer()