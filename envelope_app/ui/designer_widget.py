from __future__ import annotations

import enum
import math
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QSize, Qt, QMimeData, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QDrag,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QFont,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFontComboBox,
    QFrame,
    QFileDialog,
    QGridLayout,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneMouseEvent,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QScrollArea,
    QToolButton,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from envelope_app.layout import (
    DEFAULT_ENVELOPE_SIZE_ID,
    ENVELOPE_SIZE_ORDER,
    ENVELOPE_SIZES,
    LAYOUT_KIND_A4,
    LAYOUT_KIND_ENVELOPE,
    LAYOUT_KIND_US_LETTER,
    ORIENTATION_LANDSCAPE,
    ORIENTATION_PORTRAIT,
    PAGE_H_PT,
    PAGE_W_PT,
    ImageElement,
    LayoutElement,
    TextElement,
    get_page_dimensions,
    layout_orientation,
    layout_to_json,
    page_size_points_from_layout_json,
    parse_layout,
    read_envelope_size_id,
    remap_box_elements,
)
from envelope_app.paths import app_data_dir, template_images_dir
from envelope_app.merge import merge_template


UID_ROLE = Qt.ItemDataRole.UserRole + 1

# Readable default for new blocks (avoid decorative “Academy Engraved” as first combo pick).
_DEFAULT_UI_FONT = "Arial"


class HandleKind(enum.IntEnum):
    """Bounding-box handle positions (Photoshop-style transform)."""

    NW = 0
    N = 1
    NE = 2
    E = 3
    SE = 4
    S = 5
    SW = 6
    W = 7


# Explicit order — do not rely on IntEnum iteration for positioning vs. creation.
_HANDLE_KIND_ORDER: tuple[HandleKind, ...] = (
    HandleKind.NW,
    HandleKind.N,
    HandleKind.NE,
    HandleKind.E,
    HandleKind.SE,
    HandleKind.S,
    HandleKind.SW,
    HandleKind.W,
)


HANDLE_SIZE_PT = 9.0
# Layout items use z = 0, 1, 2, … ; handles must stay above every block or N/S get covered.
HANDLE_Z = 1_000_000.0
FRAME_Z = 999_990.0


class SelectionFrameItem(QGraphicsRectItem):
    """Dashed box is visual only; do not steal mouse from content below."""

    def shape(self) -> QPainterPath:
        return QPainterPath()


def _cursor_for_handle(kind: HandleKind) -> Qt.CursorShape:
    if kind in (HandleKind.N, HandleKind.S):
        return Qt.CursorShape.SizeVerCursor
    if kind in (HandleKind.E, HandleKind.W):
        return Qt.CursorShape.SizeHorCursor
    if kind in (HandleKind.NW, HandleKind.SE):
        return Qt.CursorShape.SizeFDiagCursor
    return Qt.CursorShape.SizeBDiagCursor


class TransformHandleItem(QGraphicsRectItem):
    """Eight Photoshop-style handles: box resize for images; width + corner moves for text."""

    def __init__(
        self,
        kind: HandleKind,
        target: QGraphicsItem,
        on_change: Callable[[], None],
    ) -> None:
        super().__init__(0, 0, HANDLE_SIZE_PT, HANDLE_SIZE_PT)
        self._kind = kind
        self._target = target
        self._on_change = on_change
        self._press_scene: QPointF | None = None
        self._start_rect = QRectF()
        self._start_pos = QPointF()
        self._start_w = 0.0
        self._start_h = 0.0
        self._start_text_w = 0.0
        self._start_font_pt = 11.0

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptHoverEvents(True)
        self.setCursor(_cursor_for_handle(kind))
        pen = QPen(QColor("#2563eb"), 1.2)
        self.setPen(pen)
        self.setBrush(QColor(255, 255, 255, 245))
        self.setZValue(HANDLE_Z)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)

    def _center_at(self, cx: float, cy: float) -> None:
        r = self.rect()
        self.setPos(cx - r.width() / 2.0, cy - r.height() / 2.0)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self._press_scene = event.scenePos()
        self._start_rect = self._target.sceneBoundingRect()
        self._start_pos = self._target.pos()
        if isinstance(self._target, TemplateTextItem):
            tw = self._target.textWidth()
            self._start_text_w = float(tw) if tw > 0 else self._start_rect.width()
            f = self._target.font()
            self._start_font_pt = float(f.pointSizeF() or f.pointSize() or 11)
        elif isinstance(self._target, TemplateImageItem):
            self._start_w = float(self._target._w)
            self._start_h = float(self._target._h)
        event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not (event.buttons() & Qt.MouseButton.LeftButton) or self._press_scene is None:
            return super().mouseMoveEvent(event)
        m = event.scenePos()
        if isinstance(self._target, TemplateTextItem):
            self._resize_text(m)
        elif isinstance(self._target, TemplateImageItem):
            self._resize_image(m)
        if self._on_change:
            self._on_change()
        sc = self.scene()
        if sc is not None and hasattr(sc, "sync_selection_chrome"):
            sc.sync_selection_chrome()
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self._press_scene = None
        super().mouseReleaseEvent(event)

    def _apply_text_font_scale(self, rel: float) -> None:
        t = self._target
        if not isinstance(t, TemplateTextItem):
            return
        pt = max(5.0, min(288.0, self._start_font_pt * rel))
        f = QFont(t.font())
        f.setPointSizeF(pt)
        t.setFont(f)

    def _resize_text(self, m: QPointF) -> None:
        t = self._target
        sr = self._start_rect
        left, top, right, bottom = sr.left(), sr.top(), sr.right(), sr.bottom()
        h0 = sr.height()
        sy = self._start_pos.y()
        sx = self._start_pos.x()
        k = self._kind

        if k == HandleKind.E:
            new_w = max(48.0, m.x() - left)
            t.setPos(QPointF(left, sy))
            t.setTextWidth(new_w)
        elif k == HandleKind.W:
            new_w = max(48.0, right - m.x())
            t.setPos(QPointF(m.x(), sy))
            t.setTextWidth(new_w)
        elif k == HandleKind.N:
            if self._press_scene is not None:
                dy = m.y() - self._press_scene.y()
                self._apply_text_font_scale(1.0 - dy / 120.0)
        elif k == HandleKind.S:
            if self._press_scene is not None:
                dy = m.y() - self._press_scene.y()
                self._apply_text_font_scale(1.0 + dy / 120.0)
        elif k == HandleKind.NE:
            new_w = max(48.0, m.x() - left)
            t.setPos(QPointF(left, m.y()))
            t.setTextWidth(new_w)
        elif k == HandleKind.NW:
            new_w = max(48.0, right - m.x())
            t.setPos(QPointF(m.x(), m.y()))
            t.setTextWidth(new_w)
        elif k == HandleKind.SE:
            new_w = max(48.0, m.x() - left)
            t.setPos(QPointF(left, m.y() - h0))
            t.setTextWidth(new_w)
        elif k == HandleKind.SW:
            new_w = max(48.0, right - m.x())
            t.setPos(QPointF(m.x(), m.y() - h0))
            t.setTextWidth(new_w)

    def _resize_image(self, m: QPointF) -> None:
        img = self._target
        sr = self._start_rect
        left, top, right, bottom = sr.left(), sr.top(), sr.right(), sr.bottom()
        k = self._kind

        def set_box_at(x: float, y: float, w: float, h: float) -> None:
            w = max(24.0, w)
            h = max(24.0, h)
            img.setPos(QPointF(x, y))
            img.set_box_size(w, h)

        if k == HandleKind.E:
            set_box_at(left, top, m.x() - left, self._start_h)
        elif k == HandleKind.W:
            nw = right - m.x()
            set_box_at(m.x(), top, nw, self._start_h)
        elif k == HandleKind.S:
            set_box_at(left, top, self._start_w, m.y() - top)
        elif k == HandleKind.N:
            nh = bottom - m.y()
            set_box_at(left, m.y(), self._start_w, nh)
        elif k == HandleKind.NW:
            nw, nh = right - m.x(), bottom - m.y()
            set_box_at(m.x(), m.y(), nw, nh)
        elif k == HandleKind.NE:
            nw, nh = m.x() - left, bottom - m.y()
            set_box_at(left, m.y(), nw, nh)
        elif k == HandleKind.SW:
            nw, nh = right - m.x(), m.y() - top
            set_box_at(m.x(), top, nw, nh)
        elif k == HandleKind.SE:
            nw, nh = m.x() - left, m.y() - top
            set_box_at(left, top, nw, nh)




def _show_layout_context_menu(
    scene: QGraphicsScene,
    item: QGraphicsItem,
    event: QGraphicsSceneContextMenuEvent,
) -> None:
    if not item.data(UID_ROLE):
        return
    if not hasattr(scene, "layout_element_context"):
        return
    menu = QMenu()
    if isinstance(item, TemplateTextItem):
        act_copy = menu.addAction("Copy text")
        act_dup = menu.addAction("Duplicate block")
        menu.addSeparator()
        act_del = menu.addAction("Delete block")
        chosen = menu.exec(event.screenPos())
        if chosen is None:
            return
        if chosen == act_copy:
            scene.layout_element_context.emit(item, "copy")
        elif chosen == act_dup:
            scene.layout_element_context.emit(item, "duplicate")
        elif chosen == act_del:
            scene.layout_element_context.emit(item, "delete")
        return
    if isinstance(item, TemplateImageItem):
        act_rep = menu.addAction("Replace image…")
        act_dup = menu.addAction("Duplicate")
        menu.addSeparator()
        act_del = menu.addAction("Delete")
        chosen = menu.exec(event.screenPos())
        if chosen is None:
            return
        if chosen == act_rep:
            scene.layout_element_context.emit(item, "replace_image")
        elif chosen == act_dup:
            scene.layout_element_context.emit(item, "duplicate")
        elif chosen == act_del:
            scene.layout_element_context.emit(item, "delete")
        return


class TemplateTextItem(QGraphicsTextItem):
    def __init__(self, text: str, on_change: Callable[[], None] | None = None) -> None:
        super().__init__(text)
        self._on_change = on_change
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        # Single click = select / move / resize; double-click opens in-canvas editing.
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        super().mouseDoubleClickEvent(event)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: object) -> object:
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged and not value:
            self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self._on_change:
            self._on_change()
        if change in (
            QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged,
            QGraphicsItem.GraphicsItemChange.ItemScenePositionHasChanged,
        ):
            sc = self.scene()
            if sc is not None and hasattr(sc, "sync_selection_chrome"):
                sc.sync_selection_chrome()
        return result

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        sc = self.scene()
        if sc is None:
            return
        _show_layout_context_menu(sc, self, event)

    def to_text_element(self) -> TextElement:
        br = self.sceneBoundingRect()
        font = self.font()
        fam = font.family()
        tw = self.textWidth()
        return TextElement(
            uid=str(self.data(UID_ROLE)),
            x=float(self.pos().x()),
            y=float(self.pos().y()),
            w=float(tw if tw > 0 else br.width()),
            h=float(br.height()),
            text=self.toPlainText(),
            font_pt=float(font.pointSizeF() or font.pointSize() or 11),
            font_family=fam,
        )


class TemplateImageItem(QGraphicsPixmapItem):
    """Placed image; path is relative to app data dir."""

    def __init__(
        self,
        el: ImageElement,
        source: QPixmap,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._on_change = on_change
        self._rel_path = el.path
        self._w = el.w
        self._h = el.h
        self._source = source if not source.isNull() else QPixmap(1, 1)
        self.setData(UID_ROLE, el.uid)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._apply_scaled()

    def _resolved_path(self) -> Path:
        return app_data_dir() / self._rel_path.replace("\\", "/")

    def _apply_scaled(self) -> None:
        pm = self._source.scaled(
            QSize(int(self._w), int(self._h)),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(pm)

    def set_box_width(self, w: float) -> None:
        w = max(24.0, w)
        ow = max(self._source.width(), 1)
        oh = self._source.height()
        self._w = w
        self._h = w * (oh / ow)
        self._apply_scaled()

    def set_box_size(self, w: float, h: float) -> None:
        self._w = max(24.0, w)
        self._h = max(24.0, h)
        self._apply_scaled()

    def to_image_element(self) -> ImageElement:
        return ImageElement(
            uid=str(self.data(UID_ROLE)),
            x=float(self.pos().x()),
            y=float(self.pos().y()),
            w=float(self._w),
            h=float(self._h),
            path=self._rel_path,
        )

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: object) -> object:
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self._on_change:
            self._on_change()
        if change in (
            QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged,
            QGraphicsItem.GraphicsItemChange.ItemScenePositionHasChanged,
        ):
            sc = self.scene()
            if sc is not None and hasattr(sc, "sync_selection_chrome"):
                sc.sync_selection_chrome()
        return result

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        sc = self.scene()
        if sc is None:
            return
        _show_layout_context_menu(sc, self, event)

    def replace_image_from_path(self, abs_path: Path) -> None:
        template_images_dir().mkdir(parents=True, exist_ok=True)
        dest = template_images_dir() / f"{uuid.uuid4()}{abs_path.suffix.lower()}"
        shutil.copy2(abs_path, dest)
        self._rel_path = str(dest.relative_to(app_data_dir()))
        pm = QPixmap(str(dest))
        self._source = pm if not pm.isNull() else QPixmap(1, 1)
        ow = max(self._source.width(), 1)
        oh = self._source.height()
        self._h = self._w * (oh / ow)
        self._apply_scaled()
        if self._on_change:
            self._on_change()


class EnvelopeScene(QGraphicsScene):
    layout_element_context = Signal(QGraphicsItem, str)

    def __init__(self) -> None:
        super().__init__()
        self._on_change: Callable[[], None] | None = None
        self._border: QGraphicsRectItem | None = None
        self._chrome_frame: SelectionFrameItem | None = None
        self._chrome_handles: list[TransformHandleItem] = []
        self._chrome_target: QGraphicsItem | None = None
        self.setBackgroundBrush(QColor(255, 254, 249))
        self.set_page_size(PAGE_W_PT, PAGE_H_PT)
        self.selectionChanged.connect(self._on_selection_changed)

    def _emit_layout(self) -> None:
        if self._on_change:
            self._on_change()

    def _on_selection_changed(self) -> None:
        texts = [
            i
            for i in self.selectedItems()
            if isinstance(i, TemplateTextItem) and i.data(UID_ROLE)
        ]
        imgs = [
            i
            for i in self.selectedItems()
            if isinstance(i, TemplateImageItem) and i.data(UID_ROLE)
        ]
        if len(texts) == 1:
            self._set_selection_chrome(texts[0])
        elif len(imgs) == 1:
            self._set_selection_chrome(imgs[0])
        else:
            self._clear_selection_chrome()

    def clear_selection_chrome(self) -> None:
        self._clear_selection_chrome()

    def _clear_selection_chrome(self) -> None:
        self._chrome_target = None
        if self._chrome_frame is not None:
            self.removeItem(self._chrome_frame)
            self._chrome_frame = None
        for h in self._chrome_handles:
            self.removeItem(h)
        self._chrome_handles.clear()

    def _set_selection_chrome(self, target: QGraphicsItem) -> None:
        self._clear_selection_chrome()
        self._chrome_target = target
        self._chrome_frame = SelectionFrameItem()
        self._chrome_frame.setZValue(FRAME_Z)
        self._chrome_frame.setPen(QPen(QColor("#6366f1"), 1.5, Qt.PenStyle.DashLine))
        self._chrome_frame.setBrush(Qt.BrushStyle.NoBrush)
        self._chrome_frame.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.addItem(self._chrome_frame)

        for kind in _HANDLE_KIND_ORDER:
            h = TransformHandleItem(kind, target, self._emit_layout)
            self.addItem(h)
            self._chrome_handles.append(h)
        self.sync_selection_chrome()

    def sync_selection_chrome(self) -> None:
        if self._chrome_target is None:
            return
        target = self._chrome_target
        if target.scene() != self:
            self._clear_selection_chrome()
            return
        if self._chrome_frame is None:
            return
        br = target.sceneBoundingRect()
        pad = 3.0
        self._chrome_frame.setPos(br.x() - pad, br.y() - pad)
        self._chrome_frame.setRect(0, 0, br.width() + 2 * pad, br.height() + 2 * pad)
        fl = br.x() - pad
        ft = br.y() - pad
        fr = br.right() + pad
        fb = br.bottom() + pad
        mid_x = (fl + fr) * 0.5
        mid_y = (ft + fb) * 0.5
        for h in self._chrome_handles:
            kind = h._kind
            if kind == HandleKind.NW:
                h._center_at(fl, ft)
            elif kind == HandleKind.N:
                h._center_at(mid_x, ft)
            elif kind == HandleKind.NE:
                h._center_at(fr, ft)
            elif kind == HandleKind.E:
                h._center_at(fr, mid_y)
            elif kind == HandleKind.SE:
                h._center_at(fr, fb)
            elif kind == HandleKind.S:
                h._center_at(mid_x, fb)
            elif kind == HandleKind.SW:
                h._center_at(fl, fb)
            else:  # W
                h._center_at(fl, mid_y)

    def set_page_size(self, pw: float, ph: float) -> None:
        if self._border is not None:
            self.removeItem(self._border)
            self._border = None
        self.setSceneRect(0, 0, pw, ph)
        border = self.addRect(QRectF(0, 0, pw, ph), QPen(QColor(148, 163, 184), 1.0))
        border.setZValue(-1)
        border.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._border = border
        self.sync_selection_chrome()

    def _font_from_element(self, el: TextElement) -> QFont:
        f = QFont()
        if el.font_family:
            f.setFamily(el.font_family)
        else:
            f.setFamily(_DEFAULT_UI_FONT)
        f.setPointSizeF(el.font_pt)
        return f

    def add_text_element(self, el: TextElement, z: float | None = None) -> TemplateTextItem:
        item = TemplateTextItem(el.text, self._on_change)
        item.setData(UID_ROLE, el.uid)
        item.setDefaultTextColor(QColor("#0f172a"))
        item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        item.setFont(self._font_from_element(el))
        item.setTextWidth(el.w)
        item.setPos(QPointF(el.x, el.y))
        item.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIsMovable, True)
        item.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIsSelectable, True)
        if z is not None:
            item.setZValue(z)
        self.addItem(item)
        return item

    def add_image_element(self, el: ImageElement, z: float | None = None) -> TemplateImageItem | None:
        p = app_data_dir() / el.path.replace("\\", "/")
        pm = QPixmap(str(p)) if p.is_file() else QPixmap()
        if pm.isNull():
            return None
        item = TemplateImageItem(el, pm, self._on_change)
        if z is not None:
            item.setZValue(z)
        self.addItem(item)
        return item

    def elements_from_scene(self) -> list[LayoutElement]:
        rows: list[tuple[float, LayoutElement]] = []
        for item in self.items():
            if isinstance(item, TemplateTextItem) and item.data(UID_ROLE):
                rows.append((item.zValue(), item.to_text_element()))
            elif isinstance(item, TemplateImageItem) and item.data(UID_ROLE):
                rows.append((item.zValue(), item.to_image_element()))
        rows.sort(key=lambda t: t[0])
        return [e for _, e in rows]


class MergeFieldChip(QPushButton):
    def __init__(
        self,
        shortcode: str,
        *,
        on_copy: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(shortcode, parent)
        self._shortcode = shortcode
        self._on_copy = on_copy
        self._drag_start: QPointF | None = None

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        if self._on_copy is None:
            return super().contextMenuEvent(event)
        menu = QMenu(self)
        act = menu.addAction("Copy to clipboard")
        chosen = menu.exec(event.globalPos())
        if chosen == act:
            self._on_copy()
        event.accept()

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_start = e.position()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._drag_start is None or not (e.buttons() & Qt.MouseButton.LeftButton):
            return super().mouseMoveEvent(e)
        delta = e.position() - self._drag_start
        if delta.manhattanLength() < QApplication.startDragDistance():
            return super().mouseMoveEvent(e)
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(self._shortcode)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)
        self._drag_start = None

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        self._drag_start = None
        super().mouseReleaseEvent(e)


RULER_THICKNESS = 28
# Layout scene coords are typographic points; 72 pt = 1 inch (PDF/print convention).
PT_PER_INCH = 72.0


def _nice_step(raw: float) -> float:
    if raw <= 0:
        return 1.0
    exp = math.floor(math.log10(raw))
    base = 10.0**exp
    for f in (1, 2, 5, 10):
        step = float(f) * base
        if step >= raw * 0.999:
            return step
    return float(10 * base)


def _fmt_scene_tick(v: float) -> str:
    if abs(v) >= 100:
        return str(int(round(v)))
    if abs(v) >= 10:
        return str(int(round(v)))
    s = f"{v:.1f}"
    if s.endswith(".0"):
        return s[:-2]
    return s


def _fmt_inch_tick(v: float) -> str:
    if abs(v) >= 100:
        return f"{v:.0f}"
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s if s else "0"


class _RulerViewportFilter(QObject):
    def __init__(self, fn: Callable[[], None]) -> None:
        super().__init__()
        self._fn = fn

    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        if ev.type() == QEvent.Type.Resize:
            self._fn()
        return False


class CanvasRuler(QWidget):
    """Rulers: scene space is in points; labels show points or inches (72 pt = 1 in)."""

    def __init__(
        self,
        view: QGraphicsView,
        horizontal: bool,
        parent: QWidget | None = None,
        *,
        use_inches: Callable[[], bool],
    ) -> None:
        super().__init__(parent)
        self._view = view
        self._horizontal = horizontal
        self._use_inches = use_inches
        self.setObjectName("designerRuler")
        if horizontal:
            self.setFixedHeight(RULER_THICKNESS)
        else:
            self.setFixedWidth(RULER_THICKNESS)

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.fillRect(self.rect(), QColor(248, 250, 252))

        view = self._view
        vp = view.viewport()
        vr = vp.rect()
        if vr.width() < 1 or vr.height() < 1:
            painter.setPen(QPen(QColor(226, 232, 240)))
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
            return

        # PySide6: mapToScene accepts QPoint / int coords, not QPointF.
        tl = view.mapToScene(vr.topLeft())
        br = view.mapToScene(vr.bottomRight())
        xmin, xmax = min(tl.x(), br.x()), max(tl.x(), br.x())
        ymin, ymax = min(tl.y(), br.y()), max(tl.y(), br.y())
        span_x = xmax - xmin
        span_y = ymax - ymin
        if span_x < 1e-9:
            span_x = 1.0
        if span_y < 1e-9:
            span_y = 1.0

        w_px = max(1, self.width())
        h_px = max(1, self.height())
        edge = QColor(226, 232, 240)
        tick_maj = QColor(100, 116, 139)
        tick_min = QColor(203, 213, 225)

        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)

        inch = self._use_inches()

        if self._horizontal:
            painter.setPen(QPen(edge))
            painter.drawLine(0, h_px - 1, w_px, h_px - 1)
            if inch:
                umin, umax = xmin / PT_PER_INCH, xmax / PT_PER_INCH
                span_u = max(umax - umin, 1e-9)
                spp_u = span_u / float(w_px)
                major_u = _nice_step(64.0 * spp_u)
                minor_u = major_u / 5.0 if major_u > 1e-9 else major_u
                painter.setPen(QPen(tick_min))
                t = math.floor(umin / minor_u) * minor_u
                while t <= umax + minor_u * 0.5:
                    x_scene = t * PT_PER_INCH
                    px = (x_scene - xmin) / span_x * w_px
                    if -2 <= px <= w_px + 2:
                        on_major = math.isclose(t / major_u, round(t / major_u), rel_tol=0, abs_tol=1e-6)
                        h_tick = h_px * 0.42 if on_major else h_px * 0.22
                        painter.drawLine(int(px), h_px - 1, int(px), int(h_px - 1 - h_tick))
                    t += minor_u
                painter.setPen(QPen(tick_maj))
                t = math.floor(umin / major_u) * major_u
                while t <= umax + major_u * 0.5:
                    x_scene = t * PT_PER_INCH
                    px = (x_scene - xmin) / span_x * w_px
                    if 4 <= px <= w_px - 4:
                        painter.drawText(int(px) + 2, int(h_px * 0.62), _fmt_inch_tick(t))
                    t += major_u
            else:
                spp = span_x / float(w_px)
                major = _nice_step(64.0 * spp)
                minor = major / 5.0 if major > 1e-6 else major
                painter.setPen(QPen(tick_min))
                x = math.floor(xmin / minor) * minor
                while x <= xmax + minor * 0.5:
                    px = (x - xmin) / span_x * w_px
                    if -2 <= px <= w_px + 2:
                        on_major = math.isclose(x / major, round(x / major), rel_tol=0, abs_tol=1e-3)
                        h_tick = h_px * 0.42 if on_major else h_px * 0.22
                        painter.drawLine(int(px), h_px - 1, int(px), int(h_px - 1 - h_tick))
                    x += minor
                painter.setPen(QPen(tick_maj))
                x = math.floor(xmin / major) * major
                while x <= xmax + major * 0.5:
                    px = (x - xmin) / span_x * w_px
                    if 4 <= px <= w_px - 4:
                        painter.drawText(int(px) + 2, int(h_px * 0.62), _fmt_scene_tick(x))
                    x += major
        else:
            painter.setPen(QPen(edge))
            painter.drawLine(w_px - 1, 0, w_px - 1, h_px)
            if inch:
                umin, umax = ymin / PT_PER_INCH, ymax / PT_PER_INCH
                span_u = max(umax - umin, 1e-9)
                spp_u = span_u / float(h_px)
                major_u = _nice_step(64.0 * spp_u)
                minor_u = major_u / 5.0 if major_u > 1e-9 else major_u
                painter.setPen(QPen(tick_min))
                t = math.floor(umin / minor_u) * minor_u
                while t <= umax + minor_u * 0.5:
                    y_scene = t * PT_PER_INCH
                    py = (y_scene - ymin) / span_y * h_px
                    if -2 <= py <= h_px + 2:
                        on_major = math.isclose(t / major_u, round(t / major_u), rel_tol=0, abs_tol=1e-6)
                        w_tick = w_px * 0.42 if on_major else w_px * 0.22
                        painter.drawLine(w_px - 1, int(py), int(w_px - 1 - w_tick), int(py))
                    t += minor_u
                painter.setPen(QPen(tick_maj))
                t = math.floor(umin / major_u) * major_u
                while t <= umax + major_u * 0.5:
                    y_scene = t * PT_PER_INCH
                    py = (y_scene - ymin) / span_y * h_px
                    if 6 <= py <= h_px - 10:
                        painter.save()
                        painter.translate(int(w_px * 0.35), int(py))
                        painter.rotate(-90.0)
                        painter.drawText(0, 0, _fmt_inch_tick(t))
                        painter.restore()
                    t += major_u
            else:
                spp_y = span_y / float(h_px)
                major = _nice_step(64.0 * spp_y)
                minor = major / 5.0 if major > 1e-6 else major
                painter.setPen(QPen(tick_min))
                y = math.floor(ymin / minor) * minor
                while y <= ymax + minor * 0.5:
                    py = (y - ymin) / span_y * h_px
                    if -2 <= py <= h_px + 2:
                        on_major = math.isclose(y / major, round(y / major), rel_tol=0, abs_tol=1e-3)
                        w_tick = w_px * 0.42 if on_major else w_px * 0.22
                        painter.drawLine(w_px - 1, int(py), int(w_px - 1 - w_tick), int(py))
                    y += minor
                painter.setPen(QPen(tick_maj))
                y = math.floor(ymin / major) * major
                while y <= ymax + major * 0.5:
                    py = (y - ymin) / span_y * h_px
                    if 6 <= py <= h_px - 10:
                        painter.save()
                        painter.translate(int(w_px * 0.35), int(py))
                        painter.rotate(-90.0)
                        painter.drawText(0, 0, _fmt_scene_tick(y))
                        painter.restore()
                    y += major


class DesignerGraphicsView(QGraphicsView):
    text_dropped = Signal(str)
    canvas_add_requested = Signal()
    canvas_add_image_requested = Signal()

    def __init__(self, scene: QGraphicsScene, parent: QWidget | None = None) -> None:
        super().__init__(scene, parent)
        self.setAcceptDrops(True)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            hit_content = False
            for it in self.items(event.pos()):
                if isinstance(it, TransformHandleItem):
                    hit_content = True
                    break
                if isinstance(it, (TemplateTextItem, TemplateImageItem)) and it.data(UID_ROLE):
                    hit_content = True
                    break
            if not hit_content:
                self.scene().clearSelection()
                event.accept()
                return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        scene_pos = self.mapToScene(event.pos())
        item = self.scene().itemAt(scene_pos, self.transform())
        if isinstance(item, TemplateTextItem) and item.data(UID_ROLE):
            return super().contextMenuEvent(event)
        if isinstance(item, TemplateImageItem) and item.data(UID_ROLE):
            return super().contextMenuEvent(event)
        if isinstance(item, TransformHandleItem):
            return super().contextMenuEvent(event)
        menu = QMenu(self)
        act_add = menu.addAction("Add text block")
        act_img = menu.addAction("Add image…")
        chosen = menu.exec(event.globalPos())
        if chosen == act_add:
            self.canvas_add_requested.emit()
        elif chosen == act_img:
            self.canvas_add_image_requested.emit()
        event.accept()

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        if e.mimeData().hasText():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e: QDragMoveEvent) -> None:
        if e.mimeData().hasText():
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e: QDropEvent) -> None:
        if e.mimeData().hasText():
            self.text_dropped.emit(e.mimeData().text())
            e.acceptProposedAction()
        else:
            super().dropEvent(e)


class DesignerWidget(QWidget):
    layout_changed = Signal()
    shortcode_copied = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        layout_kind: str = LAYOUT_KIND_ENVELOPE,
        envelope_size_id: str | None = None,
        lock_envelope_size: bool = False,
    ) -> None:
        super().__init__(parent)
        self._suppress_nav = False
        self._layout_kind = layout_kind
        self._orientation = ORIENTATION_PORTRAIT
        self._suppress_envelope_ui = False
        self._lock_envelope_size = (
            lock_envelope_size
            and layout_kind == LAYOUT_KIND_ENVELOPE
            and (envelope_size_id or "").strip() != ""
        )
        if self._lock_envelope_size:
            self._envelope_size_id = str(envelope_size_id)
            # Direct thermal label stock defaults to landscape (feed direction) matching default_thermal_label_layout().
            self._orientation = ORIENTATION_LANDSCAPE
        else:
            self._envelope_size_id = envelope_size_id or DEFAULT_ENVELOPE_SIZE_ID
        self._scene = EnvelopeScene()
        self._scene._on_change = self.layout_changed.emit
        pw, ph = self._page_dims()
        self._scene.set_page_size(pw, ph)

        self._view = DesignerGraphicsView(self._scene)
        self._view.text_dropped.connect(self._on_canvas_text_drop)
        self._view.canvas_add_requested.connect(self._add_block)
        self._view.canvas_add_image_requested.connect(self._add_image_dialog)
        self._scene.layout_element_context.connect(self._on_layout_element)
        self._setup_view()
        self._configure_view_for_page_kind()

        self._btn_add = QPushButton("+  Add text block")
        self._btn_add.setMinimumHeight(32)
        self._btn_add.clicked.connect(self._add_block)

        self._btn_add_img = QPushButton("+  Add image")
        self._btn_add_img.setMinimumHeight(32)
        self._btn_add_img.clicked.connect(self._add_image_dialog)

        self._font_combo = QFontComboBox()
        self._font_combo.setObjectName("designerFontCombo")
        self._font_combo.setMaxVisibleItems(12)
        self._font_combo.setFontFilters(
            QFontComboBox.FontFilter.ScalableFonts | QFontComboBox.FontFilter.ProportionalFonts
        )
        self._font_combo.setCurrentFont(QFont(_DEFAULT_UI_FONT))
        self._font_combo.currentFontChanged.connect(self._on_font_combo_changed)
        self._font_combo.view().setUniformItemSizes(True)

        self._font_spin = QSpinBox()
        self._font_spin.setObjectName("designerFontSize")
        self._font_spin.setRange(6, 96)
        self._font_spin.setValue(11)
        self._font_spin.setMinimumWidth(56)
        self._font_spin.setMinimumHeight(28)
        self._font_spin.valueChanged.connect(self._apply_font_size_to_selection)

        self._btn_smaller = QPushButton("A−")
        self._btn_smaller.setObjectName("toolTinyBtn")
        self._btn_smaller.setFixedSize(36, 32)
        self._btn_smaller.setToolTip("Smaller")
        self._btn_smaller.clicked.connect(self._shrink_font)

        self._btn_bigger = QPushButton("A+")
        self._btn_bigger.setObjectName("toolTinyBtn")
        self._btn_bigger.setFixedSize(36, 32)
        self._btn_bigger.setToolTip("Bigger")
        self._btn_bigger.clicked.connect(self._grow_font)

        self._editor = QTextEdit()
        self._editor.setObjectName("mergeTemplateEditor")
        self._editor.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        self._editor.setPlaceholderText("{name}\n{phone}\n{tracking_number}")
        self._editor.setMinimumHeight(72)
        self._editor.textChanged.connect(self._on_editor_changed)

        self._scene.selectionChanged.connect(self._on_selection)
        self._suppress_editor = False
        self._suppress_font_widgets = False

        lab_fam = QLabel("Font")
        lab_fam.setObjectName("fieldLabel")
        self._font_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        row_add = QHBoxLayout()
        row_add.setSpacing(8)
        row_add.addWidget(self._btn_add, 1)
        row_add.addWidget(self._btn_add_img, 1)

        lab_sz = QLabel("Size (pt)")
        lab_sz.setObjectName("fieldLabel")
        row_sz = QHBoxLayout()
        row_sz.setSpacing(6)
        row_sz.addWidget(lab_sz)
        row_sz.addWidget(self._btn_smaller)
        row_sz.addWidget(self._font_spin)
        row_sz.addWidget(self._btn_bigger)
        row_sz.addStretch(1)

        lab_o = QLabel("Orientation")
        lab_o.setObjectName("fieldLabel")
        self._orientation_combo = QComboBox()
        self._orientation_combo.setObjectName("designerOrientationCombo")
        self._orientation_combo.setMinimumWidth(80)
        self._orientation_combo.addItem("Portrait", ORIENTATION_PORTRAIT)
        self._orientation_combo.addItem("Landscape", ORIENTATION_LANDSCAPE)
        self._orientation_combo.currentIndexChanged.connect(self._on_orientation_changed)
        self._orientation_combo.view().setUniformItemSizes(True)
        self._orientation_combo.blockSignals(True)
        try:
            _oi = self._orientation_combo.findData(self._orientation)
            if _oi >= 0:
                self._orientation_combo.setCurrentIndex(_oi)
        finally:
            self._orientation_combo.blockSignals(False)

        self._lbl_envelope_size = QLabel("Envelope size")
        self._lbl_envelope_size.setObjectName("fieldLabel")
        env_visible = layout_kind == LAYOUT_KIND_ENVELOPE and not self._lock_envelope_size
        self._lbl_envelope_size.setVisible(env_visible)
        self._envelope_combo = QComboBox()
        self._envelope_combo.setObjectName("designerEnvelopeSizeCombo")
        self._envelope_combo.setMinimumWidth(120)
        for eid in ENVELOPE_SIZE_ORDER:
            self._envelope_combo.addItem(ENVELOPE_SIZES[eid][0], eid)
        # macOS/Qt often limits the popup to ~10 rows by default; scrolling hides the last entries.
        self._envelope_combo.setMaxVisibleItems(max(16, len(ENVELOPE_SIZE_ORDER)))
        ei = self._envelope_combo.findData(self._envelope_size_id)
        if ei >= 0:
            self._envelope_combo.setCurrentIndex(ei)
        self._envelope_combo.currentIndexChanged.connect(self._on_envelope_size_changed)
        self._envelope_combo.setVisible(env_visible)

        self._fields_bar = QFrame()
        self._fields_bar.setObjectName("mergeFieldsBar")
        fbl = QVBoxLayout(self._fields_bar)
        fbl.setContentsMargins(0, 0, 0, 0)
        fbl.setSpacing(6)
        self._fields_title = QLabel("Merge fields — click or drag onto the page")
        self._fields_title.setObjectName("fieldLabel")
        fbl.addWidget(self._fields_title)
        self._fields_empty = QLabel(
            "Import a CSV on the Data tab — column shortcodes will appear here."
        )
        self._fields_empty.setObjectName("hint")
        self._fields_empty.setWordWrap(True)
        fbl.addWidget(self._fields_empty)
        self._fields_scroll = QScrollArea()
        self._fields_scroll.setObjectName("mergeFieldsScroll")
        self._fields_scroll.setWidgetResizable(True)
        self._fields_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._fields_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._fields_scroll.setFixedHeight(44)
        self._fields_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._fields_inner = QWidget()
        self._fields_layout = QHBoxLayout(self._fields_inner)
        self._fields_layout.setContentsMargins(0, 4, 0, 4)
        self._fields_layout.setSpacing(8)
        self._fields_scroll.setWidget(self._fields_inner)
        self._fields_scroll.hide()
        fbl.addWidget(self._fields_scroll)

        nav_title = QLabel("Layers")
        nav_title.setObjectName("propsTitle")
        self._layer_list = QListWidget()
        self._layer_list.setObjectName("layerNavigatorList")
        self._layer_list.setAlternatingRowColors(True)
        self._layer_list.setMinimumHeight(100)
        self._layer_list.setMaximumHeight(220)
        self._layer_list.itemClicked.connect(self._on_nav_layer_clicked)

        canvas_frame = QFrame()
        canvas_frame.setObjectName("designerCanvasFrame")

        self._ruler_inches = True
        self._ruler_unit_btn = QToolButton()
        self._ruler_unit_btn.setObjectName("designerRulerCorner")
        self._ruler_unit_btn.setFixedSize(RULER_THICKNESS, RULER_THICKNESS)
        self._ruler_unit_btn.setText("in")
        self._ruler_unit_btn.setAutoRaise(True)
        self._ruler_unit_btn.setToolTip(
            "Ruler units: inches (72 pt = 1 in). Click to switch to typographic points (layout JSON units)."
        )
        self._ruler_unit_btn.clicked.connect(self._toggle_ruler_unit)

        self._ruler_h = CanvasRuler(
            self._view, True, canvas_frame, use_inches=lambda: self._ruler_inches
        )
        self._ruler_v = CanvasRuler(
            self._view, False, canvas_frame, use_inches=lambda: self._ruler_inches
        )

        cfl = QGridLayout(canvas_frame)
        cfl.setContentsMargins(0, 0, 0, 0)
        cfl.setSpacing(0)
        cfl.addWidget(self._ruler_unit_btn, 0, 0)
        cfl.addWidget(self._ruler_h, 0, 1)
        cfl.addWidget(self._ruler_v, 1, 0)
        cfl.addWidget(self._view, 1, 1)
        cfl.setColumnStretch(1, 1)
        cfl.setRowStretch(1, 1)

        pt = QLabel("SELECTED BLOCK")
        pt.setObjectName("propsTitle")
        self._hint = QLabel(
            "Single-click a block to move or resize; double-click text to edit on canvas. "
            "Or edit the merge template below."
        )
        self._hint.setObjectName("hint")
        self._hint.setWordWrap(True)

        et = QLabel("Merge template")
        et.setObjectName("cardTitle")

        hint2 = QLabel(
            "Paste copied shortcodes into the template above, or type {column_name} by hand."
        )
        hint2.setObjectName("hint")
        hint2.setWordWrap(True)

        right_panel = QFrame()
        right_panel.setObjectName("designerRightPanel")
        rp = QVBoxLayout(right_panel)
        rp.setContentsMargins(10, 8, 10, 10)
        rp.setSpacing(8)
        rp.addLayout(row_add)
        rp.addWidget(lab_fam)
        rp.addWidget(self._font_combo)
        rp.addLayout(row_sz)
        rp.addWidget(lab_o)
        rp.addWidget(self._orientation_combo)
        rp.addWidget(self._lbl_envelope_size)
        rp.addWidget(self._envelope_combo)
        rp.addWidget(self._fields_bar)
        rp.addSpacing(4)
        rp.addWidget(nav_title)
        rp.addWidget(self._layer_list)
        rp.addSpacing(4)
        rp.addWidget(pt)
        rp.addWidget(self._hint)
        rp.addWidget(et)
        rp.addWidget(self._editor, stretch=1)
        rp.addWidget(hint2)

        right_scroll = QScrollArea()
        right_scroll.setObjectName("designerRightScroll")
        right_scroll.setWidgetResizable(True)
        right_scroll.setWidget(right_panel)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setMinimumWidth(248)
        right_scroll.setMaximumWidth(384)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        root.addWidget(canvas_frame, 1)
        root.addWidget(right_scroll, 0)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._ruler_filter = _RulerViewportFilter(self._update_rulers)
        self._view.viewport().installEventFilter(self._ruler_filter)
        self._view.horizontalScrollBar().valueChanged.connect(lambda *_: self._update_rulers())
        self._view.verticalScrollBar().valueChanged.connect(lambda *_: self._update_rulers())

        self.layout_changed.connect(self._refresh_layer_navigator)
        self._refresh_layer_navigator()

    def _update_rulers(self) -> None:
        self._ruler_h.update()
        self._ruler_v.update()

    def _page_dims(self) -> tuple[float, float]:
        if self._layout_kind == LAYOUT_KIND_ENVELOPE:
            return get_page_dimensions(
                self._layout_kind,
                self._orientation,
                envelope_size_id=self._envelope_size_id,
            )
        return get_page_dimensions(self._layout_kind, self._orientation)

    def _on_envelope_size_changed(self, _index: int) -> None:
        if self._layout_kind != LAYOUT_KIND_ENVELOPE:
            return
        if self._lock_envelope_size:
            return
        if self._suppress_envelope_ui:
            return
        new_id = self._envelope_combo.currentData()
        if new_id is None:
            return
        new_id = str(new_id)
        if new_id == self._envelope_size_id:
            return
        old_w, old_h = get_page_dimensions(
            LAYOUT_KIND_ENVELOPE,
            self._orientation,
            envelope_size_id=self._envelope_size_id,
        )
        self._envelope_size_id = new_id
        new_w, new_h = get_page_dimensions(
            LAYOUT_KIND_ENVELOPE,
            self._orientation,
            envelope_size_id=self._envelope_size_id,
        )
        sx = new_w / old_w if old_w > 1e-9 else 1.0
        sy = new_h / old_h if old_h > 1e-9 else 1.0
        for it in list(self._scene.items()):
            if not isinstance(it, (TemplateTextItem, TemplateImageItem)) or not it.data(UID_ROLE):
                continue
            it.setPos(QPointF(it.pos().x() * sx, it.pos().y() * sy))
            if isinstance(it, TemplateTextItem):
                tw = it.textWidth()
                if tw > 0:
                    it.setTextWidth(max(48.0, tw * sx))
            else:
                it.set_box_size(max(24.0, it._w * sx), max(24.0, it._h * sy))
        self._scene.set_page_size(new_w, new_h)
        self._scene.sync_selection_chrome()
        self.layout_changed.emit()

    def _toggle_ruler_unit(self) -> None:
        self._ruler_inches = not self._ruler_inches
        self._ruler_unit_btn.setText("in" if self._ruler_inches else "pt")
        self._ruler_unit_btn.setToolTip(
            "Ruler units: typographic points (JSON x/y/w/h). Click to switch to inches."
            if not self._ruler_inches
            else "Ruler units: inches. Click to switch to points."
        )
        self._update_rulers()

    def set_column_keys(self, keys: list[str]) -> None:
        """Show clickable {column} chips from the active import (same order as the Data table)."""
        while self._fields_layout.count():
            item = self._fields_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        if not keys:
            self._fields_empty.setVisible(True)
            self._fields_scroll.hide()
            return

        self._fields_empty.setVisible(False)
        self._fields_scroll.show()
        for key in keys:
            shortcode = f"{{{key}}}"
            btn = MergeFieldChip(shortcode, on_copy=lambda k=key: self._copy_shortcode(k))
            btn.setObjectName("mergeFieldChip")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"Click to copy {shortcode}, or drag onto a selected text block")
            btn.clicked.connect(lambda checked=False, k=key: self._copy_shortcode(k))
            self._fields_layout.addWidget(btn)
        self._fields_layout.addStretch(1)

    def _copy_shortcode(self, key: str) -> None:
        text = f"{{{key}}}"
        QApplication.clipboard().setText(text)
        self.shortcode_copied.emit(text)

    def _on_layout_element(self, item: QGraphicsItem, action: str) -> None:
        if isinstance(item, TemplateTextItem):
            if action == "copy":
                QApplication.clipboard().setText(item.toPlainText())
                return
            if action == "duplicate":
                self._duplicate_text_block(item)
                return
            if action == "delete":
                self._delete_layout_item(item)
                return
        elif isinstance(item, TemplateImageItem):
            if action == "replace_image":
                path, _ = QFileDialog.getOpenFileName(
                    self,
                    "Replace image",
                    "",
                    "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp);;All files (*)",
                )
                if path:
                    item.replace_image_from_path(Path(path))
                return
            if action == "duplicate":
                self._duplicate_image_block(item)
                return
            if action == "delete":
                self._delete_layout_item(item)

    def _duplicate_text_block(self, item: TemplateTextItem) -> None:
        br = item.sceneBoundingRect()
        tw = item.textWidth() or br.width()
        fam = item.font().family()
        el = TextElement(
            uid=str(uuid.uuid4()),
            x=float(item.pos().x()) + 12.0,
            y=float(item.pos().y()) + 12.0,
            w=float(tw),
            h=float(br.height()),
            text=item.toPlainText(),
            font_pt=float(item.font().pointSizeF() or item.font().pointSize() or 11),
            font_family=fam,
        )
        new_item = self._scene.add_text_element(el)
        self._scene.clearSelection()
        new_item.setSelected(True)
        self.layout_changed.emit()

    def _duplicate_image_block(self, item: TemplateImageItem) -> None:
        src = item._resolved_path()
        if not src.is_file():
            return
        template_images_dir().mkdir(parents=True, exist_ok=True)
        dest = template_images_dir() / f"{uuid.uuid4()}{src.suffix.lower()}"
        shutil.copy2(src, dest)
        rel = str(dest.relative_to(app_data_dir()))
        el = ImageElement(
            uid=str(uuid.uuid4()),
            x=float(item.pos().x()) + 12.0,
            y=float(item.pos().y()) + 12.0,
            w=float(item._w),
            h=float(item._h),
            path=rel,
        )
        new_item = self._scene.add_image_element(el)
        if new_item is None:
            return
        self._scene.clearSelection()
        new_item.setSelected(True)
        self.layout_changed.emit()

    def _delete_layout_item(self, item: QGraphicsItem) -> None:
        self._scene.clear_selection_chrome()
        self._scene.removeItem(item)
        self.layout_changed.emit()
        self._on_selection()

    def _on_orientation_changed(self, _index: int) -> None:
        new_o = self._orientation_combo.currentData()
        if new_o is None or new_o == self._orientation:
            return
        self._scene.clear_selection_chrome()
        elems = self._scene.elements_from_scene()
        remap_box_elements(elems)
        self._orientation = str(new_o)
        pw, ph = self._page_dims()
        self._scene.set_page_size(pw, ph)
        for item in list(self._scene.items()):
            if isinstance(item, (TemplateTextItem, TemplateImageItem)) and item.data(UID_ROLE):
                self._scene.removeItem(item)
        z = 0.0
        for el in elems:
            if isinstance(el, TextElement):
                self._scene.add_text_element(el, z=z)
            elif isinstance(el, ImageElement):
                self._scene.add_image_element(el, z=z)
            z += 1.0
        self.fit_view()
        self.layout_changed.emit()

    def _on_canvas_text_drop(self, text: str) -> None:
        item = self._selected_text_item()
        if not item:
            return
        self._suppress_editor = True
        try:
            item.setPlainText(item.toPlainText() + text)
            self._editor.setPlainText(item.toPlainText())
        finally:
            self._suppress_editor = False
        self._scene.sync_selection_chrome()
        self.layout_changed.emit()

    def _setup_view(self) -> None:
        self._view.setObjectName("designerGraphicsView")
        self._view.setStyleSheet(
            "QGraphicsView#designerGraphicsView { background: transparent; border: none; }"
        )
        self._view.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._view.setMinimumHeight(160)
        self._view.setMinimumWidth(220)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rh = QPainter.RenderHint
        self._view.setRenderHints(
            rh.Antialiasing | rh.TextAntialiasing | rh.SmoothPixmapTransform
        )

    def _configure_view_for_page_kind(self) -> None:
        if self._layout_kind in (LAYOUT_KIND_A4, LAYOUT_KIND_US_LETTER):
            self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._layout_kind not in (LAYOUT_KIND_A4, LAYOUT_KIND_US_LETTER):
            self.fit_view()
        self._update_rulers()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._update_rulers()

    def _selected_text_item(self) -> TemplateTextItem | None:
        for it in self._scene.selectedItems():
            if isinstance(it, TemplateTextItem) and it.data(UID_ROLE):
                return it
        return None

    def _selected_image_item(self) -> TemplateImageItem | None:
        for it in self._scene.selectedItems():
            if isinstance(it, TemplateImageItem) and it.data(UID_ROLE):
                return it
        return None

    def _find_item_by_uid(self, uid: str) -> QGraphicsItem | None:
        for it in self._scene.items():
            if isinstance(it, (TemplateTextItem, TemplateImageItem)) and str(it.data(UID_ROLE)) == uid:
                return it
        return None

    def _refresh_layer_navigator(self) -> None:
        self._suppress_nav = True
        try:
            self._layer_list.clear()
            for el in self._scene.elements_from_scene():
                if isinstance(el, TextElement):
                    preview = el.text.replace("\n", " ")[:40]
                    label = f"Text · {preview}{'…' if len(el.text) > 40 else ''}"
                elif isinstance(el, ImageElement):
                    label = f"Image · {Path(el.path).name}"
                else:
                    continue
                lw = QListWidgetItem(label)
                lw.setData(Qt.ItemDataRole.UserRole, el.uid)
                self._layer_list.addItem(lw)
        finally:
            self._suppress_nav = False
        self._sync_nav_from_selection()

    def _sync_nav_from_selection(self) -> None:
        if self._suppress_nav:
            return
        sel_uid: str | None = None
        for it in self._scene.selectedItems():
            if isinstance(it, (TemplateTextItem, TemplateImageItem)) and it.data(UID_ROLE):
                sel_uid = str(it.data(UID_ROLE))
                break
        self._suppress_nav = True
        try:
            if sel_uid is None:
                self._layer_list.clearSelection()
                return
            for i in range(self._layer_list.count()):
                item = self._layer_list.item(i)
                u = item.data(Qt.ItemDataRole.UserRole)
                if u is not None and str(u) == sel_uid:
                    self._layer_list.setCurrentItem(item)
                    return
            self._layer_list.clearSelection()
        finally:
            self._suppress_nav = False

    def _on_nav_layer_clicked(self, item: QListWidgetItem) -> None:
        if self._suppress_nav:
            return
        uid = item.data(Qt.ItemDataRole.UserRole)
        if uid is None:
            return
        found = self._find_item_by_uid(str(uid))
        if found is None:
            return
        self._scene.clearSelection()
        found.setSelected(True)
        self._view.ensureVisible(found, 48, 48)

    def _on_selection(self) -> None:
        text_item = self._selected_text_item()
        img_item = self._selected_image_item()
        self._suppress_editor = True
        self._suppress_font_widgets = True
        self._font_combo.blockSignals(True)
        try:
            font_enabled = text_item is not None
            self._font_combo.setEnabled(font_enabled)
            self._font_spin.setEnabled(font_enabled)
            self._btn_smaller.setEnabled(font_enabled)
            self._btn_bigger.setEnabled(font_enabled)
            if text_item:
                self._editor.setReadOnly(False)
                self._editor.setPlainText(text_item.toPlainText())
                f = text_item.font()
                self._font_spin.setValue(int(round(f.pointSizeF() or f.pointSize() or 11)))
                self._font_combo.setCurrentFont(f)
                self._hint.setText(
                    "Drag the block to move it. Drag the purple handle on the right edge to change line width."
                )
            elif img_item:
                self._editor.setReadOnly(True)
                self._editor.clear()
                self._hint.setText(
                    "Drag to move or resize. Right‑click the image → Replace image… or Duplicate."
                )
            else:
                self._editor.setReadOnly(True)
                self._editor.clear()
                _surf = "page" if self._layout_kind in (LAYOUT_KIND_A4, LAYOUT_KIND_US_LETTER) else "envelope"
                self._hint.setText(
                    f"Click a block on the {_surf}, then edit merge fields below."
                )
        finally:
            self._font_combo.blockSignals(False)
            self._suppress_editor = False
            self._suppress_font_widgets = False
        self._scene.sync_selection_chrome()
        self._sync_nav_from_selection()

    def _on_font_combo_changed(self, font: QFont) -> None:
        if self._suppress_font_widgets:
            return
        item = self._selected_text_item()
        if not item:
            return
        new_f = QFont(font)
        new_f.setPointSizeF(float(self._font_spin.value()))
        item.setFont(new_f)
        self._scene.sync_selection_chrome()
        self.layout_changed.emit()

    def _apply_font_size_to_selection(self) -> None:
        if self._suppress_font_widgets:
            return
        item = self._selected_text_item()
        if not item:
            return
        f = item.font()
        f.setPointSize(self._font_spin.value())
        item.setFont(f)
        self._scene.sync_selection_chrome()
        self.layout_changed.emit()

    def _shrink_font(self) -> None:
        self._font_spin.setValue(max(6, self._font_spin.value() - 1))

    def _grow_font(self) -> None:
        self._font_spin.setValue(min(96, self._font_spin.value() + 1))

    def _on_editor_changed(self) -> None:
        if self._suppress_editor:
            return
        item = self._selected_text_item()
        if not item:
            return
        item.setPlainText(self._editor.toPlainText())
        self._scene.sync_selection_chrome()
        self.layout_changed.emit()

    def _add_block(self) -> None:
        fam = self._font_combo.currentFont().family()
        pw, ph = self._page_dims()
        el = TextElement(
            uid=str(uuid.uuid4()),
            x=48.0,
            y=ph / 3.0,
            w=pw - 96.0,
            h=80.0,
            text="{name}",
            font_pt=float(self._font_spin.value()),
            font_family=fam,
        )
        item = self._scene.add_text_element(el)
        self._scene.clearSelection()
        item.setSelected(True)
        self.layout_changed.emit()

    def _add_image_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Add image",
            "",
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp);;All files (*)",
        )
        if not path:
            return
        self._add_image_from_path(Path(path))

    def _add_image_from_path(self, src: Path) -> None:
        if not src.is_file():
            return
        template_images_dir().mkdir(parents=True, exist_ok=True)
        dest = template_images_dir() / f"{uuid.uuid4()}{src.suffix.lower()}"
        shutil.copy2(src, dest)
        rel = str(dest.relative_to(app_data_dir()))
        pm = QPixmap(str(dest))
        if pm.isNull():
            return
        ow = max(pm.width(), 1)
        oh = pm.height()
        pw, ph = self._page_dims()
        tw = min(200.0, max(48.0, pw - 96.0))
        th = tw * (oh / ow)
        el = ImageElement(
            uid=str(uuid.uuid4()),
            x=48.0,
            y=ph / 4.0,
            w=tw,
            h=th,
            path=rel,
        )
        new_item = self._scene.add_image_element(el)
        if new_item is None:
            return
        self._scene.clearSelection()
        new_item.setSelected(True)
        self.layout_changed.emit()

    def load_layout_json(self, layout_json: str) -> None:
        self._scene.clear_selection_chrome()
        o = layout_orientation(layout_json)
        self._orientation_combo.blockSignals(True)
        try:
            idx = self._orientation_combo.findData(o)
            if idx >= 0:
                self._orientation_combo.setCurrentIndex(idx)
            self._orientation = o
        finally:
            self._orientation_combo.blockSignals(False)
        self._suppress_envelope_ui = True
        try:
            if self._layout_kind == LAYOUT_KIND_ENVELOPE:
                self._envelope_combo.blockSignals(True)
                try:
                    self._envelope_size_id = read_envelope_size_id(layout_json)
                    ei = self._envelope_combo.findData(self._envelope_size_id)
                    if ei >= 0:
                        self._envelope_combo.setCurrentIndex(ei)
                finally:
                    self._envelope_combo.blockSignals(False)
            pw, ph = page_size_points_from_layout_json(layout_json)
            self._scene.set_page_size(pw, ph)
        finally:
            self._suppress_envelope_ui = False
        for item in list(self._scene.items()):
            if isinstance(item, (TemplateTextItem, TemplateImageItem)) and item.data(UID_ROLE):
                self._scene.removeItem(item)
        z = 0.0
        for el in parse_layout(layout_json):
            if isinstance(el, TextElement):
                self._scene.add_text_element(el, z=z)
            elif isinstance(el, ImageElement):
                self._scene.add_image_element(el, z=z)
            z += 1.0
        self.fit_view()
        self.layout_changed.emit()

    def layout_json(self) -> str:
        eid = self._envelope_size_id if self._layout_kind == LAYOUT_KIND_ENVELOPE else None
        return layout_to_json(
            self._scene.elements_from_scene(),
            self._orientation,
            layout_kind=self._layout_kind,
            envelope_size_id=eid,
        )

    def preview_merge(self, row: dict[str, Any]) -> None:
        for item in self._scene.items():
            if not isinstance(item, QGraphicsTextItem):
                continue
            if not item.data(UID_ROLE):
                continue
            raw = item.toPlainText()
            merged = merge_template(raw, row)
            item.setPlainText(merged)
        self._scene.sync_selection_chrome()

    def restore_templates_after_preview(self, backup: list[tuple[str, str]]) -> None:
        for item in self._scene.items():
            if not isinstance(item, QGraphicsTextItem):
                continue
            uid = item.data(UID_ROLE)
            if not uid:
                continue
            for u, text in backup:
                if u == str(uid):
                    item.setPlainText(text)
                    break
        self._scene.sync_selection_chrome()

    def snapshot_texts(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for item in self._scene.items():
            if not isinstance(item, QGraphicsTextItem):
                continue
            uid = item.data(UID_ROLE)
            if not uid:
                continue
            out.append((str(uid), item.toPlainText()))
        return out

    def fit_view(self) -> None:
        r = self._scene.sceneRect()
        self._view.resetTransform()
        if self._layout_kind in (LAYOUT_KIND_A4, LAYOUT_KIND_US_LETTER):
            self._view.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            vp = self._view.viewport().rect()
            margin = 24.0
            usable_w = max(float(vp.width()) - margin, 160.0)
            scale = usable_w / r.width() if r.width() > 0 else 1.0
            scale = max(0.5, min(scale, 4.0))
            self._view.scale(scale, scale)
            self._view.horizontalScrollBar().setValue(self._view.horizontalScrollBar().minimum())
            self._view.verticalScrollBar().setValue(self._view.verticalScrollBar().minimum())
        else:
            self._view.fitInView(r, Qt.AspectRatioMode.KeepAspectRatio)
        self._update_rulers()
