from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QPointF, QMarginsF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPageLayout, QPainter, QPageSize, QPixmap
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsTextItem

from envelope_app.layout import (
    LAYOUT_KIND_A4,
    ORIENTATION_LANDSCAPE,
    ImageElement,
    TextElement,
    get_page_dimensions,
    layout_orientation,
    parse_layout,
    read_layout_kind,
)
from envelope_app.merge import merge_template
from envelope_app.paths import app_data_dir


def _resolve_image_path(rel: str) -> Path:
    return app_data_dir() / rel.replace("\\", "/")


def build_merged_scene(layout_json: str, record: dict[str, Any]) -> QGraphicsScene:
    orient = layout_orientation(layout_json)
    lk = read_layout_kind(layout_json)
    pw, ph = get_page_dimensions(lk, orient)
    scene = QGraphicsScene(0, 0, pw, ph)
    # White paper; explicit text color so print/PDF never inherits app palette (e.g. light on white).
    scene.setBackgroundBrush(QColor(255, 255, 255))
    z = 0
    for el in parse_layout(layout_json):
        if isinstance(el, TextElement):
            merged = merge_template(el.text, record)
            item = QGraphicsTextItem(merged)
            item.setDefaultTextColor(QColor("#0f172a"))
            font = QFont()
            if el.font_family:
                font.setFamily(el.font_family)
            font.setPointSizeF(el.font_pt)
            item.setFont(font)
            item.setTextWidth(el.w)
            item.setPos(QPointF(el.x, el.y))
            item.setZValue(z)
            scene.addItem(item)
        elif isinstance(el, ImageElement):
            p = _resolve_image_path(el.path)
            pm = QPixmap(str(p)) if p.is_file() else QPixmap()
            if pm.isNull():
                continue
            item = QGraphicsPixmapItem(pm.scaled(el.w, el.h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation))
            item.setPos(QPointF(el.x, el.y))
            item.setZValue(z)
            scene.addItem(item)
        z += 1
    return scene


def paint_record(
    painter: QPainter,
    layout_json: str,
    record: dict[str, Any],
    target_rect: QRectF,
) -> None:
    orient = layout_orientation(layout_json)
    lk = read_layout_kind(layout_json)
    pw, ph = get_page_dimensions(lk, orient)
    scene = build_merged_scene(layout_json, record)
    scene.render(
        painter,
        target_rect,
        QRectF(0, 0, pw, ph),
        Qt.AspectRatioMode.KeepAspectRatio,
    )


def apply_printer_page(printer: QPrinter, layout_json: str) -> None:
    """Match printer page size (#10 vs A4) and orientation to the saved layout."""
    orient = layout_orientation(layout_json)
    lk = read_layout_kind(layout_json)
    if lk == LAYOUT_KIND_A4:
        page_size = QPageSize(QPageSize.PageSizeId.A4)
    else:
        page_size = QPageSize(QPageSize.PageSizeId.Envelope10)
    page_layout = QPageLayout(
        page_size,
        QPageLayout.Orientation.Landscape
        if orient == ORIENTATION_LANDSCAPE
        else QPageLayout.Orientation.Portrait,
        QMarginsF(0, 0, 0, 0),
        QPageLayout.Unit.Point,
    )
    printer.setPageLayout(page_layout)


def print_records(
    parent: Any,
    layout_json: str,
    records: list[dict[str, Any]],
    *,
    show_dialog: bool = True,
) -> bool:
    from PySide6.QtWidgets import QDialog

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    apply_printer_page(printer, layout_json)

    if show_dialog:
        dlg = QPrintDialog(printer, parent)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False

    painter = QPainter(printer)
    try:
        for i, rec in enumerate(records):
            if i > 0:
                printer.newPage()
            page = printer.pageRect(QPrinter.Unit.DevicePixel)
            paint_record(painter, layout_json, rec, QRectF(page))
    finally:
        painter.end()
    return True


def export_pdf(
    file_path: str,
    layout_json: str,
    records: list[dict[str, Any]],
) -> bool:
    """
    Write one #10-sized page per record to a PDF file (vector-friendly via QPrinter PDF).
    """
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(file_path)
    apply_printer_page(printer, layout_json)

    painter = QPainter(printer)
    try:
        for i, rec in enumerate(records):
            if i > 0:
                printer.newPage()
            page = printer.pageRect(QPrinter.Unit.DevicePixel)
            paint_record(painter, layout_json, rec, QRectF(page))
    finally:
        painter.end()
    return True
