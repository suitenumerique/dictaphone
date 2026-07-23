"""
Tests for files API endpoint in dictaphone's core app: list
"""

import csv
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.utils.dateparse import parse_datetime

import pytest
from faker import Faker
from freezegun import freeze_time
from rest_framework.pagination import PageNumberPagination
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core import factories, models
from core.api import serializers as api_serializers
from core.api.serializers import compute_ai_job_throughput

fake = Faker()
pytestmark = pytest.mark.django_db


def test_api_files_list_anonymous_not_allowed():
    """
    Anonymous users should not be allowed to list files whatever the
    """
    response = APIClient().get("/api/v1.0/files/")
    assert response.status_code == 401


def test_api_files_list_authentificated_user_allowed():
    """
    Authentificated users should be allowed to list files
    """
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    response = client.get("/api/v1.0/files/")
    assert response.status_code == 200
    assert response.data == {"count": 0, "next": None, "previous": None, "results": []}


def test_api_files_list_authentificated_user_allowed_with_jwt():
    """Authenticated users should be allowed to list files with JWT auth."""
    user = factories.UserFactory()
    access = RefreshToken.for_user(user).access_token

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    response = client.get("/api/v1.0/files/")
    assert response.status_code == 200
    assert response.data == {"count": 0, "next": None, "previous": None, "results": []}


def test_api_files_list_format(settings):
    """Validate the format of files as returned by the list view."""
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    file = factories.FileFactory(
        type=models.FileTypeChoices.AUDIO_RECORDING,
        title="item 1",
        creator=user,
    )

    # A file from another user should not appear
    factories.FileFactory(
        type=models.FileTypeChoices.AUDIO_RECORDING,
        title="file 2",
    )

    # hard deleted file should not appear
    factories.FileFactory(
        type=models.FileTypeChoices.AUDIO_RECORDING,
        hard_deleted_at=timezone.now(),
        title="hard deleted item",
        creator=user,
    )

    response = client.get("/api/v1.0/files/")

    assert response.status_code == 200
    content = response.json()
    results = content.pop("results")
    assert content == {
        "count": 1,
        "next": None,
        "previous": None,
    }
    assert len(results) == 1
    assert results == [
        {
            "id": str(file.id),
            "created_at": file.created_at.isoformat().replace("+00:00", "Z"),
            "creator": {
                "id": str(file.creator.id),
                "full_name": file.creator.full_name,
                "short_name": file.creator.short_name,
            },
            "ai_jobs": [],
            "title": file.title,
            "updated_at": file.updated_at.isoformat().replace("+00:00", "Z"),
            "type": models.FileTypeChoices.AUDIO_RECORDING,
            "upload_state": file.upload_state,
            "lifecycle_state": file.lifecycle_state,
            "url": None,
            "mimetype": file.mimetype,
            "filename": file.filename,
            "duration_seconds": file.duration_seconds,
            "size": None,
            "source": "unknown",
            "language": file.language,
            "description": None,
            "deleted_at": None,
            "hard_deleted_at": None,
            "original_file_file_delete_at": (
                file.created_at
                + timedelta(days=settings.ORIGINAL_FILE_DATA_DELETE_AFTER_DAYS)
            )
            .isoformat()
            .replace("+00:00", "Z"),
            "will_auto_delete_at": (
                file.created_at
                + timedelta(days=settings.FILE_AUTO_HARD_DELETE_AFTER_DAYS)
            )
            .isoformat()
            .replace("+00:00", "Z"),
            "abilities": {
                "destroy": True,
                "hard_delete": False,
                "media_auth": True,
                "restore": False,
                "partial_update": True,
                "retrieve": True,
                "update": True,
                "upload_ended": True,
            },
        }
    ]


def test_api_files_list_excludes_files_past_hard_delete_deadline(settings):
    """Files older than hard-delete deadline should be excluded from API list."""
    settings.FILE_AUTO_HARD_DELETE_AFTER_DAYS = 10
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    visible_file = factories.FileFactory(creator=user)
    excluded_file = factories.FileFactory(creator=user)
    models.File.objects.filter(pk=excluded_file.pk).update(
        created_at=timezone.now() - timedelta(days=11),
    )

    response = client.get("/api/v1.0/files/")

    assert response.status_code == 200
    returned_ids = {result["id"] for result in response.json()["results"]}
    assert str(visible_file.id) in returned_ids
    assert str(excluded_file.id) not in returned_ids


def test_api_files_list_excludes_pending_auto_hard_delete_files():
    """Files pending auto hard delete should not be listed."""
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    visible_file = factories.FileFactory(creator=user)
    excluded_file = factories.FileFactory(creator=user)
    excluded_file.lifecycle_state = (
        models.FileLifecycleStateChoices.PENDING_AUTO_HARD_DELETE
    )
    excluded_file.save(update_fields=["lifecycle_state"])

    response = client.get("/api/v1.0/files/")

    assert response.status_code == 200
    returned_ids = {result["id"] for result in response.json()["results"]}
    assert str(visible_file.id) in returned_ids
    assert str(excluded_file.id) not in returned_ids


def test_api_files_list_has_url_for_ready_active_file(settings):
    """Ready active files newer than original-data cutoff should expose media URL."""
    settings.ORIGINAL_FILE_DATA_DELETE_AFTER_DAYS = 10
    user = factories.UserFactory()
    file = factories.FileFactory(creator=user)
    file.upload_state = models.FileUploadStateChoices.READY
    file.save(update_fields=["upload_state"])

    client = APIClient()
    client.force_login(user)

    response = client.get("/api/v1.0/files/")

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["id"] == str(file.id)
    assert result["url"] is not None


@mock.patch.object(PageNumberPagination, "get_page_size", return_value=2)
def test_api_files_list_pagination(
    _mock_page_size,
):
    """Pagination should work as expected."""
    user = factories.UserFactory()

    client = APIClient()
    client.force_login(user)

    file_ids = [
        str(file.id)
        for file in factories.FileFactory.create_batch(
            3,
            creator=user,
            type=models.FileTypeChoices.AUDIO_RECORDING,
        )
    ]
    # Get page 1
    response = client.get(
        "/api/v1.0/files/",
    )

    assert response.status_code == 200
    content = response.json()

    assert content["count"] == 3
    assert content["next"] == "http://testserver/api/v1.0/files/?page=2"
    assert content["previous"] is None

    assert len(content["results"]) == 2
    for file in content["results"]:
        file_ids.remove(file["id"])

    # Get page 2
    response = client.get(
        "/api/v1.0/files/?page=2",
    )

    assert response.status_code == 200
    content = response.json()

    assert content["count"] == 3
    assert content["next"] is None
    assert content["previous"] == "http://testserver/api/v1.0/files/"

    assert len(content["results"]) == 1
    for file in content["results"]:
        file_ids.remove(file["id"])
    assert file_ids == []


def test_api_files_list_pending_ai_jobs_have_estimated_processing_expected_end_at():
    """Pending AI jobs should include expected processing end datetimes."""
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    now = timezone.now()

    pending_file_1 = factories.FileFactory(creator=user, duration_seconds=60)
    pending_file_2 = factories.FileFactory(creator=user, duration_seconds=120)
    pending_file_3 = factories.FileFactory(creator=user, duration_seconds=45)

    pending_job_1 = factories.AiFileJobFactory(
        file=pending_file_1,
        status=models.AiJobStatusChoices.PENDING,
        type=models.AiJobTypeChoices.TRANSCRIPT,
    )
    pending_job_2 = factories.AiFileJobFactory(
        file=pending_file_2,
        status=models.AiJobStatusChoices.PENDING,
        type=models.AiJobTypeChoices.TRANSCRIPT,
    )
    pending_job_3 = factories.AiFileJobFactory(
        file=pending_file_3,
        status=models.AiJobStatusChoices.PENDING,
        type=models.AiJobTypeChoices.TRANSCRIPT,
    )

    models.AiFileJob.objects.filter(pk=pending_job_1.pk).update(created_at=now)
    models.AiFileJob.objects.filter(pk=pending_job_2.pk).update(
        created_at=now + timedelta(seconds=1)
    )
    models.AiFileJob.objects.filter(pk=pending_job_3.pk).update(
        created_at=now + timedelta(seconds=2)
    )

    with (
        mock.patch("core.api.serializers.timezone.now", return_value=now),
        mock.patch(
            "core.api.serializers.compute_ai_job_throughput",
            return_value=2,
        ),
    ):
        response = client.get("/api/v1.0/files/")

    assert response.status_code == 200
    ai_jobs = {
        job["id"]: job
        for file_data in response.json()["results"]
        for job in file_data["ai_jobs"]
    }

    assert parse_datetime(
        ai_jobs[str(pending_job_1.id)]["processing_expected_end_at"]
    ) == now + timedelta(seconds=30)
    assert parse_datetime(
        ai_jobs[str(pending_job_2.id)]["processing_expected_end_at"]
    ) == (now + timedelta(seconds=90))
    assert parse_datetime(
        ai_jobs[str(pending_job_3.id)]["processing_expected_end_at"]
    ) == (now + timedelta(seconds=113))


def test_api_files_list_pending_ai_jobs_have_estimated_processing_expected_end_at_real_case():
    """
    Pending AI jobs should include expected processing end datetimes using real case data.
    """
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    data = list(
        csv.DictReader(
            (Path(__file__).parent.parent / "assets" / "export-throughput.csv").open(
                "r"
            ),
            delimiter=",",
        )
    )

    for row in data:
        file = factories.FileFactory(duration_seconds=float(row["duration_seconds"]))
        created_at = timezone.make_aware(
            datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
        )
        updated_at = timezone.make_aware(
            datetime.strptime(row["updated_at"], "%Y-%m-%d %H:%M:%S")
        )
        job = factories.AiFileJobFactory(
            file=file,
            status=models.AiJobStatusChoices.SUCCESS,
            type=models.AiJobTypeChoices.TRANSCRIPT,
        )
        models.AiFileJob.objects.filter(pk=job.pk).update(
            created_at=created_at,
            updated_at=updated_at,
        )

    file = factories.FileFactory(duration_seconds=100, creator=user)
    created_at = timezone.make_aware(
        datetime.strptime("2026-06-23 17:20:19", "%Y-%m-%d %H:%M:%S")
    )
    updated_at = timezone.make_aware(
        datetime.strptime("2026-06-23 17:20:19", "%Y-%m-%d %H:%M:%S")
    )
    job = factories.AiFileJobFactory(
        file=file,
        status=models.AiJobStatusChoices.PENDING,
        type=models.AiJobTypeChoices.TRANSCRIPT,
    )
    models.AiFileJob.objects.filter(pk=job.pk).update(
        created_at=created_at,
        updated_at=updated_at,
    )

    with freeze_time("2026-06-23 17:31:19"):
        throughput = compute_ai_job_throughput(models.AiJobTypeChoices.TRANSCRIPT)
        assert throughput == pytest.approx(33.09, rel=0.01)
        response = client.get(f"/api/v1.0/files/{file.id}/")

    assert response.status_code == 200
    assert (
        response.json()["ai_jobs"][0]["processing_expected_end_at"]
        == "2026-06-23T17:31:23Z"
    )


def test_api_files_list_ai_job_estimation_avoids_n_plus_one_queries():
    """AI estimation should not issue one database query per file/job."""
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    now = timezone.now()
    for index in range(5):
        file = factories.FileFactory(
            creator=user,
            duration_seconds=50 + index * 10,
        )
        factories.AiFileJobFactory(
            file=file,
            status=models.AiJobStatusChoices.PENDING,
            type=models.AiJobTypeChoices.TRANSCRIPT,
        )

    throughput_user = factories.UserFactory()
    for index in range(4):
        success_file = factories.FileFactory(
            creator=throughput_user, duration_seconds=80
        )
        success_job = factories.AiFileJobFactory(
            file=success_file,
            status=models.AiJobStatusChoices.SUCCESS,
            type=models.AiJobTypeChoices.TRANSCRIPT,
        )
        started_at = now - timedelta(minutes=3, seconds=index * 30 + 30)
        models.AiFileJob.objects.filter(pk=success_job.pk).update(
            created_at=started_at,
            updated_at=started_at + timedelta(seconds=40),
        )

    with CaptureQueriesContext(connection) as context:
        response = client.get("/api/v1.0/files/")

    assert response.status_code == 200
    ai_job_queries = [
        query["sql"]
        for query in context.captured_queries
        if 'FROM "ai_job"' in query["sql"]
    ]
    assert len(ai_job_queries) <= 4


def test_compute_ai_job_throughput_returns_default_without_success_jobs():
    """Throughput should fall back to the default when no successful jobs exist."""
    throughput = api_serializers.compute_ai_job_throughput(
        models.AiJobTypeChoices.TRANSCRIPT
    )
    assert throughput == api_serializers.AI_JOB_DEFAULT_THROUGHPUT


def test_compute_ai_job_throughput_averages_bucket_throughputs():
    """Throughput should be the average throughput across occupied time buckets."""
    now = timezone.now().replace(microsecond=0)
    job_type = models.AiJobTypeChoices.TRANSCRIPT

    samples = [
        (120, now - timedelta(seconds=10)),
        (30, now - timedelta(seconds=20)),
        (60, now - timedelta(seconds=80)),
    ]
    for duration_seconds, updated_at in samples:
        file = factories.FileFactory(duration_seconds=duration_seconds)
        job = factories.AiFileJobFactory(
            file=file,
            status=models.AiJobStatusChoices.SUCCESS,
            type=job_type,
        )
        models.AiFileJob.objects.filter(pk=job.pk).update(
            created_at=updated_at - timedelta(seconds=10),
            updated_at=updated_at,
        )

    with (
        mock.patch("core.api.serializers.timezone.now", return_value=now),
        mock.patch("core.api.serializers.THROUGHPUT_WINDOW_SECONDS", 60),
        mock.patch("core.api.serializers.N_THROUGHPUT_WINDOWS", 3),
        mock.patch("core.api.serializers.MIN_JOB_SAMPLES_THROUGHPUT_ESTIMATION", 1),
    ):
        throughput = api_serializers.compute_ai_job_throughput(job_type)

    assert throughput == pytest.approx((150 / 60 + 60 / 60) / 2)


def test_compute_ai_job_throughput_falls_back_to_latest_min_samples():
    """When window-filtered jobs are insufficient, latest samples should be used."""
    now = timezone.now().replace(microsecond=0)
    job_type = models.AiJobTypeChoices.TRANSCRIPT

    durations_by_age = [50, 40, 30, 20, 10]
    for index, duration_seconds in enumerate(durations_by_age):
        updated_at = now - timedelta(hours=2, seconds=index + 1)
        file = factories.FileFactory(duration_seconds=duration_seconds)
        job = factories.AiFileJobFactory(
            file=file,
            status=models.AiJobStatusChoices.SUCCESS,
            type=job_type,
        )
        models.AiFileJob.objects.filter(pk=job.pk).update(
            created_at=now - timedelta(hours=1),
            updated_at=updated_at,
        )

    th_window_seconds = 10
    with (
        mock.patch("core.api.serializers.timezone.now", return_value=now),
        mock.patch("core.api.serializers.THROUGHPUT_WINDOW_SECONDS", th_window_seconds),
        mock.patch("core.api.serializers.N_THROUGHPUT_WINDOWS", 0),
        mock.patch("core.api.serializers.MIN_JOB_SAMPLES_THROUGHPUT_ESTIMATION", 4),
    ):
        throughput = api_serializers.compute_ai_job_throughput(job_type)

    assert throughput == pytest.approx((50 + 40 + 30 + 20) / th_window_seconds)
