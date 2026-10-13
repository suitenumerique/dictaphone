"""Internal subprocess entry point; the supervisor supplies input over stdin."""

import json
import logging
import sys

from audio_extractor.api_models import (
    TranscodingCompletion,
    TranscodingJob,
    ValidationCompletion,
    ValidationJob,
)
from audio_extractor.http_client import close_session, configure_session
from audio_extractor.sentry import init_sentry
from audio_extractor.settings import Settings
from audio_extractor.worker import (
    _post_completion,
    process_transcoding_job,
    process_validation_job,
)


def main() -> None:
    """Process one attempt or report failure within a supervisor-enforced budget."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    payload = json.load(sys.stdin)
    settings = Settings.model_validate(payload["settings"])
    model = TranscodingJob if settings.mode == "transcoding" else ValidationJob
    job = model.model_validate(payload["job"])
    init_sentry(settings)
    configure_session(settings)
    try:
        if payload["report_failure"]:
            completion = (
                TranscodingCompletion
                if settings.mode == "transcoding"
                else ValidationCompletion
            )
            _post_completion(
                settings,
                f"audio-jobs/{settings.mode}/complete",
                completion(
                    id=job.id,
                    status="failure",
                    error="Attempt exceeded its deadline or its child process failed",
                ),
            )
        elif settings.mode == "transcoding":
            process_transcoding_job(settings, job)
        else:
            process_validation_job(settings, job)
    finally:
        close_session()


if __name__ == "__main__":
    main()
