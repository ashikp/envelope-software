@echo off
REM Double-click or run from cmd in the project folder.
cd /d "%~dp0.."

echo Installing deps...
python -m pip install -U pip
pip install -e ".[dev]"

echo Cleaning...
if exist build\envelope-studio rmdir /s /q build\envelope-studio
if exist dist\EnvelopeStudio rmdir /s /q dist\EnvelopeStudio

echo Building...
pyinstaller -y envelope-studio.spec

echo.
echo Output: dist\EnvelopeStudio\EnvelopeStudio.exe
pause
