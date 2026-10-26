"""Tests for custom environment-backed settings values."""

import pytest

from dictaphone.values import (
    JsonDictValue,
    OptionalURLPrefixesValue,
    PositiveFloatValue,
)


@pytest.mark.parametrize(
    "serialized_value,expected",
    [
        ("null", None),
        ("[]", frozenset()),
        (
            '["https://storage.example/bucket/"]',
            frozenset({"https://storage.example/bucket/"}),
        ),
        (
            '["https://storage.example/bucket/", "https://storage.example/bucket/"]',
            frozenset({"https://storage.example/bucket/"}),
        ),
    ],
)
def test_optional_url_prefixes_from_environment(
    monkeypatch, serialized_value, expected
):
    """Distinguish disabled validation, deny-all, and configured URL prefixes."""
    name = "EXTERNAL_SOURCE_ALLOWED_URL_PREFIXES"
    monkeypatch.setenv(name, serialized_value)
    parsed = OptionalURLPrefixesValue(None, environ_prefix=None).setup(name)
    assert parsed == expected
    assert parsed is None or isinstance(parsed, frozenset)


@pytest.mark.parametrize(
    "serialized_value",
    ['"https://example.com"', "{}", "[1]", "[null]", '[""]', "invalid"],
)
def test_optional_url_prefixes_reject_invalid_values(serialized_value):
    """Do not silently disable checks for a malformed environment value."""
    with pytest.raises(ValueError):
        OptionalURLPrefixesValue().to_python(serialized_value)


def test_optional_url_prefixes_unset_defaults_to_none(monkeypatch):
    """An absent setting keeps backwards compatibility with a warning per fetch."""
    name = "EXTERNAL_SOURCE_ALLOWED_URL_PREFIXES"
    monkeypatch.delenv(name, raising=False)
    assert OptionalURLPrefixesValue(None, environ_prefix=None).setup(name) is None


@pytest.mark.parametrize(
    "serialized_value,expected", [("0.5", 0.5), ("24", 24.0), ("0", 0.0)]
)
def test_positive_float_value_from_environment(monkeypatch, serialized_value, expected):
    """Accept fractional hours and existing integer quota environment values."""
    name = "RATE_LIMIT_AI_TRANSCRIPTION_AUDIO_HOURS_PER_24H"
    monkeypatch.setenv(name, serialized_value)
    value = PositiveFloatValue(24.0, environ_prefix=None)

    assert value.setup(name) == expected


@pytest.mark.parametrize("serialized_value", ["-0.5", "nan", "inf", "-inf", "invalid"])
def test_positive_float_value_rejects_invalid_limits(serialized_value):
    """Reject negative, non-finite and non-numeric quotas."""
    with pytest.raises(ValueError, match="Cannot interpret value"):
        PositiveFloatValue().to_python(serialized_value)


@pytest.mark.parametrize(
    "serialized_value",
    [
        '{"default": {"default": true, "bucket": "default"}}',
        "{'default': {'default': True, 'bucket': 'default'}}",
    ],
)
def test_json_dict_value_accepts_json_and_python_literals(serialized_value):
    """Accept both JSON and the legacy Python-literal representation."""
    value = JsonDictValue({})

    assert value.to_python(serialized_value) == {
        "default": {"default": True, "bucket": "default"}
    }


def test_json_dict_value_rejects_non_dictionaries():
    """Reject serialized values that do not contain a dictionary."""
    value = JsonDictValue({})

    with pytest.raises(ValueError, match="Cannot interpret dict value"):
        value.to_python("[1, 2, 3]")
