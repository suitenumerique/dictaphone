"""aiohttp application lifecycle and streaming S3 proxy handlers."""

import asyncio
import logging
import time
from collections.abc import Callable

import aiohttp
from aiohttp import web
from multidict import CIMultiDict
from pydantic import ValidationError

from audio_extractor.sentry import init_sentry

from .headers import RESPONSE_HEADERS, forward_headers
from .rules import load_rules, validate_target
from .settings import GatewaySettings

LOGGER = logging.getLogger("audio_extractor.s3_gateway")
CHUNK_SIZE = 64 * 1024
LOG_REASON = web.RequestKey("log_reason", str)
LOG_UPSTREAM = web.RequestKey("log_upstream", str)
LOG_ERROR = web.RequestKey("log_error", str)


@web.middleware
async def log_requests(request, handler):
    """Log transfer outcomes without raw URLs, headers, or exception messages."""
    if request.path == "/healthz":
        return await handler(request)
    started = time.monotonic()
    status = 500
    try:
        response = await handler(request)
        status = response.status
        return response
    except web.HTTPException as exc:
        status = exc.status
        raise
    except asyncio.CancelledError:
        status = 499
        request[LOG_REASON] = "cancelled"
        raise
    finally:
        default_reason = "complete" if status < 400 else "rejected"
        if status == 500:
            default_reason = "internal_error"
        reason = request.get(LOG_REASON, default_reason)
        method = request.method if request.method in {"GET", "PUT"} else "OTHER"
        LOGGER.log(
            logging.WARNING if status >= 400 or reason != "complete" else logging.INFO,
            "Gateway request method=%s status=%s upstream=%s reason=%s "
            "error=%s duration_ms=%.1f",
            method,
            status,
            request.get(LOG_UPSTREAM, "-"),
            reason,
            request.get(LOG_ERROR, "-"),
            (time.monotonic() - started) * 1000,
        )


# pylint: disable=too-many-statements
def create_app(  # noqa: PLR0915 - lifecycle
    config: GatewaySettings,
    *,
    connector_factory: Callable[..., aiohttp.BaseConnector] = aiohttp.TCPConnector,
) -> web.Application:
    """Create an independently configured gateway and its shared connection pool.

    ``connector_factory`` lets tests route upstream DNS and TLS to local servers.
    """
    grants = load_rules(config.rules, config.force_https)
    active = 0
    session = None

    async def session_context(_app):
        nonlocal session
        connector = connector_factory(
            limit=config.max_concurrent_requests,
            ttl_dns_cache=60,
        )
        try:
            async with aiohttp.ClientSession(
                connector=connector,
                trust_env=False,
                auto_decompress=False,
                cookie_jar=aiohttp.DummyCookieJar(),
                skip_auto_headers={
                    "User-Agent",
                    "Accept-Encoding",
                    "Content-Type",
                    "Accept",
                },
                timeout=aiohttp.ClientTimeout(
                    total=config.timeout_seconds,
                    connect=config.connect_timeout_seconds,
                    sock_read=config.timeout_seconds,
                ),
            ) as client:
                # aiohttp otherwise retries idempotent PUTs on stale pooled sockets.
                # There is no public switch for this behavior in aiohttp 3.x.
                client._retry_connection = False  # pylint: disable=protected-access
                session = client
                LOGGER.info(
                    "Gateway ready port=%s grants=%s force_https=%s "
                    "max_upload_bytes=%s max_concurrent_requests=%s timeout_seconds=%s",
                    config.port,
                    len(grants),
                    config.force_https,
                    config.max_upload_bytes,
                    config.max_concurrent_requests,
                    config.timeout_seconds,
                )
                yield
        finally:
            LOGGER.info("Gateway stopped")

    async def health(_request):
        return web.Response(text="ok")

    async def proxy(  # noqa: PLR0912, PLR0915 - fail-closed validation and diagnostics
        request,
    ):  # pylint: disable=too-many-branches
        nonlocal active
        if sum(len(k) + len(v) for k, v in request.headers.items()) > 32768:
            request[LOG_REASON] = "headers_too_large"
            raise web.HTTPRequestHeaderFieldsTooLarge(text="Headers too large")
        if request.query_string:
            request[LOG_REASON] = "proxy_query_forbidden"
            raise web.HTTPForbidden(text="Request forbidden")
        if active >= config.max_concurrent_requests:
            request[LOG_REASON] = "concurrency_limit"
            raise web.HTTPServiceUnavailable(text="Gateway busy")
        if len(request.headers.getall("X-Target-URL", [])) != 1:
            request[LOG_REASON] = "missing_or_duplicate_target"
            raise web.HTTPForbidden(text="Request forbidden")
        try:
            request[LOG_REASON] = "target_not_allowed"
            target = validate_target(
                request.headers["X-Target-URL"], request.method, grants
            )
            request[LOG_UPSTREAM] = target.raw_authority
            request[LOG_REASON] = "headers_not_allowed"
            headers = forward_headers(request, target)
        except ValueError, UnicodeError:
            raise web.HTTPForbidden(text="Request forbidden") from None
        request.pop(LOG_REASON)
        if request.method == "PUT":
            if request.content_length is None:
                request[LOG_REASON] = "content_length_required"
                raise web.HTTPLengthRequired(text="Content-Length required")
            if request.content_length > config.max_upload_bytes:
                request[LOG_REASON] = "upload_too_large"
                raise web.HTTPRequestEntityTooLarge(
                    max_size=config.max_upload_bytes,
                    actual_size=request.content_length,
                    text="Upload too large",
                )
        elif request.can_read_body:
            request[LOG_REASON] = "get_body_forbidden"
            raise web.HTTPForbidden(text="GET body forbidden")
        active += 1
        response = None
        try:
            async with (
                asyncio.timeout(config.timeout_seconds),
                session.request(
                    request.method,
                    target,
                    headers=headers,
                    allow_redirects=False,
                    data=request.content.iter_chunked(CHUNK_SIZE)
                    if request.method == "PUT"
                    else None,
                ) as upstream,
            ):
                if upstream.status < 200 or (
                    300 <= upstream.status < 400 and upstream.status != 304
                ):
                    request[LOG_REASON] = "upstream_redirect_forbidden"
                    request[LOG_ERROR] = f"HTTP_{upstream.status}"
                    raise web.HTTPBadGateway(text="Upstream redirect forbidden")
                connection_tokens = {
                    token.strip().lower()
                    for token in upstream.headers.get("Connection", "").split(",")
                }
                safe_headers = CIMultiDict(
                    (name, value)
                    for name, value in upstream.headers.items()
                    if name.lower() in RESPONSE_HEADERS
                    and name.lower() not in connection_tokens
                )
                # Error XML can echo the signed request; never expose upstream errors.
                if upstream.status >= 400:
                    request[LOG_REASON] = "upstream_error"
                    return web.Response(
                        status=upstream.status, text="Storage request failed"
                    )
                response = web.StreamResponse(
                    status=upstream.status, headers=safe_headers
                )
                await response.prepare(request)
                async for chunk in upstream.content.iter_chunked(CHUNK_SIZE):
                    await response.write(chunk)
                await response.write_eof()
                return response
        except (aiohttp.ClientError, OSError, TimeoutError) as exc:
            request[LOG_REASON] = "transfer_failed"
            request[LOG_ERROR] = type(exc).__name__
            if response is not None and response.prepared:
                if request.transport:
                    request.transport.close()
                return response
            raise web.HTTPBadGateway(text="Storage unavailable") from None
        finally:
            active -= 1

    app = web.Application(
        middlewares=[log_requests],
        client_max_size=config.max_upload_bytes,
        handler_args={
            "auto_decompress": False,
            "max_line_size": 16384,
            "max_field_size": 16384,
            "max_headers": 64,
            "logger": SanitizedHTTPLogger(LOGGER, {}),
        },
    )
    app.cleanup_ctx.append(session_context)
    app.router.add_get("/healthz", health, allow_head=False)
    app.router.add_get("/proxy", proxy, allow_head=False)
    app.router.add_put("/proxy", proxy)
    return app


class SanitizedHTTPLogger(logging.LoggerAdapter):
    """Parser errors may contain raw signed headers; suppress diagnostic payloads."""

    def log(self, level, msg, *args, **kwargs):  # pylint: disable=unused-argument
        # Discard format arguments too: they can contain the malformed request.
        if self.isEnabledFor(level):
            self.logger.log(level, "Gateway HTTP error")


def main():
    """Serve with bounded headers, raw bodies, cancellation, and graceful drain."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        config = GatewaySettings()
        init_sentry(config, application="s3-gateway")
        app = create_app(config)
    except ValidationError as exc:
        fields = sorted(
            {".".join(map(str, error["loc"])) or "rules" for error in exc.errors()}
        )
        LOGGER.error("Invalid S3 gateway settings: %s", ", ".join(fields))
        raise SystemExit(1) from None
    except ValueError, TypeError, KeyError:
        LOGGER.error("Invalid S3 gateway configuration")
        raise SystemExit(1) from None
    web.run_app(
        app,
        port=config.port,
        access_log=None,
        logger=SanitizedHTTPLogger(LOGGER, {}),
        handler_cancellation=True,
        auto_decompress=False,
        max_line_size=16384,
        max_field_size=16384,
        max_headers=64,
        shutdown_timeout=config.shutdown_grace_seconds,
    )
