import dataclasses
import io

import pytest

import byteparse as bp
from byteparse import this


class Point(bp.Struct, endian="little"):
    x: int = bp.u16()
    y: int = bp.u16()
    pad: None = bp.padding(2)


def test_instances_are_frozen_dataclasses():
    p = Point.parse(b"\x01\x00\x02\x00\x00\x00")
    assert p == Point(x=1, y=2, pad=None)
    assert hash(p) == hash(Point(x=1, y=2, pad=None))
    assert repr(p) == "Point(x=1, y=2)"
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.x = 5  # type: ignore[misc]


def test_constructor_is_keyword_only():
    with pytest.raises(TypeError):
        Point(1, 2, None)  # type: ignore[misc]


def test_to_dict_is_recursive_and_skips_padding():
    class Shape(bp.Struct, endian="little"):
        origin: Point
        corners: tuple[Point, ...] = bp.array(Point, 2)

    data = bytes(range(18))
    assert Shape.parse(data).to_dict() == {
        "origin": {"x": 0x0100, "y": 0x0302},
        "corners": [{"x": 0x0706, "y": 0x0908}, {"x": 0x0D0C, "y": 0x0F0E}],
    }


def test_trailing_bytes_rejected_unless_allowed():
    data = b"\x01\x00\x02\x00\x00\x00extra"
    with pytest.raises(bp.ParseError, match="5 trailing bytes"):
        Point.parse(data)
    assert Point.parse(data, allow_trailing=True).x == 1


def test_parse_stream_reads_only_what_it_needs():
    stream = io.BytesIO(b"\x01\x00\x02\x00\x00\x00rest")
    assert Point.parse_stream(stream).y == 2
    assert stream.read() == b"rest"


def test_shared_specifier_is_bound_per_struct():
    shared = bp.u16()

    class Big(bp.Struct, endian="big"):
        v: int = shared

    class Little(bp.Struct, endian="little"):
        v: int = shared

    assert Big.parse(b"\x01\x00").v == 256
    assert Little.parse(b"\x01\x00").v == 1


def test_missing_endian_is_definition_error():
    with pytest.raises(bp.DefinitionError, match="Bad.v: multi-byte field needs endian"):

        class Bad(bp.Struct):
            v: int = bp.u16()


def test_bad_struct_endian():
    with pytest.raises(bp.DefinitionError, match="endian must be"):

        class Bad(bp.Struct, endian="middle"):  # type: ignore[arg-type]
            v: int = bp.u8()


def test_field_without_specifier_is_definition_error():
    with pytest.raises(bp.DefinitionError, match="Bad.v: needs a byteparse specifier"):

        class Bad(bp.Struct):
            v: int


def test_plain_default_is_definition_error():
    with pytest.raises(bp.DefinitionError, match="default values are not supported"):

        class Bad(bp.Struct):
            v: int = 3


def test_ref_to_later_field_is_definition_error():
    with pytest.raises(bp.DefinitionError, match=r"Bad.data: this.length does not refer"):

        class Bad(bp.Struct):
            data: bytes = bp.bytes(this.length)
            length: int = bp.u8()


def test_dotted_ref_is_checked():
    class Head(bp.Struct):
        n: int = bp.u8()

    class Good(bp.Struct):
        head: Head
        data: bytes = bp.bytes(this.head.n)

    assert Good.parse(b"\x02ab").data == b"ab"
    with pytest.raises(bp.DefinitionError, match="this.head.m does not refer"):

        class Bad(bp.Struct):
            head: Head
            data: bytes = bp.bytes(this.head.m)

    with pytest.raises(bp.DefinitionError, match="reaches into a non-struct"):

        class Bad2(bp.Struct):
            n: int = bp.u8()
            data: bytes = bp.bytes(this.n.x)


def test_subclassing_a_struct_with_fields_is_rejected():
    with pytest.raises(bp.DefinitionError, match="subclassing a struct with fields"):

        class More(Point):
            z: int = bp.u16()


@pytest.mark.parametrize(
    "make, message",
    [
        (lambda: bp.bytes(-1), "bytes size must be a non-negative int"),
        (lambda: bp.array(bp.u8()), "exactly one of"),
        (lambda: bp.array(bp.u8(), 2, greedy=True), "exactly one of"),
        (lambda: bp.cstring("no-such-codec"), "unknown encoding"),
        (lambda: bp.pascal_string(bp.bytes(2)), "prefix must be an integer"),  # type: ignore[arg-type]
        (lambda: bp.enum(bp.u8(), int), "Enum subclass"),  # type: ignore[type-var]
        (lambda: bp.if_(True, bp.u8()), "condition must be"),
        (lambda: bp.bits(0), "positive int"),
        (lambda: bp.u16(endian="middle"), "endian must be"),  # type: ignore[arg-type]
        (lambda: bp.array(int, 2), "array element must be"),
    ],
)
def test_specifier_argument_errors(make, message):
    with pytest.raises(bp.DefinitionError, match=message):
        make()


def test_empty_struct():
    class Empty(bp.Struct):
        pass

    assert Empty.parse(b"") == Empty()
    with pytest.raises(bp.ParseError, match="1 trailing bytes"):
        Empty.parse(b"x")


def test_self_reference_gives_clear_error():
    with pytest.raises(bp.DefinitionError, match="cannot resolve annotation 'Node'"):

        class Node(bp.Struct):
            value: int = bp.u8()
            child: "Node"


def test_memoryview_of_wider_items():
    import array

    words = array.array("H", [1, 2])
    data = memoryview(words)
    assert Point.parse(bytes(data) + b"\0\0").x == 1
    assert Point.parse(memoryview(bytes(data) + b"\0\0")).y == 2
