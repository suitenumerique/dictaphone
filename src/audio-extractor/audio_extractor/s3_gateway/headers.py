"""Allowlisted request and response header handling for the S3 proxy."""

from urllib.parse import parse_qsl

from multidict import CIMultiDict
from yarl import URL

REQUEST_HEADERS = frozenset(
    {
        "content-type",
        "content-length",
        "content-encoding",
        "content-md5",
        "content-disposition",
        "cache-control",
        "expires",
        "range",
        "if-match",
        "if-none-match",
        "if-modified-since",
        "if-unmodified-since",
        "x-amz-content-sha256",
        "x-amz-acl",
        "x-amz-security-token",
        "x-amz-date",
        "x-amz-server-side-encryption",
        "x-amz-server-side-encryption-aws-kms-key-id",
        "x-amz-server-side-encryption-context",
        "x-amz-storage-class",
    }
)
RESPONSE_HEADERS = frozenset(
    {
        "content-type",
        "content-length",
        "content-encoding",
        "content-range",
        "accept-ranges",
        "etag",
        "last-modified",
        "cache-control",
        "expires",
        "content-disposition",
        "x-amz-request-id",
        "x-amz-id-2",
        "x-amz-version-id",
        "x-amz-server-side-encryption",
    }
)
HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)


def forward_headers(request, target: URL) -> CIMultiDict:
    """Only supported object headers may select behavior; signed ones must survive."""
    headers = CIMultiDict()
    connection_tokens = {
        token.strip().lower()
        for token in request.headers.get("Connection", "").split(",")
    }
    for name, value in request.headers.items():
        lower = name.lower()
        if (
            lower.startswith("x-amz-")
            and lower not in REQUEST_HEADERS
            and not lower.startswith("x-amz-meta-")
        ):
            raise ValueError("Unsupported S3 header")
        if lower in REQUEST_HEADERS or lower.startswith("x-amz-meta-"):
            if lower in connection_tokens or len(request.headers.getall(name)) != 1:
                raise ValueError("Ambiguous headers")
            headers[name] = value
    if request.headers.get("Authorization") or request.headers.get("Transfer-Encoding"):
        raise ValueError("Unsupported authentication or transfer encoding")
    if headers.get("Content-Encoding", "").lower() == "aws-chunked":
        raise ValueError("Streaming signatures are unsupported")
    signed = dict(parse_qsl(target.raw_query_string)).get("X-Amz-SignedHeaders", "")
    names = signed.split(";") if signed else []
    if names and ("host" not in names or len(names) != len(set(names))):
        raise ValueError("Invalid signed headers")
    for name in names:
        if name != "host" and (
            name not in headers or name in HOP_HEADERS or name in connection_tokens
        ):
            raise ValueError("Required signed header missing or unsupported")
    headers["Host"] = target.raw_authority
    return headers
