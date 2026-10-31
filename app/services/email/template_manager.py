"""Email template manager using Jinja2."""

import os
import logging
from datetime import datetime
from typing import Dict, Any, Tuple, Optional
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateNotFound
from jinja2.exceptions import TemplateError

from ...config.settings import settings

logger = logging.getLogger(__name__)


class EmailTemplateManager:
    """Manages email templates with Jinja2."""

    def __init__(self, templates_dir: Optional[str] = None):
        """
        Initialize template manager.

        Args:
            templates_dir: Directory containing email templates
        """
        self.templates_dir = templates_dir or settings.email_template_dir
        self.templates_path = Path(self.templates_dir)

        # Ensure templates directory exists
        self.templates_path.mkdir(parents=True, exist_ok=True)

        # Initialize Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_path)),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True
        )

        # Add custom filters
        self._add_custom_filters()

        # Template cache
        self._template_cache = {}

    def _add_custom_filters(self):
        """Add custom Jinja2 filters for email templates."""

        def currency_filter(value, currency='USD'):
            """Format currency values."""
            if value is None:
                return "Not specified"
            try:
                if currency == 'USD':
                    return f"${value:,.0f}"
                return f"{value:,.0f} {currency}"
            except (ValueError, TypeError):
                return str(value)

        def date_filter(value, format='%B %d, %Y'):
            """Format date values."""
            if value is None:
                return ""
            try:
                if hasattr(value, 'strftime'):
                    return value.strftime(format)
                return str(value)
            except Exception:
                return str(value)

        def truncate_words(value, length=20):
            """Truncate text to specified number of words."""
            if not value:
                return ""
            words = str(value).split()
            if len(words) <= length:
                return value
            return " ".join(words[:length]) + "..."

        # Register filters
        self.env.filters['currency'] = currency_filter
        self.env.filters['date'] = date_filter
        self.env.filters['truncate_words'] = truncate_words

    async def render_template(
        self,
        template_name: str,
        context: Dict[str, Any]
    ) -> Tuple[str, str]:
        """
        Render HTML and text versions of an email template.

        Args:
            template_name: Name of template (without extension)
            context: Template context variables

        Returns:
            Tuple of (html_content, text_content)

        Raises:
            TemplateNotFound: If template doesn't exist
            TemplateError: If template rendering fails
        """
        try:
            # Add global context variables
            full_context = self._build_context(context)

            # Render HTML version
            html_template_name = f"{template_name}.html"
            html_content = await self._render_single_template(html_template_name, full_context)

            # Render text version (fallback to auto-generated if not exists)
            text_template_name = f"{template_name}.txt"
            try:
                text_content = await self._render_single_template(text_template_name, full_context)
            except TemplateNotFound:
                # Generate basic text version from HTML
                text_content = self._html_to_text(html_content)
                logger.warning(f"Text template {text_template_name} not found, generated from HTML")

            return html_content, text_content

        except TemplateNotFound as e:
            logger.error(f"Template not found: {e}")
            raise
        except TemplateError as e:
            logger.error(f"Template rendering error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error rendering template {template_name}: {e}")
            raise TemplateError(f"Failed to render template: {e}")

    async def _render_single_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """Render a single template file."""
        try:
            template = self.env.get_template(template_name)
            return template.render(**context)
        except TemplateNotFound:
            raise
        except Exception as e:
            raise TemplateError(f"Error rendering {template_name}: {e}")

    def _build_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Build full template context with global variables."""
        base_context = {
            'app_name': 'JobRadar',
            'app_url': settings.frontend_url,
            'support_email': settings.ses_from_email,
            'company_name': 'JobRadar',
            'current_year': datetime.utcnow().year,
            'from_name': settings.ses_from_name,
        }

        # Merge with provided context (user context takes precedence)
        base_context.update(context)
        return base_context

    def _html_to_text(self, html_content: str) -> str:
        """Convert HTML content to plain text (basic implementation)."""
        import re

        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', html_content)

        # Decode HTML entities
        import html
        text = html.unescape(text)

        # Clean up whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = text.strip()

        return text

    def load_template(self, template_name: str):
        """Load a template instance."""
        try:
            return self.env.get_template(template_name)
        except TemplateNotFound:
            logger.error(f"Template not found: {template_name}")
            raise

    def get_template_list(self) -> list:
        """Get list of available templates."""
        try:
            return self.env.list_templates(extensions=['html', 'txt'])
        except Exception as e:
            logger.error(f"Error listing templates: {e}")
            return []

    def validate_template(self, template_content: str) -> bool:
        """Validate template syntax."""
        try:
            self.env.from_string(template_content)
            return True
        except TemplateError as e:
            logger.error(f"Template validation failed: {e}")
            return False

    def template_exists(self, template_name: str) -> bool:
        """Check if a template exists."""
        template_path = self.templates_path / template_name
        return template_path.exists()

    def get_template_path(self, template_name: str) -> Path:
        """Get full path to a template file."""
        return self.templates_path / template_name

    def create_template(self, template_name: str, content: str) -> bool:
        """Create a new template file."""
        try:
            template_path = self.get_template_path(template_name)
            template_path.parent.mkdir(parents=True, exist_ok=True)

            with open(template_path, 'w', encoding='utf-8') as f:
                f.write(content)

            logger.info(f"Template created: {template_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to create template {template_name}: {e}")
            return False