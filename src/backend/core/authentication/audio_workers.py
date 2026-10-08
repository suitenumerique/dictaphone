"""Mode-scoped bearer authentication for isolated audio workers."""

import logging
import secrets

from django.conf import settings
from django.contrib.auth.models import AnonymousUser

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger(__name__)


class AudioWorkerAuthentication(BaseAuthentication):
    """
    Authenticate an audio worker using the token configured for its mode.

    Audio workers do not use a user session or database token.
    """

    def authenticate(self, request):
        mode = request.parser_context["kwargs"]["mode"]
        token = getattr(settings, f"AUDIO_EXTRACTOR_{mode.upper()}_TOKEN", "")
        authorization_header: str = request.headers.get("Authorization") or ""
        if (
            not token
            or not authorization_header.startswith("Bearer ")
            or not secrets.compare_digest(
                authorization_header.removeprefix("Bearer ").encode(), token.encode()
            )
        ):
            logger.warning(
                "Authentication failed: Bad Authorization header for audio worker "
                "(mode: %s, ip: %s)",
                mode,
                request.META.get("REMOTE_ADDR"),
            )
            raise AuthenticationFailed("Invalid audio worker token.")
        return AnonymousUser(), mode

    def authenticate_header(self, request):
        return "Bearer"
