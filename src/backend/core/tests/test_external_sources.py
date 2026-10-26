"""Security policy for externally supplied transcript and summary URLs."""

import traceback
from unittest.mock import Mock

import pytest
import requests

from core.external_sources import (
    fetch_external_source,
    validate_external_source_url,
)
from core.utils import redact_url


@pytest.fixture(autouse=True)
def external_source_policy(settings):
    """Enable production-like checks independently of the test environment."""
    settings.EXTERNAL_SOURCE_ALLOWED_URL_PREFIXES = frozenset(
        {"https://storage.example/bucket/"}
    )
    settings.EXTERNAL_SOURCE_REQUIRE_HTTPS = True


@pytest.mark.parametrize(
    "url",
    [
        "https://storage.example/bucket/object.json",
        "https://storage.example/bucket/nested/object.txt?X-Amz-Signature=secret",
        "https://STORAGE.example:443/bucket/object.json",
        "https://storage.example/bucket/a%20file.json",
    ],
)
def test_allowed_sources(url):
    """Accept objects in the exact bucket, preserving signed query strings."""
    session = Mock()
    session.get.return_value.status_code = 200
    assert fetch_external_source(session, url) is session.get.return_value
    session.get.assert_called_once_with(
        url, timeout=(10, 20), allow_redirects=False, stream=True
    )
    session.get.return_value.raise_for_status.assert_called_once_with()


@pytest.mark.parametrize(
    "url",
    [
        "http://storage.example/bucket/file",
        "ftp://storage.example/bucket/file",
        "file:///bucket/file",
        "//storage.example/bucket/file",
        "https://other.example/bucket/file",
        "https://storage.example.evil/bucket/file",
        "https://storage.example@evil.example/bucket/file",
        "https://user:password@storage.example/bucket/file",
        "https://storage.example:444/bucket/file",
        "https://storage.example:0/bucket/file",
        "https://storage.example/bucket-other/file",
        "https://storage.example/other/file?bucket=/bucket/",
        "https://storage.example/bucket/../other/file",
        "https://storage.example/bucket/%2e%2e/other/file",
        "https://storage.example/bucket/%252e%252e/other/file",
        "https://storage.example/bucket/%2f..%2fother/file",
        "https://storage.example/bucket/./file",
        "https://storage.example/bucket/\\../other/file",
        "https://storage.example/bucket/%5c..%5cother/file",
        "https://storage.example/bucket/file#fragment",
        "https://storage.example/bucket/file\n",
        "https://storage.example/bucket/%00file",
        "https://storage.example:invalid/bucket/file",
        "",
        None,
    ],
)
def test_disallowed_sources_never_make_request(url):
    """Reject origin spoofing, sibling buckets, traversal, and malformed URLs."""
    session = Mock()
    with pytest.raises(ValueError):
        fetch_external_source(session, url)
    session.get.assert_not_called()


def test_http_can_be_allowed(settings):
    """Local development can permit HTTP explicitly."""
    settings.EXTERNAL_SOURCE_ALLOWED_URL_PREFIXES = ["http://rustfs:9000/bucket/"]
    settings.EXTERNAL_SOURCE_REQUIRE_HTTPS = False
    validate_external_source_url("http://rustfs:9000/bucket/object")
    with pytest.raises(ValueError, match="not allowed"):
        validate_external_source_url("http://rustfs:9001/bucket/object")


def test_https_required_even_with_http_prefix(settings):
    """An HTTP allowlist entry cannot override the HTTPS setting."""
    settings.EXTERNAL_SOURCE_ALLOWED_URL_PREFIXES = ["http://storage.example/bucket/"]
    with pytest.raises(ValueError, match="HTTPS"):
        validate_external_source_url("http://storage.example/bucket/file")


def test_none_skips_all_url_checks_and_warns_each_time(settings, caplog):
    """Compatibility mode emits one warning per check without exposing secrets."""
    settings.EXTERNAL_SOURCE_ALLOWED_URL_PREFIXES = None
    for _ in range(2):
        validate_external_source_url("http://unlisted.example/file?signature=secret")
    assert len(caplog.records) == 2
    assert all("validation is disabled" in record.message for record in caplog.records)
    assert "secret" not in caplog.text


def test_empty_list_denies_all(settings):
    """An empty allowlist never falls back to disabled checks."""
    settings.EXTERNAL_SOURCE_ALLOWED_URL_PREFIXES = []
    with pytest.raises(ValueError, match="not allowed"):
        validate_external_source_url("https://storage.example/bucket/file")


@pytest.mark.parametrize(
    "prefix", ["https://storage.example", "https://storage.example/"]
)
def test_origin_prefix(settings, prefix):
    """A root prefix allows any bucket only on the configured origin."""
    settings.EXTERNAL_SOURCE_ALLOWED_URL_PREFIXES = [prefix]
    validate_external_source_url("https://storage.example/another-bucket/file")
    with pytest.raises(ValueError):
        validate_external_source_url("https://storage.example.evil/another-bucket/file")


def test_multiple_prefixes(settings):
    """A later matching prefix is accepted, with or without a trailing slash."""
    settings.EXTERNAL_SOURCE_ALLOWED_URL_PREFIXES |= {"https://second.example/results"}
    validate_external_source_url("https://second.example/results/file")


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("validation_enabled", [True, False])
def test_redirects_are_rejected(settings, status, validation_enabled):
    """An allowed URL cannot redirect to an unapproved host or bucket."""
    if not validation_enabled:
        settings.EXTERNAL_SOURCE_ALLOWED_URL_PREFIXES = None
    session = Mock()
    session.get.return_value.status_code = status
    session.get.return_value.headers = {"Location": "http://internal.example/secrets"}
    with pytest.raises(ValueError, match="redirects"):
        fetch_external_source(session, "https://storage.example/bucket/file")
    session.get.assert_called_once()
    session.get.return_value.close.assert_called_once_with()


def test_http_errors_propagate():
    """Transient HTTP errors retain the existing task retry behavior."""
    session = Mock()
    session.get.return_value.raise_for_status.side_effect = requests.HTTPError()
    with pytest.raises(requests.HTTPError):
        fetch_external_source(session, "https://storage.example/bucket/file")


@pytest.mark.parametrize(
    "failure_point,error_type",
    [
        ("get", requests.ConnectionError),
        ("get", requests.Timeout),
        ("raise_for_status", requests.HTTPError),
    ],
)
def test_request_errors_redact_signed_url(failure_point, error_type):
    """Request failures preserve retries without exposing signed credentials."""
    url = "https://storage.example/bucket/file?signature=private-signature-value"
    request = requests.Request("GET", url).prepare()
    response = requests.Response()
    response.url = url
    response.request = request
    error = error_type(f"Request failed: {url}", request=request, response=response)
    session = Mock()
    if failure_point == "get":
        session.get.side_effect = error
    else:
        session.get.return_value.raise_for_status.side_effect = error

    with pytest.raises(error_type) as caught:
        fetch_external_source(session, url)

    assert "https://storage.example/bucket/file?[redacted]" in str(caught.value)
    assert "private-signature-value" not in "".join(
        traceback.format_exception(caught.value)
    )
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__
    assert caught.value.request is None
    assert caught.value.response is None


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://other.example/bucket/file", "https://other.example/bucket/file"),
        (
            "https://other.example/bucket/file?X-Amz-Signature=secret&token=private",
            "https://other.example/bucket/file?[redacted]",
        ),
        (
            "https://user:password@other.example/bucket/file?secret#private",
            "https://other.example/bucket/file?[redacted]",
        ),
        ("https://other.example/file#secret", "https://other.example/file"),
        ("https://[invalid/file?secret", "[redacted]"),
        (None, "[redacted]"),
    ],
)
def test_rejection_logs_redacted_source(url, expected, caplog):
    """Every validation failure identifies the source without query secrets."""
    assert redact_url(url) == expected
    with pytest.raises(ValueError):
        validate_external_source_url(url)
    assert len(caplog.records) == 1
    assert caplog.records[0].message == f"Rejected external source URL {expected!r}"
    assert caplog.records[0].levelname == "WARNING"


def test_redirect_rejection_logs_redacted_source(caplog):
    """Redirect refusals identify the original source without signed queries."""
    session = Mock()
    session.get.return_value.status_code = 302
    session.get.return_value.headers = {"Location": "https://private.example/?secret"}
    with pytest.raises(ValueError, match="redirects"):
        fetch_external_source(
            session, "https://storage.example/bucket/file?signature=secret"
        )
    assert "https://storage.example/bucket/file?[redacted]" in caplog.text
    assert "secret" not in caplog.text
    assert "private.example" not in caplog.text
