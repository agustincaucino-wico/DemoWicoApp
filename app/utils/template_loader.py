"""
Email template utilities for loading and rendering email templates.
"""

import re
from pathlib import Path

from django.template import Context, Engine

# Standalone engine, independent of the project's TEMPLATES setting - these
# are plain string templates read straight from utils/email_templates/, not
# resolved through any app/template-dirs loader.
#
# string_if_invalid is set to a sentinel (instead of the default, silent
# empty string) so a missing context variable is detectable after
# rendering: NUL bytes can't occur in legitimate template content, so this
# can never collide with real output, and %s is replaced by Django with the
# name of the variable that failed to resolve. The sentinel never reaches a
# real email - _load_and_render_file raises before returning if it's found.
_MISSING_SENTINEL = "\x00MISSING:%s\x00"
_MISSING_RE = re.compile(r"\x00MISSING:(.*?)\x00")
_engine = Engine(string_if_invalid=_MISSING_SENTINEL)


class EmailTemplateLoader:
    """Utility class for loading and rendering email templates."""

    def __init__(self):
        self.template_dir = Path(__file__).parent / "email_templates"

    def load_template(self, template_name, context):
        """
        Load and render an email template with the given context.

        Args:
            template_name: Name of the template file (without extension)
            context: Dictionary with template variables

        Returns:
            tuple: (html_content, text_content)
        """
        html_path = self.template_dir / f"{template_name}.html"
        text_path = self.template_dir / f"{template_name}.txt"

        # HTML is autoescaped (context values may contain user-controlled
        # text like names); the one field that's intentionally pre-built raw
        # HTML (company_html) is marked {{ company_html|safe }} in the
        # templates that use it. Plain text has no HTML meaning, so it's
        # rendered with autoescape off - otherwise a literal "&" or "<" in
        # someone's name would come out as "&amp;"/"&lt;" in a plain-text
        # email.
        html_content = self._load_and_render_file(html_path, context, autoescape=True)
        text_content = self._load_and_render_file(text_path, context, autoescape=False)

        return html_content, text_content

    def _load_and_render_file(self, file_path, context, autoescape):
        """Load a template file and render it with context variables."""
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                template_content = file.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Template file not found: {file_path}")

        rendered = _engine.from_string(template_content).render(
            Context(context, autoescape=autoescape)
        )

        missing = _MISSING_RE.findall(rendered)
        if missing:
            raise ValueError(
                f"Missing template variable(s): {', '.join(sorted(set(missing)))}"
            )

        return rendered


# Global instance
email_template_loader = EmailTemplateLoader()
