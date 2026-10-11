from enum import IntEnum, IntFlag

import pytest

import byteparse as bp
from byteparse import this


class Item(bp.Struct):
    kind: int = bp.u8()
    value: int = bp.u8()


def test_array_fixed_count_and_ref_count():
    class Fixed(bp.Struct):
        items: tuple[Item, ...] = bp.array(Item, 2)

    class Counted(bp.Struct):
        n: int = bp.u8()
        items: tuple[Item, ...] = bp.array(Item, this.n)

    assert Fixed.parse(b"\x01\x02\x03\x04").items == (Item(kind=1, value=2), Item(kind=3, value=4))
    assert len(Counted.parse(b"\x01\x05\x06").items) == 1


def test_array_of_primitives_uses_struct_endian():
    class Words(bp.Struct, endian="little"):
        words: tuple[int, ...] = bp.array(bp.u16(), 2)

    assert Words.parse(b"\x01\x00\x02\x00").words == (1, 2)


def test_array_until_includes_terminator():
    class Items(bp.Struct):
        items: tuple[Item, ...] = bp.array(Item, until=lambda it: it.kind == 0)

    parsed = Items.parse(b"\x01\x01\x02\x02\x00\x00")
    assert [i.kind for i in parsed.items] == [1, 2, 0]


def test_array_greedy_stops_at_end():
    class Items(bp.Struct):
        items: tuple[Item, ...] = bp.array(Item, greedy=True)

    assert len(Items.parse(b"\x01\x01\x02\x02").items) == 2
    assert Items.parse(b"").items == ()


def test_greedy_zero_size_element_is_error():
    class Empty(bp.Struct):
        nothing: bytes = bp.bytes(0)

    class Items(bp.Struct):
        items: tuple[Empty, ...] = bp.array(Empty, greedy=True)

    with pytest.raises(bp.ParseError, match="consumed no bytes"):
        Items.parse(b"\x01")


class Kind(IntEnum):
    A = 1
    B = 2


def test_enum_known_and_unknown():
    class E(bp.Struct, endian="big"):
        kind: Kind | int = bp.enum(bp.u16(), Kind)

    assert E.parse(b"\x00\x02").kind is Kind.B
    unknown = E.parse(b"\x00\x09").kind
    assert unknown == 9 and not isinstance(unknown, Kind)


def test_if_present_and_absent():
    class Opt(bp.Struct):
        has_extra: int = bp.u8()
        extra: int | None = bp.if_(this.has_extra, bp.u8())
        big: bytes | None = bp.if_(lambda ctx: ctx.has_extra > 1, bp.bytes(2))

    assert Opt.parse(b"\x00").extra is None
    v = Opt.parse(b"\x02\x07ab")
    assert (v.extra, v.big) == (7, b"ab")


class Hello(bp.Struct):
    version: int = bp.u8()


class Bye(bp.Struct):
    reason: int = bp.u8()
    code: int = bp.u8()


class Message(bp.Struct, endian="big"):
    msg_type: int = bp.u8()
    length: int = bp.u16()
    body: Hello | Bye | bytes = bp.switch(
        this.msg_type, {1: Hello, 2: Bye}, default=bp.bytes(this.length)
    )


def test_switch_cases_and_default():
    assert Message.parse(b"\x01\x00\x01\x05").body == Hello(version=5)
    assert Message.parse(b"\x02\x00\x02\x01\x02").body == Bye(reason=1, code=2)
    assert Message.parse(b"\x09\x00\x03xyz").body == b"xyz"


def test_switch_without_default_rejects_unknown_key():
    class Strict(bp.Struct):
        t: int = bp.u8()
        body: Hello = bp.switch(this.t, {1: Hello})

    with pytest.raises(bp.ParseError, match="no switch case for 7"):
        Strict.parse(b"\x07\x00")


def test_sized_limits_inner_parse():
    class Framed(bp.Struct, endian="big"):
        length: int = bp.u16()
        items: tuple[Item, ...] = bp.sized(this.length, bp.array(Item, greedy=True))
        trailer: int = bp.u8()

    v = Framed.parse(b"\x00\x04\x01\x01\x02\x02\xff")
    assert (len(v.items), v.trailer) == (2, 255)


def test_sized_with_unused_bytes_is_error():
    class Framed(bp.Struct):
        length: int = bp.u8()
        item: Item = bp.sized(this.length, Item)

    with pytest.raises(bp.ParseError, match="1 unused bytes at end of sized region"):
        Framed.parse(b"\x03\x01\x02\x03")


def test_sized_region_too_short_for_inner():
    class Framed(bp.Struct):
        length: int = bp.u8()
        item: Item = bp.sized(this.length, Item)
        rest: bytes = bp.bytes(2)

    with pytest.raises(bp.ParseError, match="expected 1 bytes, got 0"):
        Framed.parse(b"\x01\x01\x02\x03")


def test_parent_context_from_nested_struct():
    class Child(bp.Struct):
        data: bytes = bp.bytes(lambda ctx: ctx._parent.n)

    class Parent(bp.Struct):
        n: int = bp.u8()
        child: Child

    assert Parent.parse(b"\x02ab").child.data == b"ab"


class Perm(IntFlag):
    R = 4
    W = 2
    X = 1


def test_intflag_keeps_unknown_bits():
    class Mode(bp.Struct):
        perm: Perm | int = bp.enum(bp.u8(), Perm)

    assert Mode.parse(b"\x06").perm == Perm.R | Perm.W
    assert int(Mode.parse(b"\x0e").perm) == 14
