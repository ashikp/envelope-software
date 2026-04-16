from __future__ import annotations

import re
from typing import Any, Mapping

_PLACEHOLDER = re.compile(r"\{([^{}]+)\}")


def merge_template(text: str, row: Mapping[str, Any]) -> str:
    def repl(m: re.Match[str]) -> str:
        key = m.group(1).strip()
        if key not in row or row[key] is None:
            return ""
        return str(row[key])

    return _PLACEHOLDER.sub(repl, text)


def keys_from_template(text: str) -> list[str]:
    return [m.group(1).strip() for m in _PLACEHOLDER.finditer(text)]
