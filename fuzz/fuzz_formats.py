"""Atheris fuzz target for the format catalog.

pip install atheris
python fuzz/fuzz_formats.py -max_total_time=60
"""

import sys

import atheris

with atheris.instrument_imports():
    import byteparse as bp
    from byteparse.formats import FORMATS

NAMES = sorted(FORMATS)
LIMITS = dict(max_field_bytes=1 << 16, max_items=1024, max_depth=32)


def test_one_input(data: bytes) -> None:
    if not data:
        return
    struct_cls = FORMATS[NAMES[data[0] % len(NAMES)]]
    try:
        struct_cls.parse(data[1:], **LIMITS)
    except bp.ParseError:
        pass


if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
