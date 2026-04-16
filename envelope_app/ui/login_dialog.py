from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from envelope_app.auth import verify_fixed_login


class LoginDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sign in")
        self.setModal(True)
        self.resize(400, 160)

        lay = QVBoxLayout(self)
        lay.addWidget(
            QLabel("Sign in to Envelope Studio."),
        )
        self._user = QLineEdit()
        self._user.setPlaceholderText("Username")
        self._pw = QLineEdit()
        self._pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw.setPlaceholderText("Password")
        self._pw.returnPressed.connect(self._try_ok)
        form = QFormLayout()
        form.addRow("Username", self._user)
        form.addRow("Password", self._pw)
        lay.addLayout(form)

        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        box.accepted.connect(self._try_ok)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def _try_ok(self) -> None:
        if verify_fixed_login(self._user.text(), self._pw.text()):
            self.accept()
            return
        QMessageBox.warning(self, "Sign in", "Incorrect username or password.")
        self._pw.clear()
        self._pw.setFocus()


def ensure_logged_in(parent=None) -> bool:
    """Show login; returns True if the main window may open."""
    dlg = LoginDialog(parent=parent)
    return dlg.exec() == QDialog.DialogCode.Accepted
