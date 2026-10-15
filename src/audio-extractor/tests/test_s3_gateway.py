"""Allowlist and real TLS streaming tests, with test-only upstream DNS mapping."""

import asyncio
import gzip
import hashlib
import hmac
import json
import logging
import socket
import ssl
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlsplit

import aiohttp
import boto3
import pytest
import trustme
from aiohttp import web
from botocore.auth import S3SigV4QueryAuth
from botocore.awsrequest import AWSRequest
from botocore.config import Config
from botocore.credentials import Credentials

from audio_extractor import s3_gateway as gateway
from audio_extractor.http_client import configure_session
from audio_extractor.s3_gateway import app as gateway_app
from audio_extractor.settings import Settings
from audio_extractor.utils import _download, _upload

TARGET = "https://storage.test/audio-bucket/files/a?X-Amz-Signature=SECRET_SIGNATURE"


def rules(style="path", **methods):
    return json.dumps(
        [
            {
                "endpoint": "https://storage.test",
                "addressing_style": style,
                "buckets": {
                    "audio-bucket": methods or {"GET": ["files/"], "PUT": ["files/"]}
                },
            }
        ]
    )


@pytest.fixture
def grants():
    """Built outside ``pytest.raises`` so a broken baseline cannot pass silently."""
    return gateway.load_rules(rules())


def request_log(caplog):
    """Return the latest request outcome line, ignoring lifecycle messages."""
    lines = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("Gateway request")
    ]
    return lines[-1] if lines else ""


async def eventually(check, timeout=2):
    """Poll an async condition instead of sleeping for a guessed duration."""
    async with asyncio.timeout(timeout):
        while not await check():
            await asyncio.sleep(0.01)


# Configuration and startup


def test_invalid_settings_report_field_without_value(monkeypatch, caplog):
    """Report invalid setting names without exposing their values."""
    monkeypatch.setenv("S3_GATEWAY_RULES", rules())
    monkeypatch.setenv("S3_GATEWAY_MAX_UPLOAD_BYTES", "1.073741824e+09")
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "private-invalid-value")

    with pytest.raises(SystemExit) as exc:
        gateway_app.main()

    assert exc.value.code == 1
    assert "max_upload_bytes" in caplog.text
    assert "SENTRY_TRACES_SAMPLE_RATE" in caplog.text
    assert "1.073741824e+09" not in caplog.text
    assert "private-invalid-value" not in caplog.text


@pytest.mark.parametrize(
    ("raw", "field"),
    [("[]", "rules"), ('[{"endpoint":"private-invalid-value"}]', "0.endpoint")],
)
def test_invalid_rules_report_field_without_value(monkeypatch, caplog, raw, field):
    """Report malformed rule fields without logging their private values."""
    monkeypatch.setenv("S3_GATEWAY_RULES", raw)
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    with pytest.raises(SystemExit) as exc:
        gateway_app.main()

    assert exc.value.code == 1
    assert field in caplog.text
    assert "private-invalid-value" not in caplog.text


def test_conflicting_rules_exit_without_details(monkeypatch, caplog):
    """Reject semantically conflicting rules that pass schema validation."""
    monkeypatch.setenv("S3_GATEWAY_RULES", rules()[:-1] + "," + rules()[1:])
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    with pytest.raises(SystemExit) as exc:
        gateway_app.main()

    assert exc.value.code == 1
    assert "Invalid S3 gateway configuration" in caplog.text
    assert "storage.test" not in caplog.text


# Rule parsing and target authorization


@pytest.mark.parametrize("style", ["path", "virtual"])
def test_addressing_styles_and_escaped_url(style):
    """Preserve escaped URLs and query strings for both S3 addressing styles."""
    host_path = (
        "storage.test/audio-bucket" if style == "path" else "audio-bucket.storage.test"
    )
    raw = f"https://{host_path}/files/caf%C3%A9%20a+z.ogg?X-Amz-Signature=a%2Bb&X-Amz-Credential=x%2Fy"
    target = gateway.validate_target(raw, "GET", gateway.load_rules(rules(style)))
    assert str(target) == raw
    assert target.raw_query_string == raw.split("?")[1]


@pytest.mark.parametrize(
    "change",
    [
        {"endpoint": "http://storage.test"},
        {"endpoint": "https://storage.test:443"},
        {"endpoint": "https://storage.test/"},
        {"endpoint": "https://storage.test?x=y"},
        {"endpoint": "https://user@storage.test"},
        {"endpoint": "https://127.0.0.1"},
        {"endpoint": "https://storage.test#fragment"},
        {"addressing_style": "auto"},
        {"buckets": {}},
        {"buckets": {"audio-bucket": {}}},
        {"buckets": {"Bad_Bucket": {"GET": ["files/"]}}},
        {"buckets": {"audio-bucket": {"DELETE": ["files/"]}}},
        {"buckets": {"audio-bucket": {"GET": [""]}}},
        {"buckets": {"audio-bucket": {"GET": ["files"]}}},
        {"buckets": {"audio-bucket": {"GET": ["files/../"]}}},
        {"unknown": True},
    ],
)
def test_invalid_configuration(change):
    """Reject rule configurations outside the gateway's security policy."""
    config = json.loads(rules())
    config[0].update(change)
    with pytest.raises(ValueError):
        gateway.load_rules(json.dumps(config))


@pytest.mark.parametrize(
    "raw", ["[]", "{}", "null", "not json", rules()[:-1] + "," + rules()[1:]]
)
def test_empty_and_conflicting_rules(raw):
    """Reject empty, invalid, and conflicting rule documents."""
    with pytest.raises(ValueError):
        gateway.load_rules(raw)


def test_duplicate_json_keys():
    """Reject JSON rules that repeat a key with conflicting values."""
    with pytest.raises(ValueError):
        gateway.load_rules(
            '[{"endpoint":"https://good.test","endpoint":"https://evil.test"}]'
        )


@pytest.mark.parametrize(
    "suffix",
    [
        "files%2Fa.ogg",
        "files/%252fsecret",
        "files/%5csecret",
        "files/%GG",
        "files/%",
        "files/../secret",
        "files/%2e%2e/secret",
        "files//secret",
        "files/%FF",
        "files/%00secret",
        "other/file",
        "",
        "files/\\secret",
        "files/audio?uploads=",
        "files/audio?uploadId=123",
        "files/audio?partNumber=1",
        "files/audio?acl=",
        "files/audio?tagging=",
        "files/audio?list-type=2",
        "files/audio?X-Amz-Signature=a&X-Amz-Signature=b",
    ],
)
def test_ambiguous_keys_and_operations(grants, suffix):
    """Reject ambiguous object keys and unsupported S3 query operations."""
    assert gateway.validate_target(
        "https://storage.test/audio-bucket/files/audio", "GET", grants
    )
    with pytest.raises(ValueError):
        gateway.validate_target(
            "https://storage.test/audio-bucket/" + suffix, "GET", grants
        )


@pytest.mark.parametrize(
    "raw",
    [
        "http://storage.test/audio-bucket/files/a",
        "https://storage.test.evil/audio-bucket/files/a",
        "https://other.storage.test/audio-bucket/files/a",
        "https://storage.test/other-bucket/files/a",
        "https://storage.test:8443/audio-bucket/files/a",
        "https://user@storage.test/audio-bucket/files/a",
        "https://storage.test/audio-bucket/files/a#fragment",
        "https://storage.test/audio-bucket/files/a\n",
        "https://169.254.169.254/audio-bucket/files/a",
    ],
)
def test_destinations(grants, raw):
    """Reject targets that do not match the configured storage destination."""
    with pytest.raises(ValueError):
        gateway.validate_target(raw, "GET", grants)


@pytest.mark.parametrize(
    ("method", "key", "allowed"),
    [
        ("GET", "inputs/a", True),
        ("PUT", "outputs/a", True),
        ("PUT", "inputs/a", False),
        ("GET", "outputs/a", False),
        ("DELETE", "inputs/a", False),
    ],
)
def test_method_permissions(method, key, allowed):
    """Enforce method-specific key-prefix permissions."""
    grants = gateway.load_rules(rules(GET=["inputs/"], PUT=["outputs/"]))
    url = f"https://storage.test/audio-bucket/{key}"
    if allowed:
        assert str(gateway.validate_target(url, method, grants)) == url
    else:
        with pytest.raises(ValueError):
            gateway.validate_target(url, method, grants)


def test_http_requires_opt_out_and_preserves_authority():
    """Require explicit HTTP opt-out and enforce the configured authority."""
    assert gateway.load_rules(rules(), force_https=False)
    development_rules = rules().replace("https://storage.test", "http://rustfs:9000")
    with pytest.raises(ValueError):
        gateway.load_rules(development_rules)
    grants = gateway.load_rules(development_rules, force_https=False)
    raw = "http://rustfs:9000/audio-bucket/files/a?X-Amz-Signature=unchanged"
    assert str(gateway.validate_target(raw, "GET", grants)) == raw
    for target in [
        raw.replace(":9000", ":9001"),
        raw.replace("http:", "https:"),
        raw.replace("rustfs", "evil"),
    ]:
        with pytest.raises(ValueError):
            gateway.validate_target(target, "GET", grants)


def test_http_error_logger_never_emits_raw_headers(caplog):
    """Redact secrets from HTTP error messages, arguments, and tracebacks."""
    logger = gateway.SanitizedHTTPLogger(gateway.LOGGER, {})
    try:
        raise ValueError("X-Target-URL: SECRET_SIGNATURE")
    except ValueError:
        logger.error("SECRET_SIGNATURE %s", "SECRET_ARGUMENT", exc_info=True)
    assert "SECRET_SIGNATURE" not in caplog.text
    assert "SECRET_ARGUMENT" not in caplog.text
    assert "Gateway HTTP error" in caplog.text


# Proxy behaviour against a real TLS upstream


@pytest.fixture(scope="module")
def tls():
    authority = trustme.CA()
    certificate = authority.issue_cert("storage.test", "audio-bucket.storage.test")
    server = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    certificate.configure_cert(server)
    client = ssl.create_default_context()
    authority.configure_trust(client)
    return SimpleNamespace(server=server, client=client)


class LocalResolver(aiohttp.abc.AbstractResolver):
    """Resolve every storage hostname to the local upstream test server."""

    def __init__(self, port):
        self.port = port

    async def resolve(self, host, port=443, family=socket.AF_INET):
        return [
            {
                "hostname": host,
                "host": "127.0.0.1",
                "port": self.port,
                "family": socket.AF_INET,
                "proto": 0,
                "flags": 0,
            }
        ]

    async def close(self):
        pass


@pytest.fixture
def start_gateway(aiohttp_server, aiohttp_client, tls):
    """Start a TLS upstream with ``handler`` and a gateway client routed to it."""

    async def start(handler, **settings):
        upstream_app = web.Application(handler_args={"auto_decompress": False})
        upstream_app.router.add_route("*", "/{path:.*}", handler)
        upstream = await aiohttp_server(
            upstream_app, ssl=tls.server, auto_decompress=False
        )

        def connector(**kwargs):
            return aiohttp.TCPConnector(
                resolver=LocalResolver(upstream.port), ssl=tls.client, **kwargs
            )

        app = gateway.create_app(
            gateway.GatewaySettings(rules=settings.pop("rules", rules()), **settings),
            connector_factory=connector,
        )
        return await aiohttp_client(await aiohttp_server(app, auto_decompress=False))

    return start


async def raw_request(client, head: bytes, body: bytes = b"") -> bytes:
    """Send bytes the aiohttp client would normalize, returning the status line."""
    reader, writer = await asyncio.open_connection(client.host, client.port)
    try:
        writer.write(head + b"\r\n\r\n" + body)
        await writer.drain()
        return await reader.readline()
    finally:
        writer.close()


async def unreachable_upstream(_request):
    pytest.fail("Forbidden request reached upstream")


async def test_routes(start_gateway):
    """Expose only health checks and GET/PUT proxy routes."""
    client = await start_gateway(unreachable_upstream)
    target = {"X-Target-URL": TARGET}
    assert (await client.get("/healthz")).status == 200
    assert (await client.head("/healthz")).status == 405
    assert (await client.post("/proxy", headers=target)).status == 405
    assert (await client.get("/other")).status == 404


async def chunked_body():
    yield b"unknown length"


@pytest.mark.parametrize(
    ("method", "path", "headers", "body", "status", "reason"),
    [
        ("GET", "/proxy", [], None, 403, "missing_or_duplicate_target"),
        (
            "GET",
            "/proxy",
            [("X-Target-URL", TARGET), ("X-Target-URL", TARGET)],
            None,
            403,
            "missing_or_duplicate_target",
        ),
        (
            "GET",
            "/proxy?acl",
            [("X-Target-URL", TARGET)],
            None,
            403,
            "proxy_query_forbidden",
        ),
        (
            "GET",
            "/proxy",
            [("X-Target-URL", "SECRET_BAD_URL")],
            None,
            403,
            "target_not_allowed",
        ),
        (
            "GET",
            "/proxy",
            [("X-Pad-%d" % i, "a" * 12000) for i in range(3)],
            None,
            431,
            "headers_too_large",
        ),
        *(
            ("GET", "/proxy", [("X-Target-URL", TARGET), *extra], None, 403, reason)
            for extra, reason in [
                ([("x-amz-copy-source", "/evil")], "headers_not_allowed"),
                ([("x-amz-tagging", "SECRET_HEADER")], "headers_not_allowed"),
                ([("Authorization", "SECRET_AUTH")], "headers_not_allowed"),
                (
                    [("Connection", "content-type"), ("Content-Type", "audio/ogg")],
                    "headers_not_allowed",
                ),
            ]
        ),
        *(
            (
                "GET",
                "/proxy",
                [("X-Target-URL", TARGET + signed), ("Content-Type", "audio/ogg")],
                None,
                403,
                "headers_not_allowed",
            )
            # Missing signed header, missing host, duplicate entries.
            for signed in [
                "&X-Amz-SignedHeaders=host%3Bcontent-md5",
                "&X-Amz-SignedHeaders=content-type",
                "&X-Amz-SignedHeaders=host%3Bhost",
            ]
        ),
        ("GET", "/proxy", [("X-Target-URL", TARGET)], b"x", 403, "get_body_forbidden"),
        (
            "PUT",
            "/proxy",
            [("X-Target-URL", TARGET), ("Content-Encoding", "aws-chunked")],
            b"x",
            403,
            "headers_not_allowed",
        ),
        (
            "PUT",
            "/proxy",
            [("X-Target-URL", TARGET)],
            "chunked",
            403,
            "headers_not_allowed",
        ),
        (
            "PUT",
            "/proxy",
            [("X-Target-URL", TARGET)],
            b"x" * 11,
            413,
            "upload_too_large",
        ),
    ],
)
async def test_rejected_requests_never_reach_upstream(  # noqa: PLR0913
    start_gateway, caplog, method, path, headers, body, status, reason
):
    """Reject unsupported requests locally with a logged, secret-free reason."""
    client = await start_gateway(unreachable_upstream, max_upload_bytes=10)
    response = await client.request(
        method,
        path,
        headers=headers,
        data=chunked_body() if body == "chunked" else body,
    )
    assert response.status == status
    assert f"status={status} upstream=" in request_log(caplog)
    assert f"reason={reason} " in request_log(caplog)
    assert "SECRET" not in caplog.text


async def test_put_without_content_length_is_rejected(start_gateway, caplog):
    """Require an explicit length so uploads cannot be silently truncated."""
    client = await start_gateway(unreachable_upstream)
    status = await raw_request(
        client,
        b"PUT /proxy HTTP/1.1\r\nHost: gateway\r\nConnection: close\r\n"
        b"X-Target-URL: " + TARGET.encode(),
    )
    assert status.startswith(b"HTTP/1.1 411")
    assert "reason=content_length_required" in request_log(caplog)


async def test_tls_streaming_and_exact_signed_url(start_gateway):
    """Stream uploads and downloads over TLS while preserving signed URL bytes."""
    data = gzip.compress(b"media data" * 300000)
    raw_path = "/audio-bucket/files/caf%C3%A9%20a+z?X-Amz-Signature=a%2Bb&X-Amz-SignedHeaders=content-type%3Bhost"
    seen = []

    async def upstream(request):
        assert request.raw_path == raw_path
        assert request.headers["Host"] == "storage.test"
        assert request.headers["Content-Type"] == "audio/ogg"
        assert "X-Target-URL" not in request.headers
        assert "Forwarded" not in request.headers
        assert "Cookie" not in request.headers
        assert "Accept-Encoding" not in request.headers
        if request.method == "PUT":
            body = bytearray()
            async for chunk in request.content.iter_chunked(16384):
                body.extend(chunk)
            assert request.content_length == len(data)
            assert hashlib.sha256(body).digest() == hashlib.sha256(data).digest()
            seen.append("PUT")
            return web.Response(
                status=200, headers={"ETag": '"hash"', "Set-Cookie": "secret=x"}
            )
        seen.append("GET")
        response = web.StreamResponse(
            headers={"Content-Encoding": "gzip", "Content-Length": str(len(data))}
        )
        await response.prepare(request)
        for offset in range(0, len(data), 16384):
            await response.write(data[offset : offset + 16384])
        return response

    client = await start_gateway(upstream)
    headers = {
        "X-Target-URL": "https://storage.test" + raw_path,
        "Content-Type": "audio/ogg",
        "Forwarded": "for=evil",
        "Cookie": "credential=secret",
        "Content-Encoding": "gzip",
    }
    response = await client.put("/proxy", headers=headers, data=data)
    assert response.status == 200
    assert response.headers["ETag"] == '"hash"'
    assert "Set-Cookie" not in response.headers
    response = await client.get("/proxy", headers=headers, auto_decompress=False)
    assert response.status == 200
    assert await response.read() == data
    assert seen == ["PUT", "GET"]


async def test_response_headers_named_by_connection_are_dropped(start_gateway):
    """Treat headers listed in upstream Connection as hop-by-hop."""

    async def upstream(_request):
        return web.Response(
            headers={
                "Connection": "x-amz-version-id",
                "x-amz-version-id": "hop-scoped",
                "ETag": '"hash"',
            }
        )

    client = await start_gateway(upstream)
    response = await client.get("/proxy", headers={"X-Target-URL": TARGET})
    assert response.status == 200
    assert response.headers["ETag"] == '"hash"'
    assert "x-amz-version-id" not in response.headers


@pytest.mark.parametrize("status", [301, 307, 403, 500])
async def test_sanitized_upstream_errors_and_redirects(start_gateway, caplog, status):
    """Sanitize upstream errors and refuse redirects without logging secrets."""

    async def upstream(_request):
        return web.Response(
            status=status,
            text="SECRET_SIGNATURE",
            headers={"Location": "http://127.0.0.1/SECRET_SIGNATURE"},
        )

    client = await start_gateway(upstream)
    response = await client.get("/proxy", headers={"X-Target-URL": TARGET})
    assert response.status == (502 if status < 400 else status)
    assert "SECRET_SIGNATURE" not in await response.text()
    assert "Location" not in response.headers
    assert "SECRET_SIGNATURE" not in caplog.text
    if status < 400:
        assert "reason=upstream_redirect_forbidden" in request_log(caplog)
        assert f"error=HTTP_{status}" in request_log(caplog)
    else:
        assert f"status={status}" in request_log(caplog)
        assert "reason=upstream_error" in request_log(caplog)


async def test_conditional_get_preserves_not_modified(start_gateway):
    """Preserve an upstream 304 response and its entity tag."""

    async def upstream(request):
        assert request.headers["If-None-Match"] == '"hash"'
        return web.Response(status=304, headers={"ETag": '"hash"'})

    client = await start_gateway(upstream)
    response = await client.get(
        "/proxy", headers={"X-Target-URL": TARGET, "If-None-Match": '"hash"'}
    )
    assert response.status == 304
    assert response.headers["ETag"] == '"hash"'
    assert await response.read() == b""


async def test_request_logs_explain_outcomes_without_credentials(start_gateway, caplog):
    """Log completed transfers without credentials or body contents."""
    caplog.set_level(logging.INFO, logger="audio_extractor.s3_gateway")

    async def upstream(_request):
        return web.Response(body=b"SECRET_BODY")

    client = await start_gateway(upstream)
    caplog.clear()
    assert (await client.get("/healthz")).status == 200
    assert not caplog.records
    response = await client.get("/proxy", headers={"X-Target-URL": TARGET})
    assert await response.read() == b"SECRET_BODY"
    log = request_log(caplog)
    assert "method=GET status=200 upstream=storage.test reason=complete" in log
    assert "duration_ms=" in log
    await client.close()
    assert "Gateway stopped" in caplog.text
    assert "SECRET" not in caplog.text


async def test_upstream_timeout_is_sanitized(start_gateway, caplog):
    """Return a sanitized failure when an upstream transfer times out."""

    async def upstream(_request):
        await asyncio.Event().wait()

    client = await start_gateway(upstream, timeout_seconds=0.05)
    response = await client.get("/proxy", headers={"X-Target-URL": TARGET})
    assert response.status == 502
    assert await response.text() == "Storage unavailable"
    assert "SECRET" not in caplog.text
    assert "reason=transfer_failed" in request_log(caplog)
    assert "error=TimeoutError" in request_log(caplog)


async def test_upstream_failure_mid_stream_breaks_client_response(
    start_gateway, caplog
):
    """Never let a truncated download look like a complete response."""
    first_chunk_seen = asyncio.Event()

    async def upstream(request):
        response = web.StreamResponse(headers={"Content-Length": "100"})
        await response.prepare(request)
        await response.write(b"partial")
        await first_chunk_seen.wait()
        request.transport.abort()
        return response

    client = await start_gateway(upstream)
    response = await client.get("/proxy", headers={"X-Target-URL": TARGET})
    assert response.status == 200
    assert await response.content.readexactly(7) == b"partial"
    first_chunk_seen.set()
    with pytest.raises(aiohttp.ClientPayloadError):
        await response.read()

    async def logged():
        return "reason=transfer_failed" in request_log(caplog)

    await eventually(logged)
    assert "error=ClientPayloadError" in request_log(caplog)


async def test_client_disconnect_during_upload_aborts_upstream(start_gateway, caplog):
    """A client disconnect must not deliver a partial object to storage."""
    started, finished = asyncio.Event(), asyncio.Event()
    outcome = []

    async def upstream(request):
        started.set()
        try:
            await request.read()
            outcome.append("complete")
        except BaseException:
            outcome.append("incomplete")
            raise
        finally:
            finished.set()
        return web.Response()

    client = await start_gateway(upstream)
    reader, writer = await asyncio.open_connection(client.host, client.port)
    writer.write(
        b"PUT /proxy HTTP/1.1\r\nHost: gateway\r\nContent-Length: 1000\r\n"
        b"X-Target-URL: " + TARGET.encode() + b"\r\n\r\n" + b"x" * 10
    )
    await writer.drain()
    await asyncio.wait_for(started.wait(), 2)
    writer.close()
    await asyncio.wait_for(finished.wait(), 2)
    assert outcome == ["incomplete"]

    async def logged():
        return "reason=cancelled" in request_log(caplog)

    await eventually(logged)
    assert "status=499" in request_log(caplog)


async def test_concurrency_and_disconnect_release_upstream(start_gateway):
    """Return a busy response at capacity and free the slot after disconnect."""
    started, cancelled, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def upstream(request):
        response = web.StreamResponse()
        await response.prepare(request)
        await response.write(b"first")
        started.set()
        try:
            await release.wait()
            await response.write(b"last")
        except asyncio.CancelledError, ConnectionError:
            cancelled.set()
            raise
        return response

    client = await start_gateway(upstream, max_concurrent_requests=1)
    headers = {"X-Target-URL": TARGET}
    first = await client.get("/proxy", headers=headers)
    await asyncio.wait_for(started.wait(), 2)
    assert (await client.get("/proxy", headers=headers)).status == 503
    first.close()
    await asyncio.wait_for(cancelled.wait(), 2)
    release.set()

    async def slot_available():
        response = await client.get("/proxy", headers=headers)
        await response.read()
        return response.status == 200

    await eventually(slot_available)


async def test_streams_without_buffering_whole_body(start_gateway):
    """Forward data before the whole body exists, keeping contents intact."""
    chunk = b"0123456789abcdef" * 4096
    count = 512
    expected = hashlib.sha256(chunk * count).digest()
    first_upload = asyncio.Event()
    first_download = asyncio.Event()

    async def upstream(request):
        if request.method == "PUT":
            digest = hashlib.sha256()
            async for block in request.content.iter_chunked(65536):
                first_upload.set()
                digest.update(block)
            assert digest.digest() == expected
            return web.Response()
        response = web.StreamResponse(
            headers={"Content-Length": str(len(chunk) * count)}
        )
        await response.prepare(request)
        await response.write(chunk)
        # Deadlocks (then times out) if the gateway waits for the full body.
        await asyncio.wait_for(first_download.wait(), 2)
        for _ in range(count - 1):
            await response.write(chunk)
        return response

    async def body():
        yield chunk
        await asyncio.wait_for(first_upload.wait(), 2)
        for _ in range(count - 1):
            yield chunk

    client = await start_gateway(upstream)
    headers = {"X-Target-URL": "https://storage.test/audio-bucket/files/large"}
    response = await client.put(
        "/proxy",
        data=body(),
        headers=headers | {"Content-Length": str(len(chunk) * count)},
    )
    assert response.status == 200
    response = await client.get("/proxy", headers=headers)
    digest = hashlib.sha256()
    async for block in response.content.iter_chunked(65536):
        first_download.set()
        digest.update(block)
    assert digest.digest() == expected


async def test_graceful_shutdown_drains_active_transfer(start_gateway):
    """Wait for an active transfer to finish during graceful shutdown."""
    release = asyncio.Event()

    async def upstream(request):
        response = web.StreamResponse()
        await response.prepare(request)
        await response.write(b"first")
        await release.wait()
        await response.write(b"last")
        return response

    client = await start_gateway(upstream)
    response = await client.get("/proxy", headers={"X-Target-URL": TARGET})
    cleanup = asyncio.create_task(client.server.runner.cleanup())
    done, _ = await asyncio.wait({cleanup}, timeout=0.05)
    assert not done
    release.set()
    assert await response.read() == b"firstlast"
    await asyncio.wait_for(cleanup, 2)


async def test_put_connection_failure_is_never_replayed(start_gateway):
    """Avoid replaying a PUT after the upstream connection fails."""
    attempts = []

    async def upstream(request):
        attempts.append(request.method)
        await request.read()
        request.transport.abort()
        return web.Response()

    client = await start_gateway(upstream)
    response = await client.put(
        "/proxy", headers={"X-Target-URL": TARGET}, data=b"object"
    )
    assert response.status == 502
    assert attempts == ["PUT"]


@pytest.mark.parametrize("style", ["path", "virtual"])
@pytest.mark.parametrize("acl", [None, "public-read"])
async def test_real_sigv4_signatures_and_worker_round_trip(
    start_gateway, tmp_path, style, acl
):
    """Verify real presigned SigV4 uploads and downloads through the worker."""
    signer = boto3.client(
        "s3",
        endpoint_url="https://storage.test",
        region_name="us-east-1",
        aws_access_key_id="gateway-test",
        aws_secret_access_key="gateway-test-secret",
        config=Config(signature_version="s3v4", s3={"addressing_style": style}),
    )
    params = {"Bucket": "audio-bucket", "Key": "files/café + signed.ogg"}
    upload_headers = {"Content-Type": "audio/ogg"}
    acl_params = {}
    if acl is not None:
        acl_params["ACL"] = acl
        upload_headers["X-amz-acl"] = acl
    put_url = signer.generate_presigned_url(
        "put_object", Params=params | {"ContentType": "audio/ogg"} | acl_params
    )
    get_url = signer.generate_presigned_url("get_object", Params=params)
    objects = {}

    async def upstream(request):
        raw_url = f"https://{request.host}{request.raw_path}"
        unsigned, signature = raw_url.rsplit("&X-Amz-Signature=", 1)
        aws_request = AWSRequest(
            method=request.method,
            url=unsigned,
            headers={
                "Host": request.host,
                **(
                    {name: request.headers[name] for name in upload_headers}
                    if request.method == "PUT"
                    else {}
                ),
            },
        )
        aws_request.context["timestamp"] = dict(parse_qsl(urlsplit(unsigned).query))[
            "X-Amz-Date"
        ]
        auth = S3SigV4QueryAuth(
            Credentials("gateway-test", "gateway-test-secret"), "s3", "us-east-1"
        )
        string_to_sign = auth.string_to_sign(
            aws_request, auth.canonical_request(aws_request)
        )
        assert hmac.compare_digest(
            signature, auth.signature(string_to_sign, aws_request)
        )
        if request.method == "PUT":
            assert request.headers.get("X-amz-acl") == acl
            objects["data"] = await request.read()
            return web.Response()
        return web.Response(body=objects["data"])

    client = await start_gateway(upstream, rules=rules(style))
    configure_session(
        Settings(
            api_url="https://api.example.test",
            token="worker-token-for-tests-0123456789",
            s3_gateway_url=str(client.make_url("/proxy")),
        )
    )
    source, destination = tmp_path / "source", tmp_path / "destination"
    source.write_bytes(b"signed object data" * 10000)
    if acl is not None:
        response = await client.put(
            "/proxy",
            headers={"X-Target-URL": put_url, "Content-Type": "audio/ogg"},
            data=b"missing signed ACL header",
        )
        assert response.status == 403
    await asyncio.to_thread(_upload, put_url, source, 10, upload_headers)
    await asyncio.to_thread(_download, get_url, destination, 10, 1000000)
    assert destination.read_bytes() == source.read_bytes()
