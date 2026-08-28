"""
Tests for files API endpoint in dictaphone's core app: list
"""

import csv
import logging
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
            "audio_extraction_state": file.audio_extraction_state,
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
        file_auto_hard_delete_at=timezone.now() - timedelta(days=1),
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

    pending_file_1 = factories.FileFactory(
        creator=user,
        duration_seconds=60,
        audio_extraction_state=models.FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    pending_file_2 = factories.FileFactory(
        creator=user,
        duration_seconds=120,
        audio_extraction_state=models.FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    pending_file_3 = factories.FileFactory(
        creator=user,
        duration_seconds=45,
        audio_extraction_state=models.FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )

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

    models.AiFileJob.objects.filter(pk=pending_job_1.pk).update(
        created_at=now - timedelta(seconds=2)
    )
    models.AiFileJob.objects.filter(pk=pending_job_2.pk).update(
        created_at=now - timedelta(seconds=1)
    )
    models.AiFileJob.objects.filter(pk=pending_job_3.pk).update(created_at=now)

    with mock.patch("core.api.serializers.timezone.now", return_value=now):
        response = client.get("/api/v1.0/files/")

    assert response.status_code == 200
    ai_jobs = {
        job["id"]: job
        for file_data in response.json()["results"]
        for job in file_data["ai_jobs"]
    }

    assert (
        parse_datetime(ai_jobs[str(pending_job_1.id)]["processing_expected_end_at"])
        == now
    )
    assert parse_datetime(
        ai_jobs[str(pending_job_2.id)]["processing_expected_end_at"]
    ) == now + timedelta(seconds=120 / 33)
    assert parse_datetime(
        ai_jobs[str(pending_job_3.id)]["processing_expected_end_at"]
    ) == now + timedelta(seconds=5)


def test_ai_job_serializer_caches_missing_estimate_results():
    """A missing or unavailable ETA must not trigger another queue computation."""
    file = factories.FileFactory(
        duration_seconds=33,
        audio_extraction_state=models.FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    jobs = [
        factories.AiFileJobFactory(
            file=file,
            status=models.AiJobStatusChoices.PENDING,
            type=models.AiJobTypeChoices.TRANSCRIPT,
        )
        for _ in range(2)
    ]

    with mock.patch(
        "core.api.serializers._build_processing_expected_end_at_by_pending_job_id",
        return_value={jobs[0].id: None},
    ) as build_estimates:
        data = api_serializers.AiJobSerializer(jobs, many=True, context={}).data

    assert [job["processing_expected_end_at"] for job in data] == [None, None]
    build_estimates.assert_called_once()


def test_ai_job_estimation_uses_django_settings(settings):
    """Serializer forwards its capacity-estimator parameters from settings."""
    now = timezone.now()
    file = factories.FileFactory(
        duration_seconds=33,
        audio_extraction_state=models.FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    job = factories.AiFileJobFactory(
        file=file,
        status=models.AiJobStatusChoices.PENDING,
        type=models.AiJobTypeChoices.TRANSCRIPT,
    )
    settings.AI_JOB_ESTIMATION_THROUGHPUT_PER_WORKER = 42
    settings.AI_JOB_ESTIMATION_DEFAULT_CAPACITY = 3
    settings.AI_JOB_ESTIMATION_CAPACITY_LOOKBACK_SECONDS = 101
    settings.AI_JOB_ESTIMATION_CAPACITY_WINDOW_SECONDS = 102
    settings.AI_JOB_ESTIMATION_CAPACITY_STEP_SECONDS = 103
    settings.AI_JOB_ESTIMATION_CAPACITY_HALF_LIFE_SECONDS = 104
    settings.AI_JOB_ESTIMATION_REPLAY_HORIZON_SECONDS = 105

    with (
        mock.patch("core.api.serializers.timezone.now", return_value=now),
        mock.patch(
            "core.api.serializers.estimate_tasks_eta",
            return_value={str(job.id): mock.Mock(eta=now)},
        ) as estimate_tasks,
    ):
        estimates = (
            # pylint: disable=protected-access
            api_serializers._build_processing_expected_end_at_by_pending_job_id()
        )

    assert estimates == {job.id: now}
    assert estimate_tasks.call_args.kwargs == {
        "C": 42,
        "now": now,
        "default_capacity": 3,
        "capacity_lookback": timedelta(seconds=101),
        "capacity_window": timedelta(seconds=102),
        "capacity_step": timedelta(seconds=103),
        "capacity_half_life": timedelta(seconds=104),
        "replay_horizon": timedelta(seconds=105),
    }


def test_api_files_list_returns_no_eta_when_estimation_fails(caplog):
    """Estimator failures are logged and never make the files endpoint fail."""
    caplog.set_level(logging.DEBUG, logger="core.api.serializers")
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)
    file = factories.FileFactory(
        creator=user,
        duration_seconds=33,
        audio_extraction_state=models.FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    job = factories.AiFileJobFactory(
        file=file,
        status=models.AiJobStatusChoices.PENDING,
        type=models.AiJobTypeChoices.TRANSCRIPT,
    )

    with mock.patch(
        "core.api.serializers.estimate_tasks_eta",
        side_effect=RuntimeError("estimator unavailable"),
    ):
        response = client.get("/api/v1.0/files/")

    assert response.status_code == 200
    ai_jobs = {
        job_data["id"]: job_data
        for file_data in response.json()["results"]
        for job_data in file_data["ai_jobs"]
    }
    assert ai_jobs[str(job.id)]["processing_expected_end_at"] is None
    assert "Unable to compute AI job processing estimates" in caplog.text
    assert "Computed AI job processing estimates in" in caplog.text


def test_api_files_list_estimates_each_ai_job_type_with_its_own_queue():
    """Transcript work must not delay summary work, or conversely."""
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)
    now = timezone.now()

    transcript_file_1 = factories.FileFactory(
        creator=user,
        duration_seconds=330,
        audio_extraction_state=models.FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    transcript_file_2 = factories.FileFactory(
        creator=user,
        duration_seconds=33,
        audio_extraction_state=models.FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    summary_file = factories.FileFactory(
        creator=user,
        duration_seconds=33,
        audio_extraction_state=models.FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
    transcript_job_1 = factories.AiFileJobFactory(
        file=transcript_file_1,
        status=models.AiJobStatusChoices.PENDING,
        type=models.AiJobTypeChoices.TRANSCRIPT,
    )
    transcript_job_2 = factories.AiFileJobFactory(
        file=transcript_file_2,
        status=models.AiJobStatusChoices.PENDING,
        type=models.AiJobTypeChoices.TRANSCRIPT,
    )
    summary_job = factories.AiFileJobFactory(
        file=summary_file,
        status=models.AiJobStatusChoices.PENDING,
        type=models.AiJobTypeChoices.SUMMARIZE,
    )
    models.AiFileJob.objects.filter(pk=transcript_job_1.pk).update(
        created_at=now - timedelta(seconds=2)
    )
    models.AiFileJob.objects.filter(pk=transcript_job_2.pk).update(
        created_at=now - timedelta(seconds=1)
    )
    models.AiFileJob.objects.filter(pk=summary_job.pk).update(
        created_at=now - timedelta(seconds=1)
    )

    with mock.patch("core.api.serializers.timezone.now", return_value=now):
        response = client.get("/api/v1.0/files/")

    assert response.status_code == 200
    ai_jobs = {
        job["id"]: job
        for file_data in response.json()["results"]
        for job in file_data["ai_jobs"]
    }
    assert parse_datetime(
        ai_jobs[str(transcript_job_1.id)]["processing_expected_end_at"]
    ) == now + timedelta(seconds=8)
    assert parse_datetime(
        ai_jobs[str(transcript_job_2.id)]["processing_expected_end_at"]
    ) == now + timedelta(seconds=9)
    assert (
        parse_datetime(ai_jobs[str(summary_job.id)]["processing_expected_end_at"])
        == now
    )


def test_api_files_list_has_no_transcription_eta_before_audio_extraction():
    """Pending extraction jobs do not pretend to be in the transcription queue."""
    user = factories.UserFactory()
    client = APIClient()
    client.force_login(user)

    pending_file = factories.FileFactory(
        creator=user,
        duration_seconds=120,
        audio_extraction_state=models.FileAudioExtractionStateChoices.PENDING_AUDIO_EXTRACTION,
    )
    extracting_file = factories.FileFactory(
        creator=user,
        duration_seconds=120,
        audio_extraction_state=models.FileAudioExtractionStateChoices.EXTRACTING_AUDIO,
    )
    pending_jobs = [
        factories.AiFileJobFactory(
            file=file,
            status=models.AiJobStatusChoices.PENDING,
            type=models.AiJobTypeChoices.TRANSCRIPT,
        )
        for file in (pending_file, extracting_file)
    ]

    response = client.get("/api/v1.0/files/")

    assert response.status_code == 200
    ai_jobs = {
        job["id"]: job
        for file_data in response.json()["results"]
        for job in file_data["ai_jobs"]
    }
    assert all(
        ai_jobs[str(job.id)]["processing_expected_end_at"] is None
        for job in pending_jobs
    )


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
        file = factories.FileFactory(
            duration_seconds=float(row["duration_seconds"]),
            audio_extraction_state=models.FileAudioExtractionStateChoices.EXTRACTION_DONE,
        )
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

    file = factories.FileFactory(
        duration_seconds=100,
        creator=user,
        audio_extraction_state=models.FileAudioExtractionStateChoices.EXTRACTION_DONE,
    )
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
        response = client.get(f"/api/v1.0/files/{file.id}/")

    assert response.status_code == 200
    assert (
        response.json()["ai_jobs"][0]["processing_expected_end_at"]
        == "2026-06-23T17:31:19Z"
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
            audio_extraction_state=models.FileAudioExtractionStateChoices.EXTRACTION_DONE,
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
