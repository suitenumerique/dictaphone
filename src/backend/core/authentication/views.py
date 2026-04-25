"""PKCE OIDC Authentication Views"""

import logging
import secrets
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.http import HttpResponseRedirect

from lasuite.oidc_login.views import (
    OIDCAuthenticationCallbackView,
    OIDCAuthenticationRequestView,
)
from mozilla_django_oidc.utils import generate_code_challenge
from pydantic import ValidationError
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from core.authentication.models import (
    PKCEAuthenticationRequestModel,
    PKCETokenExchangeModel,
)
from core.utils import update_url_query_params

logger = logging.getLogger(__name__)
User = get_user_model()


PKCE_AUTH_CODE_CACHE_KEY_PREFIX = "pkce-auth-code"
AUTHORIZATION_CODE_SIZE = 64


def get_pkce_authorization_code_cache_key(code: str) -> str:
    """Generate cache key for PKCE authorization code"""
    return f"{PKCE_AUTH_CODE_CACHE_KEY_PREFIX}:{code}"


def is_mobile_login_url(url: str) -> bool:
    """Check if URL is for mobile login"""
    return urlsplit(url).path == "/mobile-login"


class PKCEOIDCAuthenticationRequestView(OIDCAuthenticationRequestView):
    """
    Handles PKCE (Proof Key for Code Exchange) OpenID Connect authentication requests.

    This view extends the OIDCAuthenticationRequestView to add functionality for
    handling PKCE-specific parameters during OpenID Connect authentication flows.
    It validates and processes PKCE-related attributes from the incoming request,
    ensuring compliance with PKCE standards. If `response_type` is "code", the
    view validates the PKCE parameters (`code_challenge`, `code_challenge_method`,
    and `state`) and stores them in the user's session.

    Methods
    -------
    get(request)
        Handles GET requests by extending the behavior of the parent class and
        managing PKCE-specific parameters when applicable.
    """

    def get(self, request):
        response = super().get(request)

        if request.GET.get("response_type", None) != "code":
            return response

        try:
            pkce_data = PKCEAuthenticationRequestModel.model_validate(
                {
                    "code_challenge": request.GET.get("code_challenge"),
                    "code_challenge_method": request.GET.get(
                        "code_challenge_method",
                        "S256",
                    ),
                    "state": request.GET.get("state"),
                }
            )
        except ValidationError as e:
            return Response(
                {"detail": "Invalid pkce request parameters.", "errors": e.errors()},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # We store the info in the session for use in the callback
        request.session["pkce_oidc_response_type"] = "code"
        request.session["pkce_oidc_data"] = pkce_data.model_dump()
        request.session.save()
        return response


class MobileFriendlyRedirect(HttpResponseRedirect):
    """Redirect that allows mobile deep link schemes."""

    @property
    def allowed_schemes(self) -> list[str]:
        """Add the mobile deep link prefix to the allowed schemes list"""
        return [
            *HttpResponseRedirect.allowed_schemes,
            settings.MOBILE_DEEP_LINK_SCHEME.split(":")[0],
        ]


class OIDCAuthenticationCallbackWithPkceView(OIDCAuthenticationCallbackView):
    """
    Handles the PKCE (Proof Key for Code Exchange) authentication callback.

    This view extends the base OIDCAuthenticationCallbackView to add support
    for the PKCE extension, which is primarily used in mobile application
    authentication flows. It adds a layer of security to the
    OAuth 2.0 protocol by generating a one-time use authorization code tied
    to the mobile application's specific client state.


    Methods
    -------
    login_success()
        Handles the successful login process, verifies PKCE-related session
        data, generates an authorization code, stores it in a cache with user
        and PKCE parameters, and redirects to the appropriate mobile deep link URL.
    """

    def login_success(self):
        """Handles successful login callback."""
        res = super().login_success()
        if self.request.session.pop("pkce_oidc_response_type", None) != "code":
            return res

        pkce_data = self.request.session.pop("pkce_oidc_data", None)
        self.request.session.save()
        if not pkce_data:
            logger.error("No PKCE data found in session")
            return self.login_failure()

        authorization_code = secrets.token_urlsafe(AUTHORIZATION_CODE_SIZE)
        cache.set(
            get_pkce_authorization_code_cache_key(authorization_code),
            {
                "user_id": self.user.pk,
                "code_challenge": pkce_data["code_challenge"],
                "code_challenge_method": pkce_data["code_challenge_method"],
            },
            timeout=settings.AUTH_PKCE_CACHE_TTL_SECONDS,
        )

        if not is_mobile_login_url(res.url):
            logger.warning(
                "PKCE mobile callback did not resolve to the expected mobile login URL"
            )
            return self.login_failure()

        mobile_redirect = update_url_query_params(
            settings.MOBILE_DEEP_LINK_SCHEME,
            {"code": [authorization_code], "state": [pkce_data["state"]]},
        )
        return MobileFriendlyRedirect(mobile_redirect)


class PKCEOAuthTokenExchangeView(APIView):
    """
    Handles PKCE OAuth token exchange requests.

    This API view is designed to facilitate PKCE (Proof Key for Code Exchange)
    token exchange. It validates the incoming request, checks the authorization code,
    and generates access and refresh tokens for authenticated users. The view ensures
    security by performing stringent validation on the code verifier against the
    computed challenge.

    Attributes:
        permission_classes (list): List of permissions for the view. Defaults to AllowAny.
        authentication_classes (list): List of authentication methods for the view.
            This view requires no authentication.

    Methods:
        post: Handles POST requests for the PKCE token exchange process, validates
            parameters, and returns tokens upon successful verification.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request) -> Response:
        """Handles request for PKCE OAuth token exchange."""
        try:
            request_data = PKCETokenExchangeModel.model_validate(request.data)
        except ValidationError as e:
            return Response(
                {"detail": "Invalid pkce request parameters.", "errors": e.errors()},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key = get_pkce_authorization_code_cache_key(request_data.code)
        code_data = cache.get(cache_key)
        if not code_data:
            return Response(
                {"detail": "Invalid or expired authorization code."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # We allow only 1 try
        cache.delete(cache_key)

        expected_challenge = code_data["code_challenge"]
        method = code_data.get("code_challenge_method", "S256")

        computed_challenge = generate_code_challenge(request_data.code_verifier, method)
        if not secrets.compare_digest(computed_challenge, expected_challenge):
            logger.warning("Invalid code_verifier for PKCE token exchange")
            return Response(
                {"detail": "Invalid code_verifier."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.filter(pk=code_data["user_id"], is_active=True).first()
        if not user:
            return Response(
                {"detail": "Invalid authorization code user."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            }
        )
