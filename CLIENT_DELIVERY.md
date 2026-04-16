# Delivering Envelope Studio to a client

## What to send

After a successful build, zip the **entire** folder:

- `dist/EnvelopeStudio/` (macOS or Windows — build on the platform the client uses)

Example (macOS):

```bash
cd dist
zip -r EnvelopeStudio-$(uname -m)-v1.0.0.zip EnvelopeStudio
```

Send the ZIP (or a USB copy of the `EnvelopeStudio` folder). The client must keep **`EnvelopeStudio` and `_internal` together** — do not move only the executable.

## Client setup

1. Unzip the archive.
2. Open **`EnvelopeStudio`** (macOS) or **`EnvelopeStudio.exe`** (Windows).
3. **First launch (macOS):** If the system blocks the app (“unidentified developer”), **right‑click → Open** once, then confirm.
4. Sign in with the **username and password** you provide separately (do not share these in public repos or email in plain text if you can avoid it).

## Where data is saved

Imports, templates, and the database are stored in the app’s user data folder on that computer (not inside the zip). Backups = export PDFs / keep copies of CSV files as needed.

## Windows `.exe`

Must be produced **on Windows** (or [GitHub Actions](../.github/workflows/build-windows.yml) `workflow_dispatch`). See **`BUILD.md`** for `scripts/build_release_windows.ps1` and the downloadable artifact **EnvelopeStudio-Windows-x64**.

Deliver the **entire** `EnvelopeStudio` folder: `EnvelopeStudio.exe` and `_internal` must stay together.
