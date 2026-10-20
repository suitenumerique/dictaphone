"""Password policy for Django administrator accounts."""

from unittest.mock import patch

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError

import pytest

from core.models import User


@pytest.mark.parametrize("length", [8, 11, 12, 20])
def test_password_minimum_length(length):
    """Reject passwords below 12 characters and accept the boundary."""
    password = "zQ7!vR2@kL9#sT4$xN6%"[:length]
    if length < 12:
        with pytest.raises(ValidationError) as exc:
            validate_password(password)
        assert exc.value.error_list[0].code == "password_too_short"
    else:
        validate_password(password)


@pytest.mark.parametrize(
    "password,code",
    [
        ("password123456", "password_too_common"),
        ("739182645083", "password_entirely_numeric"),
        ("administrator@example.com", "password_too_similar"),
    ],
)
def test_password_strength(password, code):
    """Reject weak passwords even when they satisfy the minimum length."""
    user = User(admin_email="administrator@example.com")
    with pytest.raises(ValidationError) as exc:
        validate_password(password, user=user)
    assert code in [error.code for error in exc.value.error_list]


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("password", ["zQ7!vR2@kL9", "zQ7!vR2@kL9#"])
def test_createsuperuser_validates_before_saving(existing, password):
    """Apply the policy before creating or updating an administrator."""
    user = User(admin_email="administrator@example.com")
    with (
        patch.object(User.objects, "get") as get_user,
        patch.object(User, "save") as save,
    ):
        if existing:
            get_user.return_value = user
        else:
            get_user.side_effect = User.DoesNotExist

        if len(password) < 12:
            with pytest.raises(CommandError, match="at least 12"):
                call_command(
                    "createsuperuser", email=user.admin_email, password=password
                )
            save.assert_not_called()
        else:
            call_command("createsuperuser", email=user.admin_email, password=password)
            save.assert_called_once()
            if existing:
                assert user.check_password(password)
                assert user.is_staff and user.is_superuser
