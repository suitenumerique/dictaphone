#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <new-version>"
    exit 1
fi

NEW_VERSION="$1"

BACKEND_FILE="src/backend/pyproject.toml"
FRONTEND_FILE="src/frontend/package.json"
AUDIO_EXTRACTOR_FILE="src/audio-extractor/pyproject.toml"

echo "== Backend =="

OLD_BACKEND_VERSION=$(
    grep '^version *= *"' "$BACKEND_FILE" \
    | sed -E 's/version *= *"([^"]+)"/\1/'
)

echo "Current version: $OLD_BACKEND_VERSION"

sed -Ei.bak \
    "s/^version *= *\"[^\"]+\"/version = \"$NEW_VERSION\"/" \
    "$BACKEND_FILE"
rm "$BACKEND_FILE.bak"

NEW_BACKEND_VERSION=$(
    grep '^version *= *"' "$BACKEND_FILE" \
    | sed -E 's/version *= *"([^"]+)"/\1/'
)

echo "Updated version: $NEW_BACKEND_VERSION"

echo
echo "== Audio extractor =="

OLD_AUDIO_EXTRACTOR_VERSION=$(
    grep '^version *= *"' "$AUDIO_EXTRACTOR_FILE" \
    | sed -E 's/version *= *"([^"]+)"/\1/'
)

echo "Current version: $OLD_AUDIO_EXTRACTOR_VERSION"

sed -Ei.bak \
    "s/^version *= *\"[^\"]+\"/version = \"$NEW_VERSION\"/" \
    "$AUDIO_EXTRACTOR_FILE"
rm "$AUDIO_EXTRACTOR_FILE.bak"

NEW_AUDIO_EXTRACTOR_VERSION=$(
    grep '^version *= *"' "$AUDIO_EXTRACTOR_FILE" \
    | sed -E 's/version *= *"([^"]+)"/\1/'
)

echo "Updated version: $NEW_AUDIO_EXTRACTOR_VERSION"

echo
echo "Running uv lock..."
(
    cd src/backend
    uv lock
)

echo
echo "Running audio-extractor uv lock..."
(
    cd src/audio-extractor
    uv lock
)

echo
echo "== Frontend =="

OLD_FRONTEND_VERSION=$(
    grep '"version"' "$FRONTEND_FILE" \
    | sed -E 's/.*"version": *"([^"]+)".*/\1/'
)

echo "Current version: $OLD_FRONTEND_VERSION"

sed -Ei.bak \
    "s/(\"version\": *)\"[^\"]+\"/\1\"$NEW_VERSION\"/" \
    "$FRONTEND_FILE"
rm "$FRONTEND_FILE.bak"

NEW_FRONTEND_VERSION=$(
    grep '"version"' "$FRONTEND_FILE" \
    | sed -E 's/.*"version": *"([^"]+)".*/\1/'
)

echo "Updated version: $NEW_FRONTEND_VERSION"

echo
echo "Running npm install..."
(
    cd src/frontend
    npm install
)

echo
echo "Done!"
