"""Compare byteparse with struct.unpack and construct: python benchmarks/bench.py"""

from __future__ import annotations

import struct
import sys
import timeit
from collections.abc import Callable
from pathlib import Path

import byteparse as bp
from byteparse.formats import PNGFile

ROOT = Path(__file__).resolve().parent.parent
DNS_HEADER = struct.pack(">HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0)
PNG = (ROOT / "tests" / "fixtures" / "tiny.png").read_bytes()
RECORDS = b"".join(struct.pack("<IHH", i, i & 0xFFFF, 7) for i in range(10_000))


class Header(bp.Struct, endian="big"):
    id: int = bp.u16()
    flags: int = bp.u16()
    qd_count: int = bp.u16()
    an_count: int = bp.u16()
    ns_count: int = bp.u16()
    ar_count: int = bp.u16()


class Record(bp.Struct, endian="little"):
    key: int = bp.u32()
    a: int = bp.u16()
    b: int = bp.u16()


class Records(bp.Struct, endian="little"):
    items: tuple[Record, ...] = bp.array(Record, greedy=True)


def struct_header() -> tuple[int, ...]:
    return struct.unpack(">HHHHHH", DNS_HEADER)


def struct_records() -> list[tuple[int, ...]]:
    return list(struct.iter_unpack("<IHH", RECORDS))


def cases() -> list[tuple[str, str, Callable[[], object], int]]:
    out: list[tuple[str, str, Callable[[], object], int]] = [
        ("dns header", "struct", struct_header, 200_000),
        ("dns header", "byteparse", lambda: Header.parse(DNS_HEADER), 200_000),
        ("png file", "byteparse", lambda: PNGFile.parse(PNG), 20_000),
        ("10k records", "struct", struct_records, 50),
        ("10k records", "byteparse", lambda: Records.parse(RECORDS), 50),
    ]
    try:
        import construct as c
    except ImportError:
        print("construct not installed; skipping its rows", file=sys.stderr)
        return out
    c_header = c.Struct(
        "id" / c.Int16ub,
        "flags" / c.Int16ub,
        "qd_count" / c.Int16ub,
        "an_count" / c.Int16ub,
        "ns_count" / c.Int16ub,
        "ar_count" / c.Int16ub,
    )
    c_records = c.GreedyRange(c.Struct("key" / c.Int32ul, "a" / c.Int16ul, "b" / c.Int16ul))
    out += [
        ("dns header", "construct", lambda: c_header.parse(DNS_HEADER), 200_000),
        ("10k records", "construct", lambda: c_records.parse(RECORDS), 50),
    ]
    return out


def main() -> None:
    print(f"{'case':<12} {'library':<10} {'us/op':>10}")
    for case, lib, fn, number in sorted(cases(), key=lambda row: (row[0], row[1])):
        best = min(timeit.repeat(fn, number=number, repeat=5)) / number
        print(f"{case:<12} {lib:<10} {best * 1e6:>10.2f}")


if __name__ == "__main__":
    main()
