from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Sequence, Union

# US #10 envelope — points (1 pt = 1/72 in)
PAGE_W_PT = 4.125 * 72.0
PAGE_H_PT = 9.5 * 72.0

# ISO A4 — points (210 mm × 297 mm)
A4_W_PT = 210.0 * 72.0 / 25.4
A4_H_PT = 297.0 * 72.0 / 25.4

LAYOUT_VERSION = 1

ORIENTATION_PORTRAIT = "portrait"
ORIENTATION_LANDSCAPE = "landscape"

LAYOUT_KIND_ENVELOPE = "envelope"
LAYOUT_KIND_A4 = "a4"

LayoutElement = Union["TextElement", "ImageElement"]


def get_page_dimensions(layout_kind: str, orientation: str) -> tuple[float, float]:
    """Return page width/height in pt for envelope #10 or A4; swap for landscape."""
    if layout_kind == LAYOUT_KIND_A4:
        w, h = A4_W_PT, A4_H_PT
    else:
        w, h = PAGE_W_PT, PAGE_H_PT
    if orientation == ORIENTATION_LANDSCAPE:
        return h, w
    return w, h


def read_layout_kind(layout_json: str) -> str:
    """Envelope vs A4; infer from stored page size when `layout_kind` is missing (legacy files)."""
    try:
        data = json.loads(layout_json)
    except (json.JSONDecodeError, TypeError):
        return LAYOUT_KIND_ENVELOPE
    if not isinstance(data, dict):
        return LAYOUT_KIND_ENVELOPE
    k = data.get("layout_kind")
    if k in (LAYOUT_KIND_ENVELOPE, LAYOUT_KIND_A4):
        return str(k)
    page = data.get("page")
    if isinstance(page, dict):
        pw = float(page.get("width_pt", PAGE_W_PT))
        ph = float(page.get("height_pt", PAGE_H_PT))
        short, long_ = min(pw, ph), max(pw, ph)
        a4s, a4l = min(A4_W_PT, A4_H_PT), max(A4_W_PT, A4_H_PT)
        if abs(short - a4s) < 3.0 and abs(long_ - a4l) < 3.0:
            return LAYOUT_KIND_A4
    return LAYOUT_KIND_ENVELOPE


def layout_orientation(layout_json: str) -> str:
    """Read orientation from saved layout; infer from page size for older files."""
    try:
        data = json.loads(layout_json)
    except (json.JSONDecodeError, TypeError):
        return ORIENTATION_PORTRAIT
    if not isinstance(data, dict):
        return ORIENTATION_PORTRAIT
    o = data.get("orientation")
    if o in (ORIENTATION_PORTRAIT, ORIENTATION_LANDSCAPE):
        return str(o)
    page = data.get("page")
    if isinstance(page, dict):
        pw = float(page.get("width_pt", PAGE_W_PT))
        ph = float(page.get("height_pt", PAGE_H_PT))
        if pw > ph:
            return ORIENTATION_LANDSCAPE
    return ORIENTATION_PORTRAIT


def remap_box_elements(elements: Sequence[LayoutElement]) -> None:
    """Swap x↔y and w↔h for each block when toggling portrait ↔ landscape."""
    for e in elements:
        e.x, e.y = e.y, e.x
        e.w, e.h = e.h, e.w


def remap_elements_for_orientation(elements: list[TextElement]) -> None:
    """Backward-compatible name for text-only callers."""
    remap_box_elements(elements)


@dataclass
class TextElement:
    uid: str
    x: float
    y: float
    w: float
    h: float
    text: str
    font_pt: float
    font_family: str = ""


@dataclass
class ImageElement:
    """path is relative to app data directory (e.g. template_images/abc.png)."""

    uid: str
    x: float
    y: float
    w: float
    h: float
    path: str


def default_layout() -> str:
    el = TextElement(
        uid=str(uuid.uuid4()),
        x=36.0,
        y=72.0,
        w=PAGE_W_PT - 72.0,
        h=120.0,
        text="{name}\n{phone}",
        font_pt=11.0,
        font_family="",
    )
    return layout_to_json([el], ORIENTATION_PORTRAIT, layout_kind=LAYOUT_KIND_ENVELOPE)


def default_a4_layout() -> str:
    pw, _ph = get_page_dimensions(LAYOUT_KIND_A4, ORIENTATION_PORTRAIT)
    el = TextElement(
        uid=str(uuid.uuid4()),
        x=48.0,
        y=72.0,
        w=pw - 96.0,
        h=120.0,
        text="{name}\n{phone}",
        font_pt=11.0,
        font_family="",
    )
    return layout_to_json([el], ORIENTATION_PORTRAIT, layout_kind=LAYOUT_KIND_A4)


def layout_to_json(
    elements: Sequence[LayoutElement],
    orientation: str = ORIENTATION_PORTRAIT,
    *,
    layout_kind: str = LAYOUT_KIND_ENVELOPE,
) -> str:
    """Serialize a mixed ordered list of text and image elements."""
    pw, ph = get_page_dimensions(layout_kind, orientation)
    out_el: list[dict[str, Any]] = []
    for e in elements:
        if isinstance(e, TextElement):
            out_el.append(
                {
                    "type": "text",
                    "id": e.uid,
                    "x": e.x,
                    "y": e.y,
                    "w": e.w,
                    "h": e.h,
                    "text": e.text,
                    "font_pt": e.font_pt,
                    "font_family": e.font_family,
                }
            )
        elif isinstance(e, ImageElement):
            out_el.append(
                {
                    "type": "image",
                    "id": e.uid,
                    "x": e.x,
                    "y": e.y,
                    "w": e.w,
                    "h": e.h,
                    "path": e.path,
                }
            )
    data: dict[str, Any] = {
        "version": LAYOUT_VERSION,
        "layout_kind": layout_kind,
        "orientation": orientation,
        "page": {"width_pt": pw, "height_pt": ph},
        "elements": out_el,
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def parse_layout(layout_json: str) -> list[LayoutElement]:
    """Parse elements in file order (z-order on load: first = bottom)."""
    data = json.loads(layout_json)
    if not isinstance(data, dict):
        return []
    raw = data.get("elements")
    if not isinstance(raw, list):
        return []
    out: list[LayoutElement] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        typ = item.get("type")
        if typ == "text":
            uid = str(item.get("id") or uuid.uuid4())
            out.append(
                TextElement(
                    uid=uid,
                    x=float(item.get("x", 0)),
                    y=float(item.get("y", 0)),
                    w=float(item.get("w", 100)),
                    h=float(item.get("h", 40)),
                    text=str(item.get("text", "")),
                    font_pt=float(item.get("font_pt", 11)),
                    font_family=str(item.get("font_family", "") or ""),
                )
            )
        elif typ == "image":
            uid = str(item.get("id") or uuid.uuid4())
            out.append(
                ImageElement(
                    uid=uid,
                    x=float(item.get("x", 0)),
                    y=float(item.get("y", 0)),
                    w=float(item.get("w", 120)),
                    h=float(item.get("h", 80)),
                    path=str(item.get("path", "")),
                )
            )
    return out


def parse_layout_texts_only(layout_json: str) -> list[TextElement]:
    """Legacy helper: only text blocks (e.g. if images absent)."""
    return [e for e in parse_layout(layout_json) if isinstance(e, TextElement)]
