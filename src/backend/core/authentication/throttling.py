"""Failed-attempt throttling for the public PKCE token exchange."""

import logging
import math
from ipaddress import ip_address

from django.conf import settings

from rest_framework.throttling import SimpleRateThrottle

from core.authentication.proxies import _trusted_networks

logger = logging.getLogger(__name__)


def _parse_ip(value):
    """Normalize equivalent IPv4 and IPv4-mapped IPv6 addresses."""
    address = ip_address(value)
    return getattr(address, "ipv4_mapped", None) or address


def get_client_ip(request):
    """Walk forwarded addresses from the peer through explicitly trusted proxies."""
    try:
        address = _parse_ip(request.META.get("REMOTE_ADDR", ""))
    except ValueError:
        return "unknown"

    trusted = _trusted_networks(tuple(settings.AUTH_PKCE_TRUSTED_PROXIES))
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    for value in reversed(forwarded.split(",")):
        if not any(address in network for network in trusted):
            break
        try:
            address = _parse_ip(value.strip())
        except ValueError:
            # Retain the last valid address; do not trust entries beyond this point.
            break
    return str(address)


class FailedRequestThrottle(SimpleRateThrottle):
    """Count only failed POST requests, using atomic increments in fixed windows.

    Production must use a shared cache with atomic add/incr (the default Redis
    backend supports both). Successful requests never write to the counter.
    """

    key = None
    ident = None
    expires_at = None

    def get_cache_key(self, request, view):
        """Bucket failures by client IP within the current fixed window."""
        self.ident = get_client_ip(request)
        window = int(self.timer() // self.duration)
        self.expires_at = (window + 1) * self.duration
        return f"{self.scope}:{self.ident}:{self.duration}:{window}"

    def allow_request(self, request, view):
        """Reject exhausted IPs before parsing or consuming authorization codes."""
        if request.method != "POST" or self.rate is None:
            return True
        self.key = self.get_cache_key(request, view)
        return self.cache.get(self.key, 0) < self.num_requests

    def record_failure(self):
        """Atomically record a failure without extending the window on retries."""
        if self.key is None:
            return
        timeout = max(1, math.ceil(self.expires_at - self.timer()))
        if self.cache.add(self.key, 1, timeout=timeout):
            failures = 1
        else:
            try:
                failures = self.cache.incr(self.key)
            except ValueError:
                # The key may have expired between add and incr.
                return
        if failures == self.num_requests:
            logger.warning(
                "%s rate limit reached for IP %s (%s failures, rate %s)",
                self.scope,
                self.ident,
                failures,
                self.rate,
            )

    def wait(self):
        """Return the remaining window duration for the Retry-After header."""
        return max(0, self.expires_at - self.timer())


class FailedRequestThrottleMixin:
    """Record client errors using the same throttle instances that checked the request."""

    def get_throttles(self):
        """Retain initialized counters, including their IP and window boundaries."""
        throttles = super().get_throttles()
        self.failure_throttles = [
            throttle
            for throttle in throttles
            if isinstance(throttle, FailedRequestThrottle)
        ]
        return throttles

    def finalize_response(self, request, response, *args, **kwargs):
        """Count 4xx responses except rate-limit rejections after finalizing them."""
        response = super().finalize_response(request, response, *args, **kwargs)
        if 400 <= response.status_code < 500 and response.status_code != 429:
            for throttle in getattr(self, "failure_throttles", ()):
                throttle.record_failure()
        return response


class PKCETokenExchangeThrottle(FailedRequestThrottle):
    """Apply the configured failed-attempt rate to PKCE token exchanges by IP."""

    scope = "pkce_token_exchange_failures"
