from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Sequence, Union

# Typographic points (1 pt = 1/72 inch)
_PT = 72.0


def _in(w_in: float, h_in: float) -> tuple[float, float]:
    """Portrait page size in pt: width × height (width ≤ height)."""
    w_pt, h_pt = w_in * _PT, h_in * _PT
    return (min(w_pt, h_pt), max(w_pt, h_pt))


# —— US #10 (legacy constants; catalog entry env_10 matches)
PAGE_W_PT = 4.125 * _PT
PAGE_H_PT = 9.5 * _PT

# ISO A4 — points (210 mm × 297 mm)
A4_W_PT = 210.0 * _PT / 25.4
A4_H_PT = 297.0 * _PT / 25.4

# US Letter — 8.5 × 11 in
LAYOUT_KIND_US_LETTER = "us_letter"
US_LETTER_W_PT = 8.5 * _PT
US_LETTER_H_PT = 11.0 * _PT

LAYOUT_VERSION = 1

ORIENTATION_PORTRAIT = "portrait"
ORIENTATION_LANDSCAPE = "landscape"

LAYOUT_KIND_ENVELOPE = "envelope"
LAYOUT_KIND_A4 = "a4"

LayoutElement = Union["TextElement", "ImageElement"]


# Stable id → (label, width_in, height_in) portrait; dimensions follow common US commercial sizes.
ENVELOPE_SIZES: dict[str, tuple[str, float, float]] = {
    "env_6_25": ("6-1/4 envelope", *_in(3.5, 6.0)),
    "env_6_75": ("6-3/4 envelope", *_in(3.625, 6.5)),
    "env_7": ("7 envelope", *_in(3.75, 6.75)),
    "env_8_625": ("8-5/8 envelope", *_in(3.625, 8.625)),
    "env_9": ("9 envelope", *_in(3.875, 8.875)),
    "env_11": ("11 envelope", *_in(4.5, 10.375)),
    "env_12": ("12 envelope", *_in(4.75, 11.0)),
    "env_14": ("14 envelope", *_in(5.0, 11.5)),
    "env_6": ("6 envelope", *_in(3.625, 6.5)),
    "env_6_5": ("6-1/2 envelope", *_in(3.5, 6.5)),
    "env_6_625": ("6-5/8 envelope", *_in(3.625, 6.625)),
    "env_9_5": ("9-1/2 envelope", *_in(4.0, 9.25)),
    "env_10": ("10 envelope (#10)", *_in(4.125, 9.5)),
    "env_6x9": ("6 × 9 envelope", *_in(6.0, 9.0)),
    "env_9x12": ("9 × 12 envelope", *_in(9.0, 12.0)),
    "env_10x13": ("10 × 13 envelope", *_in(10.0, 13.0)),
    # Direct thermal rolls (often 2.625″ wide × 1″ tall face stock)
    "label_dt_2625x1": ("2.625 × 1 in Direct Thermal Labels", *_in(2.625, 1.0)),
}

# Combo order (matches client list; duplicates merged into one row each)
ENVELOPE_SIZE_ORDER: tuple[str, ...] = (
    "env_6_25",
    "env_6_75",
    "env_7",
    "env_8_625",
    "env_9",
    "env_11",
    "env_12",
    "env_14",
    "env_6",
    "env_6_5",
    "env_6_625",
    "env_9_5",
    "env_10",
    "env_6x9",
    "env_9x12",
    "env_10x13",
)

DEFAULT_ENVELOPE_SIZE_ID = "env_10"

# Direct thermal 2.625″ × 1″ — used as its own “Design for” layout (fixed size).
LABEL_DT_THERMAL_ID = "label_dt_2625x1"


def envelope_dimensions_pt(size_id: str) -> tuple[float, float]:
    """Return (width_pt, height_pt) portrait for an envelope size id."""
    if size_id not in ENVELOPE_SIZES:
        size_id = DEFAULT_ENVELOPE_SIZE_ID
    _label, w_pt, h_pt = ENVELOPE_SIZES[size_id]
    assert isinstance(w_pt, (int, float)) and isinstance(h_pt, (int, float))
    return float(w_pt), float(h_pt)


def get_page_dimensions(
    layout_kind: str,
    orientation: str,
    *,
    envelope_size_id: str | None = None,
) -> tuple[float, float]:
    """Return page width/height in pt; swap for landscape."""
    if layout_kind == LAYOUT_KIND_A4:
        w, h = A4_W_PT, A4_H_PT
    elif layout_kind == LAYOUT_KIND_US_LETTER:
        w, h = US_LETTER_W_PT, US_LETTER_H_PT
    else:
        eid = envelope_size_id or DEFAULT_ENVELOPE_SIZE_ID
        w, h = envelope_dimensions_pt(eid)
    if orientation == ORIENTATION_LANDSCAPE:
        return h, w
    return w, h


def read_envelope_size_id(layout_json: str) -> str:
    """Read envelope_size field from JSON; otherwise default."""
    try:
        data = json.loads(layout_json)
    except (json.JSONDecodeError, TypeError):
        return DEFAULT_ENVELOPE_SIZE_ID
    if not isinstance(data, dict):
        return DEFAULT_ENVELOPE_SIZE_ID
    v = data.get("envelope_size")
    if isinstance(v, str) and v in ENVELOPE_SIZES:
        return v
    return DEFAULT_ENVELOPE_SIZE_ID


def page_size_points_from_layout_json(layout_json: str) -> tuple[float, float]:
    """Use saved page rect if present; else derive from kind + options."""
    try:
        data = json.loads(layout_json)
        if isinstance(data, dict):
            page = data.get("page")
            if isinstance(page, dict):
                pw = page.get("width_pt")
                ph = page.get("height_pt")
                if pw is not None and ph is not None:
                    return float(pw), float(ph)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    lk = read_layout_kind(layout_json)
    orient = layout_orientation(layout_json)
    eid = read_envelope_size_id(layout_json) if lk == LAYOUT_KIND_ENVELOPE else None
    return get_page_dimensions(lk, orient, envelope_size_id=eid)


def read_layout_kind(layout_json: str) -> str:
    """Envelope vs A4 vs US Letter; infer from stored page when keys missing."""
    try:
        data = json.loads(layout_json)
    except (json.JSONDecodeError, TypeError):
        return LAYOUT_KIND_ENVELOPE
    if not isinstance(data, dict):
        return LAYOUT_KIND_ENVELOPE
    k = data.get("layout_kind")
    if k in (LAYOUT_KIND_ENVELOPE, LAYOUT_KIND_A4, LAYOUT_KIND_US_LETTER):
        return str(k)
    page = data.get("page")
    if isinstance(page, dict):
        try:
            pw = float(page.get("width_pt", PAGE_W_PT))
            ph = float(page.get("height_pt", PAGE_H_PT))
        except (TypeError, ValueError):
            return LAYOUT_KIND_ENVELOPE
        short, long_ = min(pw, ph), max(pw, ph)
        a4s, a4l = min(A4_W_PT, A4_H_PT), max(A4_W_PT, A4_H_PT)
        if abs(short - a4s) < 3.0 and abs(long_ - a4l) < 3.0:
            return LAYOUT_KIND_A4
        let_s, let_l = min(US_LETTER_W_PT, US_LETTER_H_PT), max(US_LETTER_W_PT, US_LETTER_H_PT)
        if abs(short - let_s) < 3.0 and abs(long_ - let_l) < 3.0:
            return LAYOUT_KIND_US_LETTER
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
        try:
            pw = float(page.get("width_pt", PAGE_W_PT))
            ph = float(page.get("height_pt", PAGE_H_PT))
        except (TypeError, ValueError):
            return ORIENTATION_PORTRAIT
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


def default_thermal_label_layout() -> str:
    """Default layout for locked 2.625″ × 1″ thermal stock (typically landscape on the roll)."""
    pw, ph = get_page_dimensions(
        LAYOUT_KIND_ENVELOPE,
        ORIENTATION_LANDSCAPE,
        envelope_size_id=LABEL_DT_THERMAL_ID,
    )
    mx = min(24.0, pw * 0.08)
    my = min(18.0, ph * 0.12)
    el = TextElement(
        uid=str(uuid.uuid4()),
        x=mx,
        y=my,
        w=max(pw - 2 * mx, 36.0),
        h=max(min(48.0, ph - 2 * my), 20.0),
        text="{name}",
        font_pt=10.0,
        font_family="",
    )
    return layout_to_json(
        [el],
        ORIENTATION_LANDSCAPE,
        layout_kind=LAYOUT_KIND_ENVELOPE,
        envelope_size_id=LABEL_DT_THERMAL_ID,
    )


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
    return layout_to_json(
        [el],
        ORIENTATION_PORTRAIT,
        layout_kind=LAYOUT_KIND_ENVELOPE,
        envelope_size_id=DEFAULT_ENVELOPE_SIZE_ID,
    )


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


def default_us_letter_layout() -> str:
    pw, _ph = get_page_dimensions(LAYOUT_KIND_US_LETTER, ORIENTATION_PORTRAIT)
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
    return layout_to_json([el], ORIENTATION_PORTRAIT, layout_kind=LAYOUT_KIND_US_LETTER)


def layout_to_json(
    elements: Sequence[LayoutElement],
    orientation: str = ORIENTATION_PORTRAIT,
    *,
    layout_kind: str = LAYOUT_KIND_ENVELOPE,
    envelope_size_id: str | None = None,
) -> str:
    """Serialize a mixed ordered list of text and image elements."""
    pw, ph = get_page_dimensions(
        layout_kind,
        orientation,
        envelope_size_id=envelope_size_id or DEFAULT_ENVELOPE_SIZE_ID,
    )
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
    if layout_kind == LAYOUT_KIND_ENVELOPE:
        data["envelope_size"] = envelope_size_id or DEFAULT_ENVELOPE_SIZE_ID
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
