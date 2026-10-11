import io

import pytest

from byteparse.errors import LimitError, ParseError
from byteparse.reader import BufferReader, Limits, StreamReader


def readers(data: bytes, limits: Limits | None = None):
    limits = limits or Limits()
    return [BufferReader(data, limits), StreamReader(io.BytesIO(data), limits)]


@pytest.mark.parametrize("r", readers(b"abcdef"))
def test_read_tracks_offset(r):
    assert r.read(2) == b"ab"
    assert r.tell() == 2
    assert r.read(4) == b"cdef"
    assert r.at_end()


@pytest.mark.parametrize("r", readers(b"abc"))
def test_short_read_reports_start_offset(r):
    r.read(1)
    with pytest.raises(ParseError) as exc:
        r.read(5)
    assert exc.value.reason == "expected 5 bytes, got 2"
    assert exc.value.offset == 1


@pytest.mark.parametrize("r", readers(b"abc"))
def test_try_read_leaves_position_on_failure(r):
    assert r.try_read(5) is None
    assert r.tell() == 0
    assert r.read(3) == b"abc"


@pytest.mark.parametrize("r", readers(b"abcdef"))
def test_region_limits_reads(r):
    r.push_region(2)
    assert r.remaining() == 2
    with pytest.raises(ParseError, match="expected 3 bytes, got 2"):
        r.read(3)
    assert r.read(2) == b"ab"
    assert r.at_end()
    r.pop_region()
    assert not r.at_end()


def test_region_larger_than_buffer_fails():
    r = BufferReader(b"abc", Limits())
    with pytest.raises(ParseError, match="expected 10 bytes, got 3"):
        r.push_region(10)


@pytest.mark.parametrize("r", readers(b"hi\0rest"))
def test_cstring(r):
    assert r.read_cstring() == b"hi"
    assert r.tell() == 3


@pytest.mark.parametrize("r", readers(b"no terminator"))
def test_unterminated_cstring(r):
    with pytest.raises(ParseError, match="unterminated string"):
        r.read_cstring()


@pytest.mark.parametrize("r", readers(b"x" * 20 + b"\0", Limits(max_field_bytes=8)))
def test_cstring_limit(r):
    with pytest.raises(LimitError, match="max_field_bytes 8"):
        r.read_cstring()


def test_depth_limit():
    r = BufferReader(b"", Limits(max_depth=2))
    r.enter()
    r.enter()
    with pytest.raises(LimitError, match="max_depth 2"):
        r.enter()
    assert r.depth == 2


def test_buffer_accepts_bytearray_and_memoryview():
    assert BufferReader(bytearray(b"ab"), Limits()).read(2) == b"ab"
    assert BufferReader(memoryview(b"ab"), Limits()).read(2) == b"ab"


class Trickle(io.RawIOBase):
    """A stream that returns at most one byte per read, like a slow pipe."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def readable(self) -> bool:
        return True

    def read(self, n: int = -1) -> bytes:
        chunk, self._data = self._data[:1], self._data[1:]
        return chunk


def test_stream_with_short_reads():
    r = StreamReader(Trickle(b"abcdef"), Limits())  # type: ignore[arg-type]
    assert r.read(4) == b"abcd"
    assert r.try_read(5) is None
    assert r.read(2) == b"ef"
    assert r.at_end()


def test_stream_pushback_does_not_make_parsing_quadratic():
    import time

    import byteparse as bp
    from byteparse import this

    class Rec(bp.Struct, endian="big"):
        v: int = bp.u32()

    class Msg(bp.Struct, endian="big"):
        count: int = bp.u32()
        recs: tuple[Rec, ...] = bp.array(Rec, this.count)

    def cost(n: int) -> float:
        # One byte short: the bulk read fails, pushes everything back, and
        # the elements are then parsed one by one from the pushed-back bytes.
        data = n.to_bytes(4, "big") + bytes(4 * n - 1)
        best = float("inf")
        for _ in range(3):
            t = time.perf_counter()
            with pytest.raises(bp.ParseError):
                Msg.parse_stream(io.BytesIO(data))
            best = min(best, time.perf_counter() - t)
        return best

    # Linear work grows ~4x for 4x the input; the quadratic bug grew ~16x.
    assert cost(200_000) / cost(50_000) < 8
