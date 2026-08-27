"""Tests for S3 upload policy generation."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from core.utils import generate_upload_policy


@pytest.mark.parametrize("upload_acl", ["private", "public-read", None])
def test_generate_upload_policy_uses_configured_upload_acl(settings, upload_acl):
    """Upload policies should include ACL only when the bucket config defines one."""
    file = SimpleNamespace(temporary_file_key="tmp/file.wav")
    storage = object()
    s3_client = Mock()
    s3_client.generate_presigned_url.return_value = "https://example.test/upload"
    configuration = SimpleNamespace(upload_acl=upload_acl)

    with (
        patch("core.utils.get_storage_for_file", return_value=storage),
        patch("core.utils.get_storage_bucket_name", return_value="bucket"),
        patch(
            "core.utils.get_bucket_configuration_for_file",
            return_value=configuration,
        ),
        patch("core.utils._get_s3_client", return_value=s3_client),
    ):
        policy = generate_upload_policy(file)

    expected_params = {"Bucket": "bucket", "Key": "tmp/file.wav"}
    if upload_acl is not None:
        expected_params["ACL"] = upload_acl

    assert policy == "https://example.test/upload"
    s3_client.generate_presigned_url.assert_called_once_with(
        ClientMethod="put_object",
        Params=expected_params,
        ExpiresIn=settings.AWS_S3_UPLOAD_POLICY_EXPIRATION,
    )
