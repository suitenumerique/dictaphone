"""
Utils functions used in the core app
"""

# pylint: disable=R0913, R0917

import logging
import mimetypes
import string

from django.conf import settings
from django.core.files.storage import default_storage

import boto3
import botocore
import magic

from core.webhook_models import WhisperXResponse

logger = logging.getLogger(__name__)


def generate_s3_authorization_headers(key):
    """
    Generate authorization headers for an s3 object.
    These headers can be used as an alternative to signed urls with many benefits:
    - the urls of our files never expire and can be stored in our recording' metadata
    - we don't leak authorized urls that could be shared (file access can only be done
      with cookies)
    - access control is truly realtime
    - the object storage service does not need to be exposed on internet
    """

    url = default_storage.unsigned_connection.meta.client.generate_presigned_url(
        "get_object",
        ExpiresIn=0,
        Params={"Bucket": default_storage.bucket_name, "Key": key},
    )

    request = botocore.awsrequest.AWSRequest(method="get", url=url)

    s3_client = default_storage.connection.meta.client
    # pylint: disable=protected-access
    credentials = s3_client._request_signer._credentials  # noqa: SLF001
    frozen_credentials = credentials.get_frozen_credentials()
    region = s3_client.meta.region_name
    auth = botocore.auth.S3SigV4Auth(frozen_credentials, "s3", region)
    auth.add_auth(request)

    return request


ALPHANUMERIC_CHARSET = string.ascii_letters + string.digits


def detect_mimetype(file_buffer: bytes, filename: str | None = None) -> str:
    """
    Detect MIME type using multiple methods for better accuracy.

    This function combines:
    1. Magic bytes detection (python-magic) - most reliable for actual file content
    2. File extension detection (mimetypes) - useful as fallback or for validation

    Args:
        file_buffer: The file content buffer (first bytes of the file)
        filename: Optional filename to extract extension from

    Returns:
        str: The detected MIME type

    Notes:
        Originally from https://github.com/suitenumerique/drive/blob/564822d31f071c6dfacd112ef4b7146c73077cd9/src/backend/core/api/utils.py#L166 # pylint:disable=line-too-long
    """
    # Initialize magic detector
    mime_detector = magic.Magic(mime=True)

    # Method 1: Detect from file content (magic bytes) - most reliable
    mimetype_from_content = mime_detector.from_buffer(file_buffer)

    # If we have a filename, try extension-based detection as well
    mimetype_from_extension = None
    if filename:
        # Use mimetypes module to guess from extension
        # Use guess_file_type (Python 3.13+) instead of deprecated guess_type
        mimetype_from_extension, _ = mimetypes.guess_file_type(filename, strict=False)

    logger.debug("detect_mimetype: mimetype_from_content: %s", mimetype_from_content)
    logger.debug(
        "detect_mimetype: mimetype_from_extension: %s", mimetype_from_extension
    )

    # Strategy: Prefer content-based detection, but use extension if:
    # 1. Content detection returns generic types (application/octet-stream, text/plain)
    # 2. Content detection fails or returns None
    # 3. Extension detection provides a more specific type

    # Generic/unreliable MIME types that we should try to improve
    generic_types = {
        "application/octet-stream",
        "application/x-ole-storage",  # used by .xls, .doc and .ppt
        "application/zip",
        "text/plain",
    }

    # If content detection gives us a generic type and we have extension info
    if mimetype_from_content in generic_types and mimetype_from_extension:
        # Use extension-based detection if it's more specific
        if mimetype_from_extension not in generic_types:
            return mimetype_from_extension

    # If content detection failed, returned None or is a generic type, use extension if available
    if not mimetype_from_content or mimetype_from_content in generic_types:
        if mimetype_from_extension:
            return mimetype_from_extension

    # Default to content-based detection (most reliable)
    return mimetype_from_content or "application/octet-stream"


def generate_upload_policy(file):
    """
    Generate a S3 upload policy for a given file.

    Notes:
        Originally taken from https://github.com/suitenumerique/drive/blob/564822d31f071c6dfacd112ef4b7146c73077cd9/src/backend/core/api/utils.py#L102  # pylint: disable=line-too-long
    """

    key = file.file_key

    # This settings should be used if the backend application and the frontend application
    # can't connect to the object storage with the same domain. This is the case in the
    # docker compose stack used in development. The frontend application will use localhost
    # to connect to the object storage while the backend application will use the object storage
    # service name declared in the docker compose stack.
    # This is needed because the domain name is used to compute the signature. So it can't be
    # changed dynamically by the frontend application.
    if settings.AWS_S3_DOMAIN_REPLACE:
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_S3_SECRET_ACCESS_KEY,
            endpoint_url=settings.AWS_S3_DOMAIN_REPLACE,
            config=botocore.client.Config(
                region_name=settings.AWS_S3_REGION_NAME,
                signature_version=settings.AWS_S3_SIGNATURE_VERSION,
            ),
        )
    else:
        s3_client = default_storage.connection.meta.client

    # Generate the policy
    policy = s3_client.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": default_storage.bucket_name, "Key": key, "ACL": "private"},
        ExpiresIn=settings.AWS_S3_UPLOAD_POLICY_EXPIRATION,
    )

    return policy


def generate_download_file_url(file, *, expires_in: int, override_domain: bool = True):
    """
    Generate a S3 signed download url for a given file.
    """

    key = file.file_key

    # This settings should be used if the backend application and the frontend application
    # can't connect to the object storage with the same domain. This is the case in the
    # docker compose stack used in development. The frontend application will use localhost
    # to connect to the object storage while the backend application will use the object storage
    # service name declared in the docker compose stack.
    # This is needed because the domain name is used to compute the signature. So it can't be
    # changed dynamically by the frontend application.
    if settings.AWS_S3_DOMAIN_REPLACE and override_domain:
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_S3_SECRET_ACCESS_KEY,
            endpoint_url=settings.AWS_S3_DOMAIN_REPLACE,
            config=botocore.client.Config(
                region_name=settings.AWS_S3_REGION_NAME,
                signature_version=settings.AWS_S3_SIGNATURE_VERSION,
            ),
        )
    else:
        s3_client = default_storage.connection.meta.client

    return s3_client.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": default_storage.bucket_name, "Key": key},
        ExpiresIn=expires_in,
    )


def format_transcript(transcript: WhisperXResponse) -> str:
    """
    Format a transcript from whisperX to text.
    """
    formatted_output = ""
    previous_speaker = None

    for segment in transcript.segments:
        speaker = segment.speaker or "Unknown Speaker"
        text = segment.text
        if text:
            if speaker != previous_speaker:
                formatted_output += f"\n\n**{speaker}**: {text}"
                previous_speaker = speaker
            else:
                formatted_output += f" {text}"

    return formatted_output
