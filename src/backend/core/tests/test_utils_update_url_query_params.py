"""
Test utils.update_url_query_params
"""

import pytest

from core.utils import update_url_query_params


@pytest.mark.parametrize(
    "url, query_parameters, expected_url",
    [
        (
            "https://example.com/path",
            {"key1": ["value1"]},
            "https://example.com/path?key1=value1",
        ),
        (
            "https://example.com/path?existing_key=existing_value",
            {"key1": ["value1"]},
            "https://example.com/path?existing_key=existing_value&key1=value1",
        ),
        (
            "https://example.com/path",
            {"key1": ["value1"], "key2": ["value2", "value3"]},
            "https://example.com/path?key1=value1&key2=value2&key2=value3",
        ),
        (
            "https://example.com/path?key1=old_value",
            {"key1": ["new_value"]},
            "https://example.com/path?key1=new_value",
        ),
    ],
)
def test_update_url_query_params(url, query_parameters, expected_url):
    """Test updating URL query parameters with various inputs."""
    updated_url = update_url_query_params(url, query_parameters)
    assert updated_url == expected_url
