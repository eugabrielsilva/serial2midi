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

OS_NAME="$(uname -s)"

if [[ "${OS_NAME}" == "Darwin" ]]; then
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

COMMON_ARGS=(
    --noconfirm
    --clean
    --name serial2midi
    # Only the Qt modules the app actually uses
    --hidden-import=PySide6.QtCore
    --hidden-import=PySide6.QtWidgets
    --hidden-import=PySide6.QtGui
    --hidden-import=serial.tools.list_ports
    # Exclude heavy Qt modules not used by this app
    --exclude-module=PySide6.QtWebEngine
    --exclude-module=PySide6.QtWebEngineCore
    --exclude-module=PySide6.QtWebEngineWidgets
    --exclude-module=PySide6.QtMultimedia
    --exclude-module=PySide6.QtMultimediaWidgets
    --exclude-module=PySide6.Qt3DCore
    --exclude-module=PySide6.Qt3DRender
    --exclude-module=PySide6.Qt3DInput
    --exclude-module=PySide6.Qt3DLogic
    --exclude-module=PySide6.Qt3DAnimation
    --exclude-module=PySide6.Qt3DExtras
    --exclude-module=PySide6.QtCharts
    --exclude-module=PySide6.QtDataVisualization
    --exclude-module=PySide6.QtLocation
    --exclude-module=PySide6.QtPositioning
    --exclude-module=PySide6.QtRemoteObjects
    --exclude-module=PySide6.QtSensors
    --exclude-module=PySide6.QtSerialBus
    --exclude-module=PySide6.QtSpatialAudio
    --exclude-module=PySide6.QtVirtualKeyboard
    # Exclude unused Python stdlib modules
    --exclude-module=unittest
    --exclude-module=email
    --exclude-module=html
    --exclude-module=http
    --exclude-module=xml
    --exclude-module=xmlrpc
    --exclude-module=tkinter
    --exclude-module=_tkinter
    "${ROOT_DIR}/main.py"
)

if [[ "${OS_NAME}" == "Darwin" ]]; then
    echo "Building macOS app bundle (.app)..."
    "${PYTHON_BIN}" -m PyInstaller \
        --windowed \
        --onedir \
        "${COMMON_ARGS[@]}"

    APP_PATH="${ROOT_DIR}/dist/serial2midi.app"
    BIN_PATH="${APP_PATH}/Contents/MacOS/serial2midi"

    if command -v codesign >/dev/null 2>&1; then
        echo "Applying ad-hoc signature to app bundle..."
        codesign --force --deep --sign - "${APP_PATH}" || true
    fi

    if command -v xattr >/dev/null 2>&1; then
        echo "Removing quarantine attributes from app bundle..."
        xattr -cr "${APP_PATH}" || true
    fi

    cat > "${ROOT_DIR}/dist/run_serial2midi_debug.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
LOG_FILE="\${HOME}/serial2midi_boot.log"
"${BIN_PATH}" > "\${LOG_FILE}" 2>&1 || true
echo "Debug log written to: \${LOG_FILE}"
EOF
    chmod +x "${ROOT_DIR}/dist/run_serial2midi_debug.sh"

    echo
    echo "Build completed: ${APP_PATH}"
    echo "If the app closes unexpectedly, run: ${ROOT_DIR}/dist/run_serial2midi_debug.sh"
else
    echo "Building single-file executable..."
    "${PYTHON_BIN}" -m PyInstaller \
        --onefile \
        "${COMMON_ARGS[@]}"

    echo
    echo "Build completed: ${ROOT_DIR}/dist/serial2midi"
fi
