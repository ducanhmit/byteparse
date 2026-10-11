from __future__ import annotations

from dataclasses import dataclass
from typing import IO

from .errors import LimitError, ParseError

_CHUNK = 1 << 20


@dataclass(frozen=True)
class Limits:
    max_field_bytes: int = 64 * 2**20
    max_items: int = 1_000_000
    max_depth: int = 64


class Reader:
    """Byte source with absolute offsets, nested size regions and parse limits."""

    def __init__(self, limits: Limits) -> None:
        self.limits = limits
        self.pos = 0
        self.depth = 0
        self.empty_items = 0
        self._ends: list[int] = []

    def tell(self) -> int:
        return self.pos

    def _source_remaining(self) -> int | None:
        raise NotImplementedError

    def _take(self, n: int) -> bytes:
        """Return up to n bytes, fewer only at end of input."""
        raise NotImplementedError

    def _untake(self, data: bytes) -> None:
        raise NotImplementedError

    def remaining(self) -> int | None:
        src = self._source_remaining()
        if self._ends:
            region = self._ends[-1] - self.pos
            return region if src is None else min(region, src)
        return src

    def read(self, n: int) -> bytes:
        start = self.pos
        avail = self.remaining()
        if avail is not None and n > avail:
            raise ParseError(f"expected {n} bytes, got {avail}", offset=start)
        data = self._take(n)
        if len(data) < n:
            raise ParseError(f"expected {n} bytes, got {len(data)}", offset=start)
        return data

    def try_read(self, n: int) -> bytes | None:
        avail = self.remaining()
        if avail is not None and n > avail:
            return None
        data = self._take(n)
        if len(data) < n:
            self._untake(data)
            return None
        return data

    def at_end(self) -> bool:
        avail = self.remaining()
        if avail is not None:
            return avail == 0
        data = self._take(1)
        if not data:
            return True
        self._untake(data)
        return False

    def read_cstring(self) -> bytes:
        start = self.pos
        limit = self.limits.max_field_bytes
        out = bytearray()
        while True:
            byte = self.try_read(1)
            if byte is None:
                raise ParseError("unterminated string", offset=start)
            if byte == b"\0":
                return bytes(out)
            if len(out) >= limit:
                raise LimitError(f"string exceeds max_field_bytes {limit}", offset=start)
            out += byte

    def push_region(self, n: int) -> None:
        avail = self.remaining()
        if avail is not None and n > avail:
            raise ParseError(f"expected {n} bytes, got {avail}", offset=self.pos)
        self._ends.append(self.pos + n)

    def pop_region(self) -> None:
        self._ends.pop()

    def enter(self) -> None:
        self.depth += 1
        if self.depth > self.limits.max_depth:
            self.depth -= 1
            raise LimitError(f"nesting exceeds max_depth {self.limits.max_depth}", offset=self.pos)

    def leave(self) -> None:
        self.depth -= 1


class BufferReader(Reader):
    def __init__(self, data: bytes | bytearray | memoryview, limits: Limits) -> None:
        super().__init__(limits)
        self._data = bytes(data)

    def _source_remaining(self) -> int:
        return len(self._data) - self.pos

    def _take(self, n: int) -> bytes:
        data = self._data[self.pos : self.pos + n]
        self.pos += len(data)
        return data

    def _untake(self, data: bytes) -> None:
        self.pos -= len(data)

    def read_cstring(self) -> bytes:
        start = self.pos
        limit = self.limits.max_field_bytes
        avail = self.remaining()
        assert avail is not None
        end = start + min(avail, limit + 1)
        idx = self._data.find(b"\0", start, end)
        if idx < 0:
            if avail > limit:
                raise LimitError(f"string exceeds max_field_bytes {limit}", offset=start)
            raise ParseError("unterminated string", offset=start)
        self.pos = idx + 1
        return self._data[start:idx]


class StreamReader(Reader):
    def __init__(self, stream: IO[bytes], limits: Limits) -> None:
        super().__init__(limits)
        self._stream = stream
        # Pushed-back bytes are read through an index so each read copies only
        # what it returns, not the whole pushed-back buffer.
        self._pending = b""
        self._pi = 0

    def _source_remaining(self) -> None:
        return None

    def _take(self, n: int) -> bytes:
        head = self._pending[self._pi : self._pi + n]
        self._pi += len(head)
        if self._pi == len(self._pending):
            self._pending, self._pi = b"", 0
        parts = [head]
        got = len(head)
        while got < n:
            chunk = self._stream.read(min(n - got, _CHUNK))
            if not chunk:
                break
            parts.append(chunk)
            got += len(chunk)
        self.pos += got
        return b"".join(parts)

    def _untake(self, data: bytes) -> None:
        k = len(data)
        if k <= self._pi and self._pending[self._pi - k : self._pi] == data:
            self._pi -= k
        else:
            self._pending = data + self._pending[self._pi :]
            self._pi = 0
        self.pos -= k
