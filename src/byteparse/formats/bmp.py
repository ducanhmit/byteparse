import byteparse as bp


class BMPFileHeader(bp.Struct, endian="little"):
    magic: bytes = bp.bytes(2, const=b"BM")
    file_size: int = bp.u32()
    reserved: None = bp.padding(4)
    pixel_offset: int = bp.u32()


class DIBHeader(bp.Struct, endian="little"):
    header_size: int = bp.u32(min=40)
    width: int = bp.i32()
    height: int = bp.i32()
    planes: int = bp.u16(const=1)
    bits_per_pixel: int = bp.u16(one_of=(1, 4, 8, 16, 24, 32))
    compression: int = bp.u32()
    image_size: int = bp.u32()
    x_pixels_per_meter: int = bp.i32()
    y_pixels_per_meter: int = bp.i32()
    colors_used: int = bp.u32()
    colors_important: int = bp.u32()
    extra: None = bp.padding(lambda ctx: ctx.header_size - 40)


class BMPFile(bp.Struct, endian="little"):
    file_header: BMPFileHeader
    dib: DIBHeader
    color_table: bytes = bp.bytes(
        lambda ctx: ctx.file_header.pixel_offset - 14 - ctx.dib.header_size
    )
    pixels: bytes = bp.bytes(lambda ctx: ctx.file_header.file_size - ctx.file_header.pixel_offset)
