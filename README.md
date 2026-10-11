# byteparse

Typed, safe, declarative binary parsing for Python.

```python
from byteparse.formats import PNGFile

png = PNGFile.parse(open("image.png", "rb").read())
print(png.ihdr.width, png.ihdr.height)
```

## Why byteparse

- **Typed classes.** Fields are real Python types, so mypy, pyright and your
  IDE know that `chunk.length` is an `int`. No plugin needed.
- **Safe by default.** Length fields can't make the parser allocate gigabytes
  or loop forever: per-field size, array length and nesting depth are limited
  out of the box.
- **Errors that say where.** `PNGFile.chunks[3].data: expected 1024 bytes, got
  812 (offset 0x1a3)`, plus everything parsed before the failure.
- **Formats included.** PNG, WAV, BMP and DNS ship ready to use.
- **Fast.** Fixed-size runs of fields are read with one precompiled
  `struct.Struct` call.

## Define your own

```python
import zlib
import byteparse as bp
from byteparse import this

class Chunk(bp.Struct, endian="big"):
    length: int = bp.u32(max=2**31 - 1)
    chunk_type: bytes = bp.bytes(4)
    data: bytes = bp.bytes(this.length)
    crc: int = bp.u32(check=lambda v, ctx: v == zlib.crc32(ctx.chunk_type + ctx.data))

chunk = Chunk.parse(raw)              # bytes, bytearray or memoryview
chunk = Chunk.parse_stream(file_obj)  # reads only what it needs
```

`this.length` refers to an earlier field. For anything more complex, use a
lambda: `bp.bytes(lambda ctx: ctx.total - ctx.header_len)`.

## Field specifiers

| Specifier | Type |
|-----------|------|
| `u8 u16 u24 u32 u64`, `i8 ... i64` | `int` |
| `f32 f64` | `float` |
| `boolean()` | `bool` |
| `bytes(n)` | `bytes` |
| `cstring()`, `pascal_string(u16())` | `str` |
| `padding(n)` | `None` |
| `bits(n)`, `flag()` | `int`, `bool` |
| `enum(u8(), MyEnum)` | `MyEnum \| int` |
| `array(Item, count)` / `until=` / `greedy=True` | `tuple[Item, ...]` |
| `if_(cond, spec)` | `T \| None` |
| `switch(key, {1: A, 2: B}, default=...)` | union you annotate |
| `sized(n, Inner)` | `Inner` |

Validators are keyword arguments: `const=`, `min=`, `max=`, `one_of=`,
`check=lambda value, ctx: ...`.

## Errors

```python
try:
    png = PNGFile.parse(data)
except bp.ParseError as e:
    print(e)          # PNGFile.chunks[2].crc: check failed for value 2923585666 (offset 0x47)
    e.path            # ("chunks", 2, "crc")
    e.offset          # 0x47
    e.partial         # everything parsed before the failure
```

## Command line

```
python -m byteparse dump image.png --format png
python -m byteparse dump answer.bin --format dns --json
```

## Status

byteparse 0.1 parses only. Building (serializing) structs is planned for 1.x.
Requires Python 3.11+, no dependencies.
