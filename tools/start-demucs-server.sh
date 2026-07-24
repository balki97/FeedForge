#!/usr/bin/env bash
#
# POSIX (Linux/macOS) launcher for the FeedForge local Demucs stem server.
# This mirrors tools/start-demucs-server.ps1 for non-Windows platforms:
# it provisions a local virtualenv, installs the stem dependencies, and
# launches the FastAPI/uvicorn server. Driven by the same FEEDFORGE_* env vars.
#
set -euo pipefail

log() { printf 'FeedForge: %s\n' "$*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/pyproject.toml" ]; then
  SOURCE_ROOT="${SCRIPT_DIR}"
else
  SOURCE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
fi

INSTALL_ROOT="${FEEDFORGE_DEMUCS_HOME:-${SOURCE_ROOT}}"
MODEL="${FEEDFORGE_DEMUCS_MODEL:-htdemucs_6s}"
DEVICE="${FEEDFORGE_DEMUCS_DEVICE:-auto}"
CONCURRENCY="${FEEDFORGE_DEMUCS_CONCURRENCY:-1}"

CACHE_ROOT="${INSTALL_ROOT}/model-cache"
RUNTIME_ROOT="${INSTALL_ROOT}/runtime"
TEMP_ROOT="${RUNTIME_ROOT}/temp"
STORAGE_ROOT="${RUNTIME_ROOT}/jobs"
mkdir -p "${CACHE_ROOT}" "${TEMP_ROOT}" "${STORAGE_ROOT}"

export TORCH_HOME="${CACHE_ROOT}/torch"
export XDG_CACHE_HOME="${CACHE_ROOT}"
export PIP_CACHE_DIR="${INSTALL_ROOT}/pip-cache"
export HF_HOME="${CACHE_ROOT}/huggingface"
export TMPDIR="${TEMP_ROOT}"

TORCH_INDEX="${FEEDFORGE_TORCH_INDEX:-}"
if [ "${TORCH_INDEX}" = "auto" ]; then
  if command -v nvidia-smi >/dev/null 2>&1; then
    TORCH_INDEX="https://download.pytorch.org/whl/cu128"
  else
    TORCH_INDEX=""
  fi
fi

VENV="${INSTALL_ROOT}/.demucs-venv"
PYTHON="${VENV}/bin/python"

SYSTEM_PYTHON=""
if [ -n "${FEEDFORGE_PYTHON_EXE:-}" ] && [ -x "${FEEDFORGE_PYTHON_EXE}" ]; then
  SYSTEM_PYTHON="${FEEDFORGE_PYTHON_EXE}"
elif command -v python3 >/dev/null 2>&1; then
  SYSTEM_PYTHON="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  SYSTEM_PYTHON="$(command -v python)"
fi

MARKER="${INSTALL_ROOT}/.feedforge-stems-source"
PYPROJECT="${SOURCE_ROOT}/pyproject.toml"
STAMP_MTIME="$(stat -c %Y "${PYPROJECT}" 2>/dev/null || stat -f %m "${PYPROJECT}" 2>/dev/null || echo 0)"
SOURCE_STAMP="${SOURCE_ROOT}|${STAMP_MTIME}|torch=${TORCH_INDEX}"

log "preparing local stem setup"
log "install folder ${INSTALL_ROOT}"
log "runtime folder ${RUNTIME_ROOT}"
log "selected model ${MODEL}"
log "selected device ${DEVICE}"

if [ ! -x "${PYTHON}" ]; then
  if [ -z "${SYSTEM_PYTHON}" ]; then
    echo "Python 3.11 or newer was not found. Install Python 3.11+ (e.g. from your package manager or https://www.python.org/downloads/), then start the local stem server again." >&2
    exit 2
  fi
  mkdir -p "${INSTALL_ROOT}"
  log "creating local Python environment"
  log "source Python ${SYSTEM_PYTHON}"
  "${SYSTEM_PYTHON}" -m venv "${VENV}"
else
  log "reusing local Python environment"
fi

CURRENT_STAMP=""
if [ -f "${MARKER}" ]; then
  CURRENT_STAMP="$(cat "${MARKER}" 2>/dev/null || echo "")"
fi

if [ "${CURRENT_STAMP}" != "${SOURCE_STAMP}" ]; then
  log "installing FeedForge stem dependencies"
  "${PYTHON}" -m pip install --upgrade pip
  "${PYTHON}" -m pip install -e "${SOURCE_ROOT}[stems]"
  if [ -n "${TORCH_INDEX}" ]; then
    if "${PYTHON}" -c "import torch, sys; sys.exit(0 if getattr(torch.version, 'cuda', None) else 1)" >/dev/null 2>&1; then
      log "CUDA PyTorch runtime already installed"
    else
      log "installing CUDA PyTorch runtime"
      "${PYTHON}" -m pip install --upgrade torch torchvision torchaudio --index-url "${TORCH_INDEX}"
    fi
  fi
  printf '%s' "${SOURCE_STAMP}" > "${MARKER}"
else
  log "dependencies already installed"
fi

log "verifying Demucs runtime"
if ! "${PYTHON}" -c "import demucs, fastapi, soundfile, torch" >/dev/null 2>&1; then
  log "repairing missing stem dependencies"
  "${PYTHON}" -m pip install -e "${SOURCE_ROOT}[stems]"
  "${PYTHON}" -c "import demucs, fastapi, soundfile, torch"
  printf '%s' "${SOURCE_STAMP}" > "${MARKER}"
fi

log "starting Demucs server"
log "loading selected model. First launch may download model files and can take several minutes."
exec "${PYTHON}" -m feedback_converter.demucs_server \
  --host 127.0.0.1 \
  --port 7865 \
  --model "${MODEL}" \
  --device "${DEVICE}" \
  --concurrency "${CONCURRENCY}" \
  --storage-dir "${STORAGE_ROOT}" \
  --preload-model
