from enum import IntEnum

import byteparse as bp
from byteparse import this


class RRType(IntEnum):
    A = 1
    NS = 2
    CNAME = 5
    SOA = 6
    PTR = 12
    MX = 15
    TXT = 16
    AAAA = 28


class DNSFlags(bp.BitStruct):
    qr: bool = bp.flag()
    opcode: int = bp.bits(4)
    aa: bool = bp.flag()
    tc: bool = bp.flag()
    rd: bool = bp.flag()
    ra: bool = bp.flag()
    z: int = bp.bits(3)
    rcode: int = bp.bits(4)


class DNSHeader(bp.Struct, endian="big"):
    id: int = bp.u16()
    flags: DNSFlags
    qd_count: int = bp.u16()
    an_count: int = bp.u16()
    ns_count: int = bp.u16()
    ar_count: int = bp.u16()


class DNSLabel(bp.Struct):
    # 0xC0 pointers (name compression) are rejected by max=63 in v1.
    length: int = bp.u8(max=63)
    label: bytes = bp.bytes(this.length)


class DNSName(bp.Struct):
    labels: tuple[DNSLabel, ...] = bp.array(DNSLabel, until=lambda lab: lab.length == 0)

    def __str__(self) -> str:
        return ".".join(lab.label.decode("ascii", "replace") for lab in self.labels[:-1]) + "."


class DNSQuestion(bp.Struct, endian="big"):
    name: DNSName
    qtype: RRType | int = bp.enum(bp.u16(), RRType)
    qclass: int = bp.u16()


class DNSRecord(bp.Struct, endian="big"):
    name: DNSName
    rtype: RRType | int = bp.enum(bp.u16(), RRType)
    rclass: int = bp.u16()
    ttl: int = bp.u32()
    rdlength: int = bp.u16()
    rdata: bytes = bp.bytes(this.rdlength)


class DNSMessage(bp.Struct, endian="big"):
    header: DNSHeader
    questions: tuple[DNSQuestion, ...] = bp.array(DNSQuestion, this.header.qd_count)
    answers: tuple[DNSRecord, ...] = bp.array(DNSRecord, this.header.an_count)
    authority: tuple[DNSRecord, ...] = bp.array(DNSRecord, this.header.ns_count)
    additional: tuple[DNSRecord, ...] = bp.array(DNSRecord, this.header.ar_count)
