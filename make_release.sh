#!/bin/bash
# Builds dist/steam-frame-helper.tar.gz from the committed files only (git archive),
# so nothing untracked or ignored (private/, local state) can end up in a release.
# Usage: ./make_release.sh   (run from a clean, committed tree)
set -euo pipefail
cd "$(dirname "$0")"

if [ -n "$(git status --porcelain -- steam_frame_helper install.sh LICENSE README.md README.ru.md docs)" ]; then
    echo "Uncommitted changes in release files — commit first." >&2
    exit 1
fi
VERSION="$(cat steam_frame_helper/VERSION)"
mkdir -p dist
git archive --format=tar.gz -o dist/steam-frame-helper.tar.gz HEAD \
    steam_frame_helper install.sh LICENSE README.md README.ru.md docs
echo "dist/steam-frame-helper.tar.gz  (v$VERSION)"
tar -tzf dist/steam-frame-helper.tar.gz | grep -ci amnezia && { echo "amnezia files in archive!" >&2; exit 1; } || true
