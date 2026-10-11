from __future__ import annotations

import argparse
import enum
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .errors import ParseError, Partial
from .fields import short_repr
from .formats import FORMATS
from .struct import Struct


def render(value: Any, indent: int = 0) -> list[str]:
    pad = "  " * indent
    if isinstance(value, (Struct, Partial)):
        if isinstance(value, Struct):
            items: Mapping[str, Any] = value._bp_values()
            title = type(value).__name__
        else:
            items, title = value, f"{value.struct_name} (partial)"
        lines = [f"{pad}{title}"]
        for key, v in items.items():
            lines.extend(_render_item(key, v, indent + 1))
        return lines
    return [f"{pad}{_scalar(value)}"]


def _render_item(key: str, value: Any, indent: int) -> list[str]:
    pad = "  " * indent
    if isinstance(value, (Struct, Partial)):
        first, *rest = render(value, indent)
        return [f"{pad}{key}: {first.strip()}", *rest]
    if isinstance(value, tuple):
        lines = [f"{pad}{key}: [{len(value)}]"]
        for i, item in enumerate(value):
            lines.extend(_render_item(f"[{i}]", item, indent + 1))
        return lines
    return [f"{pad}{key}: {_scalar(value)}"]


def _scalar(value: Any) -> str:
    if isinstance(value, enum.Enum):
        return f"{value.name} ({value.value})"
    return short_repr(value)


def _json_default(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, Partial):
        return dict(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _jsonable(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.name
    if isinstance(value, Struct):
        return {k: _jsonable(v) for k, v in value._bp_values().items()}
    if isinstance(value, Partial):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m byteparse")
    sub = parser.add_subparsers(dest="command", required=True)
    dump = sub.add_parser("dump", help="parse a file and print its fields")
    dump.add_argument("file", type=Path)
    dump.add_argument("--format", required=True, choices=sorted(FORMATS))
    dump.add_argument("--json", action="store_true", help="print JSON instead of a tree")
    args = parser.parse_args(argv)

    struct_cls = FORMATS[args.format]
    try:
        data = args.file.read_bytes()
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    try:
        result: Any = struct_cls.parse(data)
        ok = True
    except ParseError as e:
        print(f"error: {e}", file=sys.stderr)
        result, ok = e.partial, False
        if result is None:
            return 1
        print("partial result:", file=sys.stderr)

    if args.json:
        print(json.dumps(_jsonable(result), default=_json_default, indent=2))
    else:
        print("\n".join(render(result)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
