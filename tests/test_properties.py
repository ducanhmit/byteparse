from hypothesis import given, settings
from hypothesis import strategies as st

import byteparse as bp
from byteparse.formats import FORMATS
from byteparse.formats.dns import DNSMessage

LIMITS = dict(max_field_bytes=4096, max_items=256, max_depth=16)


@settings(max_examples=300)
@given(name=st.sampled_from(sorted(FORMATS)), data=st.binary(max_size=512))
def test_arbitrary_bytes_parse_or_raise_parse_error(name, data):
    try:
        FORMATS[name].parse(data, **LIMITS)
    except bp.ParseError:
        pass


@settings(max_examples=200)
@given(data=st.binary(min_size=12, max_size=64))
def test_dns_header_counts_cannot_force_huge_work(data):
    huge_counts = data[:4] + b"\xff\xff" * 4 + data[12:]
    try:
        DNSMessage.parse(huge_counts, **LIMITS)
    except bp.ParseError:
        pass
