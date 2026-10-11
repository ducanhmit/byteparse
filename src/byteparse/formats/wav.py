import byteparse as bp
from byteparse import this


class RiffChunk(bp.Struct, endian="little"):
    chunk_id: bytes = bp.bytes(4)
    size: int = bp.u32()
    body: bytes = bp.bytes(this.size)
    pad: None = bp.padding(lambda ctx: ctx.size & 1)


class WAVFormat(bp.Struct, endian="little"):
    audio_format: int = bp.u16()
    channels: int = bp.u16(min=1)
    sample_rate: int = bp.u32()
    byte_rate: int = bp.u32()
    block_align: int = bp.u16()
    bits_per_sample: int = bp.u16()


class WAVFile(bp.Struct, endian="little"):
    riff: bytes = bp.bytes(4, const=b"RIFF")
    size: int = bp.u32(min=4)
    wave: bytes = bp.bytes(4, const=b"WAVE")
    chunks: tuple[RiffChunk, ...] = bp.sized(
        lambda ctx: ctx.size - 4, bp.array(RiffChunk, greedy=True)
    )

    def chunk(self, chunk_id: bytes) -> RiffChunk:
        for c in self.chunks:
            if c.chunk_id == chunk_id:
                return c
        raise KeyError(chunk_id)

    @property
    def format(self) -> WAVFormat:
        return WAVFormat.parse(self.chunk(b"fmt ").body, allow_trailing=True)

    @property
    def data(self) -> bytes:
        return self.chunk(b"data").body
