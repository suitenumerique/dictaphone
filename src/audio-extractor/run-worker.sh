#!/bin/sh
set -eu

audio_process_timeout_seconds=${AUDIO_EXTRACTOR_PROCESS_TIMEOUT_SECONDS:-1200}
audio_shutdown_grace_seconds=${AUDIO_EXTRACTOR_SHUTDOWN_GRACE_SECONDS:-30}
for audio_duration in "$audio_process_timeout_seconds" "$audio_shutdown_grace_seconds"; do
  case "$audio_duration" in
    *[!0-9]*|'')
      echo 'Process timeout and shutdown grace must be positive integers.' >&2
      exit 2
      ;;
  esac
  if [ "$audio_duration" -le 0 ]; then
    echo 'Process timeout and shutdown grace must be positive integers.' >&2
    exit 2
  fi
done

# Normal recycling happens inside Python. This independent watchdog bounds a
# stuck supervisor: request clean cancellation, then force termination.
exec timeout --signal=TERM --kill-after="${audio_shutdown_grace_seconds}s"   "${audio_process_timeout_seconds}s" python -m audio_extractor "$@"
