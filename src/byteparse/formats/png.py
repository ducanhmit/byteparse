import zlib
from enum import IntEnum

import byteparse as bp
from byteparse import this

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class ColorType(IntEnum):
    GRAYSCALE = 0
    RGB = 2
    PALETTE = 3
    GRAYSCALE_ALPHA = 4
    RGBA = 6


class PNGChunk(bp.Struct, endian="big"):
    length: int = bp.u32(max=2**31 - 1)
    chunk_type: bytes = bp.bytes(4)
    data: bytes = bp.bytes(this.length)
    crc: int = bp.u32(check=lambda v, ctx: v == zlib.crc32(ctx.chunk_type + ctx.data))


class IHDR(bp.Struct, endian="big"):
    width: int = bp.u32(min=1)
    height: int = bp.u32(min=1)
    bit_depth: int = bp.u8(one_of=(1, 2, 4, 8, 16))
    color_type: ColorType | int = bp.enum(bp.u8(), ColorType)
    compression: int = bp.u8(const=0)
    filter_method: int = bp.u8(const=0)
    interlace: int = bp.u8(one_of=(0, 1))


class PNGFile(bp.Struct, endian="big"):
    signature: bytes = bp.bytes(8, const=PNG_SIGNATURE)
    chunks: tuple[PNGChunk, ...] = bp.array(PNGChunk, until=lambda c: c.chunk_type == b"IEND")

    @property
    def ihdr(self) -> IHDR:
        first = self.chunks[0]
        if first.chunk_type != b"IHDR":
            raise bp.ParseError(f"first chunk is {first.chunk_type!r}, not b'IHDR'")
        return IHDR.parse(first.data)
