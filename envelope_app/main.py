from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from envelope_app.db import Database
from envelope_app.paths import database_path
from envelope_app.ui.login_dialog import ensure_logged_in
from envelope_app.ui.main_window import MainWindow
from envelope_app.ui.theme import apply_app_theme


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Envelope Studio")
    app.setOrganizationName("EnvelopeStudio")
    apply_app_theme(app)

    db = Database(database_path())
    if not ensure_logged_in():
        db.close()
        raise SystemExit(0)
    win = MainWindow(db)
    win.show()
    rc = app.exec()
    db.close()
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
