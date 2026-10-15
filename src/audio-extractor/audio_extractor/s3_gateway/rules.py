"""S3 rule parsing and exact presigned URL authorization."""

import ipaddress
import json
import re
from typing import Annotated, Literal
from urllib.parse import parse_qsl, unquote, urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationInfo,
    field_validator,
)
from yarl import URL

BAD_ESCAPE = re.compile(r"%(?![0-9a-fA-F]{2})")
ENCODED_SEPARATOR = re.compile(r"%(?:2f|5c|25)", re.IGNORECASE)
DNS_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
DNS_NAME = rf"{DNS_LABEL}(?:\.{DNS_LABEL})*"
HOSTNAME = re.compile(DNS_NAME)

# Exclude dot segments and characters that make decoded object keys ambiguous.
KEY_SEGMENT = r"(?!\.{1,2}(?:/|\Z))[^/\\%\x00-\x1f\x7f]+"
KEY_PATH = rf"{KEY_SEGMENT}(?:/{KEY_SEGMENT})*"
OBJECT_KEY = re.compile(rf"{KEY_PATH}/*")

BucketName = Annotated[
    str,
    Field(
        min_length=3,
        max_length=63,
        pattern=re.compile(rf"\A(?![0-9]+(?:\.[0-9]+){{3}}\Z){DNS_NAME}\Z"),
    ),
]
KeyPrefix = Annotated[str, Field(pattern=re.compile(rf"\A{KEY_PATH}/+\Z"))]
Prefixes = Annotated[list[KeyPrefix], Field(min_length=1)]
Methods = Annotated[dict[Literal["GET", "PUT"], Prefixes], Field(min_length=1)]
QUERY_KEYS = frozenset(
    {
        "X-Amz-Algorithm",
        "X-Amz-Credential",
        "X-Amz-Date",
        "X-Amz-Expires",
        "X-Amz-SignedHeaders",
        "X-Amz-Signature",
        "X-Amz-Security-Token",
        "AWSAccessKeyId",
        "Signature",
        "Expires",
        "x-amz-security-token",
    }
)


class Grant(BaseModel):
    """Immutable resolved allowlist entry."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    host: str
    bucket: BucketName
    style: Literal["path", "virtual"]
    method: Literal["GET", "PUT"]
    prefixes: tuple[KeyPrefix, ...]
    scheme: Literal["http", "https"] = "https"
    allow_private_network: bool = False


def strict_url(value: str, *, allow_http: bool = False):
    """Require a plain ASCII DNS authority and HTTPS unless explicitly disabled."""
    if not value or any(ord(c) <= 32 or ord(c) >= 127 for c in value):
        raise ValueError("Invalid URL")
    if "\\" in value or "#" in value or BAD_ESCAPE.search(value):
        raise ValueError("Invalid URL")
    parts = urlsplit(value)
    host = parts.hostname or ""
    authority = host
    if allow_http and parts.port is not None:
        authority = f"{host}:{parts.port}"
    schemes = {"http", "https"} if allow_http else {"https"}
    if (
        parts.scheme not in schemes
        or parts.netloc != authority
        or not HOSTNAME.fullmatch(host)
    ):
        raise ValueError("Invalid destination")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP literals are forbidden")
    return parts


def valid_key(value: str) -> bool:
    """Keys use UTF-8, literal separators, and no ambiguous path segments."""
    return OBJECT_KEY.fullmatch(value) is not None


class Rule(BaseModel):
    """One storage endpoint and its allowed bucket, method, and key prefixes."""

    model_config = ConfigDict(strict=True, extra="forbid")

    # Keep the original authority: URL types normalize ports and trailing slashes.
    endpoint: str = Field(pattern=re.compile(rf"\Ahttps?://{DNS_NAME}(?::[0-9]+)?\Z"))
    addressing_style: Literal["path", "virtual"]
    buckets: dict[BucketName, Methods] = Field(min_length=1)

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str, info: ValidationInfo) -> str:
        """Apply the HTTPS policy without normalizing the configured URL."""
        force_https = (info.context or {}).get("force_https", True)
        strict_url(value, allow_http=not force_https)
        return value


RULES = TypeAdapter(Annotated[list[Rule], Field(min_length=1)])


def unique_object(pairs):
    """Reject duplicate JSON keys before Pydantic receives the parsed objects."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate configuration key")
        result[key] = value
    return result


def load_rules(raw: str, force_https: bool = True) -> tuple[Grant, ...]:
    """Validate the configuration with Pydantic and compile unambiguous grants."""
    rules = RULES.validate_python(
        json.loads(raw, object_pairs_hook=unique_object),
        context={"force_https": force_https},
    )
    grants = []
    destinations = set()
    for rule in rules:
        endpoint = urlsplit(rule.endpoint)
        allow_private_network = endpoint.scheme == "http"
        for bucket, methods in rule.buckets.items():
            host = (
                endpoint.netloc
                if rule.addressing_style == "path"
                else f"{bucket}.{endpoint.netloc}"
            )
            destination = (host, bucket if rule.addressing_style == "path" else None)
            if destination in destinations or any(
                other_host == host and (other_bucket is None or destination[1] is None)
                for other_host, other_bucket in destinations
            ):
                raise ValueError("Conflicting rules")
            destinations.add(destination)
            for method, prefixes in methods.items():
                grants.append(
                    Grant(
                        host=host,
                        bucket=bucket,
                        style=rule.addressing_style,
                        method=method,
                        prefixes=tuple(prefixes),
                        scheme=endpoint.scheme,
                        allow_private_network=allow_private_network,
                    )
                )
    return tuple(grants)


def validate_target(raw: str, method: str, grants: tuple[Grant, ...]) -> URL:
    """Authorize the decoded key, retaining the exact original wire URL."""
    parts = strict_url(
        raw, allow_http=any(grant.allow_private_network for grant in grants)
    )
    if method not in {"GET", "PUT"} or ENCODED_SEPARATOR.search(parts.path):
        raise ValueError("Unsupported request")
    key_path = unquote(parts.path, encoding="utf-8", errors="strict")
    if not key_path.startswith("/") or not valid_key(key_path[1:]):
        raise ValueError("Invalid object key")
    pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
    if any(key not in QUERY_KEYS or not value for key, value in pairs):
        raise ValueError("Unsupported S3 operation")
    if len({key for key, _ in pairs}) != len(pairs):
        raise ValueError("Duplicate query parameters")
    for grant in grants:
        if (
            grant.host != parts.netloc
            or grant.scheme != parts.scheme
            or grant.method != method
        ):
            continue
        key = key_path[1:]
        if grant.style == "path":
            bucket, separator, key = key.partition("/")
            if not separator or bucket != grant.bucket:
                continue
        if key and any(key.startswith(prefix) for prefix in grant.prefixes):
            return URL(raw, encoded=True)
    raise ValueError("Destination not authorized")
