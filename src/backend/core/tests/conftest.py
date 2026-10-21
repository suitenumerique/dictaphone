"""Fixtures for tests in the Dictaphone core application"""

from unittest import mock

import pytest

from core.configuration import clear_configuration_cache
from core.storage import clear_storage_cache

USER = "user"
TEAM = "team"
VIA = [USER, TEAM]


@pytest.fixture(autouse=True)
def reset_runtime_configuration_cache(settings):
    """Keep the process-level configuration cache isolated between tests."""
    clear_configuration_cache()
    clear_storage_cache()
    # Django caches default_storage separately from our per-bucket clients.
    # Reassigning STORAGES resets it now and when the settings fixture restores
    # the original value, so temporary bucket endpoints cannot leak across tests.
    settings.STORAGES = settings.STORAGES
    yield
    clear_configuration_cache()
    clear_storage_cache()


@pytest.fixture
def mock_user_get_teams():
    """Mock for the "get_teams" method on the User model."""
    with mock.patch("core.models.User.get_teams") as mock_get_teams:
        yield mock_get_teams
