"""
Email template utilities for loading and rendering email templates.
"""

from pathlib import Path


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

        html_content = self._load_and_render_file(html_path, context)
        text_content = self._load_and_render_file(text_path, context)

        return html_content, text_content

    def _load_and_render_file(self, file_path, context):
        """Load a template file and render it with context variables."""
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                template_content = file.read()

            # Simple string formatting - you could use Jinja2 or Django templates here
            return template_content.format(**context)

        except FileNotFoundError:
            raise FileNotFoundError(f"Template file not found: {file_path}")
        except KeyError as e:
            raise ValueError(f"Missing template variable: {e}")


# Global instance
email_template_loader = EmailTemplateLoader()
