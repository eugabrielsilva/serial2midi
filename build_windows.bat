@echo off
setlocal

set "ROOT_DIR=%~dp0"

set "PYTHON_CMD="

if defined VIRTUAL_ENV (
    if exist "%VIRTUAL_ENV%\Scripts\python.exe" (
        set "PYTHON_CMD=""%VIRTUAL_ENV%\Scripts\python.exe"""
    )
)

if not defined PYTHON_CMD (
    if exist "%ROOT_DIR%venv\Scripts\python.exe" (
        set "PYTHON_CMD=""%ROOT_DIR%venv\Scripts\python.exe"""
    )
)

if not defined PYTHON_CMD (
    where py >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_CMD=py -3"
    )
)

if not defined PYTHON_CMD (
    where python >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_CMD=python"
    )
)

if not defined PYTHON_CMD (
    echo Python 3 was not found. Activate the project's virtual environment first.
    exit /b 1
)

echo Using Python: %PYTHON_CMD%

%PYTHON_CMD% -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found. Installing it into the active environment...
    %PYTHON_CMD% -m pip install pyinstaller || exit /b 1
)

if exist "%ROOT_DIR%build" rmdir /s /q "%ROOT_DIR%build"
if exist "%ROOT_DIR%dist" rmdir /s /q "%ROOT_DIR%dist"
if exist "%ROOT_DIR%serial2midi.spec" del /f /q "%ROOT_DIR%serial2midi.spec"

echo Building single-file executable...

%PYTHON_CMD% -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --name serial2midi ^
    --onefile ^
    --hidden-import=PySide6.QtCore ^
    --hidden-import=PySide6.QtWidgets ^
    --hidden-import=PySide6.QtGui ^
    --hidden-import=serial.tools.list_ports ^
    --exclude-module=PySide6.QtWebEngine ^
    --exclude-module=PySide6.QtWebEngineCore ^
    --exclude-module=PySide6.QtWebEngineWidgets ^
    --exclude-module=PySide6.QtMultimedia ^
    --exclude-module=PySide6.QtMultimediaWidgets ^
    --exclude-module=PySide6.Qt3DCore ^
    --exclude-module=PySide6.Qt3DRender ^
    --exclude-module=PySide6.Qt3DInput ^
    --exclude-module=PySide6.Qt3DLogic ^
    --exclude-module=PySide6.Qt3DAnimation ^
    --exclude-module=PySide6.Qt3DExtras ^
    --exclude-module=PySide6.QtCharts ^
    --exclude-module=PySide6.QtDataVisualization ^
    --exclude-module=PySide6.QtLocation ^
    --exclude-module=PySide6.QtPositioning ^
    --exclude-module=PySide6.QtRemoteObjects ^
    --exclude-module=PySide6.QtSensors ^
    --exclude-module=PySide6.QtSerialBus ^
    --exclude-module=PySide6.QtSpatialAudio ^
    --exclude-module=PySide6.QtVirtualKeyboard ^
    --exclude-module=unittest ^
    --exclude-module=email ^
    --exclude-module=html ^
    --exclude-module=http ^
    --exclude-module=xml ^
    --exclude-module=xmlrpc ^
    --exclude-module=tkinter ^
    --exclude-module=_tkinter ^
    "%ROOT_DIR%main.py"

if errorlevel 1 exit /b 1

echo.
echo Build completed: %ROOT_DIR%dist\serial2midi.exe

exit /b 0