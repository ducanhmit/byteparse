import struct
import zlib
from pathlib import Path

import pytest

import byteparse as bp
from byteparse.formats import BMPFile, DNSMessage, PNGFile, WAVFile
from byteparse.formats.dns import RRType
from byteparse.formats.png import ColorType

FIXTURES = Path(__file__).parent / "fixtures"


def test_png():
    png = PNGFile.parse((FIXTURES / "tiny.png").read_bytes())
    assert [c.chunk_type for c in png.chunks] == [b"IHDR", b"IDAT", b"IEND"]
    ihdr = png.ihdr
    assert (ihdr.width, ihdr.height, ihdr.bit_depth) == (2, 2, 8)
    assert ihdr.color_type is ColorType.RGB


def test_png_bad_crc():
    data = bytearray((FIXTURES / "tiny.png").read_bytes())
    data[29] ^= 0xFF  # last byte of the IHDR CRC
    with pytest.raises(bp.ValidationError) as exc:
        PNGFile.parse(bytes(data))
    assert exc.value.path == ("chunks", 0, "crc")


def test_wav():
    wav = WAVFile.parse((FIXTURES / "tone.wav").read_bytes())
    fmt = wav.format
    assert (fmt.audio_format, fmt.channels, fmt.sample_rate, fmt.bits_per_sample) == (
        1,
        1,
        8000,
        16,
    )
    assert struct.unpack("<8h", wav.data)[1] == 1000


def test_wav_odd_chunk_is_padded():
    body = b"abc"
    chunk = b"junk" + struct.pack("<I", 3) + body + b"\0"
    fmt = b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 8000, 1, 8)
    payload = b"WAVE" + chunk + fmt
    wav = WAVFile.parse(b"RIFF" + struct.pack("<I", len(payload)) + payload)
    assert [c.chunk_id for c in wav.chunks] == [b"junk", b"fmt "]


def test_bmp():
    bmp = BMPFile.parse((FIXTURES / "tiny.bmp").read_bytes())
    assert (bmp.dib.width, bmp.dib.height, bmp.dib.bits_per_pixel) == (2, 2, 24)
    assert len(bmp.pixels) == 16


def test_dns():
    msg = DNSMessage.parse((FIXTURES / "example_a.dns").read_bytes())
    assert msg.header.flags.qr and msg.header.flags.rd
    assert str(msg.questions[0].name) == "example.com."
    answer = msg.answers[0]
    assert answer.rtype is RRType.A and answer.ttl == 300
    assert answer.rdata == bytes([93, 184, 215, 14])


def test_dns_compressed_name_is_rejected_clearly():
    data = bytearray((FIXTURES / "example_a.dns").read_bytes())
    answer_start = 12 + 13 + 4
    data[answer_start : answer_start + 13] = b"\xc0\x0c"
    with pytest.raises(bp.ValidationError) as exc:
        DNSMessage.parse(bytes(data))
    assert exc.value.path == ("answers", 0, "name", "labels", 0, "length")


def test_png_not_png():
    with pytest.raises(bp.ValidationError) as exc:
        PNGFile.parse(b"GIF89a" + bytes(20))
    assert exc.value.path == ("signature",)


def test_png_chunk_crc_matches_zlib():
    data = (FIXTURES / "tiny.png").read_bytes()
    chunk = PNGFile.parse(data).chunks[1]
    assert chunk.crc == zlib.crc32(chunk.chunk_type + chunk.data)
