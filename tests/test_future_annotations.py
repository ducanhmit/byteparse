from __future__ import annotations

import pytest

import byteparse as bp


class Inner(bp.Struct):
    v: int = bp.u8()


class Outer(bp.Struct):
    inner: Inner
    items: tuple[Inner, ...] = bp.array(Inner, 2)


def test_string_annotations_resolve_module_level_structs():
    assert Outer.parse(b"\x01\x02\x03").items[1].v == 3


def test_local_struct_with_string_annotations_explains_itself():
    class LocalInner(bp.Struct):
        v: int = bp.u8()

    with pytest.raises(bp.DefinitionError, match="cannot resolve annotation 'LocalInner'"):

        class LocalOuter(bp.Struct):
            inner: LocalInner


def test_forward_ref_annotations_resolve_or_explain_themselves():
    # Python 3.14 returns ForwardRef objects for annotations it can't evaluate yet.
    import typing

    def make(name: str, ref: str) -> type:
        ns = {"__annotations__": {"inner": typing.ForwardRef(ref)}, "__module__": __name__}
        return type(name, (bp.Struct,), ns)

    assert make("UsesInner", "Inner").parse(b"\x07").inner == Inner(v=7)
    with pytest.raises(bp.DefinitionError, match="cannot resolve annotation 'Missing'"):
        make("UsesMissing", "Missing")
