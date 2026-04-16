# Envelope Studio

**Design envelope and letter layouts, merge CSV data, print or export PDF — all on your own computer.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## What we built (summary)

**Envelope Studio** is an open-source, cross-platform GUI application that lets small businesses, offices, and individuals:

- Import mailing lists from **CSV** (or JSON).
- Design layouts on a **visual canvas** for **US #10 envelopes** or **A4 paper** — text blocks, images, and merge shortcodes like `{name}` matching column headers.
- **Preview** merged data on the design before printing.
- **Print** to a local printer or **export multi-page PDF** (one page per recipient).
- Store data **locally** in SQLite — no cloud required.

The stack is **Python 3.9+**, **PySide6 (Qt)** for the UI, **PyInstaller** for standalone builds. Authentication is a simple local gate (configurable in code).


## Features

| Capability | Description |
|------------|-------------|
| **Data import** | Import **CSV** (first row = column names) or JSON; each column becomes a merge field like `{email}` or `{tracking_number}`. |
| **Dual layouts** | Separate designers for **US #10 envelope** and **A4** paper — portrait/landscape, text blocks, images, layer navigator. |
| **Mail merge** | Drag shortcodes from the field bar or type `{column_name}` in text blocks; live preview against a chosen row. |
| **Output** | **Print** to a local printer or **export PDF** (one page per row); page size matches envelope or A4. |
| **Templates** | Save, load, and delete envelope/A4 templates stored locally in **SQLite**. |
| **Privacy** | No account, no cloud — lists and templates stay on the machine running the app. |

---

## Why this project exists

Many teams still send **physical mail** (invoices, notices, marketing) or need **PDF packs** per recipient. Generic office tools are either heavy, subscription-based, or weak at **variable data** on a fixed layout.

**Envelope Studio** was created to offer a **simple, focused tool**: one place to design the layout, bind it to spreadsheet columns, and produce print-ready output — without uploading customer data to a third party.

---

## Who it helps

- **Small businesses** sending personalized envelopes or letters in bulk.  
- **Offices** that already work in **Excel/CSV** and want a straightforward print workflow.  
- **Anyone** who wants **merge + PDF** with a visual designer instead of only mail-merge in a word processor.

---

## Tech stack

- **Python 3.9+**
- **PySide6** (Qt) — cross-platform desktop UI
- **SQLite** — batches, records, saved templates
- **PyInstaller** — optional standalone `.exe` / macOS app (see `BUILD.md`)

---

## Install & run (from source)

### 1. Clone the repository

```bash
git clone https://github.com/ashikp/envelope-software.git
cd envelope-software
```

(Replace with your real GitHub URL after you publish.)

### 2. Create a virtual environment (recommended)

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -e .
```

### 3. Start the application

```bash
envelope-studio
```

If the command is not found, run:

```bash
python -m envelope_app.main
```

---

## Default login

When the app starts, sign in with:

| Field | Value |
|--------|--------|
| **Username** | `ashik` |
| **Password** | `ashik@123` |

> **Security note:** These credentials are a **simple local gate** in `envelope_app/auth.py`. If you **fork this repo publicly**, change `APP_USERNAME` and `APP_PASSWORD` before publishing, or anyone can read them from the source. For shared or production use, replace them with your own values.

---

## How to use (quick workflow)

1. **Sign in** with the credentials above.  
2. **Data** — Import a CSV; check that column headers look correct.  
3. **Designer** — Choose **envelope** or **A4**, add text/images, insert `{column}` placeholders, **Save envelope** / **Save A4** as needed.  
4. **Print** — Pick the list, choose layout (envelope or A4), **Export PDF** or **Print**.  

Footer shows version and credit; **Help → About** has more detail.

---

## Building standalone apps (optional)

- **Windows `.exe`:** Must be built on Windows or via **GitHub Actions** — see **`BUILD.md`** and **`scripts/build_release_windows.ps1`**.  
- **macOS app:** See **`BUILD.md`** and **`scripts/build_release.sh`**.  

Client delivery notes: **`CLIENT_DELIVERY.md`**.

---

## Repository metadata (GitHub)

See **`GITHUB.md`** for suggested **description**, **topics/tags**, and open-source notes for your GitHub **About** section.

---

## License

This project is open source under the **MIT License** — see [`LICENSE`](LICENSE).

---

## Author

**Md Ashikur Rahman** — *Envelope Studio* · Version **1.0.0** (see `envelope_app/version.py`).

---

## Open source

This project is released under the **MIT License** (see `LICENSE`). You may use, modify, and distribute it freely, including for commercial purposes, subject to the license terms.

Contributions (issues, pull requests) are welcome: improve accessibility, packaging, translations, or documentation.

---

## Releases

Tag versions (e.g. `v1.0.0`) and attach built artifacts from `BUILD.md` / GitHub Actions where appropriate.
