"""Session-bound mobile JWTs. Never accept legacy tokens without a session."""

import base64
import hashlib
from datetime import datetime
from datetime import timezone as dt_timezone
from importlib import import_module
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from cryptography.fernet import Fernet, MultiFernet
from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken, Token

from core.models import MobileAuthSession

SESSION_CLAIM = "mobile_session_id"


class SignedRefreshToken(Token):
    """Verify even consumed refresh tokens, so reuse can revoke their family."""

    token_type = "refresh"  # noqa: S105
    lifetime = api_settings.REFRESH_TOKEN_LIFETIME


class RevocationToken(Token):
    """A durable logout-only credential; never usable for API access or refresh."""

    token_type = "mobile_revoke"  # noqa: S105
    lifetime = api_settings.REFRESH_TOKEN_LIFETIME


def oidc_cipher():
    """Separate encryption purpose from Django signing and support key rotation."""
    keys = [settings.SECRET_KEY, *settings.SECRET_KEY_FALLBACKS]
    return MultiFernet(
        [
            Fernet(
                base64.urlsafe_b64encode(
                    hashlib.sha256(("mobile-oidc-id-token:" + key).encode()).digest()
                )
            )
            for key in keys
        ]
    )


def token_session_id(token):
    """Reject absent or malformed session claims before querying a UUID column."""
    try:
        return UUID(str(token[SESSION_CLAIM]))
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise AuthenticationFailed("Invalid mobile session.") from exc


def check_session(session, token):
    """Only a live session belonging to the signed token's user grants access."""
    if (
        session is None
        or str(session.user_id) != str(token.get(api_settings.USER_ID_CLAIM))
        or session.revoked_at is not None
        or session.expires_at <= timezone.now()
    ):
        raise AuthenticationFailed("Mobile session has expired or been revoked.")


def revoke_session(session, reason, *, delete_browser=True):
    """Caller holds the session row lock; deletion also prevents silent re-login."""
    if session.revoked_at is None:
        session.revoked_at = timezone.now()
        session.revocation_reason = reason
        session.save(update_fields=["revoked_at", "revocation_reason", "updated_at"])
    if delete_browser and session.browser_session_key:
        key = session.browser_session_key
        transaction.on_commit(
            lambda: import_module(settings.SESSION_ENGINE).SessionStore().delete(key),
            robust=True,
        )


def issue_token_pair(session):
    """Rotate the current token and cap both token expiries at session expiry."""
    refresh = RefreshToken.for_user(session.user)
    refresh[SESSION_CLAIM] = str(session.pk)
    refresh["exp"] = min(refresh["exp"], int(session.expires_at.timestamp()))
    session.refresh_jti = refresh[api_settings.JTI_CLAIM]
    session.save(update_fields=["refresh_jti", "updated_at"])
    # for_user creates the outstanding row before custom claims are attached.
    OutstandingToken.objects.filter(jti=session.refresh_jti).update(
        token=str(refresh),
        expires_at=datetime.fromtimestamp(refresh["exp"], tz=dt_timezone.utc),
    )
    access = refresh.access_token
    access["exp"] = min(access["exp"], int(session.expires_at.timestamp()))
    revoke = RevocationToken()
    revoke[SESSION_CLAIM] = str(session.pk)
    revoke[api_settings.USER_ID_CLAIM] = str(session.user_id)
    revoke["exp"] = int(session.expires_at.timestamp())
    return {"refresh": str(refresh), "access": str(access), "revoke": str(revoke)}


def create_mobile_session(user, **context):
    """Create one absolute-lived session per successful PKCE exchange."""
    with transaction.atomic():
        session = MobileAuthSession.objects.create(
            user=user,
            expires_at=timezone.now() + api_settings.REFRESH_TOKEN_LIFETIME,
            **context,
        )
        return issue_token_pair(session)


def refresh_mobile_session(raw_token):
    """Serialize refresh/logout and commit reuse revocation before raising 401."""
    try:
        token = SignedRefreshToken(raw_token)
    except TokenError as exc:
        raise AuthenticationFailed("Invalid refresh token.") from exc
    session_id = token_session_id(token)
    reused = False
    with transaction.atomic():
        session = (
            MobileAuthSession.objects.select_for_update().filter(pk=session_id).first()
        )
        check_session(session, token)
        if not session.user.is_active:
            raise AuthenticationFailed("User is inactive.")
        if (
            session.refresh_jti != token.get(api_settings.JTI_CLAIM)
            or BlacklistedToken.objects.filter(
                token__jti=token.get(api_settings.JTI_CLAIM)
            ).exists()
        ):
            revoke_session(session, "refresh_reuse")
            reused = True
        else:
            RefreshToken(raw_token, verify=False).blacklist()
            pair = issue_token_pair(session)
    if reused:
        raise AuthenticationFailed(
            "Refresh token reuse detected; please sign in again."
        )
    return pair


class MobileJWTAuthentication(JWTAuthentication):
    """Validate revocation on every request, including media authorization."""

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        session = MobileAuthSession.objects.filter(
            pk=token_session_id(validated_token)
        ).first()
        check_session(session, validated_token)
        return user


# Register the custom authentication class with the existing JWT OpenAPI scheme.


class MobileJWTScheme(SimpleJWTScheme):
    """Preserve bearer authentication in generated API documentation."""

    target_class = "core.authentication.mobile.MobileJWTAuthentication"
