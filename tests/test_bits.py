import pytest

import byteparse as bp


class Flags(bp.BitStruct):
    a: bool = bp.flag()
    mode: int = bp.bits(3)
    rest: int = bp.bits(4)


def test_bitstruct_msb_first():
    v = Flags.parse(b"\xb5")  # 1 011 0101
    assert (v.a, v.mode, v.rest) == (True, 3, 5)


def test_inline_bits_in_struct():
    class IPv4Start(bp.Struct, endian="big"):
        version: int = bp.bits(4)
        ihl: int = bp.bits(4)
        tos: int = bp.u8()
        frag: int = bp.bits(3)
        offset: int = bp.bits(13)

    v = IPv4Start.parse(b"\x45\x00\x40\x05")
    assert (v.version, v.ihl, v.tos, v.frag, v.offset) == (4, 5, 0, 2, 5)


def test_nested_bitstruct():
    class Header(bp.Struct, endian="big"):
        flags: Flags
        n: int = bp.u16()

    v = Header.parse(b"\x80\x00\x01")
    assert v.flags.a and v.n == 1


def test_partial_byte_group_is_definition_error():
    with pytest.raises(bp.DefinitionError, match=r"bit fields \(a, b\) total 7 bits"):

        class Bad(bp.Struct):
            a: int = bp.bits(3)
            b: int = bp.bits(4)
            c: int = bp.u8()


def test_bitstruct_rejects_byte_fields():
    with pytest.raises(bp.DefinitionError, match="BitStruct fields must be bits"):

        class Bad(bp.BitStruct):
            a: int = bp.u8()


def test_wide_bit_group():
    class Wide(bp.BitStruct):
        hi: int = bp.bits(20)
        lo: int = bp.bits(4)

    v = Wide.parse(b"\xab\xcd\xef")
    assert (v.hi, v.lo) == (0xABCDE, 0xF)
