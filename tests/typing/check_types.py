"""Checked by mypy and pyright in CI. Every `type: ignore` must be needed."""

from enum import IntEnum
from typing import Any, assert_type

import byteparse as bp
from byteparse import this


class Kind(IntEnum):
    A = 1


class Item(bp.Struct):
    v: int = bp.u8()


class Packet(bp.Struct, endian="big"):
    length: int = bp.u16()
    data: bytes = bp.bytes(this.length)
    name: str = bp.cstring()
    ratio: float = bp.f32()
    ok: bool = bp.boolean()
    bit: bool = bp.flag()
    nibble: int = bp.bits(7)
    kind: Kind | int = bp.enum(bp.u8(), Kind)
    items: tuple[Item, ...] = bp.array(Item, 2)
    words: tuple[int, ...] = bp.array(bp.u16(), 2)
    maybe: int | None = bp.if_(this.ok, bp.u8())
    inner: Item = bp.sized(1, Item)
    body: Item | bytes = bp.switch(this.kind, {1: Item}, default=bp.bytes(1))
    gap: None = bp.padding(1)
    head: Item


p = Packet.parse(b"")
assert_type(p, Packet)
assert_type(Packet.parse_stream(open("x", "rb")), Packet)
assert_type(p.length, int)
assert_type(p.items, tuple[Item, ...])
assert_type(p.maybe, int | None)
assert_type(p.to_dict(), dict[str, Any])

Item(v=1)
Item(1)  # type: ignore[call-arg]
Item(v="x")  # type: ignore[arg-type]
p.length = 3  # type: ignore[misc]


class Wrong(bp.Struct):
    a: str = bp.u8()  # type: ignore[assignment]
    b: bytes = bp.cstring()  # type: ignore[assignment]
    c: tuple[str, ...] = bp.array(Item, 1)  # type: ignore[assignment]
