#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# release_bump.sh
# Bumps version & build numbers across package.json, iOS pbxproj
# and Android build.gradle for a mobile app release.
#
# Usage:
#   ./release_bump.sh <new_version>
#   ./release_bump.sh 2.4.1
# ─────────────────────────────────────────────────────────────

set -euo pipefail

# ── Paths (relative to repo root) ────────────────────────────
PACKAGE_JSON="package.json"
PBXPROJ="ios/AssistantTranscripts.xcodeproj/project.pbxproj"
GRADLE="android/app/build.gradle"

# ── Helpers ──────────────────────────────────────────────────
red()   { echo -e "\033[0;31m$*\033[0m"; }
green() { echo -e "\033[0;32m$*\033[0m"; }
blue()  { echo -e "\033[0;34m$*\033[0m"; }

die() { red "ERROR: $*"; exit 1; }

require_cmd() {
  command -v "$1" &>/dev/null || die "'$1' is required but not found."
}

# ── Validate input ────────────────────────────────────────────
[[ $# -eq 1 ]] || die "Usage: $0 <new_version>  (e.g. 2.4.1)"

NEW_VERSION="$1"

# Validate semver format (MAJOR.MINOR.PATCH)
[[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
  || die "Version must follow semantic versioning: MAJOR.MINOR.PATCH (got '$NEW_VERSION')"

# ── Check dependencies ────────────────────────────────────────
require_cmd node
require_cmd jq

# ── Check files exist ─────────────────────────────────────────
for f in "$PACKAGE_JSON" "$PBXPROJ" "$GRADLE"; do
  [[ -f "$f" ]] || die "File not found: $f"
done

# ═════════════════════════════════════════════════════════════
# 1. package.json — update "version"
# ═════════════════════════════════════════════════════════════
blue "\n── package.json ──────────────────────────────────────────"

OLD_PKG_VERSION=$(jq -r '.version' "$PACKAGE_JSON")
echo "  version: $OLD_PKG_VERSION → $NEW_VERSION"

# Use node to rewrite in-place, preserving formatting
node -e "
  const fs = require('fs');
  const pkg = JSON.parse(fs.readFileSync('$PACKAGE_JSON', 'utf8'));
  pkg.version = '$NEW_VERSION';
  fs.writeFileSync('$PACKAGE_JSON', JSON.stringify(pkg, null, 2) + '\n');
"
green "  ✓ package.json updated"

# ═════════════════════════════════════════════════════════════
# 2. iOS — project.pbxproj
#    • CURRENT_PROJECT_VERSION  → incremented by 1  (buildNumber)
#    • MARKETING_VERSION         → new semver        (version)
# ═════════════════════════════════════════════════════════════
blue "\n── iOS · project.pbxproj ─────────────────────────────────"

# Read current build number (first occurrence is enough — all targets share it)
OLD_IOS_BUILD=$(grep -m1 'CURRENT_PROJECT_VERSION' "$PBXPROJ" \
  | sed 's/.*CURRENT_PROJECT_VERSION = \([0-9]*\).*/\1/')
[[ -n "$OLD_IOS_BUILD" ]] || die "Could not read CURRENT_PROJECT_VERSION from pbxproj"

NEW_IOS_BUILD=$(( OLD_IOS_BUILD + 1 ))

OLD_IOS_MARKETING=$(grep -m1 'MARKETING_VERSION' "$PBXPROJ" \
  | sed 's/.*MARKETING_VERSION = \([^;]*\).*/\1/')

echo "  CURRENT_PROJECT_VERSION : $OLD_IOS_BUILD → $NEW_IOS_BUILD"
echo "  MARKETING_VERSION       : $OLD_IOS_MARKETING → $NEW_VERSION"

# Replace every occurrence (Debug + Release targets)
sed -i.bak \
  "s/CURRENT_PROJECT_VERSION = $OLD_IOS_BUILD;/CURRENT_PROJECT_VERSION = $NEW_IOS_BUILD;/g" \
  "$PBXPROJ"

sed -i.bak \
  "s/MARKETING_VERSION = [^;]*;/MARKETING_VERSION = $NEW_VERSION;/g" \
  "$PBXPROJ"

rm -f "${PBXPROJ}.bak"
green "  ✓ project.pbxproj updated"

# ═════════════════════════════════════════════════════════════
# 3. Android — build.gradle
#    • versionCode  → incremented by 1
#    • versionName  → new semver
# ═════════════════════════════════════════════════════════════
blue "\n── Android · build.gradle ────────────────────────────────"

OLD_ANDROID_CODE=$(grep -m1 'versionCode' "$GRADLE" \
  | sed 's/[^0-9]*\([0-9]*\).*/\1/')
[[ -n "$OLD_ANDROID_CODE" ]] || die "Could not read versionCode from build.gradle"

NEW_ANDROID_CODE=$(( OLD_ANDROID_CODE + 1 ))

OLD_ANDROID_NAME=$(grep -m1 'versionName' "$GRADLE" \
  | sed 's/.*versionName[[:space:]]*"\([^"]*\)".*/\1/')

echo "  versionCode : $OLD_ANDROID_CODE → $NEW_ANDROID_CODE"
echo "  versionName : $OLD_ANDROID_NAME → $NEW_VERSION"

sed -i.bak \
  "s/versionCode[[:space:]]*$OLD_ANDROID_CODE/versionCode $NEW_ANDROID_CODE/" \
  "$GRADLE"

sed -i.bak \
  "s/versionName[[:space:]]*\"[^\"]*\"/versionName \"$NEW_VERSION\"/" \
  "$GRADLE"

rm -f "${GRADLE}.bak"
green "  ✓ build.gradle updated"

# ═════════════════════════════════════════════════════════════
# Summary
# ═════════════════════════════════════════════════════════════
blue "\n── Summary ───────────────────────────────────────────────"
echo "  Version  : $OLD_PKG_VERSION → $NEW_VERSION"
echo "  iOS build: $OLD_IOS_BUILD → $NEW_IOS_BUILD"
echo "  Android  : $OLD_ANDROID_CODE → $NEW_ANDROID_CODE"
green "\n✓ All files bumped successfully.\n"

echo "Next steps:"
echo "  iOS     → Open Xcode · select 'Any iOS Device (arm64)' · Product › Archive"
echo "  Android → Open Android Studio · Build › Generate Signed App Bundle"
