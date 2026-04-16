from __future__ import annotations

import shutil
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QMimeData, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QDrag,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QFont,
    QMouseEvent,
    QPainter,
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
    QSizePolicy,
    QSplitter,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from envelope_app.layout import (
    LAYOUT_KIND_A4,
    LAYOUT_KIND_ENVELOPE,
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
    parse_layout,
    remap_box_elements,
)
from envelope_app.paths import app_data_dir, template_images_dir
from envelope_app.merge import merge_template


UID_ROLE = Qt.ItemDataRole.UserRole + 1

# Readable default for new blocks (avoid decorative “Academy Engraved” as first combo pick).
_DEFAULT_UI_FONT = "Arial"


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


class ResizeHandleItem(QGraphicsRectItem):
    """Right-edge handle to resize width (text wrap column or image width)."""

    def __init__(
        self,
        apply_width: Callable[[float], None],
        on_change: Callable[[], None],
        start_width_fn: Callable[[], float],
    ) -> None:
        super().__init__()
        self._apply_width = apply_width
        self._on_change = on_change
        self._start_width_fn = start_width_fn
        self._press_scene_x: float | None = None
        self._start_w: float = 0.0
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setPen(QPen(QColor("#4338ca"), 1))
        self.setBrush(QColor(238, 242, 255, 230))
        self.setZValue(11)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_scene_x = event.scenePos().x()
            self._start_w = self._start_width_fn()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton and self._press_scene_x is not None:
            dx = event.scenePos().x() - self._press_scene_x
            new_w = max(48.0, self._start_w + dx)
            self._apply_width(new_w)
            self._on_change()
            sc = self.scene()
            if sc is not None and hasattr(sc, "sync_selection_chrome"):
                sc.sync_selection_chrome()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self._press_scene_x = None
        super().mouseReleaseEvent(event)


class EnvelopeScene(QGraphicsScene):
    layout_element_context = Signal(QGraphicsItem, str)

    def __init__(self) -> None:
        super().__init__()
        self._on_change: Callable[[], None] | None = None
        self._border: QGraphicsRectItem | None = None
        self._chrome_frame: QGraphicsRectItem | None = None
        self._chrome_handle: ResizeHandleItem | None = None
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
        if self._chrome_handle is not None:
            self.removeItem(self._chrome_handle)
            self._chrome_handle = None

    def _set_selection_chrome(self, target: QGraphicsItem) -> None:
        self._clear_selection_chrome()
        self._chrome_target = target
        self._chrome_frame = QGraphicsRectItem()
        self._chrome_frame.setZValue(10)
        self._chrome_frame.setPen(QPen(QColor("#6366f1"), 1.5, Qt.PenStyle.DashLine))
        self._chrome_frame.setBrush(Qt.BrushStyle.NoBrush)
        self._chrome_frame.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.addItem(self._chrome_frame)

        if isinstance(target, TemplateTextItem):

            def start_w() -> float:
                tw = target.textWidth()
                return float(tw) if tw > 0 else target.boundingRect().width()

            self._chrome_handle = ResizeHandleItem(
                lambda w: target.setTextWidth(w),
                self._emit_layout,
                start_w,
            )
        elif isinstance(target, TemplateImageItem):
            self._chrome_handle = ResizeHandleItem(
                lambda w: target.set_box_width(w),
                self._emit_layout,
                lambda: float(target._w),
            )
        else:
            self._chrome_handle = None

        if self._chrome_handle is not None:
            self.addItem(self._chrome_handle)
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
        if self._chrome_handle is not None:
            hw, hh = 10.0, 30.0
            self._chrome_handle.setPos(br.right() - hw, br.center().y() - hh * 0.5)
            self._chrome_handle.setRect(0, 0, hw, hh)

    def set_page_size(self, pw: float, ph: float) -> None:
        if self._border is not None:
            self.removeItem(self._border)
            self._border = None
        self.setSceneRect(0, 0, pw, ph)
        border = self.addRect(QRectF(0, 0, pw, ph), QPen(QColor(148, 163, 184), 1.0))
        border.setZValue(-1)
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
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
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


class DesignerGraphicsView(QGraphicsView):
    text_dropped = Signal(str)
    canvas_add_requested = Signal()
    canvas_add_image_requested = Signal()

    def __init__(self, scene: QGraphicsScene, parent: QWidget | None = None) -> None:
        super().__init__(scene, parent)
        self.setAcceptDrops(True)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        scene_pos = self.mapToScene(event.pos())
        item = self.scene().itemAt(scene_pos, self.transform())
        if isinstance(item, TemplateTextItem) and item.data(UID_ROLE):
            return super().contextMenuEvent(event)
        if isinstance(item, TemplateImageItem) and item.data(UID_ROLE):
            return super().contextMenuEvent(event)
        if isinstance(item, ResizeHandleItem):
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
    ) -> None:
        super().__init__(parent)
        self._suppress_nav = False
        self._layout_kind = layout_kind
        self._orientation = ORIENTATION_PORTRAIT
        self._scene = EnvelopeScene()
        self._scene._on_change = self.layout_changed.emit
        pw, ph = get_page_dimensions(self._layout_kind, self._orientation)
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
        self._editor.setMinimumHeight(140)
        self._editor.textChanged.connect(self._on_editor_changed)

        self._scene.selectionChanged.connect(self._on_selection)
        self._suppress_editor = False
        self._suppress_font_widgets = False

        row1 = QHBoxLayout()
        row1.setSpacing(12)
        row1.addWidget(self._btn_add)
        row1.addWidget(self._btn_add_img)
        lab_fam = QLabel("Font")
        lab_fam.setObjectName("fieldLabel")
        row1.addWidget(lab_fam)
        self._font_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row1.addWidget(self._font_combo, stretch=1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        lab_sz = QLabel("Size (pt)")
        lab_sz.setObjectName("fieldLabel")
        row2.addWidget(lab_sz)
        row2.addWidget(self._btn_smaller)
        row2.addWidget(self._font_spin)
        row2.addWidget(self._btn_bigger)
        row2.addStretch(1)
        lab_o = QLabel("Orientation")
        lab_o.setObjectName("fieldLabel")
        row2.addWidget(lab_o)
        self._orientation_combo = QComboBox()
        self._orientation_combo.setObjectName("designerOrientationCombo")
        self._orientation_combo.setMinimumWidth(120)
        self._orientation_combo.addItem("Portrait", ORIENTATION_PORTRAIT)
        self._orientation_combo.addItem("Landscape", ORIENTATION_LANDSCAPE)
        self._orientation_combo.currentIndexChanged.connect(self._on_orientation_changed)
        self._orientation_combo.view().setUniformItemSizes(True)
        row2.addWidget(self._orientation_combo)

        self._fields_bar = QFrame()
        self._fields_bar.setObjectName("mergeFieldsBar")
        fbl = QVBoxLayout(self._fields_bar)
        fbl.setContentsMargins(0, 0, 0, 0)
        fbl.setSpacing(6)
        self._fields_title = QLabel("Available fields from your list (click or drag onto the envelope)")
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

        nav_frame = QFrame()
        nav_frame.setObjectName("layerNavigator")
        nav_frame.setMinimumWidth(180)
        nav_frame.setMaximumWidth(300)
        nvl = QVBoxLayout(nav_frame)
        nvl.setContentsMargins(0, 0, 0, 0)
        nvl.setSpacing(6)
        nav_title = QLabel("Layers")
        nav_title.setObjectName("propsTitle")
        self._layer_list = QListWidget()
        self._layer_list.setObjectName("layerNavigatorList")
        self._layer_list.setAlternatingRowColors(True)
        self._layer_list.itemClicked.connect(self._on_nav_layer_clicked)
        nvl.addWidget(nav_title)
        nvl.addWidget(self._layer_list, stretch=1)

        canvas_frame = QFrame()
        canvas_frame.setObjectName("designerCanvasFrame")
        cfl = QVBoxLayout(canvas_frame)
        cfl.setContentsMargins(0, 0, 0, 0)
        cfl.addWidget(self._view)

        props = QFrame()
        props.setObjectName("propsPanel")
        props.setMinimumWidth(280)
        props.setMaximumWidth(420)
        pv = QVBoxLayout(props)
        pv.setContentsMargins(16, 16, 16, 16)
        pv.setSpacing(8)

        pt = QLabel("SELECTED BLOCK")
        pt.setObjectName("propsTitle")
        self._hint = QLabel("Click a block on the envelope, then edit merge fields below.")
        self._hint.setObjectName("hint")
        self._hint.setWordWrap(True)

        et = QLabel("Merge template")
        et.setObjectName("cardTitle")

        pv.addWidget(pt)
        pv.addWidget(self._hint)
        pv.addSpacing(4)
        pv.addWidget(et)
        pv.addWidget(self._editor, stretch=1)

        hint2 = QLabel(
            "Paste copied shortcodes into the template above, or type {column_name} by hand."
        )
        hint2.setObjectName("hint")
        hint2.setWordWrap(True)
        pv.addWidget(hint2)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setObjectName("designerSplit")
        split.setChildrenCollapsible(False)
        split.addWidget(nav_frame)
        split.addWidget(canvas_frame)
        split.addWidget(props)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 3)
        split.setStretchFactor(2, 1)
        split.setSizes([220, 780, 320])

        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        col.addLayout(row1)
        col.addLayout(row2)
        col.addWidget(self._fields_bar)
        col.addWidget(split, stretch=1)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.layout_changed.connect(self._refresh_layer_navigator)
        self._refresh_layer_navigator()

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
        pw, ph = get_page_dimensions(self._layout_kind, self._orientation)
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
        self._view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self._view.setMinimumHeight(300)
        self._view.setMinimumWidth(400)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rh = QPainter.RenderHint
        self._view.setRenderHints(
            rh.Antialiasing | rh.TextAntialiasing | rh.SmoothPixmapTransform
        )

    def _configure_view_for_page_kind(self) -> None:
        if self._layout_kind == LAYOUT_KIND_A4:
            self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._layout_kind == LAYOUT_KIND_A4:
            return
        self.fit_view()

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
                self._hint.setText(
                    f"Click a block on the {'page' if self._layout_kind == LAYOUT_KIND_A4 else 'envelope'}, "
                    "then edit merge fields below."
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
        pw, ph = get_page_dimensions(self._layout_kind, self._orientation)
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
        pw, ph = get_page_dimensions(self._layout_kind, self._orientation)
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
        pw, ph = get_page_dimensions(self._layout_kind, self._orientation)
        self._scene.set_page_size(pw, ph)
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
        return layout_to_json(
            self._scene.elements_from_scene(),
            self._orientation,
            layout_kind=self._layout_kind,
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
        if self._layout_kind == LAYOUT_KIND_A4:
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
