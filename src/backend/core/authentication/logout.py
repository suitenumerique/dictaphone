"""Revoke mobile token families independently of the provider's browser flow."""

import logging
import secrets
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import auth
from django.core.cache import cache
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.views import View

from cryptography.fernet import InvalidToken
from drf_spectacular.utils import extend_schema
from lasuite.oidc_login.views import (
    OIDCBackChannelLogoutView,
    OIDCLogoutView,
)
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError

from core.authentication.mobile import (
    RevocationToken,
    SignedRefreshToken,
    oidc_cipher,
    refresh_mobile_session,
    revoke_session,
    token_session_id,
)
from core.authentication.views import MobileFriendlyRedirect
from core.models import MobileAuthSession

logger = logging.getLogger(__name__)
LOGOUT_TTL = 300


def consume(key):
    """Claim a short-lived cache entry atomically across workers."""
    if not cache.add(f"{key}:claimed", True, timeout=LOGOUT_TTL):
        return None
    value = cache.get(key)
    cache.delete(key)
    return value


def browser_logout_url(request, encrypted_id_token, *, mobile):
    """Keep ID tokens server-side until a one-use browser flow is opened."""
    if not encrypted_id_token or not settings.OIDC_OP_LOGOUT_ENDPOINT:
        return None
    ticket = secrets.token_urlsafe(32)
    try:
        cache.set(
            f"mobile-logout:{ticket}",
            {"id_token": encrypted_id_token, "mobile": mobile},
            timeout=LOGOUT_TTL,
        )
    except Exception:  # noqa: BLE001 - provider logout must not undo local revocation.
        logger.warning("Provider logout context could not be stored")
        return None
    return (
        request.build_absolute_uri(reverse("mobile_logout_start"))
        + "?"
        + urlencode({"ticket": ticket})
    )


class TokenPairSerializer(serializers.Serializer):
    """Application credentials and a separate logout-only credential."""

    access = serializers.CharField()
    refresh = serializers.CharField()
    revoke = serializers.CharField()


class LogoutResponseSerializer(serializers.Serializer):
    """A single-use browser URL, when provider logout is available."""

    logout_url = serializers.URLField(allow_null=True)


class RefreshSerializer(serializers.Serializer):
    """Refresh body shared with existing mobile versions."""

    refresh = serializers.CharField(max_length=8192)


class NoStoreAPIView(APIView):
    """Token responses and logout URLs must not be cached."""

    def get_authenticate_header(self, request):
        """Body credentials still use 401 for authentication failures."""
        return 'Bearer realm="api"'

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response


class MobileTokenRefreshView(NoStoreAPIView):
    """Rotate one session under a database lock, detecting token reuse."""

    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = RefreshSerializer

    @extend_schema(request=RefreshSerializer, responses=TokenPairSerializer)
    def post(self, request):
        """Refresh is authenticated by its signed body credential."""
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(refresh_mobile_session(serializer.validated_data["refresh"]))


class LogoutSerializer(serializers.Serializer):
    """Prefer a logout-only credential; retain refresh-body compatibility."""

    refresh = serializers.CharField(required=False, max_length=8192)
    revoke = serializers.CharField(required=False, max_length=8192)

    def validate(self, attrs):
        """Exactly one credential identifies the login being revoked."""
        if bool(attrs.get("refresh")) == bool(attrs.get("revoke")):
            raise serializers.ValidationError("Provide either revoke or refresh.")
        return attrs


class MobileLogoutView(NoStoreAPIView):
    """Idempotently revoke a login, even with a consumed refresh token."""

    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = LogoutSerializer

    @extend_schema(request=LogoutSerializer, responses=LogoutResponseSerializer)
    def post(self, request):
        """Commit revocation before returning an optional provider logout URL."""
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            token = (
                RevocationToken(data["revoke"])
                if "revoke" in data
                else SignedRefreshToken(data["refresh"])
            )
        except TokenError as exc:
            raise AuthenticationFailed("Invalid logout credential.") from exc
        with transaction.atomic():
            session = (
                MobileAuthSession.objects.select_for_update()
                .filter(pk=token_session_id(token))
                .first()
            )
            if session is None:
                return Response({"logout_url": None})
            if str(session.user_id) != str(token.get("user_id")):
                raise AuthenticationFailed("Invalid mobile session.")
            revoke_session(session, "logout")
        url = browser_logout_url(request, session.encrypted_id_token, mobile=True)
        return Response({"logout_url": url})


class MobileLogoutStartView(View):
    """Exchange a one-use ticket for a provider end-session request."""

    def get(self, request):
        """The provider browser flow never needs an application bearer token."""
        ticket = request.GET.get("ticket", "")
        if len(ticket) != 43:
            return HttpResponseBadRequest("Invalid logout ticket.")
        context = consume(f"mobile-logout:{ticket}")
        if not context:
            return HttpResponseBadRequest("Invalid or expired logout ticket.")
        try:
            id_token = oidc_cipher().decrypt(context["id_token"].encode()).decode()
        except InvalidToken:
            return HttpResponseBadRequest("Expired logout context.")
        state = secrets.token_urlsafe(32)
        cache.set(f"mobile-logout-state:{state}", context["mobile"], timeout=LOGOUT_TTL)
        params = {
            "id_token_hint": id_token,
            "state": state,
            "post_logout_redirect_uri": request.build_absolute_uri(
                reverse("mobile_logout_callback")
            ),
        }
        response = HttpResponseRedirect(
            settings.OIDC_OP_LOGOUT_ENDPOINT + "?" + urlencode(params)
        )
        response["Cache-Control"] = "no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response


class MobileLogoutCallbackView(View):
    """Validate provider state independently of the deleted login cookie."""

    def get(self, request):
        """Return to the mobile callback only after validating the logout flow."""
        state = request.GET.get("state", "")
        if len(state) != 43:
            return HttpResponseBadRequest("Invalid logout state.")
        mobile = consume(f"mobile-logout-state:{state}")
        if mobile is None:
            return HttpResponseBadRequest("Invalid or expired logout state.")
        response = (
            MobileFriendlyRedirect(settings.MOBILE_DEEP_LINK_SCHEME + "?logout=1")
            if mobile
            else HttpResponseRedirect(settings.LOGOUT_REDIRECT_URL or "/")
        )
        response["Cache-Control"] = "no-store"
        return response


class SessionOIDCLogoutView(OIDCLogoutView):
    """Browser logout also revokes mobile logins issued through that session."""

    def post(self, request):
        """End local authentication before the user leaves for the provider."""
        id_token = request.session.get("oidc_id_token")
        encrypted = (
            oidc_cipher().encrypt(id_token.encode()).decode() if id_token else ""
        )
        with transaction.atomic():
            sessions = (
                MobileAuthSession.objects.select_for_update()
                .filter(
                    browser_session_key=request.session.session_key or "missing",
                    revoked_at__isnull=True,
                )
                .order_by("pk")
            )
            for session in sessions:
                revoke_session(session, "browser_logout", delete_browser=False)
        auth.logout(request)
        url = browser_logout_url(request, encrypted, mobile=False)
        response = HttpResponseRedirect(url or settings.LOGOUT_REDIRECT_URL or "/")
        response["Cache-Control"] = "no-store"
        return response


class MobileBackChannelLogoutView(OIDCBackChannelLogoutView):
    """Use indexed mobile sessions even when Django sessions live in Redis."""

    def validate_logout_token(self, logout_token):
        """Retain the verified issuer for scoped session matching."""
        if not settings.OIDC_OP_URL:
            return None
        payload = super().validate_logout_token(logout_token)
        if payload:
            if not isinstance(payload.get("jti"), str) or not payload["jti"]:
                return None
            issued_at = payload.get("iat")
            if not isinstance(issued_at, (int, float)) or (
                timezone.now().timestamp() - issued_at > self.MAX_TOKEN_AGE_SECONDS
            ):
                return None
            self.issuer = payload["iss"]
        return payload

    def logout_user_sessions(self, sub, sid=None):
        """Serialize revocation against refresh and delete associated browser cookies."""
        with transaction.atomic():
            sessions = (
                MobileAuthSession.objects.select_for_update()
                .filter(
                    oidc_issuer=self.issuer,
                )
                .order_by("pk")
            )
            if sub:
                sessions = sessions.filter(oidc_sub=sub)
            if sid:
                sessions = sessions.filter(oidc_sid=sid)
            for session in sessions:
                revoke_session(session, "provider_logout")
        # Preserve dependency handling for browser-only database-backed sessions.
        if settings.SESSION_ENGINE in (
            "django.contrib.sessions.backends.db",
            "django.contrib.sessions.backends.cached_db",
        ):
            return super().logout_user_sessions(sub, sid)
        return True
