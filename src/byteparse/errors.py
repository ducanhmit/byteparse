from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any


class ByteparseError(Exception):
    pass


class DefinitionError(ByteparseError):
    pass


class ParseError(ByteparseError):
    def __init__(self, reason: str, *, offset: int = 0) -> None:
        super().__init__(reason)
        self.reason = reason
        self.offset = offset
        self.path: tuple[str | int, ...] = ()
        self.partial: Any = None
        self.struct_name: str | None = None
        self._pinned = False

    def __str__(self) -> str:
        loc = self.struct_name or ""
        for part in self.path:
            loc += f"[{part}]" if isinstance(part, int) else f".{part}"
        loc = loc.lstrip(".")
        prefix = f"{loc}: " if loc else ""
        return f"{prefix}{self.reason} (offset {self.offset:#x})"


class ValidationError(ParseError):
    pass


class LimitError(ParseError):
    pass


def prepend(err: ParseError, component: str | int, start: int) -> None:
    if not err._pinned:
        err.offset = start
        err._pinned = True
    err.path = (component, *err.path)


class Partial(Mapping[str, Any]):
    """Fields parsed before a ParseError; nested the same way as the struct."""

    def __init__(self, struct_name: str, values: Mapping[str, Any]) -> None:
        self.struct_name = struct_name
        self._values = dict(values)

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._values[name]
        except KeyError:
            raise AttributeError(f"{self.struct_name}.{name} was not parsed") from None

    def __repr__(self) -> str:
        inner = ", ".join(f"{k}={v!r}" for k, v in self._values.items())
        return f"Partial[{self.struct_name}]({inner})"
