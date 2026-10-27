"""Dictaphone celery configuration file."""

import tomllib
from importlib import import_module
from os import environ
from pathlib import Path

import sentry_sdk
from celery import Celery, signals
from configurations.importer import install
from sentry_sdk.integrations.celery import CeleryIntegration

from dictaphone.sentry import scrub_urls

BASE_DIR = Path(__file__).resolve().parent.parent

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
# Import the backend file and mail task modules explicitly.
app.conf.imports = ("core.tasks.file", "core.tasks.mail")


def get_release():
    """Return the version of the backend package for Sentry release reporting."""
    try:
        with BASE_DIR.joinpath("pyproject.toml").open("rb") as pyproject:
            return tomllib.load(pyproject)["project"]["version"]
    except FileNotFoundError, KeyError, tomllib.TOMLDecodeError:
        return "NA"  # Default: not available


@signals.celeryd_init.connect
def init_sentry(**_kwargs):
    """
    Initialize Sentry SDK on Celery startup; when celery workers are booted
    without Django we need a specific sentry init.
    """
    sentry_dsn = environ.get("SENTRY_DSN") or environ.get("DJANGO_SENTRY_DSN")
    if sentry_dsn:
        traces_sample_rate = float(environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0"))
        sentry_sdk.init(
            include_local_variables=False,
            max_request_body_size="never",
            before_send=scrub_urls,
            before_send_transaction=scrub_urls,
            before_breadcrumb=scrub_urls,
            dsn=sentry_dsn,
            environment=environ.get("DJANGO_CONFIGURATION", "Development").lower(),
            release=get_release(),
            traces_sample_rate=traces_sample_rate,
            integrations=[CeleryIntegration()],
        )
        sentry_sdk.set_tag("application", "celery-backend")


@signals.worker_init.connect
def init_sentry_in_worker(**_kwargs):
    """
    Initialize Sentry SDK on Celery startup; when celery workers are booted
    without Django we need a specific sentry init.
    """
    sentry_dsn = environ.get("SENTRY_DSN") or environ.get("DJANGO_SENTRY_DSN")
    if sentry_dsn:
        sentry_sdk.init(
            include_local_variables=False,
            max_request_body_size="never",
            before_send=scrub_urls,
            before_send_transaction=scrub_urls,
            before_breadcrumb=scrub_urls,
            dsn=sentry_dsn,
            environment=environ.get("DJANGO_CONFIGURATION", "Development").lower(),
            release=import_module("dictaphone.settings").get_release(),
            traces_sample_rate=float(environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
            integrations=[CeleryIntegration()],
        )
        sentry_sdk.set_tag("application", "celery-backend")
