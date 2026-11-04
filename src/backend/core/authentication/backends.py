"""Authentication Backends for the Dictaphone core app."""

import re

from django.conf import settings
from django.core.exceptions import SuspiciousOperation

from lasuite.oidc_login.backends import (
    OIDCAuthenticationBackend as LaSuiteOIDCAuthenticationBackend,
)
from rest_framework.authentication import SessionAuthentication

from core.models import User


class OIDCAuthenticationBackend(LaSuiteOIDCAuthenticationBackend):
    """Custom OpenID Connect (OIDC) Authentication Backend.

    This class overrides the default OIDC Authentication Backend to accommodate differences
    in the User and Identity models, and handles signed and/or encrypted UserInfo response.
    """

    def get_extra_claims(self, user_info):
        """
        Return extra claims from user_info.

        Args:
          user_info (dict): The user information dictionary.

        Returns:
          dict: A dictionary of extra claims.

        """
        roles = user_info.get("roles")
        if isinstance(roles, str):
            roles = roles.split()
        # Malformed claims must never accidentally grant access.
        if not isinstance(roles, list) or not all(
            isinstance(role, str) for role in roles
        ):
            roles = None
        siret = user_info.get("siret")
        siret = siret.strip() if isinstance(siret, str) else ""
        return {
            "oidc_roles": roles,
            "organization_siret": siret if re.fullmatch(r"[0-9]{14}", siret) else "",
            # Get user's full name from OIDC fields defined in settings
            "full_name": self.compute_full_name(user_info),
            "short_name": user_info.get(settings.OIDC_USERINFO_SHORTNAME_FIELD),
        }

    def update_user_if_needed(self, user, claims):
        """Also persist revoked roles and cleared claims, ignored by the base backend."""
        super().update_user_if_needed(user, claims)
        cleared_fields = []
        for field in ("oidc_roles", "organization_siret"):
            if (
                field in claims
                and not claims[field]
                and getattr(user, field) != claims[field]
            ):
                setattr(user, field, claims[field])
                cleared_fields.append(field)
        if cleared_fields:
            user.save(update_fields=cleared_fields)

    def get_existing_user(self, sub, email):
        """Fetch existing user by sub or email."""
        try:
            return User.objects.get(sub=sub)
        except User.DoesNotExist:
            if email and settings.OIDC_FALLBACK_TO_EMAIL_FOR_IDENTIFICATION:
                try:
                    return User.objects.get(email__iexact=email)
                except User.DoesNotExist:
                    pass
                except User.MultipleObjectsReturned as e:
                    raise SuspiciousOperation(
                        "Multiple user accounts share a common email."
                    ) from e
        return None


class SessionAuthenticationWith401(SessionAuthentication):
    """
    Identical to DRF's SessionAuthentication, but returns a WWW-Authenticate
    header so unauthenticated requests get a 401 instead of a 403.

    The scheme is deliberately NOT 'Basic' — that would trigger the browser's
    native login popup. 'Session' is ignored by the browser's auth UI but is
    still truthy, so DRF keeps the status at 401.
    """

    def authenticate_header(self, request):
        return "Session"
