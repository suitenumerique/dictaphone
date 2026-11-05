"""Shared normalization for stored identity emails and exact email lookups."""

import string

_ASCII_LOWERCASE_TABLE = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)


def normalize_email(email: str | None) -> str | None:
    """Strip surrounding whitespace and lowercase ASCII letters only."""
    if email is None:
        return None
    return email.strip().translate(_ASCII_LOWERCASE_TABLE)
