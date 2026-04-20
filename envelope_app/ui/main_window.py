from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QMimeData, QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from envelope_app.db import Database
from envelope_app.version import VERSION
from envelope_app.record_import import load_records_file
from envelope_app.layout import LAYOUT_KIND_A4, default_a4_layout, default_layout
from envelope_app.printing import export_pdf, print_records
from envelope_app.ui.designer_widget import DesignerWidget

TEMPLATE_ENVELOPE = "default"
TEMPLATE_A4 = "a4"

APP_CREDIT = "Developed by Md Ashikur Rahman"

# Wide CSVs: never use Stretch — it splits width across all columns and makes cells unreadable.
_DATA_COL_MIN = 88
_DATA_COL_MAX = 420


def _page_header(title: str, subtitle: str) -> QWidget:
    """Title + subtitle block for each screen."""
    wrap = QWidget()
    col = QVBoxLayout(wrap)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(4)
    t = QLabel(title)
    t.setObjectName("pageTitle")
    s = QLabel(subtitle)
    s.setObjectName("pageDesc")
    s.setWordWrap(True)
    col.addWidget(t)
    col.addWidget(s)
    return wrap


class MainWindow(QMainWindow):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db
        self.setWindowTitle("Envelope Studio")
        self.resize(1440, 900)
        self.setMinimumSize(1024, 700)
        self._app_drop_filter_installed = False

        self._batch_combo = QComboBox()
        self._batch_combo.currentIndexChanged.connect(self._on_batch_changed)

        self._table = QTableWidget(0, 0)
        self._table.setObjectName("dataTable")
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(True)
        self._table.setWordWrap(False)
        self._table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(28)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setDefaultSectionSize(140)
        hdr.setMinimumSectionSize(_DATA_COL_MIN)
        hdr.setStretchLastSection(False)
        hdr.setHighlightSections(False)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_data_table_context_menu)

        self._preview_row_spin = QSpinBox()
        self._preview_row_spin.setObjectName("previewRowSpin")
        self._preview_row_spin.setMinimum(1)
        self._preview_row_spin.setMaximum(1)
        self._preview_row_spin.setMinimumWidth(88)
        self._preview_row_spin.setMinimumHeight(28)
        self._preview_row_spin.valueChanged.connect(self._apply_preview)

        self._preview_check = QCheckBox("Preview live merge (both layouts)")
        self._preview_check.setChecked(False)
        self._preview_check.toggled.connect(self._apply_preview)

        self._loading_template = False
        self._designer_env = DesignerWidget()
        self._designer_a4 = DesignerWidget(layout_kind=LAYOUT_KIND_A4)
        self._designer_env.layout_changed.connect(self._mark_dirty_envelope)
        self._designer_a4.layout_changed.connect(self._mark_dirty_a4)
        self._designer_env.shortcode_copied.connect(self._on_shortcode_copied)
        self._designer_a4.shortcode_copied.connect(self._on_shortcode_copied)

        self._dirty_envelope = False
        self._dirty_a4 = False
        self._preview_backup_env: list[tuple[str, str]] = []
        self._preview_backup_a4: list[tuple[str, str]] = []

        # —— Data page
        data_page = QWidget()
        data_page.setObjectName("page")
        d_root = QVBoxLayout(data_page)
        d_root.setContentsMargins(32, 28, 32, 24)
        d_root.setSpacing(20)

        d_root.addWidget(
            _page_header(
                "Mail data",
                "Import a CSV file (first row = column headers). Each header becomes a merge field "
                "like {name} or {tracking_number}. JSON is also supported if needed.",
            )
        )

        controls = QFrame()
        controls.setObjectName("card")
        c_l = QVBoxLayout(controls)
        c_l.setContentsMargins(20, 18, 20, 18)
        c_l.setSpacing(14)

        row1_title = QLabel("Active import")
        row1_title.setObjectName("cardTitle")
        c_l.addWidget(row1_title)

        row1 = QHBoxLayout()
        lab = QLabel("List")
        lab.setObjectName("fieldLabel")
        lab.setFixedWidth(72)
        row1.addWidget(lab)
        row1.addWidget(self._batch_combo, stretch=1)
        btn_import = QPushButton("Import CSV…")
        btn_import.setObjectName("primary")
        btn_import.clicked.connect(self._import_records)
        row1.addWidget(btn_import)
        btn_del = QPushButton("Remove list")
        btn_del.setObjectName("danger")
        btn_del.clicked.connect(self._delete_batch)
        row1.addWidget(btn_del)
        c_l.addLayout(row1)

        d_root.addWidget(controls)

        table_card = QFrame()
        table_card.setObjectName("card")
        t_l = QVBoxLayout(table_card)
        t_l.setContentsMargins(0, 0, 0, 0)
        t_head = QHBoxLayout()
        t_title = QLabel("Rows")
        t_title.setObjectName("cardTitle")
        t_head.addWidget(t_title)
        t_head.addStretch()
        t_l.addLayout(t_head)
        t_l.addWidget(self._table)
        d_root.addWidget(table_card, stretch=1)

        # —— Designer page
        designer_page = QWidget()
        designer_page.setObjectName("page")
        z_root = QVBoxLayout(designer_page)
        z_root.setContentsMargins(24, 18, 24, 14)
        z_root.setSpacing(10)

        top_bar = QHBoxLayout()
        top_bar.addWidget(
            _page_header(
                "Layout designer",
                "Envelope and A4 are saved separately — use Save envelope / Save A4. Same CSV fields for both.",
            ),
            stretch=1,
        )
        self._btn_save_env = QPushButton("Save envelope")
        self._btn_save_env.setObjectName("primary")
        self._btn_save_env.clicked.connect(self._save_envelope_template)
        self._btn_save_a4 = QPushButton("Save A4")
        self._btn_save_a4.setObjectName("primary")
        self._btn_save_a4.clicked.connect(self._save_a4_template)
        self._btn_fit = QPushButton("Fit view")
        self._btn_fit.clicked.connect(self._fit_active_designer)
        self._btn_sample_pdf = QPushButton("Sample PDF…")
        self._btn_sample_pdf.setToolTip(
            "Export a single-page PDF for sharing. If a list is loaded, uses the preview row; "
            "otherwise merge fields are left empty."
        )
        self._btn_sample_pdf.clicked.connect(self._export_sample_pdf_from_designer)
        top_bar.addWidget(self._btn_save_env, alignment=Qt.AlignmentFlag.AlignTop)
        top_bar.addWidget(self._btn_save_a4, alignment=Qt.AlignmentFlag.AlignTop)
        top_bar.addWidget(self._btn_fit, alignment=Qt.AlignmentFlag.AlignTop)
        top_bar.addWidget(self._btn_sample_pdf, alignment=Qt.AlignmentFlag.AlignTop)
        z_root.addLayout(top_bar)

        del_row = QHBoxLayout()
        del_row.addStretch(1)
        self._btn_del_env = QPushButton("Delete envelope template…")
        self._btn_del_env.setObjectName("danger")
        self._btn_del_env.clicked.connect(self._delete_envelope_template)
        self._btn_del_a4 = QPushButton("Delete A4 template…")
        self._btn_del_a4.setObjectName("danger")
        self._btn_del_a4.clicked.connect(self._delete_a4_template)
        del_row.addWidget(self._btn_del_env)
        del_row.addWidget(self._btn_del_a4)
        z_root.addLayout(del_row)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(12)
        ml = QLabel("Design for")
        ml.setObjectName("fieldLabel")
        self._designer_mode = QComboBox()
        self._designer_mode.setObjectName("designerModeCombo")
        self._designer_mode.addItem("US #10 envelope", "envelope")
        self._designer_mode.addItem("A4 letter", "a4")
        self._designer_mode.currentIndexChanged.connect(self._on_designer_mode_changed)
        mode_row.addWidget(ml)
        mode_row.addWidget(self._designer_mode)
        mode_row.addStretch(1)
        z_root.addLayout(mode_row)

        self._designer_stack = QStackedWidget()
        self._designer_stack.addWidget(self._designer_env)
        self._designer_stack.addWidget(self._designer_a4)

        preview_bar = QHBoxLayout()
        preview_bar.setSpacing(16)
        preview_bar.addWidget(self._preview_check)
        pr = QLabel("Preview row")
        pr.setObjectName("fieldLabel")
        preview_bar.addWidget(pr)
        preview_bar.addWidget(self._preview_row_spin)
        preview_bar.addStretch(1)
        z_root.addLayout(preview_bar)
        z_root.addWidget(self._designer_stack, stretch=1)
        self._designer_env.setMinimumHeight(520)
        self._designer_a4.setMinimumHeight(520)

        # —— Print page
        print_page = QWidget()
        print_page.setObjectName("page")
        p_root = QVBoxLayout(print_page)
        p_root.setContentsMargins(32, 28, 32, 24)
        p_root.setSpacing(20)

        p_root.addWidget(
            _page_header(
                "Print & export",
                "Print or export PDF — one page per list row. Pick envelope or A4 to match your layout.",
            )
        )

        print_card = QFrame()
        print_card.setObjectName("card")
        pl = QVBoxLayout(print_card)
        pl.setContentsMargins(24, 22, 24, 22)
        pl.setSpacing(16)

        self._print_batch = QComboBox()
        prow = QHBoxLayout()
        plab = QLabel("List to print")
        plab.setObjectName("fieldLabel")
        plab.setFixedWidth(100)
        prow.addWidget(plab)
        prow.addWidget(self._print_batch, stretch=1)
        pl.addLayout(prow)

        lay_row = QHBoxLayout()
        lay_lab = QLabel("Layout")
        lay_lab.setObjectName("fieldLabel")
        lay_lab.setFixedWidth(100)
        self._print_layout_combo = QComboBox()
        self._print_layout_combo.setObjectName("printLayoutCombo")
        self._print_layout_combo.addItem("US #10 envelope", "envelope")
        self._print_layout_combo.addItem("A4 letter", "a4")
        lay_row.addWidget(lay_lab)
        lay_row.addWidget(self._print_layout_combo, stretch=1)
        pl.addLayout(lay_row)

        btn_pdf = QPushButton("Export PDF…")
        btn_pdf.setMinimumHeight(44)
        btn_pdf.clicked.connect(self._export_pdf)
        pl.addWidget(btn_pdf)

        btn_sample = QPushButton("Sample PDF (1 page)…")
        btn_sample.setMinimumHeight(44)
        btn_sample.setToolTip(
            "Save one merged page as a PDF using the first row of the selected list (for proofs or email samples)."
        )
        btn_sample.clicked.connect(self._export_sample_pdf_from_print_page)
        pl.addWidget(btn_sample)

        btn_print = QPushButton("Print all…")
        btn_print.setObjectName("primary")
        btn_print.setMinimumHeight(44)
        btn_print.clicked.connect(self._print_bulk)
        pl.addWidget(btn_print)

        hint = QLabel(
            "Export PDF writes every row. Sample PDF (1 page) saves a single merged proof. "
            "Page size follows the layout (#10 or A4). For physical envelopes, load #10 stock and avoid "
            "“fit to page” scaling if alignment looks off."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        pl.addWidget(hint)

        p_root.addWidget(print_card)
        p_root.addStretch(1)

        # —— Shell: sidebar + stack
        shell = QWidget()
        shell.setObjectName("centralShell")
        shell_l = QHBoxLayout(shell)
        shell_l.setContentsMargins(0, 0, 0, 0)
        shell_l.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(236)
        sb_l = QVBoxLayout(sidebar)
        sb_l.setContentsMargins(20, 24, 16, 20)
        sb_l.setSpacing(4)

        brand = QLabel("Envelope Studio")
        brand.setObjectName("brandTitle")
        sub = QLabel("Local mail merge")
        sub.setObjectName("brandSub")
        sb_l.addWidget(brand)
        sb_l.addWidget(sub)
        sb_l.addSpacing(20)

        self._nav = QListWidget()
        self._nav.setObjectName("navList")
        self._nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for label, tip in (
            ("Data", "Import CSV lists"),
            ("Designer", "#10 envelope or A4 layout"),
            ("Print", "Bulk to printer"),
        ):
            it = QListWidgetItem(label)
            it.setToolTip(tip)
            self._nav.addItem(it)
        self._nav.setCurrentRow(0)
        self._nav.setFrameShape(QFrame.Shape.NoFrame)
        self._nav.currentRowChanged.connect(self._on_nav_changed)
        sb_l.addWidget(self._nav, stretch=1)

        self._stack = QStackedWidget()
        self._stack.setObjectName("stack")
        self._stack.addWidget(data_page)
        self._stack.addWidget(designer_page)
        self._stack.addWidget(print_page)

        shell_l.addWidget(sidebar)
        shell_l.addWidget(self._stack, stretch=1)

        footer = QLabel(f"{APP_CREDIT} · Version {VERSION}")
        footer.setObjectName("appFooter")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        central = QWidget()
        central_l = QVBoxLayout(central)
        central_l.setContentsMargins(0, 0, 0, 0)
        central_l.setSpacing(0)
        central_l.addWidget(shell, stretch=1)
        central_l.addWidget(footer)

        self.setCentralWidget(central)

        self._build_menu()
        self._reload_batches()
        self._load_template_from_db()

        # Install after the widget tree is attached; avoid filtering every QEvent during __init__.
        QTimer.singleShot(0, self._install_app_drop_filter)

    def _install_app_drop_filter(self) -> None:
        if self._app_drop_filter_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self._app_drop_filter_installed = True

    def _on_nav_changed(self, row: int) -> None:
        if row >= 0:
            self._stack.setCurrentIndex(row)

    def _build_menu(self) -> None:
        m = self.menuBar().addMenu("File")
        act = QAction("Import CSV / JSON…", self)
        act.triggered.connect(self._import_records)
        m.addAction(act)
        m.addSeparator()
        ex = QAction("Exit", self)
        ex.triggered.connect(self.close)
        m.addAction(ex)

        h = self.menuBar().addMenu("Help")
        about = QAction("About", self)
        about.triggered.connect(self._about)
        h.addAction(about)

        sb = QStatusBar()
        self.setStatusBar(sb)
        sb.showMessage(f"Database: {self._db.path}")

    def _mark_dirty_envelope(self) -> None:
        if self._loading_template:
            return
        self._dirty_envelope = True

    def _mark_dirty_a4(self) -> None:
        if self._loading_template:
            return
        self._dirty_a4 = True

    def _on_shortcode_copied(self, text: str) -> None:
        self.statusBar().showMessage(
            f"Copied {text} — paste into the merge template below", 4000
        )

    def _fit_active_designer(self) -> None:
        if self._designer_stack.currentIndex() == 0:
            self._designer_env.fit_view()
        else:
            self._designer_a4.fit_view()

    def _on_designer_mode_changed(self, index: int) -> None:
        self._designer_stack.setCurrentIndex(index)
        if index == 0:
            self._designer_env.fit_view()
        else:
            self._designer_a4.fit_view()

    def _load_template_from_db(self) -> None:
        self._loading_template = True
        try:
            t = self._db.get_template(TEMPLATE_ENVELOPE)
            if t:
                self._designer_env.load_layout_json(t.layout_json)
            else:
                self._designer_env.load_layout_json(default_layout())
            t4 = self._db.get_template(TEMPLATE_A4)
            if t4:
                self._designer_a4.load_layout_json(t4.layout_json)
            else:
                self._designer_a4.load_layout_json(default_a4_layout())
            self._dirty_envelope = False
            self._dirty_a4 = False
        finally:
            self._loading_template = False
        self._designer_env.fit_view()
        self._designer_a4.fit_view()

    def _save_envelope_template(self) -> None:
        self._db.upsert_template(TEMPLATE_ENVELOPE, self._designer_env.layout_json())
        self._dirty_envelope = False
        self.statusBar().showMessage("Envelope template saved.", 4000)

    def _save_a4_template(self) -> None:
        self._db.upsert_template(TEMPLATE_A4, self._designer_a4.layout_json())
        self._dirty_a4 = False
        self.statusBar().showMessage("A4 template saved.", 4000)

    def _delete_envelope_template(self) -> None:
        if (
            QMessageBox.question(
                self,
                "Delete envelope template",
                "Remove the saved envelope layout from the database and reset the canvas to the default "
                "starting layout?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self._db.delete_template(TEMPLATE_ENVELOPE)
        self._preview_backup_env = []
        self._loading_template = True
        try:
            self._designer_env.load_layout_json(default_layout())
        finally:
            self._loading_template = False
        self._dirty_envelope = False
        self._designer_env.fit_view()
        if self._preview_check.isChecked():
            self._apply_preview()
        self.statusBar().showMessage("Envelope template deleted; reset to default.", 5000)

    def _delete_a4_template(self) -> None:
        if (
            QMessageBox.question(
                self,
                "Delete A4 template",
                "Remove the saved A4 layout from the database and reset the canvas to the default "
                "starting layout?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self._db.delete_template(TEMPLATE_A4)
        self._preview_backup_a4 = []
        self._loading_template = True
        try:
            self._designer_a4.load_layout_json(default_a4_layout())
        finally:
            self._loading_template = False
        self._dirty_a4 = False
        self._designer_a4.fit_view()
        if self._preview_check.isChecked():
            self._apply_preview()
        self.statusBar().showMessage("A4 template deleted; reset to default.", 5000)

    def _reload_batches(self) -> None:
        self._batch_combo.blockSignals(True)
        self._print_batch.blockSignals(True)
        self._batch_combo.clear()
        self._print_batch.clear()
        batches = self._db.list_batches()
        for b in batches:
            label = f"{b.name}  ·  {b.row_count} rows  ·  #{b.id}"
            self._batch_combo.addItem(label, b.id)
            self._print_batch.addItem(label, b.id)
        self._batch_combo.blockSignals(False)
        self._print_batch.blockSignals(False)
        if batches:
            self._batch_combo.setCurrentIndex(0)
            self._print_batch.setCurrentIndex(0)
        self._on_batch_changed()

    def _on_batch_changed(self) -> None:
        bid = self._batch_combo.currentData()
        if bid is None:
            self._table.clear()
            self._table.setRowCount(0)
            self._table.setColumnCount(0)
            self._preview_row_spin.setMaximum(1)
            self._designer_env.set_column_keys([])
            self._designer_a4.set_column_keys([])
            self._apply_preview()
            return
        rows = self._db.get_records(int(bid))
        if not rows:
            self._table.clear()
            self._table.setRowCount(0)
            self._table.setColumnCount(0)
            self._preview_row_spin.setMaximum(1)
            self._designer_env.set_column_keys([])
            self._designer_a4.set_column_keys([])
            self._apply_preview()
            return
        keys: list[str] = list(rows[0].payload.keys())
        self._designer_env.set_column_keys(keys)
        self._designer_a4.set_column_keys(keys)
        self._table.setRowCount(len(rows))
        self._table.setColumnCount(len(keys))
        self._table.setHorizontalHeaderLabels(keys)
        for r, row in enumerate(rows):
            for c, k in enumerate(keys):
                v = row.payload.get(k, "")
                self._table.setItem(r, c, QTableWidgetItem("" if v is None else str(v)))
        self._fit_data_table_columns()
        self._preview_row_spin.setMaximum(len(rows))
        self._preview_row_spin.setValue(1)
        self._apply_preview()

    def _on_data_table_context_menu(self, pos: QPoint) -> None:
        it = self._table.itemAt(pos)
        if it is None:
            return
        row = it.row()
        menu = QMenu(self)
        act_cell = menu.addAction("Copy cell")
        act_row = menu.addAction("Copy row (tab-separated)")
        global_pos = self._table.viewport().mapToGlobal(pos)
        chosen = menu.exec(global_pos)
        if chosen is None:
            return
        if chosen == act_cell:
            QApplication.clipboard().setText(it.text())
            self.statusBar().showMessage("Copied cell", 2000)
            return
        if chosen == act_row:
            parts: list[str] = []
            for c in range(self._table.columnCount()):
                cell = self._table.item(row, c)
                parts.append(cell.text() if cell else "")
            QApplication.clipboard().setText("\t".join(parts))
            self.statusBar().showMessage("Copied row", 2000)

    def _fit_data_table_columns(self) -> None:
        cols = self._table.columnCount()
        if cols == 0:
            return
        self._table.setUpdatesEnabled(False)
        try:
            for c in range(cols):
                self._table.resizeColumnToContents(c)
                w = self._table.columnWidth(c)
                self._table.setColumnWidth(c, max(_DATA_COL_MIN, min(w + 24, _DATA_COL_MAX)))
        finally:
            self._table.setUpdatesEnabled(True)

    def _current_preview_row(self) -> dict[str, Any] | None:
        bid = self._batch_combo.currentData()
        if bid is None:
            return None
        rows = self._db.get_records(int(bid))
        if not rows:
            return None
        idx = max(1, min(self._preview_row_spin.value(), len(rows))) - 1
        return rows[idx].payload

    def _apply_preview(self) -> None:
        if self._preview_check.isChecked():
            row = self._current_preview_row()
            if row is None:
                return
            if not self._preview_backup_env:
                self._preview_backup_env = self._designer_env.snapshot_texts()
            if not self._preview_backup_a4:
                self._preview_backup_a4 = self._designer_a4.snapshot_texts()
            self._designer_env.preview_merge(row)
            self._designer_a4.preview_merge(row)
        else:
            if self._preview_backup_env:
                self._designer_env.restore_templates_after_preview(self._preview_backup_env)
                self._preview_backup_env = []
            if self._preview_backup_a4:
                self._designer_a4.restore_templates_after_preview(self._preview_backup_a4)
                self._preview_backup_a4 = []

    def _import_records_from_path(self, path: Path) -> None:
        try:
            records = load_records_file(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Import failed", str(e))
            return
        if not records:
            QMessageBox.warning(self, "Import", "No data rows found in that file.")
            return
        name = path.stem
        self._db.create_batch_from_records(name, records)
        self._reload_batches()
        self.statusBar().showMessage(f"Imported {len(records)} rows from {path}", 5000)

    def _import_records(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import mailing list",
            str(Path.home()),
            "CSV (*.csv);;JSON (*.json);;All files (*.*)",
        )
        if not path:
            return
        self._import_records_from_path(Path(path))

    @staticmethod
    def _first_csv_json_path(mime: QMimeData) -> Path | None:
        if not mime.hasUrls():
            return None
        for u in mime.urls():
            if u.isLocalFile():
                p = Path(u.toLocalFile())
                if p.suffix.lower() in (".csv", ".json"):
                    return p
        return None

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        # Only handle DnD — do not forward every QEvent through super(); that can crash on macOS/Qt.
        t = event.type()
        if t not in (
            QEvent.Type.DragEnter,
            QEvent.Type.DragMove,
            QEvent.Type.Drop,
        ):
            return False
        if not isinstance(obj, QWidget) or not self.isAncestorOf(obj):
            return False
        if t == QEvent.Type.DragEnter and isinstance(event, QDragEnterEvent):
            p = self._first_csv_json_path(event.mimeData())
            if p is not None:
                event.acceptProposedAction()
                return True
            return False
        if t == QEvent.Type.DragMove and isinstance(event, QDragMoveEvent):
            p = self._first_csv_json_path(event.mimeData())
            if p is not None:
                event.acceptProposedAction()
                return True
            return False
        if t == QEvent.Type.Drop and isinstance(event, QDropEvent):
            p = self._first_csv_json_path(event.mimeData())
            if p is not None:
                self._import_records_from_path(p)
                event.acceptProposedAction()
                return True
            return False
        return False

    def _delete_batch(self) -> None:
        bid = self._batch_combo.currentData()
        if bid is None:
            return
        if (
            QMessageBox.question(
                self,
                "Delete list",
                "Remove this list from the database?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self._db.delete_batch(int(bid))
        self._reload_batches()

    def _ensure_layout_saved_for_kind(self, kind: str) -> bool:
        if kind == "a4":
            if not self._dirty_a4:
                return True
            msg = "Save your A4 layout before continuing?"
        else:
            if not self._dirty_envelope:
                return True
            msg = "Save your envelope layout before continuing?"
        m = QMessageBox.question(
            self,
            "Unsaved layout",
            msg,
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Cancel
            | QMessageBox.StandardButton.Discard,
        )
        if m == QMessageBox.StandardButton.Save:
            if kind == "a4":
                self._db.upsert_template(TEMPLATE_A4, self._designer_a4.layout_json())
                self._dirty_a4 = False
            else:
                self._db.upsert_template(TEMPLATE_ENVELOPE, self._designer_env.layout_json())
                self._dirty_envelope = False
            return True
        if m == QMessageBox.StandardButton.Cancel:
            return False
        return True

    def _export_pdf(self) -> None:
        bid = self._print_batch.currentData()
        if bid is None:
            QMessageBox.information(self, "Export PDF", "Import a list first.")
            return
        records = [r.payload for r in self._db.get_records(int(bid))]
        if not records:
            QMessageBox.information(self, "Export PDF", "No rows to export.")
            return
        kind = str(self._print_layout_combo.currentData() or "envelope")
        if not self._ensure_layout_saved_for_kind(kind):
            return
        layout_json = (
            self._designer_a4.layout_json() if kind == "a4" else self._designer_env.layout_json()
        )
        default_name = "letters-a4.pdf" if kind == "a4" else "envelopes.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export PDF",
            str(Path.home() / default_name),
            "PDF (*.pdf)",
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            export_pdf(path, layout_json, records)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Export failed", str(e))
            return
        self.statusBar().showMessage(f"Saved PDF: {path}", 6000)

    def _export_one_page_pdf(self, *, kind: str, row: dict[str, Any]) -> None:
        """Write a single-page PDF using the current saved layout for envelope or A4."""
        if not self._ensure_layout_saved_for_kind(kind):
            return
        layout_json = (
            self._designer_a4.layout_json() if kind == "a4" else self._designer_env.layout_json()
        )
        default_name = "a4-sample.pdf" if kind == "a4" else "envelope-sample.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export sample PDF (one page)",
            str(Path.home() / default_name),
            "PDF (*.pdf)",
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            export_pdf(path, layout_json, [row])
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Export failed", str(e))
            return
        self.statusBar().showMessage(f"Saved sample PDF (1 page): {path}", 6000)

    def _export_sample_pdf_from_designer(self) -> None:
        """Uses Design for (#10 vs A4) and the preview row when a list is loaded."""
        kind = str(self._designer_mode.currentData() or "envelope")
        row = self._current_preview_row() or {}
        self._export_one_page_pdf(kind=kind, row=row)

    def _export_sample_pdf_from_print_page(self) -> None:
        """Uses Print tab layout and the first row of the selected batch."""
        bid = self._print_batch.currentData()
        if bid is None:
            QMessageBox.information(
                self,
                "Sample PDF",
                "Select a mailing list first (or use Sample PDF on the Designer tab for a blank merge).",
            )
            return
        records = [r.payload for r in self._db.get_records(int(bid))]
        if not records:
            QMessageBox.information(self, "Sample PDF", "That list has no rows to merge.")
            return
        kind = str(self._print_layout_combo.currentData() or "envelope")
        self._export_one_page_pdf(kind=kind, row=records[0])

    def _print_bulk(self, *, show_dialog: bool = True) -> None:
        bid = self._print_batch.currentData()
        if bid is None:
            QMessageBox.information(self, "Print", "Import a CSV (or JSON) list first.")
            return
        records = [r.payload for r in self._db.get_records(int(bid))]
        if not records:
            QMessageBox.information(self, "Print", "No rows to print.")
            return
        kind = str(self._print_layout_combo.currentData() or "envelope")
        if not self._ensure_layout_saved_for_kind(kind):
            return
        layout_json = (
            self._designer_a4.layout_json() if kind == "a4" else self._designer_env.layout_json()
        )
        ok = print_records(self, layout_json, records, show_dialog=show_dialog)
        if ok:
            self.statusBar().showMessage("Print job sent.", 4000)

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "About Envelope Studio",
            f"Version {VERSION}\n\n"
            "Design US #10 envelope or A4 letter layouts with CSV mail merge — all data stays on this computer.\n\n"
            f"{APP_CREDIT}.\n\n"
            "Merge fields use curly braces matching your column headers, e.g. {name}, {tracking_number}.",
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        app = QApplication.instance()
        if app is not None and self._app_drop_filter_installed:
            app.removeEventFilter(self)
            self._app_drop_filter_installed = False
        if self._dirty_envelope or self._dirty_a4:
            r = QMessageBox.question(
                self,
                "Quit",
                "Save layout changes before quitting?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Cancel
                | QMessageBox.StandardButton.Discard,
            )
            if r == QMessageBox.StandardButton.Save:
                if self._dirty_envelope:
                    self._db.upsert_template(TEMPLATE_ENVELOPE, self._designer_env.layout_json())
                if self._dirty_a4:
                    self._db.upsert_template(TEMPLATE_A4, self._designer_a4.layout_json())
            elif r == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
        super().closeEvent(event)
