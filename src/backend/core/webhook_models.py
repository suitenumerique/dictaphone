"""Transcribe / summary webhook models."""

from typing import Literal, Annotated, Union

from pydantic import BaseModel, Field, TypeAdapter


class BaseWebhook(BaseModel):
    """Base webhook payload."""

    source_id: str = Field(
        title="Source ID",
        description="The ID of the source document in the receiver system.",
    )


class TranscribeWebhookSuccessPayload(BaseWebhook):
    """Payload for a successful transcription webhook."""

    type: Literal["transcript"] = Field(default="transcript")
    status: Literal["success"] = Field(default="success")
    title: str = Field(title="Title", description="The title of the transcript.")
    transcript: str = Field(title="Transcript", description="The transcript text.")


class TranscribeWebhookFailurePayload(BaseWebhook):
    """Payload for a failed transcription webhook."""
    type: Literal["transcript"] = Field(default="transcript")
    status: Literal["failure"] = Field(default="failure")
    error: str = Field(title="Error", description="The error message.")


TranscribeWebhookPayloads = Annotated[
    Union[TranscribeWebhookSuccessPayload, TranscribeWebhookFailurePayload], Field(discriminator='status')]


class SummarizeWebhookSuccessPayload(BaseWebhook):
    """Payload for a successful summarization webhook."""

    type: Literal["summary"] = Field(default="summary")
    status: Literal["success"] = Field(default="success")
    summary: str = Field(title="Summary", description="The summary of the text.")


class SummarizeWebhookFailurePayload(BaseWebhook):
    """Payload for a failed summarization webhook."""
    type: Literal["summary"] = Field(default="summary")
    status: Literal["failure"] = Field(default="failure")
    error: str = Field(title="Error", description="The error message.")


SummarizeWebhookPayloads = Annotated[
    Union[SummarizeWebhookSuccessPayload, SummarizeWebhookFailurePayload], Field(discriminator='status')]

WebhookPayloads = Annotated[
    Union[TranscribeWebhookPayloads, SummarizeWebhookPayloads], Field(discriminator='type')
]

webhook_payload_adapter = TypeAdapter(WebhookPayloads)


__all__ = [
    "TranscribeWebhookSuccessPayload",
    "TranscribeWebhookFailurePayload",
    "SummarizeWebhookSuccessPayload",
    "SummarizeWebhookFailurePayload",
    "TranscribeWebhookPayloads",
    "SummarizeWebhookPayloads",
    "WebhookPayloads",
    "webhook_payload_adapter",
]
