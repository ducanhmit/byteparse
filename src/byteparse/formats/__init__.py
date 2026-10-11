from ..struct import Struct
from .bmp import BMPFile
from .dns import DNSMessage
from .png import PNGFile
from .wav import WAVFile

FORMATS: dict[str, type[Struct]] = {
    "png": PNGFile,
    "wav": WAVFile,
    "bmp": BMPFile,
    "dns": DNSMessage,
}

__all__ = ["FORMATS", "BMPFile", "DNSMessage", "PNGFile", "WAVFile"]
