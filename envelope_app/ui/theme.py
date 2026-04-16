"""Application-wide visual theme (Qt Style Sheets + Fusion)."""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication


def apply_app_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    f = QFont()
    # Use a real system default — avoids Qt warnings for missing "SF Pro Text" on some Macs.
    default = QFont().defaultFamily() or "Segoe UI"
    if hasattr(f, "setFamilies"):
        f.setFamilies([default, "Segoe UI", "Helvetica Neue", "Arial", "sans-serif"])
    else:
        f.setFamily(default)
    f.setPixelSize(13)
    app.setFont(f)
    app.setStyleSheet(APP_STYLESHEET)


# Palette: slate sidebar, cool gray chrome, indigo accent (professional / “product” feel)
APP_STYLESHEET = """
QMainWindow {
    background: #f1f5f9;
}
QWidget#centralShell {
    background: #f1f5f9;
}
QFrame#sidebar {
    background: #0f172a;
    border: none;
}
QLabel#brandTitle {
    color: #f8fafc;
    font-size: 17px;
    font-weight: 700;
    letter-spacing: -0.3px;
}
QLabel#brandSub {
    color: #94a3b8;
    font-size: 11px;
    font-weight: 400;
}
QListWidget#navList {
    background: transparent;
    color: #e2e8f0;
    border: none;
    outline: none;
    padding: 8px 0;
}
QListWidget#navList::item {
    padding: 12px 16px 12px 20px;
    margin: 2px 8px;
    border-radius: 8px;
    border-left: 3px solid transparent;
}
QListWidget#navList::item:hover {
    background: #1e293b;
}
QListWidget#navList::item:selected {
    background: #1e3a5f;
    color: #f8fafc;
    border-left: 3px solid #6366f1;
}
QStackedWidget#stack {
    background: #f1f5f9;
}
QFrame#page {
    background: transparent;
}
QLabel#pageTitle {
    font-size: 22px;
    font-weight: 700;
    color: #0f172a;
    letter-spacing: -0.4px;
}
QLabel#pageDesc {
    font-size: 13px;
    color: #64748b;
    margin-bottom: 4px;
}
QFrame#card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
}
QFrame#cardHeader {
    background: transparent;
    border: none;
    border-bottom: 1px solid #f1f5f9;
    padding-bottom: 2px;
}
QLabel#cardTitle {
    font-size: 13px;
    font-weight: 600;
    color: #334155;
}
QLabel#fieldLabel {
    font-size: 12px;
    font-weight: 500;
    color: #64748b;
}
QPushButton {
    background: #ffffff;
    color: #334155;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 8px 16px;
    min-height: 20px;
    font-weight: 500;
}
QPushButton:hover {
    background: #f8fafc;
    border-color: #94a3b8;
}
QPushButton:pressed {
    background: #f1f5f9;
}
QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #4f46e5, stop:1 #4338ca);
    color: #ffffff;
    border: none;
    font-weight: 600;
}
QPushButton#primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #6366f1, stop:1 #4f46e5);
}
QPushButton#primary:pressed {
    background: #3730a3;
}
QPushButton#danger {
    background: #ffffff;
    color: #b91c1c;
    border: 1px solid #fecaca;
}
QPushButton#danger:hover {
    background: #fef2f2;
    border-color: #f87171;
}
QPushButton#toolTinyBtn {
    padding: 4px 8px;
    min-width: 32px;
    font-weight: 700;
    font-size: 13px;
}
QFrame#mergeFieldsBar {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 10px 12px;
}
QScrollArea#mergeFieldsScroll {
    background: transparent;
}
QPushButton#mergeFieldChip {
    background: #eef2ff;
    color: #312e81;
    border: 1px solid #c7d2fe;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 600;
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    font-size: 12px;
}
QPushButton#mergeFieldChip:hover {
    background: #e0e7ff;
    border-color: #818cf8;
}
QPushButton#mergeFieldChip:pressed {
    background: #c7d2fe;
}
QComboBox {
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 8px 12px;
    min-height: 22px;
    background-color: #ffffff;
    color: #0f172a;
}
QComboBox:hover {
    border-color: #94a3b8;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 28px;
    border-left: 1px solid #e2e8f0;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    background-color: #f8fafc;
}
/*
 * Combo popups: do NOT use border-radius or padding on QAbstractItemView — Qt/macOS Fusion
 * mis-measures the viewport (clipped rows, black gap, broken scrollbar).
 * Style rows via ::item; keep the view rectangular.
 */
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    outline: none;
    selection-background-color: #e0e7ff;
    selection-color: #1e1b4b;
}
QComboBox QAbstractItemView::item {
    min-height: 28px;
    padding: 6px 12px;
    color: #0f172a;
}
QComboBox QAbstractItemView::item:selected {
    background-color: #e0e7ff;
    color: #1e1b4b;
}
/* Popup scrollbars — avoids black/unstyled strip inside the list on macOS */
QComboBox QAbstractItemView QScrollBar:vertical {
    width: 10px;
    background: #f1f5f9;
    margin: 0;
}
QComboBox QAbstractItemView QScrollBar::handle:vertical {
    background: #cbd5e1;
    border-radius: 5px;
    min-height: 24px;
}
QComboBox QAbstractItemView QScrollBar::add-line:vertical,
QComboBox QAbstractItemView QScrollBar::sub-line:vertical {
    height: 0;
    subcontrol-origin: margin;
}
QComboBox QAbstractItemView QScrollBar::add-page:vertical,
QComboBox QAbstractItemView QScrollBar::sub-page:vertical {
    background: none;
}
/* Designer / toolbar combos */
QFontComboBox#designerFontCombo,
QComboBox#designerOrientationCombo {
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 6px 10px;
    min-height: 32px;
}
QFontComboBox#designerFontCombo {
    min-width: 220px;
}
QComboBox#designerOrientationCombo {
    min-width: 120px;
}
QFontComboBox#designerFontCombo:hover,
QComboBox#designerOrientationCombo:hover {
    border-color: #94a3b8;
}
QFontComboBox#designerFontCombo::drop-down,
QComboBox#designerOrientationCombo::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 28px;
    border-left: 1px solid #e2e8f0;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    background-color: #f1f5f9;
}
/* Named spin boxes only — keeps macOS steppers readable */
QSpinBox#previewRowSpin,
QSpinBox#designerFontSize {
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 4px 8px;
    min-height: 28px;
    selection-background-color: #c7d2fe;
    selection-color: #1e1b4b;
}
QSpinBox#previewRowSpin QLineEdit,
QSpinBox#designerFontSize QLineEdit {
    background-color: #ffffff;
    color: #0f172a;
    border: none;
    padding: 2px 4px;
}
QSpinBox#previewRowSpin::up-button,
QSpinBox#previewRowSpin::down-button,
QSpinBox#designerFontSize::up-button,
QSpinBox#designerFontSize::down-button {
    subcontrol-origin: border;
    width: 18px;
    border-left: 1px solid #e2e8f0;
    background-color: #f8fafc;
}
QSpinBox#previewRowSpin {
    min-width: 80px;
}
QSpinBox#designerFontSize {
    min-width: 56px;
}
QCheckBox {
    color: #334155;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #cbd5e1;
    background: #ffffff;
}
QCheckBox::indicator:checked {
    background: #4f46e5;
    border-color: #4f46e5;
}
QTableWidget {
    gridline-color: #e8edf3;
    background: #ffffff;
    alternate-background-color: #f8fafc;
    color: #0f172a;
    border: none;
    border-radius: 8px;
    selection-background-color: #dbeafe;
    selection-color: #0f172a;
}
QTableWidget::item {
    padding: 8px 12px;
    border-bottom: 1px solid #eef2f7;
    color: #0f172a;
}
QTableWidget::item:alternate {
    background: #f8fafc;
    color: #0f172a;
}
QTableWidget::item:selected {
    background: #dbeafe;
    color: #0f172a;
}
/* Mail data grid — many columns: scroll horizontally; do not squash text */
QTableWidget#dataTable {
    color: #0f172a;
}
QTableWidget#dataTable::item {
    color: #0f172a;
}
QHeaderView::section {
    background: #f8fafc;
    color: #475569;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    padding: 10px 12px;
    border: none;
    border-bottom: 1px solid #e2e8f0;
}
/* Overrides generic header — must follow QHeaderView::section */
QTableWidget#dataTable QHeaderView::section {
    text-transform: none;
    font-size: 12px;
    font-weight: 600;
    color: #334155;
    background: #f1f5f9;
    padding: 10px 14px;
    border: none;
    border-right: 1px solid #e2e8f0;
    border-bottom: 2px solid #cbd5e1;
    letter-spacing: 0;
}
QTextEdit {
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 10px;
    background: #fafafa;
    color: #0f172a;
    selection-background-color: #c7d2fe;
}
QTextEdit:focus {
    border-color: #818cf8;
    background: #ffffff;
}
QTextEdit#mergeTemplateEditor {
    background: #ffffff;
    color: #0f172a;
    font-size: 13px;
    min-height: 140px;
}
/* Do not style QGraphicsView globally — breaks scene painting. Use #designerCanvasFrame. */
QFrame#designerCanvasFrame {
    background: #e8ecf3;
    border: 1px solid #cbd5e1;
    border-radius: 10px;
}
QSplitter#designerSplit::handle {
    background: #e2e8f0;
    width: 4px;
    margin: 2px 0;
}
QSplitter#designerSplit::handle:hover {
    background: #c7d2fe;
}
QMenuBar {
    background: #ffffff;
    border-bottom: 1px solid #e2e8f0;
    padding: 4px 8px;
    color: #334155;
}
QMenuBar::item:selected {
    background: #f1f5f9;
    border-radius: 4px;
}
QMenu {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 6px;
    color: #0f172a;
}
QMenu::item {
    padding: 8px 28px;
    border-radius: 6px;
    color: #0f172a;
    background: transparent;
}
QMenu::item:hover {
    background: #f8fafc;
    color: #0f172a;
}
QMenu::item:selected {
    background: #eef2ff;
    color: #312e81;
}
QMenu::item:selected:hover {
    background: #e0e7ff;
    color: #312e81;
}
QLabel#appFooter {
    background: #ffffff;
    border-top: 1px solid #e2e8f0;
    color: #64748b;
    font-size: 11px;
    padding: 8px 16px;
}
QStatusBar {
    background: #ffffff;
    border-top: 1px solid #e2e8f0;
    color: #64748b;
    font-size: 11px;
    padding: 4px 12px;
}
QTabWidget::pane {
    border: none;
}
QScrollBar:vertical {
    width: 10px;
    background: #f1f5f9;
    border-radius: 5px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #cbd5e1;
    border-radius: 5px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}
QScrollBar:horizontal {
    height: 10px;
    background: #f1f5f9;
    border-radius: 5px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #cbd5e1;
    border-radius: 5px;
    min-width: 28px;
}
QScrollBar::handle:horizontal:hover {
    background: #94a3b8;
}
QLabel#hint {
    color: #94a3b8;
    font-size: 12px;
}
QFrame#propsPanel {
    background: #fafafa;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
}
QLabel#propsTitle {
    font-size: 11px;
    font-weight: 700;
    color: #64748b;
    letter-spacing: 0.8px;
}
"""
