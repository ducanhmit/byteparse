import io

import pytest

import byteparse as bp
from byteparse import this


class Blob(bp.Struct, endian="big"):
    length: int = bp.u32()
    data: bytes = bp.bytes(this.length)


def test_length_beyond_input_fails_without_allocating():
    with pytest.raises(bp.ParseError, match="expected 4294967295 bytes, got 2"):
        Blob.parse(b"\xff\xff\xff\xffab", max_field_bytes=2**33)


def test_max_field_bytes():
    with pytest.raises(bp.LimitError, match="field size 100 exceeds max_field_bytes 10"):
        Blob.parse(b"\x00\x00\x00\x64" + b"x" * 100, max_field_bytes=10)


def test_default_field_limit_on_stream():
    huge = io.BytesIO(b"\x7f\xff\xff\xff")
    with pytest.raises(bp.LimitError, match="max_field_bytes 67108864"):
        Blob.parse_stream(huge)


class Items(bp.Struct):
    n: int = bp.u8()
    items: tuple[int, ...] = bp.array(bp.u8(), this.n)


def test_max_items_for_counted_array():
    with pytest.raises(bp.LimitError, match="array count 5 exceeds max_items 4"):
        Items.parse(b"\x05" + b"\x00" * 5, max_items=4)


def test_max_items_for_greedy_array():
    class Greedy(bp.Struct):
        items: tuple[int, ...] = bp.array(bp.u8(), greedy=True)

    with pytest.raises(bp.LimitError, match="array exceeds max_items 3"):
        Greedy.parse(b"\x00" * 4, max_items=3)


def test_max_depth():
    class Leaf(bp.Struct):
        v: int = bp.u8()

    class Mid(bp.Struct):
        leaf: Leaf

    class Top(bp.Struct):
        mid: Mid

    assert Top.parse(b"\x01", max_depth=3).mid.leaf.v == 1
    with pytest.raises(bp.LimitError, match="max_depth 2") as exc:
        Top.parse(b"\x01", max_depth=2)
    assert exc.value.path == ("mid", "leaf")
