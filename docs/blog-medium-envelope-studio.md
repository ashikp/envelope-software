# I Built a Desktop App for Mail Merge on Real Envelopes — Without Sending Your Data to the Cloud

*A practical tool for anyone who still prints letters, invoices, or campaigns — one page per person, straight from a spreadsheet.*

---

When you need to send **hundreds of envelopes** or **personalized PDF letters**, the usual options are awkward: mail merge in a word processor (fragile layouts), enterprise tools (expensive and heavy), or online services (your customer list leaves your machine).

I wanted something **simple**, **visual**, and **local**: design the layout once, bind it to CSV columns, then print or export a PDF where **each row becomes one page** — envelope or A4 — with **no upload**, **no subscription**, and **no surprise**.

That’s how **Envelope Studio** came to be.

---

## The problem I was solving

Small businesses, clinics, schools, and solo operators still rely on **physical mail** or **print-ready PDF packs**. Their data already lives in **Excel or CSV**. What they don’t need is another SaaS that ingests PII just to merge a name and address onto a template.

They need:

- A **canvas** that respects **real paper sizes** (US #10 envelope, A4 letter).
- **Merge fields** that map cleanly to **column headers** — `{name}`, `{tracking_number}`, whatever the file contains.
- **Print** and **PDF export** that match what they see on screen.
- **Privacy by default**: data stays in a **local database** on the computer running the app.

So I built a **cross-platform desktop app** that does exactly that — and released it **open source** under the MIT license.

---

## What Envelope Studio actually does

**Import your list**  
Drop in a CSV (or JSON). The first row defines your merge vocabulary: every header becomes a field you can drop into the design as `{column_name}`.

**Design in two worlds**  
There are **two separate layouts** — one for **US #10 envelopes**, one for **A4** paper. Each has its own saved template. You can switch orientation, add **text blocks** and **images**, and use a **layer navigator** (think “layers” in design tools) to select and reorder elements.

**Preview before you commit**  
Turn on **live preview** and scrub through rows: the canvas shows merged text so you catch typos or missing fields before you print a stack of bad envelopes.

**Ship it**  
From the Print screen, pick your list, choose **envelope or A4** output, then **print to a local printer** or **export a multi-page PDF** — one page per recipient.

No accounts. No cloud sync. Your mailing list never has to leave the machine unless **you** export or copy it.

---

## Why I chose a desktop stack (and what it’s built with)

**Python** keeps the logic readable and maintainable. **PySide6 (Qt)** gives a native-feeling UI on **Windows and macOS**. **SQLite** stores imports and templates locally — lightweight, reliable, and easy to back up by copying a file.

For distribution, **PyInstaller** wraps the app into a folder with an executable and bundled Qt libraries, so non-developers can run it without installing Python.

The fixed **login screen** in the current build is a lightweight gate for demos and shared machines — credentials live in code and can be changed for your deployment. (If you fork the project publicly, rotate them.)

---

## Who this helps

- **Small businesses** sending invoices or notices by mail.  
- **Offices** that already live in spreadsheets and want a **visual** merge, not a mail-merge wizard from 2003.  
- **Anyone** who wants **PDF batches** per row without uploading a CSV to a random website.

If your workflow is “spreadsheet + print,” this tool fits in the middle: **spreadsheet → layout → print/PDF**.

---

## Open source, on purpose

The project is on GitHub under the **MIT License**. You can use it, modify it, package it for clients, or extend it — attribution is appreciated, and contributions (documentation, accessibility, packaging) are welcome.

Building in the open also keeps the **privacy story** honest: you can read how data is stored and that nothing phones home.

---

## Try it or fork it

Clone the repo, install with `pip install -e .`, run `envelope-studio`, import a CSV, and sketch a layout. If it saves you a afternoon of wrestling with Word merge fields, it did its job.

If you’re a developer: the codebase is structured around a clear separation — **layout JSON**, **merge engine**, **print/PDF pipeline** — so features like extra paper sizes or template presets can grow without rewriting everything.

---

## Closing

**Envelope Studio** isn’t trying to replace a full marketing automation suite. It’s a **focused utility** for a workflow that refuses to die: **paper and PDF**, **personalized at scale**, **your data on your disk**.

Sometimes the best tool is the one that does **one job** — and stays **offline**.

---

**Md Ashikur Rahman**  
*Creator of Envelope Studio · v1.0.0*

*Repository & docs: see the project README on GitHub. Build instructions for Windows `.exe` and macOS app are in the repository’s `BUILD.md`.*

---

### Suggested Medium settings (when you publish)

- **Title:** Shorten the H1 if needed (Medium ~60–70 characters works well).  
- **Subtitle:** Use the italic line under the title.  
- **Tags:** `Programming`, `Python`, `Open Source`, `Privacy`, `Productivity`, `Small Business` (pick 5 Medium allows).  
- **Featured image:** A simple hero — envelope + spreadsheet, or a screenshot of the designer (your own asset avoids copyright issues).

---

*This article is provided as `docs/blog-medium-envelope-studio.md` in the Envelope Studio repository — you may edit the tone or add screenshots before publishing.*
