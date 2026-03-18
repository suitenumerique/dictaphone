"""
Tasks related to files.
"""

import logging

from django.conf import settings
from django.core.files.storage import default_storage

import requests

from core.models import File
from core.tasks._task import task
from core.utils import generate_download_file_url

logger = logging.getLogger(__name__)


@task
def process_file_deletion(file_id):
    """
    Process the deletion of a file.
    Definitely delete it in the database.
    Delete the files from the storage.
    """
    logger.info("Processing item deletion for %s", file_id)
    try:
        file = File.objects.get(id=file_id)
    except File.DoesNotExist:
        logger.error("Item %s does not exist", file_id)
        return

    if file.hard_deleted_at is None:
        logger.error("To process an item deletion, it must be hard deleted first.")
        return

    logger.info("Deleting file %s", file.file_key)
    default_storage.delete(file.file_key)

    file.delete()


@task
def call_transcribe_service(file_id):
    """
    Call the transcribe service for a given file.
    """
    try:
        file = File.objects.get(id=file_id)
    except File.DoesNotExist:
        logger.error("Item %s does not exist", file_id)
        return

    response = requests.post(
        settings.AI_SERVICE_URL,
        json={
            "remote_id": str(file.id),
            "remote_owner_id": str(file.creator.id),
            "language": 'fr',
            "cloud_storage_url": generate_download_file_url(file, expires_in=60 * 60 * 24),
        },
        headers={
            "Authorization": f"Bearer {settings.AI_SERVICE_API_KEY}",
        },
        timeout=10,
    )

    response.raise_for_status()
