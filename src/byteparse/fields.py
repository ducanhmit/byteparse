from __future__ import annotations

import codecs
import copy
import enum
import struct
from collections.abc import Callable, Iterator, Sequence
from typing import Any, Literal, cast

from .errors import DefinitionError, LimitError, ParseError, ValidationError, prepend
from .reader import Reader
from .refs import Context, Expr, Ref, call_user, check_size_arg, is_expr, resolve, resolve_size

Validator = Callable[[Any, Context], None]

_INT_CODES = {1: "b", 2: "h", 4: "i", 8: "q"}


def short_repr(value: object) -> str:
    if isinstance(value, (bytes, str)) and len(value) > 32:
        return (
            f"{value[:32]!r}... ({len(value)} {'bytes' if isinstance(value, bytes) else 'chars'})"
        )
    return repr(value)


def make_validators(
    *,
    min: Any = None,
    max: Any = None,
    const: Any = None,
    one_of: Sequence[Any] | None = None,
    check: Callable[[Any, Context], object] | None = None,
) -> tuple[Validator, ...]:
    out: list[Validator] = []
    if const is not None:

        def v_const(v: Any, ctx: Context) -> None:
            if v != const:
                raise ValidationError(f"expected {short_repr(const)}, got {short_repr(v)}")

        out.append(v_const)
    if min is not None:

        def v_min(v: Any, ctx: Context) -> None:
            if v < min:
                raise ValidationError(f"value {v!r} is less than min {min!r}")

        out.append(v_min)
    if max is not None:

        def v_max(v: Any, ctx: Context) -> None:
            if v > max:
                raise ValidationError(f"value {v!r} is greater than max {max!r}")

        out.append(v_max)
    if one_of is not None:
        allowed = tuple(one_of)

        def v_one_of(v: Any, ctx: Context) -> None:
            if v not in allowed:
                raise ValidationError(f"value {short_repr(v)} is not one of {allowed!r}")

        out.append(v_one_of)
    if check is not None:
        fn = check

        def v_check(v: Any, ctx: Context) -> None:
            if not call_user(fn, v, ctx, what="check"):
                raise ValidationError(f"check failed for value {short_repr(v)}")

        out.append(v_check)
    return tuple(out)


class Field:
    validators: tuple[Validator, ...] = ()

    def parse(self, r: Reader, ctx: Context) -> Any:
        raise NotImplementedError

    def validate(self, value: Any, ctx: Context) -> None:
        for v in self.validators:
            v(value, ctx)

    def bind(self, endian: str | None, where: str) -> Field:
        """Return a copy with the struct's default endian applied, children bound too."""
        return self

    def refs(self) -> Iterator[Ref]:
        return iter(())

    def struct_code(self) -> tuple[str, str | None] | None:
        """(struct format, required endian) if this field can join a merged read."""
        return None

    def from_raw(self, raw: Any) -> Any:
        return raw


class _Numeric(Field):
    def __init__(self, nbytes: int, endian: str | None, validators: tuple[Validator, ...]) -> None:
        if endian not in (None, "big", "little"):
            raise DefinitionError(f"endian must be 'big' or 'little', got {endian!r}")
        self.nbytes = nbytes
        self.endian: Literal["big", "little"] = cast(Literal["big", "little"], endian)
        self.validators = validators

    def bind(self, endian: str | None, where: str) -> Field:
        f = copy.copy(self)
        if f.endian is None and f.nbytes > 1:
            if endian is None:
                raise DefinitionError(
                    f"{where}: multi-byte field needs endian= on the field or the struct"
                )
            f.endian = cast(Literal["big", "little"], endian)
        return f


class Int(_Numeric):
    def __init__(
        self, nbytes: int, signed: bool, endian: str | None, validators: tuple[Validator, ...]
    ) -> None:
        super().__init__(nbytes, endian, validators)
        self.signed = signed

    def parse(self, r: Reader, ctx: Context) -> int:
        data = r.read(self.nbytes)
        value = int.from_bytes(data, self.endian or "big", signed=self.signed)
        self.validate(value, ctx)
        return value

    def struct_code(self) -> tuple[str, str | None] | None:
        code = _INT_CODES.get(self.nbytes)
        if code is None:
            return None
        return (code if self.signed else code.upper(), self.endian if self.nbytes > 1 else None)


class Float(_Numeric):
    def __init__(self, nbytes: int, endian: str | None, validators: tuple[Validator, ...]) -> None:
        super().__init__(nbytes, endian, validators)
        self._code = "f" if nbytes == 4 else "d"

    def parse(self, r: Reader, ctx: Context) -> float:
        data = r.read(self.nbytes)
        prefix = ">" if self.endian == "big" else "<"
        value: float = struct.unpack(prefix + self._code, data)[0]
        self.validate(value, ctx)
        return value

    def struct_code(self) -> tuple[str, str | None]:
        return (self._code, self.endian)


class Bool(Field):
    def __init__(self, validators: tuple[Validator, ...]) -> None:
        self.validators = validators

    def parse(self, r: Reader, ctx: Context) -> bool:
        value = r.read(1)[0] != 0
        self.validate(value, ctx)
        return value

    def struct_code(self) -> tuple[str, str | None]:
        return ("B", None)

    def from_raw(self, raw: Any) -> bool:
        return bool(raw != 0)


def _check_field_size(r: Reader, n: int) -> None:
    limit = r.limits.max_field_bytes
    if n > limit:
        raise LimitError(f"field size {n} exceeds max_field_bytes {limit}")


class Bytes(Field):
    def __init__(self, size: Expr, validators: tuple[Validator, ...]) -> None:
        check_size_arg(size, "bytes size")
        self.size = size
        self.validators = validators

    def refs(self) -> Iterator[Ref]:
        if isinstance(self.size, Ref):
            yield self.size

    def parse(self, r: Reader, ctx: Context) -> bytes:
        n = resolve_size(self.size, ctx)
        _check_field_size(r, n)
        value = r.read(n)
        self.validate(value, ctx)
        return value


class Padding(Field):
    def __init__(self, size: Expr) -> None:
        check_size_arg(size, "padding size")
        self.size = size

    def refs(self) -> Iterator[Ref]:
        if isinstance(self.size, Ref):
            yield self.size

    def parse(self, r: Reader, ctx: Context) -> None:
        n = resolve_size(self.size, ctx)
        _check_field_size(r, n)
        r.read(n)
        return None

    def struct_code(self) -> tuple[str, str | None] | None:
        if isinstance(self.size, int):
            return (f"{self.size}x", None)
        return None

    def from_raw(self, raw: Any) -> None:
        return None


def _check_encoding(encoding: str) -> None:
    try:
        codecs.lookup(encoding)
    except LookupError:
        raise DefinitionError(f"unknown encoding {encoding!r}") from None


def _decode(data: bytes, encoding: str) -> str:
    try:
        return data.decode(encoding)
    except UnicodeDecodeError as e:
        raise ParseError(f"cannot decode {encoding} string: {e.reason}") from None


class CString(Field):
    def __init__(self, encoding: str, validators: tuple[Validator, ...]) -> None:
        _check_encoding(encoding)
        self.encoding = encoding
        self.validators = validators

    def parse(self, r: Reader, ctx: Context) -> str:
        value = _decode(r.read_cstring(), self.encoding)
        self.validate(value, ctx)
        return value


class PascalString(Field):
    def __init__(self, prefix: Field, encoding: str, validators: tuple[Validator, ...]) -> None:
        if type(prefix) is not Int:
            raise DefinitionError("pascal_string prefix must be an integer specifier like u16()")
        _check_encoding(encoding)
        self.prefix: Field = prefix
        self.encoding = encoding
        self.validators = validators

    def bind(self, endian: str | None, where: str) -> Field:
        f = copy.copy(self)
        f.prefix = self.prefix.bind(endian, where)
        return f

    def parse(self, r: Reader, ctx: Context) -> str:
        n = self.prefix.parse(r, ctx)
        _check_field_size(r, n)
        value = _decode(r.read(n), self.encoding)
        self.validate(value, ctx)
        return value


class Bits(Field):
    """Only parsed as part of a BitGroup built by the struct plan."""

    def __init__(self, nbits: int, as_bool: bool) -> None:
        if isinstance(nbits, bool) or not isinstance(nbits, int) or nbits < 1:
            raise DefinitionError(f"bits() needs a positive int, got {nbits!r}")
        self.nbits = nbits
        self.as_bool = as_bool


class EnumField(Field):
    def __init__(self, base: Field, enum_type: type[enum.Enum]) -> None:
        if type(base) is not Int:
            raise DefinitionError("enum base must be an integer specifier like u8()")
        if not (isinstance(enum_type, type) and issubclass(enum_type, enum.Enum)):
            raise DefinitionError(f"enum type must be an Enum subclass, got {enum_type!r}")
        self.base: Field = base
        self.enum_type = enum_type

    def bind(self, endian: str | None, where: str) -> Field:
        f = copy.copy(self)
        f.base = self.base.bind(endian, where)
        return f

    def parse(self, r: Reader, ctx: Context) -> Any:
        value = self.base.parse(r, ctx)
        try:
            return self.enum_type(value)
        except ValueError:
            return value


class StructField(Field):
    def __init__(self, struct_cls: Any) -> None:
        self.struct_cls = struct_cls

    def parse(self, r: Reader, ctx: Context) -> Any:
        return self.struct_cls._bp_parse(r, ctx)


def as_field(spec: Any, what: str) -> Field:
    if isinstance(spec, Field):
        return spec
    if isinstance(spec, type) and hasattr(spec, "_bp_parse"):
        return StructField(spec)
    raise DefinitionError(f"{what} must be a byteparse specifier or Struct class, got {spec!r}")


class Array(Field):
    def __init__(
        self,
        element: Any,
        count: Expr | None,
        until: Callable[[Any], object] | None,
        greedy: bool,
    ) -> None:
        modes = (count is not None) + (until is not None) + bool(greedy)
        if modes != 1:
            raise DefinitionError("array() needs exactly one of: count, until=, greedy=True")
        if count is not None:
            check_size_arg(count, "array count")
        if until is not None and not callable(until):
            raise DefinitionError("array until= must be a callable taking the element")
        self.element: Field = as_field(element, "array element")
        self.count = count
        self.until = until
        self.greedy = greedy

    def bind(self, endian: str | None, where: str) -> Field:
        f = copy.copy(self)
        f.element = self.element.bind(endian, where)
        return f

    def refs(self) -> Iterator[Ref]:
        if isinstance(self.count, Ref):
            yield self.count
        yield from self.element.refs()

    def parse(self, r: Reader, ctx: Context) -> tuple[Any, ...]:
        limit = r.limits.max_items
        items: list[Any] = []
        fast = None
        struct_cls: Any = None
        if isinstance(self.element, StructField) and r.depth < r.limits.max_depth:
            struct_cls = self.element.struct_cls
            fast = struct_cls._bp_fast
        if self.count is not None:
            n = resolve_size(self.count, ctx, "array count")
            if n > limit:
                raise LimitError(f"array count {n} exceeds max_items {limit}")
            if fast is not None:
                data = r.try_read(n * fast.size)
                if data is not None:
                    return tuple(fast.make_many(struct_cls, data))
            for _ in range(n):
                self._parse_one(r, ctx, items)
        elif self.until is not None:
            while True:
                if len(items) >= limit:
                    raise LimitError(f"array exceeds max_items {limit}")
                item = self._parse_one(r, ctx, items)
                if call_user(self.until, item, what="until"):
                    break
        else:
            left = r.remaining()
            if fast is not None and left is not None and left % fast.size == 0:
                if left // fast.size <= limit:
                    return tuple(fast.make_many(struct_cls, r.read(left)))
            while not r.at_end():
                if len(items) >= limit:
                    raise LimitError(f"array exceeds max_items {limit}")
                start = r.tell()
                self._parse_one(r, ctx, items)
                if r.tell() == start:
                    raise ParseError("greedy array element consumed no bytes", offset=start)
        return tuple(items)

    def _parse_one(self, r: Reader, ctx: Context, items: list[Any]) -> Any:
        start = r.tell()
        try:
            item = self.element.parse(r, ctx)
        except ParseError as e:
            child = (e.partial,) if e.partial is not None else ()
            e.partial = (*items, *child)
            prepend(e, len(items), start)
            raise
        items.append(item)
        return item


class If(Field):
    def __init__(self, cond: Expr, inner: Any) -> None:
        if not is_expr(cond):
            raise DefinitionError("if_() condition must be a this reference or a lambda")
        self.cond = cond
        self.inner: Field = as_field(inner, "if_() field")

    def bind(self, endian: str | None, where: str) -> Field:
        f = copy.copy(self)
        f.inner = self.inner.bind(endian, where)
        return f

    def refs(self) -> Iterator[Ref]:
        if isinstance(self.cond, Ref):
            yield self.cond
        yield from self.inner.refs()

    def parse(self, r: Reader, ctx: Context) -> Any:
        if not resolve(self.cond, ctx, "if_ condition"):
            return None
        return self.inner.parse(r, ctx)


class Switch(Field):
    def __init__(self, key: Expr, cases: dict[Any, Any], default: Any) -> None:
        if not is_expr(key):
            raise DefinitionError("switch() key must be a this reference or a lambda")
        self.key = key
        self.cases: dict[Any, Field] = {
            k: as_field(v, f"switch case {k!r}") for k, v in cases.items()
        }
        self.default: Field | None = (
            None if default is None else as_field(default, "switch default")
        )

    def bind(self, endian: str | None, where: str) -> Field:
        f = copy.copy(self)
        f.cases = {k: v.bind(endian, where) for k, v in self.cases.items()}
        f.default = None if self.default is None else self.default.bind(endian, where)
        return f

    def refs(self) -> Iterator[Ref]:
        if isinstance(self.key, Ref):
            yield self.key
        for f in self.cases.values():
            yield from f.refs()
        if self.default is not None:
            yield from self.default.refs()

    def parse(self, r: Reader, ctx: Context) -> Any:
        key = resolve(self.key, ctx, "switch key")
        try:
            field = self.cases.get(key, self.default)
        except TypeError:
            raise ParseError(f"switch key {key!r} is not hashable") from None
        if field is None:
            raise ParseError(f"no switch case for {short_repr(key)}")
        return field.parse(r, ctx)


class Sized(Field):
    def __init__(self, size: Expr, inner: Any) -> None:
        check_size_arg(size, "sized size")
        self.size = size
        self.inner: Field = as_field(inner, "sized() inner")

    def bind(self, endian: str | None, where: str) -> Field:
        f = copy.copy(self)
        f.inner = self.inner.bind(endian, where)
        return f

    def refs(self) -> Iterator[Ref]:
        if isinstance(self.size, Ref):
            yield self.size
        yield from self.inner.refs()

    def parse(self, r: Reader, ctx: Context) -> Any:
        n = resolve_size(self.size, ctx, "sized size")
        r.push_region(n)
        try:
            value = self.inner.parse(r, ctx)
            left = r.remaining()
            if left:
                raise ParseError(f"{left} unused bytes at end of sized region", offset=r.tell())
        finally:
            r.pop_region()
        return value
