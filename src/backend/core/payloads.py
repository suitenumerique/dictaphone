"""Shared bounds for untrusted AI payloads, including stored legacy results."""

from contextlib import closing

from django.conf import settings

from core.storage import get_storage_bucket_name

CHUNK_SIZE = 64 * 1024


class PayloadLimitExceeded(ValueError):
    """A permanent payload rejection, deliberately outside HTTP retry errors."""


def result_limit(job_type):
    """Use the same limits when receiving, serving, and exporting results."""
    if job_type == "transcript":
        return settings.PAYLOAD_TRANSCRIPT_MAX_BYTES
    if job_type == "summary":
        return settings.PAYLOAD_SUMMARY_MAX_BYTES
    raise ValueError("Unknown AI result type")


def check_content_length(value, limit):
    """Reject an oversized advertised length; actual bytes are always counted too."""
    try:
        length = int(value)
    except TypeError, ValueError:
        return
    if length > limit:
        raise PayloadLimitExceeded("Payload exceeds byte limit")


def bounded_chunks(chunks, limit):
    """Collect at most limit bytes, without retaining an oversized chunk."""
    content = bytearray()
    for chunk in chunks:
        if len(content) + len(chunk) > limit:
            raise PayloadLimitExceeded("Payload exceeds byte limit")
        content.extend(chunk)
    return bytes(content)


def read_stream(stream, limit):
    """Never issue an unbounded read, even if size metadata is absent or false."""
    return bounded_chunks(
        iter(lambda: stream.read(min(CHUNK_SIZE, limit + 1)), b""), limit
    )


def read_response(response, limit, *, check_status=False):
    """Requests iter_content counts decompressed bytes, including gzip responses."""
    with closing(response):
        if check_status:
            response.raise_for_status()
        check_content_length(response.headers.get("Content-Length"), limit)
        return bounded_chunks(
            response.iter_content(chunk_size=min(CHUNK_SIZE, limit + 1)), limit
        )


def read_stored_result(storage, key, job_type):
    """Read S3 directly: storage.open can spool the entire object before read(n)."""
    limit = result_limit(job_type)
    result = storage.connection.meta.client.get_object(
        Bucket=get_storage_bucket_name(storage), Key=key
    )
    with closing(result["Body"]) as body:
        check_content_length(result.get("ContentLength"), limit)
        content = read_stream(body, limit)
    return content
