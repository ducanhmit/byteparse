import pytest

import byteparse as bp
from byteparse import this


class Chunk(bp.Struct, endian="big"):
    length: int = bp.u16()
    data: bytes = bp.bytes(this.length)


class File(bp.Struct, endian="big"):
    magic: bytes = bp.bytes(2, const=b"FI")
    count: int = bp.u8()
    chunks: tuple[Chunk, ...] = bp.array(Chunk, this.count)


GOOD = b"FI\x02" + b"\x00\x01a" + b"\x00\x02bc"


def test_path_offset_and_message():
    with pytest.raises(bp.ParseError) as exc:
        File.parse(GOOD[:-1])
    e = exc.value
    assert e.path == ("chunks", 1, "data")
    assert e.offset == 8
    assert str(e) == "File.chunks[1].data: expected 2 bytes, got 1 (offset 0x8)"


def test_partial_holds_parsed_fields():
    with pytest.raises(bp.ParseError) as exc:
        File.parse(GOOD[:-1])
    partial = exc.value.partial
    assert isinstance(partial, bp.Partial)
    assert partial.magic == b"FI" and partial["count"] == 2
    first, second = partial.chunks
    assert first == Chunk(length=1, data=b"a")
    assert isinstance(second, bp.Partial) and dict(second) == {"length": 2}
    with pytest.raises(AttributeError, match="Chunk.data was not parsed"):
        second.data


def test_validation_error_is_parse_error_with_path():
    with pytest.raises(bp.ParseError) as exc:
        File.parse(b"XX\x00")
    assert isinstance(exc.value, bp.ValidationError)
    assert exc.value.path == ("magic",)
    assert exc.value.offset == 0
    assert dict(exc.value.partial) == {}


def test_error_offset_is_field_start_for_multi_read_fields():
    class S(bp.Struct):
        pad: bytes = bp.bytes(3)
        name: str = bp.pascal_string(bp.u8())

    with pytest.raises(bp.ParseError) as exc:
        S.parse(b"abc\x05xy")
    assert exc.value.offset == 3
    assert exc.value.path == ("name",)


def test_exception_hierarchy():
    assert issubclass(bp.ValidationError, bp.ParseError)
    assert issubclass(bp.LimitError, bp.ParseError)
    assert issubclass(bp.ParseError, bp.ByteparseError)
    assert issubclass(bp.DefinitionError, bp.ByteparseError)
    assert not issubclass(bp.DefinitionError, bp.ParseError)
