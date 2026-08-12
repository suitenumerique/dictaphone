"""Tasks for sending email notifications."""

import smtplib
from logging import getLogger

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django.utils.translation import override

from core.tasks.constants import BACKEND_QUEUE
from core.tasks.retry import build_retry_task_options

from dictaphone.celery_app import app

logger = getLogger(__name__)


@app.task(
    queue=BACKEND_QUEUE,
    **build_retry_task_options(autoretry_for=(smtplib.SMTPException, OSError)),
)
def send_email(subject, message, recipient, from_email=None, **kwargs):
    """Send a generic email from the backend worker."""
    send_mail(
        subject,
        message,
        from_email,
        [recipient],
        fail_silently=False,
        **kwargs,
    )


@app.task(
    queue=BACKEND_QUEUE,
    **build_retry_task_options(autoretry_for=(smtplib.SMTPException, OSError)),
)
def send_transcription_ready_email(ai_job_id):
    """Notify the file creator that a transcript is ready."""
    from core.models import (  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
        AiFileJob,
        AiJobStatusChoices,
        AiJobTypeChoices,
    )

    ai_job = (
        AiFileJob.objects.select_related("file", "file__creator")
        .filter(
            id=ai_job_id,
            type=AiJobTypeChoices.TRANSCRIPT,
            status=AiJobStatusChoices.SUCCESS,
        )
        .first()
    )
    if not ai_job:
        logger.warning("No successful transcript job found for email: %s", ai_job_id)
        return

    recipient = ai_job.file.creator
    if not recipient or not recipient.email:
        logger.info("Transcript creator has no email for file %s", ai_job.file_id)
        return

    language = recipient.language or settings.LANGUAGE_CODE
    base_url = (settings.EMAIL_APP_BASE_URL or "").rstrip("/")
    link = f"{base_url}/recordings/{ai_job.file_id}"

    with override(language):
        title = _("Your transcription is ready")
        context = {
            "title": title,
            "message": _("Your recording has been transcribed:"),
            "link": link,
            "link_label": ai_job.file.title,
            "button_label": _("View transcription"),
            "brandname": settings.EMAIL_BRAND_NAME,
            "logo_img": settings.EMAIL_LOGO_IMG,
            "support_email": settings.EMAIL_SUPPORT_EMAIL,
        }
        subject = str(title)
        msg_html = render_to_string("mail/html/transcription_ready.html", context)
        msg_plain = render_to_string("mail/text/transcription_ready.txt", context)

        send_mail(
            subject,
            msg_plain,
            settings.EMAIL_FROM,
            [recipient.email],
            html_message=msg_html,
            fail_silently=False,
        )

    logger.info("Sent transcript-ready email for file %s", ai_job.file_id)
