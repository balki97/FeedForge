#!/usr/bin/env bash
#
# Build/fetch the native Linux converter tools that FeedForge bundles at
# release time, mirroring how the Windows *.exe tools are supplied. The
# resulting binaries are written to:
#
#     src/feedback_converter/tools/linux/
#
# and are intentionally git-ignored (like the Windows *.exe), so they are
# produced on the build machine / CI rather than committed.
#
# Tools produced:
#   - ww2ogg        (WEM -> OGG, built from hcs64/ww2ogg; same source as Windows)
#   - vgmstream-cli (WEM -> WAV, official statically-linked Linux release)
#
# WAV -> OGG encoding uses `oggenc` when present, otherwise falls back to
# `ffmpeg` (libvorbis, quality 5) at runtime, so no Vorbis encoder needs to be
# bundled here. Install `vorbis-tools` (for oggenc) or `ffmpeg` on the target.
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${REPO_ROOT}/src/feedback_converter/tools/linux"
WORK="$(mktemp -d)"
VGMSTREAM_RELEASE="${VGMSTREAM_RELEASE:-r2117}"

cleanup() { rm -rf "${WORK}"; }
trap cleanup EXIT

mkdir -p "${DEST}"

echo "==> Building ww2ogg from source"
curl -sL --fail --max-time 120 \
  "https://github.com/hcs64/ww2ogg/archive/refs/heads/master.tar.gz" \
  -o "${WORK}/ww2ogg.tar.gz"
tar xzf "${WORK}/ww2ogg.tar.gz" -C "${WORK}"
make -C "${WORK}/ww2ogg-master" >/dev/null
cp "${WORK}/ww2ogg-master/ww2ogg" "${DEST}/ww2ogg"
chmod +x "${DEST}/ww2ogg"
echo "    -> ${DEST}/ww2ogg"

echo "==> Fetching vgmstream-cli (${VGMSTREAM_RELEASE}, Linux static build)"
curl -sL --fail --max-time 180 \
  "https://github.com/vgmstream/vgmstream/releases/download/${VGMSTREAM_RELEASE}/vgmstream-linux.zip" \
  -o "${WORK}/vgmstream-linux.zip"
unzip -o "${WORK}/vgmstream-linux.zip" -d "${WORK}/vgmstream" >/dev/null
cp "${WORK}/vgmstream/vgmstream-cli" "${DEST}/vgmstream-cli"
chmod +x "${DEST}/vgmstream-cli"
echo "    -> ${DEST}/vgmstream-cli"

echo "==> Done. Native Linux converter tools are in ${DEST}"
