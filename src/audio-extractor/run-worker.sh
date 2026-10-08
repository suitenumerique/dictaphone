#!/bin/sh
set -eu

audio_job_timeout_seconds=${AUDIO_EXTRACTOR_JOB_TIMEOUT_SECONDS:-300}
case "$audio_job_timeout_seconds" in
  *[!0-9]*|'')
    echo 'AUDIO_EXTRACTOR_JOB_TIMEOUT_SECONDS must be a positive integer.' >&2
    exit 2
    ;;
esac
if [ "$audio_job_timeout_seconds" -le 0 ]; then
  echo 'AUDIO_EXTRACTOR_JOB_TIMEOUT_SECONDS must be a positive integer.' >&2
  exit 2
fi

# One attempt per container is intentional: restarting discards process state
# after handling untrusted media. Kill the worker and its subprocesses at the
# backend's lease deadline, even if a media command or network operation hangs.
exec timeout --signal=KILL "${audio_job_timeout_seconds}s" python -m audio_extractor "$@"
