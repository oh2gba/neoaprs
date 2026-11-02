"""Makes the macOS icon of NeoAPRS.app out of the Windows one: `make_icns.py neoaprs/desktop/icon.ico OUT/NeoAPRS.icns`. The .ico holds the drawing of scripts/make-icon.py as PNG frames from 16 to 256 px; an
.icns is the same frames in a container of its own, each under the four-letter type of its size (and the 32, 64 and 256 px frames once more as the Retina doubles of 16, 32 and 128). macOS reads PNG frames
since 10.7 and scales the 256 one up where it wants 512, so no tool of a Mac (iconutil, sips) is needed and the file can be made, and tested, anywhere. Standard library only."""
import struct
import sys
from pathlib import Path

TYPES = {16: ("icp4",), 32: ("icp5", "ic11"), 64: ("icp6", "ic12"), 128: ("ic07",), 256: ("ic08", "ic13"), 512: ("ic09", "ic14"), 1024: ("ic10",)}       # the pixel size of a frame to the types that hold it


def png_frames(ico: bytes) -> dict[int, bytes]:
    """The PNG frames of an .ico by their size in pixels; a frame that is not a PNG (a bitmap) is left out."""
    count = struct.unpack("<H", ico[4:6])[0]
    frames: dict[int, bytes] = {}
    for i in range(count):
        width, _height, _colors, _reserved, _planes, _bpp, size, offset = struct.unpack("<BBBBHHII", ico[6 + 16 * i:22 + 16 * i])
        data = ico[offset:offset + size]
        if data.startswith(b"\x89PNG"):
            frames[width or 256] = data
    return frames


def icns(frames: dict[int, bytes]) -> bytes:
    """The container: `icns`, its length, then each frame under each of its types (type, length of the entry, the PNG), the sizes in order."""
    entries = b"".join(kind.encode("ascii") + struct.pack(">I", 8 + len(data)) + data for size, data in sorted(frames.items()) for kind in TYPES.get(size, ()))
    if not entries:
        raise ValueError("no frame of a size an .icns holds")
    return b"icns" + struct.pack(">I", 8 + len(entries)) + entries


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0 if len(argv) == 2 else 2
    frames = png_frames(Path(argv[1]).read_bytes())
    Path(argv[2]).write_bytes(icns(frames))
    print(f"make_icns: {argv[2]}: {', '.join(f'{size} px' for size in sorted(frames))}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
