import logging
import os
import re
from datetime import datetime
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings

logger = logging.getLogger(__name__)

class TemplateService:
    """Template rendering service for emails."""

    def __init__(self):
        # Set up Jinja2 environment
        template_dir = os.path.join(os.path.dirname(__file__), '..', 'templates')
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True
        )

        # Add custom filters
        self.env.filters['format_date'] = self._format_date

        # Global context variables
        self.base_context = {
            "app_name": settings.APP_NAME,
            "base_url": settings.BASE_URL,
            "year": datetime.now().year,
            "current_year": datetime.now().year
        }

    def _format_date(self, value, format='%Y-%m-%d %H:%M:%S'):
        """Format datetime object."""
        if isinstance(value, datetime):
            return value.strftime(format)
        return value

    def render_email_template(self, template_name: str, context: Dict[str, Any] = None) -> Dict[str, str]:
        """
        Render email template in both HTML and text formats.
        Returns: {"html": html_content, "text": text_content}
        """
        try:
            # Merge base context with provided context
            render_context = {**self.base_context, **(context or {})}

            # Render HTML template
            html_template = self.env.get_template(f"emails/{template_name}.html")
            html_content = html_template.render(**render_context)

            # Try to render text template (optional)
            text_content = ""
            try:
                text_template = self.env.get_template(f"emails/{template_name}.txt")
                text_content = text_template.render(**render_context)
            except Exception:
                # If no text template, create a basic one from HTML
                text_content = re.sub(r'<[^>]+>', '', html_content)
                text_content = re.sub(r'\n\s*\n', '\n\n', text_content).strip()

            return {
                "html": html_content,
                "text": text_content
            }

        except Exception as e:
            logger.error(f"Failed to render template {template_name}: {e}")
            raise

    def render_template(self, template_path: str, context: Dict[str, Any] = None) -> str:
        """Render any template with given context."""
        try:
            render_context = {**self.base_context, **(context or {})}
            template = self.env.get_template(template_path)
            return template.render(**render_context)
        except Exception as e:
            logger.error(f"Failed to render template {template_path}: {e}")
            raise

template_service = TemplateService()
