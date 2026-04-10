#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
    PYTHON_BIN="${VIRTUAL_ENV}/bin/python"
elif [[ -x "${ROOT_DIR}/venv/bin/python" ]]; then
    PYTHON_BIN="${ROOT_DIR}/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
else
    echo "Python 3 was not found. Activate the project's virtual environment first."
    exit 1
fi

echo "Using Python: ${PYTHON_BIN}"

if [[ "$(uname -s)" == "Darwin" ]]; then
    if [[ -z "${MACOSX_DEPLOYMENT_TARGET:-}" ]]; then
        export MACOSX_DEPLOYMENT_TARGET="11.0"
    fi
    echo "Using MACOSX_DEPLOYMENT_TARGET: ${MACOSX_DEPLOYMENT_TARGET}"
fi

if ! "${PYTHON_BIN}" -m PyInstaller --version >/dev/null 2>&1; then
    echo "PyInstaller not found. Installing it into the active environment..."
    "${PYTHON_BIN}" -m pip install pyinstaller
fi

rm -rf "${ROOT_DIR}/build" "${ROOT_DIR}/dist" "${ROOT_DIR}/serial2midi.spec"

"${PYTHON_BIN}" -m PyInstaller \
    --noconfirm \
    --clean \
    --onefile \
    --name serial2midi \
    --hidden-import=tkinter \
    --hidden-import=_tkinter \
    --hidden-import=serial.tools.list_ports \
    "${ROOT_DIR}/main.py"

echo
echo "Build completed: ${ROOT_DIR}/dist/serial2midi"
