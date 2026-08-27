"""Dictaphone celery configuration file."""

from os import environ

import sentry_sdk
from celery import Celery, signals
from configurations.importer import install
from sentry_sdk.integrations.celery import CeleryIntegration

# Set the default Django settings module for the 'celery' program.
environ.setdefault("DJANGO_SETTINGS_MODULE", "dictaphone.settings")
environ.setdefault("DJANGO_CONFIGURATION", "Development")

install(check_options=True)

app = Celery("dictaphone")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django apps.
app.autodiscover_tasks()
# The file tasks live in a module below the conventional ``tasks.py`` name.
# Import it explicitly so every worker, including the dedicated audio worker,
# registers the extraction task.
app.conf.imports = ("core.tasks.file", "core.tasks.mail")


@signals.celeryd_init.connect
def init_sentry(**_kwargs):
    """
    Initialize Sentry SDK on Celery startup; when celery workers are booted
    without Django we need a specific sentry init.
    """
    if environ.get("DJANGO_SENTRY_DSN"):
        sentry_sdk.init(
            dsn=environ.get("DJANGO_SENTRY_DSN"),
            environment=environ.get("DJANGO_CONFIGURATION").lower(),
            integrations=[CeleryIntegration()],
        )


@signals.worker_init.connect
def init_sentry_in_worker(**_kwargs):
    """
    Initialize Sentry SDK on Celery startup; when celery workers are booted
    without Django we need a specific sentry init.
    """
    if environ.get("DJANGO_SENTRY_DSN"):
        sentry_sdk.init(
            dsn=environ.get("DJANGO_SENTRY_DSN"),
            environment=environ.get("DJANGO_CONFIGURATION").lower(),
            integrations=[CeleryIntegration()],
        )
