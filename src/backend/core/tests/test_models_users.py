"""
Unit tests for the User model
"""

from unittest import mock

from django.core.exceptions import ValidationError

import pytest

from core import factories

pytestmark = pytest.mark.django_db


def test_models_users_str():
    """The str representation should be the email."""
    user = factories.UserFactory()
    assert str(user) == user.email


def test_models_users_id_unique():
    """The "id" field should be unique."""
    user = factories.UserFactory()
    with pytest.raises(ValidationError, match="User with this Id already exists."):
        factories.UserFactory(id=user.id)


@mock.patch("celery.current_app.send_task")
def test_models_users_send_mail_main_existing(mock_send_email):
    """The "email_user" method should queue mail to the user's email address."""
    user = factories.UserFactory()

    user.email_user("my subject", "my message")

    mock_send_email.assert_called_once_with(
        "core.tasks.mail.send_email",
        args=["my subject", "my message", user.email],
        kwargs={"from_email": None},
    )


def test_models_users_send_mail_main_missing():
    """The "email_user' method should fail if the user has no email address."""
    user = factories.UserFactory(email=None)

    with pytest.raises(ValueError) as excinfo:
        user.email_user("my subject", "my message")

    assert str(excinfo.value) == "User has no email address."
