"""Internal audio worker API with the existing extractor payloads."""

import math

from rest_framework import decorators, serializers, status, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from core import audio_jobs
from core.authentication.audio_workers import AudioWorkerAuthentication
from core.models import AudioJob, AudioJobModeChoices


class AudioCompletionSerializer(serializers.Serializer):
    """Validate worker outcomes before changing an attempt."""

    id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=["success", "failure"])
    duration_seconds = serializers.FloatField(required=False, min_value=0)
    error = serializers.CharField(required=False, max_length=1000)
    metadata = serializers.DictField(child=serializers.FloatField(), required=False)

    def create(self, validated_data):
        raise NotImplementedError()

    def update(self, instance, validated_data):
        raise NotImplementedError()

    def validate(self, attrs):
        """Require a finite positive transcoding duration or a failure message."""
        duration = attrs.get("duration_seconds")
        success = attrs["status"] == "success"
        transcoding = self.context["mode"] == AudioJobModeChoices.TRANSCODING
        if success and "error" in attrs:
            raise serializers.ValidationError("Success cannot include an error.")
        if (
            success
            and transcoding
            and (duration is None or not math.isfinite(duration) or duration <= 0)
        ):
            raise serializers.ValidationError(
                "Transcoding success requires a positive finite duration."
            )
        if duration is not None and (not success or not transcoding):
            raise serializers.ValidationError(
                "Only transcoding success includes a duration."
            )
        if not success and not attrs.get("error"):
            raise serializers.ValidationError("Failure requires an error.")
        if any(
            not math.isfinite(value) for value in attrs.get("metadata", {}).values()
        ):
            raise serializers.ValidationError("Metadata values must be finite.")
        return attrs


class AudioJobViewSet(viewsets.GenericViewSet):
    """Claim and complete work with a dedicated token for each processing mode."""

    authentication_classes = [AudioWorkerAuthentication]
    permission_classes = [AllowAny]  # Authentication itself requires the worker token.
    serializer_class = AudioCompletionSerializer

    @decorators.action(detail=False, methods=["get"])
    def next(self, request, mode):
        """Return a claimed job or an empty queue response."""
        payload = audio_jobs.claim_next(mode)
        return (
            Response(payload)
            if payload
            else Response(status=status.HTTP_204_NO_CONTENT)
        )

    @decorators.action(detail=False, methods=["post"])
    def complete(self, request, mode):
        """Persist one completion and schedule its successor after commit."""
        serializer = self.serializer_class(data=request.data, context={"mode": mode})
        serializer.is_valid(raise_exception=True)
        try:
            audio_jobs.complete_job(mode, serializer.validated_data)
        except AudioJob.DoesNotExist as exc:
            raise NotFound() from exc
        except audio_jobs.AudioJobConflict as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response({"message": "Attempt completed."})
