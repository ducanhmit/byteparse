import struct

import pytest
from hypothesis import given
from hypothesis import strategies as st

import byteparse as bp
from byteparse import this
from byteparse.plan import MergedStep, build_steps
from byteparse.reader import BufferReader, Limits


class Header(bp.Struct, endian="big"):
    a: int = bp.u8()
    b: int = bp.u16(max=60000)
    flags_hi: int = bp.bits(4)
    flags_lo: int = bp.bits(4)
    pad: None = bp.padding(1)
    c: int = bp.i32(endian="little")
    d: float = bp.f32(endian="little")
    e: bool = bp.boolean()
    f: int = bp.u24()
    g: int = bp.u16(check=lambda v, ctx: v != ctx.a)


def test_fixed_runs_are_merged():
    kinds = [type(s).__name__ for s in Header._bp_steps]
    assert kinds == ["MergedStep", "MergedStep", "FieldStep", "FieldStep"]
    first = Header._bp_steps[0]
    assert isinstance(first, MergedStep)
    assert first.packer.format == ">BHB1x"


def outcome(steps, data):
    try:
        return (
            "ok",
            Header._bp_run(BufferReader(data, Limits()), check_trailing=True, steps=steps),
        )
    except bp.ParseError as e:
        return ("error", type(e), e.path, e.offset, e.reason, repr(e.partial))


UNMERGED = build_steps(list(Header._bp_fields), merge=False)


@given(st.binary(max_size=24))
def test_merged_and_unmerged_plans_agree(data):
    assert outcome(None, data) == outcome(UNMERGED, data)


def test_merged_plan_on_valid_input():
    data = (
        b"\x07"
        + b"\x00\x10"
        + b"\x5a"
        + b"\x00"
        + struct.pack("<i", -3)
        + struct.pack("<f", 0.5)
        + b"\x01"
        + b"\x00\x00\x01"
        + b"\x00\x09"
    )
    h = Header.parse(data)
    assert (h.a, h.b, h.flags_hi, h.flags_lo, h.c, h.d, h.e, h.f, h.g) == (
        7,
        16,
        5,
        10,
        -3,
        0.5,
        True,
        1,
        9,
    )


def test_validator_failure_inside_merged_run_names_the_field():
    data = b"\x07" + b"\xff\xff" + bytes(19)
    with pytest.raises(bp.ValidationError) as exc:
        Header.parse(data)
    assert exc.value.path == ("b",)
    assert exc.value.offset == 1
    assert exc.value.partial["a"] == 7


class Rec(bp.Struct, endian="little"):
    key: int = bp.u32()
    pad: None = bp.padding(1)
    small: int = bp.i8()


class Recs(bp.Struct, endian="little"):
    n: int = bp.u8()
    counted: tuple[Rec, ...] = bp.array(Rec, this.n)
    rest: tuple[Rec, ...] = bp.array(Rec, greedy=True)


def test_fast_layout_only_for_plain_fixed_structs():
    assert Rec._bp_fast is not None and Rec._bp_fast.packer.format == "<I1xb"
    assert Header._bp_fast is None  # bits, validators and u24 are not plain


def slow_outcome(fn):
    saved = Rec._bp_fast
    Rec._bp_fast = None
    try:
        return fn()
    finally:
        Rec._bp_fast = saved


def run(cls, data, **kw):
    try:
        return ("ok", cls.parse(data, **kw))
    except bp.ParseError as e:
        return ("error", type(e), e.path, e.offset, e.reason, repr(e.partial))


@given(st.binary(max_size=40), st.booleans())
def test_fast_struct_paths_match_slow_paths(data, allow_trailing):
    for cls in (Rec, Recs):
        fast = run(cls, data, allow_trailing=allow_trailing, max_items=5)
        slow = slow_outcome(lambda c=cls: run(c, data, allow_trailing=allow_trailing, max_items=5))
        assert fast == slow


def test_fast_path_respects_max_depth():
    with pytest.raises(bp.LimitError):
        Rec.parse(bytes(6), max_depth=0)
