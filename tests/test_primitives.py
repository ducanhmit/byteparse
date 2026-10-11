import struct

import pytest

import byteparse as bp
from byteparse import this


class Ints(bp.Struct, endian="big"):
    a: int = bp.u8()
    b: int = bp.i8()
    c: int = bp.u16()
    d: int = bp.i16(endian="little")
    e: int = bp.u24()
    f: int = bp.i24()
    g: int = bp.u32()
    h: int = bp.i64(endian="little")


def test_integers_endian_and_sign():
    data = (
        b"\xff"
        + b"\xff"
        + b"\x01\x02"
        + b"\xfe\xff"
        + b"\x01\x02\x03"
        + b"\xff\xff\xfe"
        + b"\x00\x00\x01\x00"
        + struct.pack("<q", -5)
    )
    v = Ints.parse(data)
    assert (v.a, v.b, v.c, v.d, v.e, v.f, v.g, v.h) == (255, -1, 0x102, -2, 0x10203, -2, 256, -5)


class Floats(bp.Struct, endian="little"):
    x: float = bp.f32()
    y: float = bp.f64(endian="big")


def test_floats():
    v = Floats.parse(struct.pack("<f", 1.5) + struct.pack(">d", -2.25))
    assert (v.x, v.y) == (1.5, -2.25)


class Misc(bp.Struct):
    ok: bool = bp.boolean()
    name: str = bp.cstring()
    title: str = bp.pascal_string(bp.u8())
    raw: bytes = bp.bytes(2)
    skip: None = bp.padding(1)
    tail: bytes = bp.bytes(lambda ctx: len(ctx.name))


def test_misc_fields():
    v = Misc.parse(b"\x02hi\0\x03abcXYzQQ")
    assert v.ok is True
    assert (v.name, v.title, v.raw, v.tail) == ("hi", "abc", b"XY", b"QQ")
    assert v.skip is None


def test_bad_utf8_is_parse_error():
    with pytest.raises(bp.ParseError, match="cannot decode utf-8"):
        Misc.parse(b"\x01\xff\0\x00XYzQQ")


class Validated(bp.Struct, endian="big"):
    magic: bytes = bp.bytes(2, const=b"OK")
    version: int = bp.u8(one_of=(1, 2))
    length: int = bp.u16(min=1, max=100)
    body: bytes = bp.bytes(this.length, check=lambda v, ctx: v.isalpha())


def test_validators_pass():
    assert Validated.parse(b"OK\x02\x00\x02ab").body == b"ab"


@pytest.mark.parametrize(
    "data, message",
    [
        (b"NO\x02\x00\x02ab", "expected b'OK', got b'NO'"),
        (b"OK\x03\x00\x02ab", "value 3 is not one of (1, 2)"),
        (b"OK\x02\x00\x00", "value 0 is less than min 1"),
        (b"OK\x02\x00\xff", "value 255 is greater than max 100"),
        (b"OK\x02\x00\x0212", "check failed for value b'12'"),
    ],
)
def test_validators_fail(data, message):
    with pytest.raises(bp.ValidationError) as exc:
        Validated.parse(data)
    assert exc.value.reason == message


def test_check_that_raises_becomes_parse_error():
    class Bad(bp.Struct):
        x: int = bp.u8(check=lambda v, ctx: 1 / 0)

    with pytest.raises(bp.ParseError, match="check raised ZeroDivisionError"):
        Bad.parse(b"\x01")


def test_long_values_are_shortened_in_messages():
    class Big(bp.Struct):
        blob: bytes = bp.bytes(100, const=b"a" * 100)

    with pytest.raises(bp.ValidationError) as exc:
        Big.parse(b"b" * 100)
    assert "(100 bytes)" in exc.value.reason
    assert len(exc.value.reason) < 200
