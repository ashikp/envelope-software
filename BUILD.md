# Building Envelope Studio for client delivery

Build **on the same OS** the client will use (PyInstaller bundles native Qt binaries). **You cannot build a Windows `.exe` on macOS** — use one of the options below.

- **macOS** → build on a Mac → deliver the `EnvelopeStudio` folder (or zip it).
- **Windows `.exe`** → must be built **on Windows** (local PC/VM) **or** via **GitHub Actions** (see below).

## Windows EXE (from macOS: use GitHub Actions)

If the repo is on GitHub:

1. Push your latest code.
2. Open **Actions** → **Build Windows EXE** → **Run workflow**.
3. When it finishes, download the artifact **EnvelopeStudio-Windows-x64** (ZIP). Inside is `EnvelopeStudio` with `EnvelopeStudio.exe` and `_internal`.

## Windows EXE (on a Windows PC)

1. Install [Python 3.9+](https://www.python.org/downloads/) (check “Add python.exe to PATH”).
2. Clone or copy the project folder.
3. In **PowerShell** (project root):

```powershell
.\scripts\build_release_windows.ps1
```

Or double-click **`scripts\build_release_windows.bat`** (installs venv not in bat — bat uses system Python; for a clean venv, use PowerShell script after `python -m venv .venv` and `.\.venv\Scripts\Activate.ps1` then `pip install -e ".[dev]"` and `pyinstaller -y envelope-studio.spec`).

Output: **`dist\EnvelopeStudio\EnvelopeStudio.exe`** — ship the **whole** `EnvelopeStudio` folder (exe + `_internal`).

## Prerequisites

- Python 3.9+ (same as `pyproject.toml`)
- Project dependencies installed

## One-time setup

```bash
cd /path/to/dan-envolope
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -U pip
pip install -e ".[dev]"
```

## Build the release

```bash
./scripts/build_release.sh
```

See **`CLIENT_DELIVERY.md`** for zipping and handoff notes.

Or manually:

```bash
rm -rf build/envelope-studio dist/EnvelopeStudio
pyinstaller -y envelope-studio.spec
```

On Windows PowerShell:

```powershell
Remove-Item -Recurse -Force build\envelope-studio, dist\EnvelopeStudio -ErrorAction SilentlyContinue
pyinstaller -y envelope-studio.spec
```

Output:

- **`dist/EnvelopeStudio/`** — folder containing **`EnvelopeStudio`** (macOS app) or **`EnvelopeStudio.exe`** (Windows) plus `_internal` with Qt libraries.

## What to give the client

1. Zip the entire **`dist/EnvelopeStudio`** folder (or use a DMG/installer on macOS if you want a nicer installer).
2. Tell them to **unzip** and double-click the app (macOS may show “unidentified developer” until you right-click → Open, or you code-sign the app).
3. **Data** (CSV imports, saved templates, SQLite DB) lives in the app’s **user data directory** (see `envelope_app/paths.py` — typically under the OS app data folder).

## Version

- **Application version** is in `envelope_app/version.py` and in **Help → About** / the footer.
- Bump `envelope_app/version.py` and `pyproject.toml` `[project] version` together when releasing.

## Optional: code signing (macOS)

For distribution without Gatekeeper warnings, sign with a Developer ID certificate:

```bash
codesign --deep --force --options runtime --sign "Developer ID Application: …" dist/EnvelopeStudio/EnvelopeStudio.app
```

(Adjust path if your `EXE` output is a `.app` bundle; one-folder builds use the executable inside `EnvelopeStudio/`.)
