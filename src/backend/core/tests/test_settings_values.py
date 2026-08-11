"""Tests for custom environment-backed settings values."""

import pytest

from dictaphone.values import JsonDictValue


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
