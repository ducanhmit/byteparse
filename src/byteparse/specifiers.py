from __future__ import annotations

import builtins
import enum as _enum
from collections.abc import Callable, Sequence
from typing import Any, ClassVar, Literal, Protocol, TypeVar, cast, overload

from . import fields as f
from .refs import Context


class _StructLike(Protocol):
    # Struct satisfies this; importing Struct here would create an import cycle.
    _bp_bits_only: ClassVar[builtins.bool]


Endian = Literal["big", "little"] | None
Size = int | Any  # int, `this` reference, or Callable[[Context], int]
Check = Callable[[Any, Context], object]

T = TypeVar("T")
S = TypeVar("S", bound=_StructLike)
E = TypeVar("E", bound=_enum.Enum)


def _int(nbytes: int, signed: bool, endian: Endian, kw: dict[str, Any]) -> int:
    return cast(int, f.Int(nbytes, signed, endian, f.make_validators(**kw)))


def u8(
    *,
    min: int | None = None,
    max: int | None = None,
    const: int | None = None,
    one_of: Sequence[int] | None = None,
    check: Check | None = None,
) -> int:
    return _int(1, False, None, dict(min=min, max=max, const=const, one_of=one_of, check=check))


def i8(
    *,
    min: int | None = None,
    max: int | None = None,
    const: int | None = None,
    one_of: Sequence[int] | None = None,
    check: Check | None = None,
) -> int:
    return _int(1, True, None, dict(min=min, max=max, const=const, one_of=one_of, check=check))


def u16(
    *,
    endian: Endian = None,
    min: int | None = None,
    max: int | None = None,
    const: int | None = None,
    one_of: Sequence[int] | None = None,
    check: Check | None = None,
) -> int:
    return _int(2, False, endian, dict(min=min, max=max, const=const, one_of=one_of, check=check))


def i16(
    *,
    endian: Endian = None,
    min: int | None = None,
    max: int | None = None,
    const: int | None = None,
    one_of: Sequence[int] | None = None,
    check: Check | None = None,
) -> int:
    return _int(2, True, endian, dict(min=min, max=max, const=const, one_of=one_of, check=check))


def u24(
    *,
    endian: Endian = None,
    min: int | None = None,
    max: int | None = None,
    const: int | None = None,
    one_of: Sequence[int] | None = None,
    check: Check | None = None,
) -> int:
    return _int(3, False, endian, dict(min=min, max=max, const=const, one_of=one_of, check=check))


def i24(
    *,
    endian: Endian = None,
    min: int | None = None,
    max: int | None = None,
    const: int | None = None,
    one_of: Sequence[int] | None = None,
    check: Check | None = None,
) -> int:
    return _int(3, True, endian, dict(min=min, max=max, const=const, one_of=one_of, check=check))


def u32(
    *,
    endian: Endian = None,
    min: int | None = None,
    max: int | None = None,
    const: int | None = None,
    one_of: Sequence[int] | None = None,
    check: Check | None = None,
) -> int:
    return _int(4, False, endian, dict(min=min, max=max, const=const, one_of=one_of, check=check))


def i32(
    *,
    endian: Endian = None,
    min: int | None = None,
    max: int | None = None,
    const: int | None = None,
    one_of: Sequence[int] | None = None,
    check: Check | None = None,
) -> int:
    return _int(4, True, endian, dict(min=min, max=max, const=const, one_of=one_of, check=check))


def u64(
    *,
    endian: Endian = None,
    min: int | None = None,
    max: int | None = None,
    const: int | None = None,
    one_of: Sequence[int] | None = None,
    check: Check | None = None,
) -> int:
    return _int(8, False, endian, dict(min=min, max=max, const=const, one_of=one_of, check=check))


def i64(
    *,
    endian: Endian = None,
    min: int | None = None,
    max: int | None = None,
    const: int | None = None,
    one_of: Sequence[int] | None = None,
    check: Check | None = None,
) -> int:
    return _int(8, True, endian, dict(min=min, max=max, const=const, one_of=one_of, check=check))


def f32(
    *,
    endian: Endian = None,
    min: float | None = None,
    max: float | None = None,
    check: Check | None = None,
) -> float:
    return cast(float, f.Float(4, endian, f.make_validators(min=min, max=max, check=check)))


def f64(
    *,
    endian: Endian = None,
    min: float | None = None,
    max: float | None = None,
    check: Check | None = None,
) -> float:
    return cast(float, f.Float(8, endian, f.make_validators(min=min, max=max, check=check)))


def boolean(*, const: bool | None = None, check: Check | None = None) -> bool:
    return cast(bool, f.Bool(f.make_validators(const=const, check=check)))


def bytes(
    size: Size,
    *,
    const: builtins.bytes | None = None,
    one_of: Sequence[builtins.bytes] | None = None,
    check: Check | None = None,
) -> builtins.bytes:
    v = f.make_validators(const=const, one_of=one_of, check=check)
    return cast(builtins.bytes, f.Bytes(size, v))


def cstring(
    encoding: str = "utf-8",
    *,
    const: str | None = None,
    one_of: Sequence[str] | None = None,
    check: Check | None = None,
) -> str:
    v = f.make_validators(const=const, one_of=one_of, check=check)
    return cast(str, f.CString(encoding, v))


def pascal_string(
    prefix: int,
    encoding: str = "utf-8",
    *,
    const: str | None = None,
    one_of: Sequence[str] | None = None,
    check: Check | None = None,
) -> str:
    v = f.make_validators(const=const, one_of=one_of, check=check)
    return cast(str, f.PascalString(cast(f.Field, prefix), encoding, v))


def padding(size: Size) -> Any:
    """Annotate as `name: None = bp.padding(n)`; the value is always None."""
    return f.Padding(size)


def bits(n: int) -> int:
    return cast(int, f.Bits(n, as_bool=False))


def flag() -> bool:
    return cast(bool, f.Bits(1, as_bool=True))


def enum(base: int, enum_type: type[E]) -> E | int:
    return cast("E | int", f.EnumField(cast(f.Field, base), enum_type))


@overload
def array(
    element: type[S],
    count: Size = ...,
    *,
    until: Callable[[S], object] | None = ...,
    greedy: builtins.bool = ...,
) -> tuple[S, ...]: ...
@overload
def array(
    element: T,
    count: Size = ...,
    *,
    until: Callable[[T], object] | None = ...,
    greedy: builtins.bool = ...,
) -> tuple[T, ...]: ...
def array(
    element: Any,
    count: Size = None,
    *,
    until: Callable[[Any], object] | None = None,
    greedy: builtins.bool = False,
) -> tuple[Any, ...]:
    return cast("tuple[Any, ...]", f.Array(element, count, until, greedy))


@overload
def if_(cond: Any, inner: type[S]) -> S | None: ...
@overload
def if_(cond: Any, inner: T) -> T | None: ...
def if_(cond: Any, inner: Any) -> Any:
    return f.If(cond, inner)


def switch(key: Any, cases: dict[Any, Any], default: Any = None) -> Any:
    return f.Switch(key, cases, default)


@overload
def sized(size: Size, inner: type[S]) -> S: ...
@overload
def sized(size: Size, inner: T) -> T: ...
def sized(size: Size, inner: Any) -> Any:
    return f.Sized(size, inner)
