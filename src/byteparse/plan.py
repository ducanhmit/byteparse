from __future__ import annotations

import struct
from typing import Any

from .errors import DefinitionError, ParseError, prepend
from .fields import Bits, Field, Float, Int, Padding
from .reader import Reader
from .refs import Context

_UINT_CODES = {1: "B", 2: "H", 4: "I", 8: "Q"}


class Step:
    def run(self, r: Reader, ctx: Context, values: dict[str, Any]) -> None:
        raise NotImplementedError

    def struct_code(self) -> tuple[str, str | None, bool] | None:
        """(format, required endian, produces a value) if mergeable."""
        return None

    def apply(self, raw: Any, start: int, ctx: Context, values: dict[str, Any]) -> None:
        raise NotImplementedError


class FieldStep(Step):
    def __init__(self, name: str, field: Field) -> None:
        self.name = name
        self.field = field

    def run(self, r: Reader, ctx: Context, values: dict[str, Any]) -> None:
        start = r.tell()
        try:
            values[self.name] = self.field.parse(r, ctx)
        except ParseError as e:
            prepend(e, self.name, start)
            raise

    def struct_code(self) -> tuple[str, str | None, bool] | None:
        code = self.field.struct_code()
        if code is None:
            return None
        return (*code, not isinstance(self.field, Padding))

    def is_plain(self) -> bool:
        """True if the raw unpacked value is the final value and nothing needs checking."""
        if isinstance(self.field, Padding):
            return self.field.struct_code() is not None
        return isinstance(self.field, (Int, Float)) and not self.field.validators

    def apply(self, raw: Any, start: int, ctx: Context, values: dict[str, Any]) -> None:
        value = self.field.from_raw(raw)
        try:
            self.field.validate(value, ctx)
        except ParseError as e:
            prepend(e, self.name, start)
            raise
        values[self.name] = value


class BitGroupStep(Step):
    def __init__(self, members: list[tuple[str, Bits]]) -> None:
        total = sum(b.nbits for _, b in members)
        if total % 8:
            names = ", ".join(n for n, _ in members)
            raise DefinitionError(
                f"bit fields ({names}) total {total} bits, not a whole number of bytes"
            )
        self.members = members
        self.nbytes = total // 8

    def run(self, r: Reader, ctx: Context, values: dict[str, Any]) -> None:
        start = r.tell()
        try:
            data = r.read(self.nbytes)
        except ParseError as e:
            prepend(e, self.members[0][0], start)
            raise
        self.apply(int.from_bytes(data, "big"), start, ctx, values)

    def struct_code(self) -> tuple[str, str | None, bool] | None:
        code = _UINT_CODES.get(self.nbytes)
        if code is None:
            return None
        return (code, "big" if self.nbytes > 1 else None, True)

    def apply(self, raw: Any, start: int, ctx: Context, values: dict[str, Any]) -> None:
        shift = self.nbytes * 8
        for name, bits in self.members:
            shift -= bits.nbits
            value = (raw >> shift) & ((1 << bits.nbits) - 1)
            values[name] = bool(value) if bits.as_bool else value


class MergedStep(Step):
    def __init__(self, steps: list[Step], endian: str | None) -> None:
        codes = [s.struct_code() for s in steps]
        assert all(c is not None for c in codes)
        prefix = "<" if endian == "little" else ">"
        self.steps = steps
        self.has_value = [c[2] for c in codes if c is not None]
        self.offsets: list[int] = []
        fmt = prefix
        for c in codes:
            assert c is not None
            self.offsets.append(struct.calcsize(fmt))
            fmt += c[0]
        self.packer = struct.Struct(fmt)
        self.plain = all(isinstance(s, FieldStep) and s.is_plain() for s in steps)
        self.value_names = tuple(
            s.name
            for s, has in zip(steps, self.has_value, strict=True)
            if has and isinstance(s, FieldStep)
        )
        self.pad_names = tuple(
            s.name for s in steps if isinstance(s, FieldStep) and isinstance(s.field, Padding)
        )

    def run(self, r: Reader, ctx: Context, values: dict[str, Any]) -> None:
        start = r.tell()
        data = r.try_read(self.packer.size)
        if data is None:
            for step in self.steps:
                step.run(r, ctx, values)
            return
        if self.plain:
            values.update(zip(self.value_names, self.packer.unpack(data), strict=True))
            for name in self.pad_names:
                values[name] = None
            return
        raws = iter(self.packer.unpack(data))
        for step, offset, has_value in zip(self.steps, self.offsets, self.has_value, strict=True):
            raw = next(raws) if has_value else None
            step.apply(raw, start + offset, ctx, values)


class FastLayout:
    """A struct made only of plain fixed-size fields: one unpack builds it."""

    def __init__(self, packer: struct.Struct, names: tuple[str, ...], pads: tuple[str, ...]):
        self.packer = packer
        self.size = packer.size
        self.names = names
        self.pads = pads

    def make(self, cls: type, data: bytes) -> Any:
        obj: Any = object.__new__(cls)
        d = obj.__dict__
        d.update(zip(self.names, self.packer.unpack(data), strict=True))
        for name in self.pads:
            d[name] = None
        return obj

    def make_from(self, cls: type, data: bytes | bytearray) -> Any:
        obj: Any = object.__new__(cls)
        d = obj.__dict__
        d.update(zip(self.names, self.packer.unpack_from(data), strict=True))
        for name in self.pads:
            d[name] = None
        return obj

    def make_many(self, cls: type, data: bytes) -> list[Any]:
        names, pads, new = self.names, self.pads, object.__new__
        out = []
        for raw in self.packer.iter_unpack(data):
            obj: Any = new(cls)
            d = obj.__dict__
            d.update(zip(names, raw, strict=True))
            for name in pads:
                d[name] = None
            out.append(obj)
        return out


def fast_layout(fields: list[tuple[str, Field]]) -> FastLayout | None:
    fmt = ""
    names: list[str] = []
    pads: list[str] = []
    endian: str | None = None
    for name, field in fields:
        if not FieldStep(name, field).is_plain():
            return None
        code = field.struct_code()
        assert code is not None
        if code[1] is not None:
            if endian is not None and code[1] != endian:
                return None
            endian = code[1]
        fmt += code[0]
        (pads if isinstance(field, Padding) else names).append(name)
    if not names:
        return None
    prefix = "<" if endian == "little" else ">"
    return FastLayout(struct.Struct(prefix + fmt), tuple(names), tuple(pads))


def build_steps(fields: list[tuple[str, Field]], *, merge: bool = True) -> list[Step]:
    atoms: list[Step] = []
    bits_run: list[tuple[str, Bits]] = []
    for name, field in fields:
        if isinstance(field, Bits):
            bits_run.append((name, field))
            continue
        if bits_run:
            atoms.append(BitGroupStep(bits_run))
            bits_run = []
        atoms.append(FieldStep(name, field))
    if bits_run:
        atoms.append(BitGroupStep(bits_run))
    if not merge:
        return atoms

    steps: list[Step] = []
    run: list[Step] = []
    run_endian: str | None = None

    def flush() -> None:
        if len(run) > 1:
            steps.append(MergedStep(list(run), run_endian))
        else:
            steps.extend(run)
        run.clear()

    for atom in atoms:
        code = atom.struct_code()
        if code is None:
            flush()
            run_endian = None
            steps.append(atom)
            continue
        endian = code[1]
        if endian is not None and run_endian is not None and endian != run_endian:
            flush()
            run_endian = None
        if endian is not None:
            run_endian = endian
        run.append(atom)
    flush()
    return steps
