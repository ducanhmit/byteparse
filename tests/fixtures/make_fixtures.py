"""Regenerate the fixture files: python tests/fixtures/make_fixtures.py"""

import struct
import wave
import zlib
from pathlib import Path

HERE = Path(__file__).parent


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def make_png() -> bytes:
    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)  # 2x2, 8-bit RGB
    rows = b"\x00\xff\x00\x00\x00\xff\x00" + b"\x00\x00\x00\xff\xff\xff\xff"
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", zlib.compress(rows, 9))
        + png_chunk(b"IEND", b"")
    )


def make_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(struct.pack("<8h", 0, 1000, 2000, 1000, 0, -1000, -2000, -1000))


def make_bmp() -> bytes:
    # 2x2, 24-bit, rows padded to 4 bytes, bottom-up
    pixels = (b"\x00\x00\xff" + b"\xff\xff\xff" + b"\x00\x00") * 2
    dib = struct.pack("<IiiHHIIiiII", 40, 2, 2, 1, 24, 0, len(pixels), 2835, 2835, 0, 0)
    offset = 14 + len(dib)
    header = b"BM" + struct.pack("<IHHI", offset + len(pixels), 0, 0, offset)
    return header + dib + pixels


def dns_name(name: str) -> bytes:
    out = b""
    for label in name.rstrip(".").split("."):
        out += bytes([len(label)]) + label.encode()
    return out + b"\x00"


def make_dns() -> bytes:
    # Response to "example.com. IN A", answer name written without compression
    header = struct.pack(">HHHHHH", 0x1234, 0x8180, 1, 1, 0, 0)
    question = dns_name("example.com") + struct.pack(">HH", 1, 1)
    answer = (
        dns_name("example.com") + struct.pack(">HHIH", 1, 1, 300, 4) + bytes([93, 184, 215, 14])
    )
    return header + question + answer


if __name__ == "__main__":
    (HERE / "tiny.png").write_bytes(make_png())
    make_wav(HERE / "tone.wav")
    (HERE / "tiny.bmp").write_bytes(make_bmp())
    (HERE / "example_a.dns").write_bytes(make_dns())
