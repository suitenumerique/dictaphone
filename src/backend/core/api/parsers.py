"""Bound webhook bodies before DRF or Pydantic materializes their JSON."""

from io import BytesIO

from django.conf import settings

from rest_framework.exceptions import APIException, ParseError
from rest_framework.parsers import DataAndFiles, JSONParser, MultiPartParser

from core.payloads import (
    PayloadLimitExceeded,
    check_content_length,
    read_stream,
)


class PayloadTooLarge(APIException):
    """Permanent rejection of an oversized incoming request."""

    status_code = 413
    default_detail = "Webhook payload exceeds configured limits."


class BoundedWebhookJSONParser(JSONParser):
    """Enforce actual byte bounds, regardless of Content-Length."""

    def parse(self, stream, media_type=None, parser_context=None):
        request = (parser_context or {}).get("request")
        try:
            if request is not None:
                check_content_length(
                    request.META.get("CONTENT_LENGTH"),
                    settings.PAYLOAD_WEBHOOK_MAX_BYTES,
                )
            content = read_stream(stream, settings.PAYLOAD_WEBHOOK_MAX_BYTES)
        except PayloadLimitExceeded as exc:
            raise PayloadTooLarge() from exc
        try:
            return super().parse(BytesIO(content), media_type, parser_context)
        except RecursionError as exc:
            raise ParseError("Webhook JSON is too deeply nested.") from exc


class BoundedWebhookMultiPartParser(MultiPartParser):
    """Preserve flat multipart webhooks with the same body ceiling as JSON."""

    def parse(self, stream, media_type=None, parser_context=None):
        request = (parser_context or {}).get("request")
        try:
            if request is not None:
                check_content_length(
                    request.META.get("CONTENT_LENGTH"),
                    settings.PAYLOAD_WEBHOOK_MAX_BYTES,
                )
            content = read_stream(stream, settings.PAYLOAD_WEBHOOK_MAX_BYTES)
        except PayloadLimitExceeded as exc:
            raise PayloadTooLarge() from exc
        parsed = super().parse(BytesIO(content), media_type, parser_context)
        return DataAndFiles(parsed.data.dict(), parsed.files)
