"""
Advanced skill extraction service with NLP capabilities.

This service extracts technical skills from job descriptions using:
- Pattern matching with comprehensive skill database
- Context-aware filtering to avoid false positives
- Skill categorization and confidence scoring
- Alias resolution for skill variations
"""

import re
import json
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import asyncio
from pathlib import Path

# For now, we'll implement without spaCy to avoid dependencies
# Can be upgraded to use spaCy for better NLP capabilities
from ..models.job import StandardJob, SkillInfo
from ..models.common import SkillCategory
from ..utils.text_processing import TextProcessor


@dataclass
class SkillExtractionResult:
    """Result of skill extraction process."""
    skills: List[SkillInfo]
    total_skills_found: int
    processing_time_ms: float
    confidence_scores: Dict[str, float]


class SkillDatabase:
    """Comprehensive skill database with patterns and aliases."""
    
    def __init__(self):
        self.skills_data = self._initialize_skill_database()
        self.skill_patterns = self._compile_patterns()
        self.aliases_map = self._build_aliases_map()
    
    def _initialize_skill_database(self) -> Dict[str, Dict[str, Any]]:
        """Initialize comprehensive skill database."""
        return {
            # Programming Languages
            "python": {
                "category": SkillCategory.PROGRAMMING_LANGUAGE,
                "aliases": ["python", "python3", "py", "cpython"],
                "patterns": [r"\bpython\b", r"\bpython\s*3\b", r"\bpy\b"],
                "weight": 1.0
            },
            "javascript": {
                "category": SkillCategory.PROGRAMMING_LANGUAGE,
                "aliases": ["javascript", "js", "ecmascript", "es6", "es2015", "es2020"],
                "patterns": [r"\bjavascript\b", r"\bjs\b", r"\becmascript\b", r"\bes[0-9]+\b"],
                "weight": 1.0
            },
            "java": {
                "category": SkillCategory.PROGRAMMING_LANGUAGE,
                "aliases": ["java", "jdk", "jre", "java8", "java11", "java17"],
                "patterns": [r"\bjava\b(?!\s*script)", r"\bjdk\b", r"\bjre\b"],
                "weight": 1.0
            },
            "typescript": {
                "category": SkillCategory.PROGRAMMING_LANGUAGE,
                "aliases": ["typescript", "ts", "tsc"],
                "patterns": [r"\btypescript\b", r"\bts\b", r"\btsc\b"],
                "weight": 1.0
            },
            "c++": {
                "category": SkillCategory.PROGRAMMING_LANGUAGE,
                "aliases": ["c++", "cpp", "cxx", "c plus plus"],
                "patterns": [r"\bc\+\+\b", r"\bcpp\b", r"\bcxx\b"],
                "weight": 1.0
            },
            "c#": {
                "category": SkillCategory.PROGRAMMING_LANGUAGE,
                "aliases": ["c#", "csharp", "c sharp", ".net"],
                "patterns": [r"\bc#\b", r"\bcsharp\b", r"\bc\s*sharp\b"],
                "weight": 1.0
            },
            "go": {
                "category": SkillCategory.PROGRAMMING_LANGUAGE,
                "aliases": ["go", "golang", "google go"],
                "patterns": [r"\bgolang\b", r"\bgo\b(?=\s*(?:lang|dev|programming))"],
                "weight": 1.0
            },
            "rust": {
                "category": SkillCategory.PROGRAMMING_LANGUAGE,
                "aliases": ["rust", "rust-lang"],
                "patterns": [r"\brust\b(?=\s*(?:lang|programming))"],
                "weight": 1.0
            },
            "php": {
                "category": SkillCategory.PROGRAMMING_LANGUAGE,
                "aliases": ["php", "php7", "php8"],
                "patterns": [r"\bphp\b", r"\bphp[0-9]+\b"],
                "weight": 1.0
            },
            "ruby": {
                "category": SkillCategory.PROGRAMMING_LANGUAGE,
                "aliases": ["ruby", "ruby on rails", "rails"],
                "patterns": [r"\bruby\b", r"\brails\b"],
                "weight": 1.0
            },
            "swift": {
                "category": SkillCategory.PROGRAMMING_LANGUAGE,
                "aliases": ["swift", "swiftui", "ios swift"],
                "patterns": [r"\bswift\b", r"\bswiftui\b"],
                "weight": 1.0
            },
            "kotlin": {
                "category": SkillCategory.PROGRAMMING_LANGUAGE,
                "aliases": ["kotlin", "kotlinc"],
                "patterns": [r"\bkotlin\b"],
                "weight": 1.0
            },
            "scala": {
                "category": SkillCategory.PROGRAMMING_LANGUAGE,
                "aliases": ["scala", "akka"],
                "patterns": [r"\bscala\b"],
                "weight": 1.0
            },
            
            # Frameworks & Libraries
            "react": {
                "category": SkillCategory.FRAMEWORK,
                "aliases": ["react", "reactjs", "react.js", "react native"],
                "patterns": [r"\breact\b", r"\breactjs\b", r"\breact\.js\b"],
                "weight": 1.0
            },
            "angular": {
                "category": SkillCategory.FRAMEWORK,
                "aliases": ["angular", "angularjs", "angular2", "angular4", "angular12"],
                "patterns": [r"\bangular\b", r"\bangularjs\b", r"\bangular[0-9]+\b"],
                "weight": 1.0
            },
            "vue": {
                "category": SkillCategory.FRAMEWORK,
                "aliases": ["vue", "vuejs", "vue.js", "vue3"],
                "patterns": [r"\bvue\b", r"\bvuejs\b", r"\bvue\.js\b"],
                "weight": 1.0
            },
            "django": {
                "category": SkillCategory.FRAMEWORK,
                "aliases": ["django", "django rest", "drf"],
                "patterns": [r"\bdjango\b", r"\bdrf\b"],
                "weight": 1.0
            },
            "flask": {
                "category": SkillCategory.FRAMEWORK,
                "aliases": ["flask", "flask-restful"],
                "patterns": [r"\bflask\b"],
                "weight": 1.0
            },
            "fastapi": {
                "category": SkillCategory.FRAMEWORK,
                "aliases": ["fastapi", "fast api"],
                "patterns": [r"\bfastapi\b", r"\bfast\s*api\b"],
                "weight": 1.0
            },
            "spring": {
                "category": SkillCategory.FRAMEWORK,
                "aliases": ["spring", "spring boot", "spring mvc", "spring framework"],
                "patterns": [r"\bspring\b", r"\bspring\s*boot\b"],
                "weight": 1.0
            },
            "express": {
                "category": SkillCategory.FRAMEWORK,
                "aliases": ["express", "expressjs", "express.js"],
                "patterns": [r"\bexpress\b", r"\bexpressjs\b"],
                "weight": 1.0
            },
            "nextjs": {
                "category": SkillCategory.FRAMEWORK,
                "aliases": ["nextjs", "next.js", "next"],
                "patterns": [r"\bnext\.js\b", r"\bnextjs\b"],
                "weight": 1.0
            },
            "laravel": {
                "category": SkillCategory.FRAMEWORK,
                "aliases": ["laravel", "laravel framework"],
                "patterns": [r"\blaravel\b"],
                "weight": 1.0
            },
            "nodejs": {
                "category": SkillCategory.FRAMEWORK,
                "aliases": ["nodejs", "node.js", "node js", "node"],
                "patterns": [r"\bnode\.js\b", r"\bnodejs\b", r"\bnode\s*js\b"],
                "weight": 1.0
            },
            "nestjs": {
                "category": SkillCategory.FRAMEWORK,
                "aliases": ["nestjs", "nest.js", "nest js"],
                "patterns": [r"\bnest\.js\b", r"\bnestjs\b", r"\bnest\s*js\b"],
                "weight": 1.0
            },
            "graphql": {
                "category": SkillCategory.FRAMEWORK,
                "aliases": ["graphql", "graph ql"],
                "patterns": [r"\bgraphql\b", r"\bgraph\s*ql\b"],
                "weight": 1.0
            },
            "grpc": {
                "category": SkillCategory.FRAMEWORK,
                "aliases": ["grpc", "grpc-web"],
                "patterns": [r"\bgrpc\b"],
                "weight": 1.0
            },
            "tailwindcss": {
                "category": SkillCategory.FRONTEND,
                "aliases": ["tailwind css", "tailwindcss", "tailwind"],
                "patterns": [r"\btailwind\s*css\b", r"\btailwindcss\b", r"\btailwind\b"],
                "weight": 1.0
            },
            "materialui": {
                "category": SkillCategory.FRONTEND,
                "aliases": ["material ui", "materialui", "material-ui", "mui"],
                "patterns": [r"\bmaterial[\s-]*ui\b", r"\bmui\b"],
                "weight": 1.0
            },
            "scss": {
                "category": SkillCategory.FRONTEND,
                "aliases": ["scss", "sass"],
                "patterns": [r"\bscss\b", r"\bsass\b"],
                "weight": 1.0
            },

            # Databases
            "postgresql": {
                "category": SkillCategory.DATABASE,
                "aliases": ["postgresql", "postgres", "psql", "pg"],
                "patterns": [r"\bpostgresql\b", r"\bpostgres\b", r"\bpsql\b"],
                "weight": 1.0
            },
            "mysql": {
                "category": SkillCategory.DATABASE,
                "aliases": ["mysql", "mariadb"],
                "patterns": [r"\bmysql\b", r"\bmariadb\b"],
                "weight": 1.0
            },
            "mongodb": {
                "category": SkillCategory.DATABASE,
                "aliases": ["mongodb", "mongo", "mongoose"],
                "patterns": [r"\bmongodb\b", r"\bmongo\b", r"\bmongoose\b"],
                "weight": 1.0
            },
            "redis": {
                "category": SkillCategory.DATABASE,
                "aliases": ["redis", "redis cache"],
                "patterns": [r"\bredis\b"],
                "weight": 1.0
            },
            "elasticsearch": {
                "category": SkillCategory.DATABASE,
                "aliases": ["elasticsearch", "elastic search", "es"],
                "patterns": [r"\belasticsearch\b", r"\belastic\s*search\b"],
                "weight": 1.0
            },
            "cassandra": {
                "category": SkillCategory.DATABASE,
                "aliases": ["cassandra", "apache cassandra"],
                "patterns": [r"\bcassandra\b"],
                "weight": 1.0
            },
            "kafka": {
                "category": SkillCategory.TOOL,
                "aliases": ["kafka", "apache kafka"],
                "patterns": [r"\bkafka\b"],
                "weight": 1.0
            },
            "rabbitmq": {
                "category": SkillCategory.TOOL,
                "aliases": ["rabbitmq", "rabbit mq"],
                "patterns": [r"\brabbitmq\b", r"\brabbit\s*mq\b"],
                "weight": 1.0
            },
            "sqlite": {
                "category": SkillCategory.DATABASE,
                "aliases": ["sqlite", "sqlite3"],
                "patterns": [r"\bsqlite\b"],
                "weight": 1.0
            },
            
            # Cloud Platforms
            "aws": {
                "category": SkillCategory.CLOUD_PLATFORM,
                "aliases": ["aws", "amazon web services", "ec2", "s3", "lambda"],
                "patterns": [r"\baws\b", r"\bamazon\s*web\s*services\b", r"\bec2\b", r"\bs3\b"],
                "weight": 1.0
            },
            "azure": {
                "category": SkillCategory.CLOUD_PLATFORM,
                "aliases": ["azure", "microsoft azure", "azure cloud"],
                "patterns": [r"\bazure\b", r"\bmicrosoft\s*azure\b"],
                "weight": 1.0
            },
            "gcp": {
                "category": SkillCategory.CLOUD_PLATFORM,
                "aliases": ["gcp", "google cloud", "google cloud platform"],
                "patterns": [r"\bgcp\b", r"\bgoogle\s*cloud\b"],
                "weight": 1.0
            },
            "heroku": {
                "category": SkillCategory.CLOUD_PLATFORM,
                "aliases": ["heroku"],
                "patterns": [r"\bheroku\b"],
                "weight": 1.0
            },
            "digitalocean": {
                "category": SkillCategory.CLOUD_PLATFORM,
                "aliases": ["digitalocean", "digital ocean", "do"],
                "patterns": [r"\bdigitalocean\b", r"\bdigital\s*ocean\b"],
                "weight": 1.0
            },
            
            # Tools & Technologies
            "docker": {
                "category": SkillCategory.TOOL,
                "aliases": ["docker", "dockerfile", "docker-compose"],
                "patterns": [r"\bdocker\b", r"\bdockerfile\b"],
                "weight": 1.0
            },
            "kubernetes": {
                "category": SkillCategory.TOOL,
                "aliases": ["kubernetes", "k8s", "kubectl"],
                "patterns": [r"\bkubernetes\b", r"\bk8s\b", r"\bkubectl\b"],
                "weight": 1.0
            },
            "git": {
                "category": SkillCategory.TOOL,
                "aliases": ["git", "github", "gitlab", "bitbucket"],
                "patterns": [r"\bgit\b", r"\bgithub\b", r"\bgitlab\b"],
                "weight": 1.0
            },
            "jenkins": {
                "category": SkillCategory.TOOL,
                "aliases": ["jenkins", "jenkins ci"],
                "patterns": [r"\bjenkins\b"],
                "weight": 1.0
            },
            "terraform": {
                "category": SkillCategory.TOOL,
                "aliases": ["terraform", "tf"],
                "patterns": [r"\bterraform\b"],
                "weight": 1.0
            },
            "ansible": {
                "category": SkillCategory.TOOL,
                "aliases": ["ansible"],
                "patterns": [r"\bansible\b"],
                "weight": 1.0
            },
            "webpack": {
                "category": SkillCategory.TOOL,
                "aliases": ["webpack", "webpack4", "webpack5"],
                "patterns": [r"\bwebpack\b"],
                "weight": 1.0
            },
            "npm": {
                "category": SkillCategory.TOOL,
                "aliases": ["npm", "yarn", "pnpm"],
                "patterns": [r"\bnpm\b", r"\byarn\b", r"\bpnpm\b"],
                "weight": 1.0
            },
            
            # Methodologies
            "agile": {
                "category": SkillCategory.METHODOLOGY,
                "aliases": ["agile", "scrum", "kanban", "sprint"],
                "patterns": [r"\bagile\b", r"\bscrum\b", r"\bkanban\b"],
                "weight": 0.8
            },
            "devops": {
                "category": SkillCategory.METHODOLOGY,
                "aliases": ["devops", "dev ops", "ci/cd", "continuous integration"],
                "patterns": [r"\bdevops\b", r"\bci/cd\b", r"\bcontinuous\s*integration\b"],
                "weight": 1.0
            },
            "tdd": {
                "category": SkillCategory.METHODOLOGY,
                "aliases": ["tdd", "test driven development", "bdd"],
                "patterns": [r"\btdd\b", r"\btest\s*driven\s*development\b", r"\bbdd\b"],
                "weight": 0.9
            },
            
            # Soft Skills
            "communication": {
                "category": SkillCategory.SOFT_SKILL,
                "aliases": ["communication", "verbal communication", "written communication"],
                "patterns": [r"\bcommunication\b", r"\bverbal\s*communication\b"],
                "weight": 0.6
            },
            "leadership": {
                "category": SkillCategory.SOFT_SKILL,
                "aliases": ["leadership", "team leadership", "project management"],
                "patterns": [r"\bleadership\b", r"\bteam\s*lead\b", r"\bproject\s*management\b"],
                "weight": 0.7
            },
            "problem-solving": {
                "category": SkillCategory.SOFT_SKILL,
                "aliases": ["problem solving", "problem-solving", "analytical thinking"],
                "patterns": [r"\bproblem\s*solving\b", r"\banalytical\s*thinking\b"],
                "weight": 0.6
            }
        }
    
    def _compile_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Compile regex patterns for efficient matching."""
        compiled = {}
        for skill, data in self.skills_data.items():
            compiled[skill] = [
                re.compile(pattern, re.IGNORECASE | re.MULTILINE)
                for pattern in data["patterns"]
            ]
        return compiled
    
    def _build_aliases_map(self) -> Dict[str, str]:
        """Build mapping from aliases to canonical skill names."""
        aliases_map = {}
        for skill, data in self.skills_data.items():
            for alias in data["aliases"]:
                aliases_map[alias.lower()] = skill
        return aliases_map
    
    def get_skill_info(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """Get skill information by name or alias."""
        canonical_name = self.aliases_map.get(skill_name.lower(), skill_name.lower())
        return self.skills_data.get(canonical_name)


class SkillExtractor:
    """Advanced skill extraction service with NLP capabilities."""
    
    def __init__(self):
        self.skill_db = SkillDatabase()
        self.context_window = 50  # Words around skill mention to analyze
        self.min_confidence = 0.3  # Minimum confidence to include skill
    
    async def extract_skills(self, text: str) -> List[SkillInfo]:
        """Extract skills from text with confidence scoring."""
        if not text or not text.strip():
            return []
        
        # Normalize text for better matching
        normalized_text = TextProcessor.normalize_text(text)
        
        extracted_skills = []
        processed_skills = set()  # Avoid duplicates
        
        # Extract skills using pattern matching
        for skill_name, patterns in self.skill_db.skill_patterns.items():
            skill_info = self.skill_db.get_skill_info(skill_name)
            if not skill_info:
                continue
            
            for pattern in patterns:
                matches = pattern.finditer(normalized_text)
                
                for match in matches:
                    if skill_name in processed_skills:
                        continue
                    
                    # Get context around the match
                    context = self._extract_context(normalized_text, match.start(), match.end())
                    
                    # Calculate confidence based on context
                    confidence = self._calculate_confidence(skill_name, context, match.group())
                    
                    if confidence >= self.min_confidence:
                        skill_obj = SkillInfo(
                            name=skill_name,
                            category=skill_info["category"],
                            confidence_score=confidence,
                            context=context,
                            is_required=True  # Default to required, can be refined later
                        )
                        extracted_skills.append(skill_obj)
                        processed_skills.add(skill_name)
                        break  # Only add each skill once
        
        # Sort by confidence score (highest first)
        extracted_skills.sort(key=lambda x: -x.confidence_score)
        
        return extracted_skills
    
    def _extract_context(self, text: str, start: int, end: int) -> str:
        """Extract context around a skill mention."""
        words = text.split()
        text_words = []
        char_count = 0
        start_word_idx = 0
        end_word_idx = len(words)
        
        # Find word indices for start and end positions
        for i, word in enumerate(words):
            if char_count <= start < char_count + len(word):
                start_word_idx = max(0, i - self.context_window // 2)
            if char_count <= end < char_count + len(word):
                end_word_idx = min(len(words), i + self.context_window // 2)
                break
            char_count += len(word) + 1  # +1 for space
        
        context_words = words[start_word_idx:end_word_idx]
        return " ".join(context_words)
    
    def _calculate_confidence(self, skill_name: str, context: str, matched_text: str) -> float:
        """Calculate confidence score for skill extraction."""
        base_confidence = 0.7
        skill_info = self.skill_db.get_skill_info(skill_name)
        
        if not skill_info:
            return 0.0
        
        # Apply skill weight
        confidence = base_confidence * skill_info.get("weight", 1.0)
        
        # Boost confidence for exact matches
        if matched_text.lower() == skill_name:
            confidence += 0.1
        
        # Context-based adjustments
        context_lower = context.lower()
        
        # Boost for technical contexts
        technical_indicators = [
            "experience", "proficient", "skilled", "knowledge", "familiar",
            "years", "development", "programming", "coding", "tech", "stack",
            "framework", "library", "database", "platform", "tool"
        ]
        
        for indicator in technical_indicators:
            if indicator in context_lower:
                confidence += 0.05
                break
        
        # Penalty for negative contexts
        negative_indicators = [
            "no experience", "not familiar", "learning", "beginner",
            "basic", "limited", "some knowledge"
        ]
        
        for indicator in negative_indicators:
            if indicator in context_lower:
                confidence -= 0.2
                break
        
        # Penalty for skills mentioned in wrong context
        if skill_info["category"] == SkillCategory.PROGRAMMING_LANGUAGE:
            if "spoken" in context_lower or "language skills" in context_lower:
                confidence -= 0.4
        
        # Ensure confidence is within bounds
        return max(0.0, min(1.0, confidence))
    
    async def categorize_skills(self, skills: List[SkillInfo]) -> Dict[SkillCategory, List[SkillInfo]]:
        """Group skills by category."""
        categorized = {}
        for skill in skills:
            if skill.category not in categorized:
                categorized[skill.category] = []
            categorized[skill.category].append(skill)
        return categorized
    
    def canonicalize_skill_names(self, raw_names: List[str]) -> List[SkillInfo]:
        """Resolve a list of raw skill labels (e.g. Instahyre's curated
        `keywords` array) through the alias map into canonical SkillInfo.

        These are human-curated at the source, so confidence is high. A
        label with no match in the alias map is kept as-is (category OTHER)
        rather than silently dropped — the source still vouches for it.
        """
        results = []
        seen = set()
        for raw_name in raw_names:
            if not raw_name or not raw_name.strip():
                continue
            name_clean = raw_name.strip()
            skill_info = self.skill_db.get_skill_info(name_clean)
            if skill_info:
                canonical_name = self.skill_db.aliases_map.get(name_clean.lower(), name_clean.lower())
                if canonical_name in seen:
                    continue
                seen.add(canonical_name)
                results.append(SkillInfo(
                    name=canonical_name,
                    category=skill_info["category"],
                    confidence_score=0.99,
                    context=None,
                    is_required=True
                ))
            else:
                key = name_clean.lower()
                if key in seen:
                    continue
                seen.add(key)
                results.append(SkillInfo(
                    name=key,
                    category=SkillCategory.OTHER,
                    confidence_score=0.8,
                    context=None,
                    is_required=True
                ))
        return results

    async def extract_from_job(self, job: StandardJob) -> SkillExtractionResult:
        """Extract skills from a StandardJob object."""
        import time
        start_time = time.time()
        
        # Combine relevant text fields
        text_parts = []
        
        if job.title:
            text_parts.append(job.title)
        if job.description:
            text_parts.append(job.description)
        if job.requirements:
            text_parts.append(job.requirements)
        if hasattr(job, 'qualifications') and job.qualifications:
            text_parts.append(job.qualifications)
        
        combined_text = "\n\n".join(filter(None, text_parts))
        
        # Extract skills
        skills = await self.extract_skills(combined_text)
        
        # Calculate processing time
        processing_time = (time.time() - start_time) * 1000
        
        # Build confidence scores dictionary
        confidence_scores = {skill.name: skill.confidence_score for skill in skills}
        
        return SkillExtractionResult(
            skills=skills,
            total_skills_found=len(skills),
            processing_time_ms=processing_time,
            confidence_scores=confidence_scores
        )
    
    async def get_top_skills(self, skills: List[SkillInfo], limit: int = 10) -> List[SkillInfo]:
        """Get top skills by confidence score."""
        return sorted(skills, key=lambda x: x.confidence_score, reverse=True)[:limit]
    
    async def filter_by_category(self, skills: List[SkillInfo], 
                               categories: List[SkillCategory]) -> List[SkillInfo]:
        """Filter skills by specific categories."""
        return [skill for skill in skills if skill.category in categories]
    
    async def get_technical_skills_only(self, skills: List[SkillInfo]) -> List[SkillInfo]:
        """Get only technical skills (excluding soft skills)."""
        technical_categories = [
            SkillCategory.PROGRAMMING_LANGUAGE,
            SkillCategory.FRAMEWORK,
            SkillCategory.DATABASE,
            SkillCategory.CLOUD_PLATFORM,
            SkillCategory.TOOL,
            SkillCategory.CERTIFICATION
        ]
        return await self.filter_by_category(skills, technical_categories)