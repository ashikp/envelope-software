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
    QScrollArea,
    QSizePolicy,
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
from envelope_app.layout import (
    LAYOUT_KIND_A4,
    LAYOUT_KIND_ENVELOPE,
    LAYOUT_KIND_US_LETTER,
    LABEL_DT_THERMAL_ID,
    default_a4_layout,
    default_layout,
    default_thermal_label_layout,
    default_us_letter_layout,
)
from envelope_app.printing import export_pdf, print_records
from envelope_app.ui.designer_widget import DesignerWidget

TEMPLATE_ENVELOPE = "default"
TEMPLATE_A4 = "a4"
TEMPLATE_US_LETTER = "us_letter"
TEMPLATE_THERMAL_LABEL = "thermal_label"

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
        self.setMinimumSize(880, 560)
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

        self._preview_check = QCheckBox("Preview live merge (all layouts)")
        self._preview_check.setChecked(False)
        self._preview_check.toggled.connect(self._apply_preview)

        self._loading_template = False
        self._designer_env = DesignerWidget()
        self._designer_a4 = DesignerWidget(layout_kind=LAYOUT_KIND_A4)
        self._designer_letter = DesignerWidget(layout_kind=LAYOUT_KIND_US_LETTER)
        self._designer_thermal = DesignerWidget(
            layout_kind=LAYOUT_KIND_ENVELOPE,
            envelope_size_id=LABEL_DT_THERMAL_ID,
            lock_envelope_size=True,
        )
        self._designer_env.layout_changed.connect(self._mark_dirty_envelope)
        self._designer_a4.layout_changed.connect(self._mark_dirty_a4)
        self._designer_letter.layout_changed.connect(self._mark_dirty_letter)
        self._designer_thermal.layout_changed.connect(self._mark_dirty_thermal)
        self._designer_env.shortcode_copied.connect(self._on_shortcode_copied)
        self._designer_a4.shortcode_copied.connect(self._on_shortcode_copied)
        self._designer_letter.shortcode_copied.connect(self._on_shortcode_copied)
        self._designer_thermal.shortcode_copied.connect(self._on_shortcode_copied)

        self._dirty_envelope = False
        self._dirty_a4 = False
        self._dirty_letter = False
        self._dirty_thermal = False
        self._preview_backup_env: list[tuple[str, str]] = []
        self._preview_backup_a4: list[tuple[str, str]] = []
        self._preview_backup_letter: list[tuple[str, str]] = []
        self._preview_backup_thermal: list[tuple[str, str]] = []

        # —— Data page
        data_page = QWidget()
        data_page.setObjectName("page")
        d_root = QVBoxLayout(data_page)
        d_root.setContentsMargins(14, 10, 14, 10)
        d_root.setSpacing(12)

        d_root.addWidget(
            _page_header(
                "Mail data",
                "Import a CSV file (first row = column headers). Each header becomes a merge field "
                "like {name} or {tracking_number}. JSON is also supported if needed.",
            )
        )

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

        # —— Designer page: stacked canvases only (saves in left app sidebar; block tools on the right in DesignerWidget)
        designer_page = QWidget()
        designer_page.setObjectName("page")
        z_root = QVBoxLayout(designer_page)
        z_root.setContentsMargins(4, 2, 4, 2)
        z_root.setSpacing(0)

        self._btn_save_env = QPushButton("Save envelope")
        self._btn_save_env.setObjectName("primary")
        self._btn_save_env.setMinimumHeight(36)
        self._btn_save_env.clicked.connect(self._save_envelope_template)
        self._btn_save_a4 = QPushButton("Save A4")
        self._btn_save_a4.setObjectName("primary")
        self._btn_save_a4.setMinimumHeight(36)
        self._btn_save_a4.clicked.connect(self._save_a4_template)
        self._btn_save_letter = QPushButton("Save US Letter")
        self._btn_save_letter.setObjectName("primary")
        self._btn_save_letter.setMinimumHeight(36)
        self._btn_save_letter.clicked.connect(self._save_us_letter_template)
        self._btn_fit = QPushButton("Fit view")
        self._btn_fit.setMinimumHeight(34)
        self._btn_fit.clicked.connect(self._fit_active_designer)
        self._btn_sample_pdf = QPushButton("Sample PDF…")
        self._btn_sample_pdf.setMinimumHeight(34)
        self._btn_sample_pdf.setToolTip(
            "Export a single-page PDF for sharing. If a list is loaded, uses the preview row; "
            "otherwise merge fields are left empty."
        )
        self._btn_sample_pdf.clicked.connect(self._export_sample_pdf_from_designer)

        self._btn_del_env = QPushButton("Delete envelope…")
        self._btn_del_env.setObjectName("danger")
        self._btn_del_env.setMinimumHeight(32)
        self._btn_del_env.clicked.connect(self._delete_envelope_template)
        self._btn_del_a4 = QPushButton("Delete A4…")
        self._btn_del_a4.setObjectName("danger")
        self._btn_del_a4.setMinimumHeight(32)
        self._btn_del_a4.clicked.connect(self._delete_a4_template)
        self._btn_del_letter = QPushButton("Delete US Letter…")
        self._btn_del_letter.setObjectName("danger")
        self._btn_del_letter.setMinimumHeight(32)
        self._btn_del_letter.clicked.connect(self._delete_us_letter_template)
        self._btn_save_thermal = QPushButton("Save thermal label")
        self._btn_save_thermal.setObjectName("primary")
        self._btn_save_thermal.setMinimumHeight(36)
        self._btn_save_thermal.clicked.connect(self._save_thermal_template)
        self._btn_del_thermal = QPushButton("Delete thermal layout…")
        self._btn_del_thermal.setObjectName("danger")
        self._btn_del_thermal.setMinimumHeight(32)
        self._btn_del_thermal.clicked.connect(self._delete_thermal_template)

        self._designer_mode = QComboBox()
        self._designer_mode.setObjectName("designerModeCombo")
        self._designer_mode.addItem("US #10 envelope", "envelope")
        self._designer_mode.addItem("A4 letter", "a4")
        self._designer_mode.addItem("US Letter (8.5 × 11 in)", "us_letter")
        self._designer_mode.addItem("2.625 × 1 in Direct Thermal", "thermal_label")
        self._designer_mode.currentIndexChanged.connect(self._on_designer_mode_changed)

        self._designer_stack = QStackedWidget()
        self._designer_stack.addWidget(self._designer_env)
        self._designer_stack.addWidget(self._designer_a4)
        self._designer_stack.addWidget(self._designer_letter)
        self._designer_stack.addWidget(self._designer_thermal)
        self._designer_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        z_root.addWidget(self._designer_stack, stretch=1)

        # —— Left sidebar: stacked tool panels (Data / Designer / Print)
        data_sidebar_page = QWidget()
        dsl = QVBoxLayout(data_sidebar_page)
        dsl.setContentsMargins(4, 0, 4, 0)
        dsl.setSpacing(10)
        ds_title = QLabel("Import & lists")
        ds_title.setObjectName("cardTitle")
        dsl.addWidget(ds_title)
        lab_list = QLabel("Active list")
        lab_list.setObjectName("fieldLabel")
        dsl.addWidget(lab_list)
        dsl.addWidget(self._batch_combo)
        self._btn_import_data = QPushButton("Import CSV…")
        self._btn_import_data.setObjectName("primary")
        self._btn_import_data.setMinimumHeight(38)
        self._btn_import_data.clicked.connect(self._import_records)
        dsl.addWidget(self._btn_import_data)
        self._btn_remove_batch = QPushButton("Remove list")
        self._btn_remove_batch.setObjectName("danger")
        self._btn_remove_batch.setMinimumHeight(34)
        self._btn_remove_batch.clicked.connect(self._delete_batch)
        dsl.addWidget(self._btn_remove_batch)
        dsl.addStretch(1)

        designer_sidebar_page = QWidget()
        dsz = QVBoxLayout(designer_sidebar_page)
        dsz.setContentsMargins(4, 0, 4, 0)
        dsz.setSpacing(8)
        side_title = QLabel("Layouts")
        side_title.setObjectName("cardTitle")
        dsz.addWidget(side_title)
        side_hint = QLabel(
            "Pick a layout below; each has its own save slot. Thermal uses fixed 2.625″×1″ label stock "
            "(envelope picker is for #10 layouts only)."
        )
        side_hint.setObjectName("hint")
        side_hint.setWordWrap(True)
        dsz.addWidget(side_hint)
        ml = QLabel("Design for")
        ml.setObjectName("fieldLabel")
        dsz.addWidget(ml)
        dsz.addWidget(self._designer_mode)
        dsz.addSpacing(4)
        dsz.addWidget(self._btn_save_env)
        dsz.addWidget(self._btn_save_a4)
        dsz.addWidget(self._btn_save_letter)
        dsz.addWidget(self._btn_save_thermal)
        row_fit_sample = QHBoxLayout()
        row_fit_sample.setSpacing(6)
        row_fit_sample.addWidget(self._btn_fit, stretch=1)
        row_fit_sample.addWidget(self._btn_sample_pdf, stretch=1)
        dsz.addLayout(row_fit_sample)
        dsz.addSpacing(2)
        dsz.addWidget(self._btn_del_env)
        dsz.addWidget(self._btn_del_a4)
        dsz.addWidget(self._btn_del_letter)
        dsz.addWidget(self._btn_del_thermal)
        dsz.addSpacing(4)
        dsz.addWidget(self._preview_check)
        pr = QLabel("Preview row")
        pr.setObjectName("fieldLabel")
        dsz.addWidget(pr)
        dsz.addWidget(self._preview_row_spin)
        dsz.addStretch(1)

        print_sidebar_page = QWidget()
        ppl = QVBoxLayout(print_sidebar_page)
        ppl.setContentsMargins(4, 0, 4, 0)
        ppl.setSpacing(10)
        pst = QLabel("Print & export")
        pst.setObjectName("cardTitle")
        ppl.addWidget(pst)
        self._print_batch = QComboBox()
        plab = QLabel("List")
        plab.setObjectName("fieldLabel")
        ppl.addWidget(plab)
        ppl.addWidget(self._print_batch)
        lay_lab = QLabel("Layout")
        lay_lab.setObjectName("fieldLabel")
        ppl.addWidget(lay_lab)
        self._print_layout_combo = QComboBox()
        self._print_layout_combo.setObjectName("printLayoutCombo")
        self._print_layout_combo.addItem("US #10 envelope", "envelope")
        self._print_layout_combo.addItem("2.625 × 1 in Direct Thermal", "thermal_label")
        self._print_layout_combo.addItem("US Letter (8.5 × 11 in)", "us_letter")
        self._print_layout_combo.addItem("A4 letter", "a4")
        ppl.addWidget(self._print_layout_combo)
        btn_pdf = QPushButton("Export PDF…")
        btn_pdf.setMinimumHeight(40)
        btn_pdf.clicked.connect(self._export_pdf)
        ppl.addWidget(btn_pdf)
        btn_sample = QPushButton("Sample PDF (1 page)…")
        btn_sample.setMinimumHeight(40)
        btn_sample.setToolTip(
            "Save one merged page as a PDF using the first row of the selected list (for proofs or email samples)."
        )
        btn_sample.clicked.connect(self._export_sample_pdf_from_print_page)
        ppl.addWidget(btn_sample)
        btn_print = QPushButton("Print all…")
        btn_print.setObjectName("primary")
        btn_print.setMinimumHeight(42)
        btn_print.clicked.connect(self._print_bulk)
        ppl.addWidget(btn_print)
        ph = QLabel(
            "Export PDF writes every row. Sample PDF is one proof page. Page size follows the saved layout."
        )
        ph.setObjectName("hint")
        ph.setWordWrap(True)
        ppl.addWidget(ph)
        ppl.addStretch(1)

        # —— Print page: center is open; use the left sidebar for actions
        print_page = QWidget()
        print_page.setObjectName("page")
        p_root = QVBoxLayout(print_page)
        p_root.setContentsMargins(14, 10, 14, 10)
        p_root.setSpacing(12)
        p_idle = QLabel(
            "Use the left sidebar to pick a list, choose envelope / US Letter / A4 layout, then export or print."
        )
        p_idle.setObjectName("pageDesc")
        p_idle.setWordWrap(True)
        p_root.addWidget(p_idle)
        p_root.addStretch(1)

        # —— Shell: sidebar + stack
        shell = QWidget()
        shell.setObjectName("centralShell")
        shell_l = QHBoxLayout(shell)
        shell_l.setContentsMargins(0, 0, 0, 0)
        shell_l.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(300)
        sb_l = QVBoxLayout(sidebar)
        sb_l.setContentsMargins(14, 18, 12, 16)
        sb_l.setSpacing(4)

        brand = QLabel("Envelope Studio")
        brand.setObjectName("brandTitle")
        sub = QLabel("Local mail merge")
        sub.setObjectName("brandSub")
        sb_l.addWidget(brand)
        sb_l.addWidget(sub)
        sb_l.addSpacing(12)

        self._nav = QListWidget()
        self._nav.setObjectName("navList")
        self._nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for label, tip in (
            ("Data", "Import and browse lists"),
            ("Designer", "Edit layouts"),
            ("Print", "Export PDF and print"),
        ):
            it = QListWidgetItem(label)
            it.setToolTip(tip)
            self._nav.addItem(it)
        self._nav.setCurrentRow(0)
        self._nav.setFrameShape(QFrame.Shape.NoFrame)
        self._nav.currentRowChanged.connect(self._on_nav_changed)
        sb_l.addWidget(self._nav, stretch=1)

        self._sidebar_stack = QStackedWidget()
        self._sidebar_stack.addWidget(data_sidebar_page)
        self._sidebar_stack.addWidget(designer_sidebar_page)
        self._sidebar_stack.addWidget(print_sidebar_page)

        self._sidebar_action_scroll = QScrollArea()
        self._sidebar_action_scroll.setObjectName("appSidebarActionsScroll")
        self._sidebar_action_scroll.setWidgetResizable(True)
        self._sidebar_action_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._sidebar_action_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._sidebar_action_scroll.setWidget(self._sidebar_stack)
        sb_l.addWidget(self._sidebar_action_scroll, stretch=2)

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
            self._sidebar_stack.setCurrentIndex(row)

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

    def _mark_dirty_letter(self) -> None:
        if self._loading_template:
            return
        self._dirty_letter = True

    def _mark_dirty_thermal(self) -> None:
        if self._loading_template:
            return
        self._dirty_thermal = True

    def _layout_json_for_kind(self, kind: str) -> str:
        if kind == "a4":
            return self._designer_a4.layout_json()
        if kind == "us_letter":
            return self._designer_letter.layout_json()
        if kind == "thermal_label":
            return self._designer_thermal.layout_json()
        return self._designer_env.layout_json()

    def _on_shortcode_copied(self, text: str) -> None:
        self.statusBar().showMessage(
            f"Copied {text} — paste into the merge template below", 4000
        )

    def _fit_active_designer(self) -> None:
        idx = self._designer_stack.currentIndex()
        if idx == 0:
            self._designer_env.fit_view()
        elif idx == 1:
            self._designer_a4.fit_view()
        elif idx == 2:
            self._designer_letter.fit_view()
        else:
            self._designer_thermal.fit_view()

    def _on_designer_mode_changed(self, index: int) -> None:
        self._designer_stack.setCurrentIndex(index)
        if index == 0:
            self._designer_env.fit_view()
        elif index == 1:
            self._designer_a4.fit_view()
        elif index == 2:
            self._designer_letter.fit_view()
        else:
            self._designer_thermal.fit_view()

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
            tl = self._db.get_template(TEMPLATE_US_LETTER)
            if tl:
                self._designer_letter.load_layout_json(tl.layout_json)
            else:
                self._designer_letter.load_layout_json(default_us_letter_layout())
            tt = self._db.get_template(TEMPLATE_THERMAL_LABEL)
            if tt:
                self._designer_thermal.load_layout_json(tt.layout_json)
            else:
                self._designer_thermal.load_layout_json(default_thermal_label_layout())
            self._dirty_envelope = False
            self._dirty_a4 = False
            self._dirty_letter = False
            self._dirty_thermal = False
        finally:
            self._loading_template = False
        self._designer_env.fit_view()
        self._designer_a4.fit_view()
        self._designer_letter.fit_view()
        self._designer_thermal.fit_view()

    def _save_envelope_template(self) -> None:
        self._db.upsert_template(TEMPLATE_ENVELOPE, self._designer_env.layout_json())
        self._dirty_envelope = False
        self.statusBar().showMessage("Envelope template saved.", 4000)

    def _save_a4_template(self) -> None:
        self._db.upsert_template(TEMPLATE_A4, self._designer_a4.layout_json())
        self._dirty_a4 = False
        self.statusBar().showMessage("A4 template saved.", 4000)

    def _save_us_letter_template(self) -> None:
        self._db.upsert_template(TEMPLATE_US_LETTER, self._designer_letter.layout_json())
        self._dirty_letter = False
        self.statusBar().showMessage("US Letter template saved.", 4000)

    def _save_thermal_template(self) -> None:
        self._db.upsert_template(TEMPLATE_THERMAL_LABEL, self._designer_thermal.layout_json())
        self._dirty_thermal = False
        self.statusBar().showMessage("Direct thermal template saved.", 4000)

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

    def _delete_us_letter_template(self) -> None:
        if (
            QMessageBox.question(
                self,
                "Delete US Letter template",
                "Remove the saved US Letter layout from the database and reset the canvas to the default "
                "starting layout?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self._db.delete_template(TEMPLATE_US_LETTER)
        self._preview_backup_letter = []
        self._loading_template = True
        try:
            self._designer_letter.load_layout_json(default_us_letter_layout())
        finally:
            self._loading_template = False
        self._dirty_letter = False
        self._designer_letter.fit_view()
        if self._preview_check.isChecked():
            self._apply_preview()
        self.statusBar().showMessage("US Letter template deleted; reset to default.", 5000)

    def _delete_thermal_template(self) -> None:
        if (
            QMessageBox.question(
                self,
                "Delete thermal label template",
                "Remove the saved 2.625″ × 1″ direct thermal layout from the database and reset to "
                "the default starting layout?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self._db.delete_template(TEMPLATE_THERMAL_LABEL)
        self._preview_backup_thermal = []
        self._loading_template = True
        try:
            self._designer_thermal.load_layout_json(default_thermal_label_layout())
        finally:
            self._loading_template = False
        self._dirty_thermal = False
        self._designer_thermal.fit_view()
        if self._preview_check.isChecked():
            self._apply_preview()
        self.statusBar().showMessage("Thermal label template deleted; reset to default.", 5000)

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
            self._designer_letter.set_column_keys([])
            self._designer_thermal.set_column_keys([])
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
            self._designer_letter.set_column_keys([])
            self._designer_thermal.set_column_keys([])
            self._apply_preview()
            return
        keys: list[str] = list(rows[0].payload.keys())
        self._designer_env.set_column_keys(keys)
        self._designer_a4.set_column_keys(keys)
        self._designer_letter.set_column_keys(keys)
        self._designer_thermal.set_column_keys(keys)
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
            if not self._preview_backup_letter:
                self._preview_backup_letter = self._designer_letter.snapshot_texts()
            if not self._preview_backup_thermal:
                self._preview_backup_thermal = self._designer_thermal.snapshot_texts()
            self._designer_env.preview_merge(row)
            self._designer_a4.preview_merge(row)
            self._designer_letter.preview_merge(row)
            self._designer_thermal.preview_merge(row)
        else:
            if self._preview_backup_env:
                self._designer_env.restore_templates_after_preview(self._preview_backup_env)
                self._preview_backup_env = []
            if self._preview_backup_a4:
                self._designer_a4.restore_templates_after_preview(self._preview_backup_a4)
                self._preview_backup_a4 = []
            if self._preview_backup_letter:
                self._designer_letter.restore_templates_after_preview(self._preview_backup_letter)
                self._preview_backup_letter = []
            if self._preview_backup_thermal:
                self._designer_thermal.restore_templates_after_preview(self._preview_backup_thermal)
                self._preview_backup_thermal = []

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
            dirty = self._dirty_a4
            msg = "Save your A4 layout before continuing?"
        elif kind == "us_letter":
            dirty = self._dirty_letter
            msg = "Save your US Letter layout before continuing?"
        elif kind == "thermal_label":
            dirty = self._dirty_thermal
            msg = "Save your direct thermal label layout before continuing?"
        else:
            dirty = self._dirty_envelope
            msg = "Save your envelope layout before continuing?"
        if not dirty:
            return True
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
            elif kind == "us_letter":
                self._db.upsert_template(TEMPLATE_US_LETTER, self._designer_letter.layout_json())
                self._dirty_letter = False
            elif kind == "thermal_label":
                self._db.upsert_template(TEMPLATE_THERMAL_LABEL, self._designer_thermal.layout_json())
                self._dirty_thermal = False
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
        layout_json = self._layout_json_for_kind(kind)
        if kind == "a4":
            default_name = "letters-a4.pdf"
        elif kind == "us_letter":
            default_name = "letters-us-letter.pdf"
        elif kind == "thermal_label":
            default_name = "thermal-labels.pdf"
        else:
            default_name = "envelopes.pdf"
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
        """Write a single-page PDF using the current saved layout for envelope, A4, or US Letter."""
        if not self._ensure_layout_saved_for_kind(kind):
            return
        layout_json = self._layout_json_for_kind(kind)
        if kind == "a4":
            default_name = "a4-sample.pdf"
        elif kind == "us_letter":
            default_name = "us-letter-sample.pdf"
        elif kind == "thermal_label":
            default_name = "thermal-label-sample.pdf"
        else:
            default_name = "envelope-sample.pdf"
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
        layout_json = self._layout_json_for_kind(kind)
        ok = print_records(self, layout_json, records, show_dialog=show_dialog)
        if ok:
            self.statusBar().showMessage("Print job sent.", 4000)

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "About Envelope Studio",
            f"Version {VERSION}\n\n"
            "Design envelope, US Letter, or A4 layouts with CSV mail merge — all data stays on this computer.\n\n"
            f"{APP_CREDIT}.\n\n"
            "Merge fields use curly braces matching your column headers, e.g. {name}, {tracking_number}.",
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        app = QApplication.instance()
        if app is not None and self._app_drop_filter_installed:
            app.removeEventFilter(self)
            self._app_drop_filter_installed = False
        if self._dirty_envelope or self._dirty_a4 or self._dirty_letter or self._dirty_thermal:
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
                if self._dirty_letter:
                    self._db.upsert_template(TEMPLATE_US_LETTER, self._designer_letter.layout_json())
                if self._dirty_thermal:
                    self._db.upsert_template(TEMPLATE_THERMAL_LABEL, self._designer_thermal.layout_json())
            elif r == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
        super().closeEvent(event)
