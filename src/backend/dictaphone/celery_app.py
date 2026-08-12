"""Dictaphone celery configuration file."""

from os import environ

from celery import Celery
from configurations.importer import install

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
