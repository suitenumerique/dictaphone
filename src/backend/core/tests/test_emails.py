"""Tests for the shared email normalization rules."""

import pytest

from core.emails import normalize_email


@pytest.mark.parametrize(
    "email, expected",
    [
        ("  John.Doe@Example.COM \t", "john.doe@example.com"),
        ("Dısk@Example.com", "dısk@example.com"),
        ("Diſk@Example.com", "diſk@example.com"),
        ("DisK@Example.com", "disK@example.com"),
        ("Élise@Example.com", "Élise@example.com"),
        (None, None),
        ("", ""),
    ],
)
def test_normalize_email(email, expected):
    """Only surrounding whitespace and ASCII case should change."""
    assert normalize_email(email) == expected
