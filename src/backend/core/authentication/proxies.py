"""Trusted proxy configuration shared by startup validation and request handling."""

from functools import lru_cache
from ipaddress import ip_network


@lru_cache(maxsize=32)
def _trusted_networks(entries):
    """Validate strict network definitions and reuse their parsed representation."""
    return tuple(ip_network(entry, strict=True) for entry in entries)
