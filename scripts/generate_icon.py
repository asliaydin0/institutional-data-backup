"""Basit uygulama ikonu (ICO) üretir — harici bağımlılık yok."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    chunk = tag + data
    return struct.pack(">I", len(data)) + chunk + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)


def _solid_png(size: int, rgb: tuple[int, int, int]) -> bytes:
    """Tek renk daire benzeri kare PNG (RGBA)."""
    r, g, b = rgb
    rows = []
    cx = cy = (size - 1) / 2
    rad = size * 0.42
    for y in range(size):
        row = [0]  # filter None
        for x in range(size):
            dx, dy = x - cx, y - cy
            if dx * dx + dy * dy <= rad * rad:
                row.extend([r, g, b, 255])
            else:
                row.extend([0, 0, 0, 0])
        rows.append(bytes(row))
    raw = b"".join(rows)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )


def write_ico(path: Path) -> None:
    """16/32/48/256 boyutlarında kurumsal mavi ICO."""
    # BGR-ish blue #1d4ed8
    color = (29, 78, 216)
    sizes = [16, 32, 48, 256]
    images = [_solid_png(s, color) for s in sizes]

    # ICO: header + directory + image data
    count = len(images)
    offset = 6 + 16 * count
    directory = []
    blobs = b""
    for size, png in zip(sizes, images):
        w = 0 if size >= 256 else size
        h = 0 if size >= 256 else size
        directory.append(
            struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(png), offset)
        )
        offset += len(png)
        blobs += png

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        fh.write(struct.pack("<HHH", 0, 1, count))
        fh.write(b"".join(directory))
        fh.write(blobs)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    out = root / "resources" / "app.ico"
    write_ico(out)
    print(f"Wrote {out}")
