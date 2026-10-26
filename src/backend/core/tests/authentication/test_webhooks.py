"""Authentication remains disabled until a webhook secret is configured."""

import pytest
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory

from core.authentication.webhooks import AiWebhookAuthentication


@pytest.mark.parametrize("secret", [None, ""])
@pytest.mark.parametrize("authorization", ["", "Bearer ", "Bearer bad-key"])
def test_webhook_without_configured_secret_rejects_requests(
    settings, secret, authorization
):
    """Missing secrets must never authenticate an empty Authorization header."""
    settings.AI_WEBHOOK_API_KEY = secret
    request = APIRequestFactory().post("/", HTTP_AUTHORIZATION=authorization)

    with pytest.raises(AuthenticationFailed):
        AiWebhookAuthentication().authenticate(request)
