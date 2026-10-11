from __future__ import annotations

import dataclasses
import inspect
import sys
from typing import IO, Any, ClassVar, Literal, Self, dataclass_transform

from . import specifiers as sp
from .errors import DefinitionError, ParseError, Partial
from .fields import Bits, Field, Padding, StructField
from .plan import Step, build_steps
from .reader import BufferReader, Limits, Reader, StreamReader
from .refs import Context

_DEFAULT = Limits()


def _annotations(cls: type) -> dict[str, Any]:
    try:
        return dict(inspect.get_annotations(cls))
    except NameError:
        if sys.version_info >= (3, 14):
            import annotationlib

            return dict(annotationlib.get_annotations(cls, format=annotationlib.Format.FORWARDREF))
        raise


def _resolve_type(annotation: Any, cls: type) -> Any:
    if not isinstance(annotation, str):
        return annotation
    module = sys.modules.get(cls.__module__)
    namespace = dict(vars(module)) if module else {}
    namespace.update(vars(cls))
    try:
        return eval(annotation, namespace)
    except Exception:
        return None


def _check_refs(cls: type, name: str, field: Field, earlier: dict[str, Field]) -> None:
    for ref in field.refs():
        fields = earlier
        path = ref._path
        for i, part in enumerate(path):
            target = fields.get(part)
            if target is None:
                raise DefinitionError(
                    f"{cls.__name__}.{name}: {ref!r} does not refer to an earlier field"
                )
            if i < len(path) - 1:
                if not isinstance(target, StructField):
                    raise DefinitionError(
                        f"{cls.__name__}.{name}: {ref!r} reaches into a non-struct field"
                    )
                fields = target.struct_cls._bp_field_map


# mypy requires field_specifiers to be a tuple literal written here.
@dataclass_transform(
    kw_only_default=True,
    frozen_default=True,
    field_specifiers=(
        sp.u8,
        sp.i8,
        sp.u16,
        sp.i16,
        sp.u24,
        sp.i24,
        sp.u32,
        sp.i32,
        sp.u64,
        sp.i64,
        sp.f32,
        sp.f64,
        sp.boolean,
        sp.bytes,
        sp.cstring,
        sp.pascal_string,
        sp.padding,
        sp.bits,
        sp.flag,
        sp.enum,
        sp.array,
        sp.if_,
        sp.switch,
        sp.sized,
    ),
)
class Struct:
    _bp_fields: ClassVar[tuple[tuple[str, Field], ...]] = ()
    _bp_field_map: ClassVar[dict[str, Field]] = {}
    _bp_steps: ClassVar[list[Step]] = []
    _bp_padding: ClassVar[frozenset[str]] = frozenset()
    _bp_bits_only: ClassVar[bool] = False

    def __init_subclass__(
        cls, *, endian: Literal["big", "little"] | None = None, **kwargs: Any
    ) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__dict__.get("_bp_abstract"):
            return
        if endian not in (None, "big", "little"):
            raise DefinitionError(f"{cls.__name__}: endian must be 'big' or 'little'")
        for base in cls.__mro__[1:]:
            if base.__dict__.get("_bp_fields"):
                raise DefinitionError(
                    f"{cls.__name__}: subclassing a struct with fields is not supported"
                )
        _build(cls, endian)

    @classmethod
    def parse(
        cls,
        data: bytes | bytearray | memoryview,
        *,
        allow_trailing: bool = False,
        max_field_bytes: int = _DEFAULT.max_field_bytes,
        max_items: int = _DEFAULT.max_items,
        max_depth: int = _DEFAULT.max_depth,
    ) -> Self:
        limits = Limits(max_field_bytes, max_items, max_depth)
        return cls._bp_run(BufferReader(data, limits), check_trailing=not allow_trailing)

    @classmethod
    def parse_stream(
        cls,
        stream: IO[bytes],
        *,
        max_field_bytes: int = _DEFAULT.max_field_bytes,
        max_items: int = _DEFAULT.max_items,
        max_depth: int = _DEFAULT.max_depth,
    ) -> Self:
        limits = Limits(max_field_bytes, max_items, max_depth)
        return cls._bp_run(StreamReader(stream, limits), check_trailing=False)

    @classmethod
    def _bp_run(cls, r: Reader, *, check_trailing: bool) -> Self:
        try:
            obj = cls._bp_parse(r, None)
            if check_trailing:
                left = r.remaining()
                if left:
                    err = ParseError(f"{left} trailing bytes after struct", offset=r.tell())
                    err.partial = Partial(cls.__name__, obj._bp_values())
                    raise err
        except ParseError as e:
            e.struct_name = cls.__name__
            raise
        return obj

    @classmethod
    def _bp_parse(cls, r: Reader, parent: Context | None) -> Self:
        r.enter()
        values: dict[str, Any] = {}
        ctx = Context(values, parent)
        try:
            for step in cls._bp_steps:
                step.run(r, ctx, values)
        except ParseError as e:
            shown = {k: v for k, v in values.items() if k not in cls._bp_padding}
            if e.partial is not None and e.path:
                shown[str(e.path[0])] = e.partial
            e.partial = Partial(cls.__name__, shown)
            raise
        finally:
            r.leave()
        return cls(**values)

    def _bp_values(self) -> dict[str, Any]:
        return {n: getattr(self, n) for n, _ in self._bp_fields if n not in self._bp_padding}

    def to_dict(self) -> dict[str, Any]:
        return {n: _plain(v) for n, v in self._bp_values().items()}


def _plain(value: Any) -> Any:
    if isinstance(value, Struct):
        return value.to_dict()
    if isinstance(value, tuple):
        return [_plain(v) for v in value]
    return value


class BitStruct(Struct):
    _bp_abstract: ClassVar[bool] = True
    _bp_bits_only: ClassVar[bool] = True


def _build(cls: type[Struct], endian: str | None) -> None:
    fields: list[tuple[str, Field]] = []
    field_map: dict[str, Field] = {}
    padding: set[str] = set()
    for name, annotation in _annotations(cls).items():
        spec = cls.__dict__.get(name, dataclasses.MISSING)
        where = f"{cls.__name__}.{name}"
        if isinstance(spec, Field):
            field = spec
        elif spec is dataclasses.MISSING:
            typ = _resolve_type(annotation, cls)
            if typ is None and isinstance(annotation, str):
                raise DefinitionError(
                    f"{where}: cannot resolve annotation {annotation!r}; nested structs must be "
                    "defined before use, at module level when using "
                    "`from __future__ import annotations`"
                )
            if not (isinstance(typ, type) and issubclass(typ, Struct)):
                raise DefinitionError(
                    f"{where}: needs a byteparse specifier, e.g. `{name}: int = bp.u8()`"
                )
            field = StructField(typ)
        else:
            raise DefinitionError(
                f"{where}: default values are not supported; use a byteparse specifier"
            )
        field = field.bind(endian, where)
        if cls._bp_bits_only and not isinstance(field, Bits):
            raise DefinitionError(f"{where}: BitStruct fields must be bits() or flag()")
        _check_refs(cls, name, field, field_map)
        fields.append((name, field))
        field_map[name] = field
        if isinstance(field, Padding):
            padding.add(name)

    steps = build_steps(fields)
    for name, _ in fields:
        if name in padding:
            setattr(cls, name, dataclasses.field(repr=False, compare=False))
        elif name in cls.__dict__:
            delattr(cls, name)
    cls._bp_fields = tuple(fields)
    cls._bp_field_map = field_map
    cls._bp_steps = steps
    cls._bp_padding = frozenset(padding)
    dataclasses.dataclass(frozen=True, kw_only=True)(cls)
