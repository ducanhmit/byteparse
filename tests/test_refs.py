import pytest

from byteparse.errors import DefinitionError, ParseError
from byteparse.refs import Context, resolve, resolve_size, this


def test_this_builds_paths():
    assert repr(this.header.count) == "this.header.count"


def test_this_rejects_operators():
    with pytest.raises(DefinitionError, match="use a lambda"):
        this.length - 4
    with pytest.raises(DefinitionError, match="use a lambda"):
        this.flag == 1
    with pytest.raises(DefinitionError, match="use a lambda"):
        bool(this.flag)


def test_resolve_ref_and_lambda():
    ctx = Context({"n": 3}, None)
    assert resolve(this.n, ctx, "size") == 3
    assert resolve(lambda c: c.n * 2, ctx, "size") == 6
    assert resolve(5, ctx, "size") == 5


def test_parent_context():
    outer = Context({"n": 7}, None)
    inner = Context({}, outer)
    assert resolve(lambda c: c._parent.n, inner, "size") == 7


def test_missing_field_in_lambda_is_parse_error():
    with pytest.raises(ParseError, match="size raised AttributeError"):
        resolve(lambda c: c.nope, Context({}, None), "size")


def test_resolve_size_rejects_negative_and_non_int():
    ctx = Context({"n": -1, "s": "x"}, None)
    with pytest.raises(ParseError, match="non-negative int, got -1"):
        resolve_size(this.n, ctx)
    with pytest.raises(ParseError, match="non-negative int, got 'x'"):
        resolve_size(this.s, ctx)
    with pytest.raises(ParseError, match="got True"):
        resolve_size(lambda c: True, ctx)
