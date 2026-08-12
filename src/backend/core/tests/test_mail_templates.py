"""Tests for rendered email templates."""

from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django.utils.translation import override

PREVIEW_DIR = Path(__file__).parent / "assets" / "email_previews"


def test_render_transcription_ready_email_previews():
    """Render a local preview for every language supported by the application."""
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

    for language, _language_name in settings.LANGUAGES:
        with override(language):
            html = render_to_string(
                "mail/html/transcription_ready.html",
                {
                    "title": _("Your transcription is ready"),
                    "message": _("Your recording has been transcribed:"),
                    "link": "https://dictaphone.example.com/recordings/123",
                    "link_label": "Team meeting",
                    "button_label": _("View transcription"),
                    "brandname": "Dictaphone",
                    "logo_img": "https://example.com/logo.png",
                    "support_email": "support@example.com",
                },
            )

        preview_path = PREVIEW_DIR / f"transcription_ready_{language}.html"
        preview_path.write_text(html, encoding="utf-8")

        assert f'<html lang="{language}">' in html
        assert "Team meeting" in html
