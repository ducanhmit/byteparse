from __future__ import annotations

from typing import Any

from .errors import DefinitionError, ParseError, prepend
from .fields import Bits, Field
from .reader import Reader
from .refs import Context


class Step:
    def run(self, r: Reader, ctx: Context, values: dict[str, Any]) -> None:
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

    def apply(self, raw: Any, start: int, ctx: Context, values: dict[str, Any]) -> None:
        shift = self.nbytes * 8
        for name, bits in self.members:
            shift -= bits.nbits
            value = (raw >> shift) & ((1 << bits.nbits) - 1)
            values[name] = bool(value) if bits.as_bool else value


def build_steps(fields: list[tuple[str, Field]]) -> list[Step]:
    steps: list[Step] = []
    bits_run: list[tuple[str, Bits]] = []
    for name, field in fields:
        if isinstance(field, Bits):
            bits_run.append((name, field))
            continue
        if bits_run:
            steps.append(BitGroupStep(bits_run))
            bits_run = []
        steps.append(FieldStep(name, field))
    if bits_run:
        steps.append(BitGroupStep(bits_run))
    return steps
