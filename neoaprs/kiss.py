"""KISS framing: a streaming decoder that turns bytes from the line into frames, and the encoder for a frame to send.

A frame is FEND, a command byte (the port in the high nibble, the command in the low one: 0x00 is data on port 0), the data with FEND and FESC escaped, FEND. The decoder keeps a partial frame between
calls, throws away what it cannot trust (a bad escape, a frame that is too long, the start of a stream that begins in the middle of a frame) and counts what it dropped."""
from dataclasses import dataclass

FEND = 0xC0
FESC = 0xDB
TFEND = 0xDC
TFESC = 0xDD

MAX_FRAME = 1024                 # bytes of a frame after unescaping, the command byte included; a longer one is dropped


@dataclass(frozen=True)
class KissFrame:
    port: int
    command: int
    payload: bytes


def encode(payload: bytes, port: int = 0, command: int = 0) -> bytes:
    """FEND, the command byte, the payload with FEND and FESC escaped, FEND."""
    if not 0 <= port <= 15 or not 0 <= command <= 15:
        raise ValueError(f"KISS port and command are 4 bits each, got port {port} and command {command}")
    body = bytes([(port << 4) | command]) + payload
    escaped = body.replace(b"\xdb", b"\xdb\xdd").replace(b"\xc0", b"\xdb\xdc")
    return bytes([FEND]) + escaped + bytes([FEND])


class KissDecoder:
    """feed() the bytes as they arrive, in chunks of any size; it returns the frames that those bytes completed. `dropped` counts the frames that were thrown away."""

    def __init__(self, max_frame: int = MAX_FRAME) -> None:
        self.max_frame = max_frame
        self.dropped = 0
        self._buf = bytearray()
        self._synced = False             # a FEND has been seen: what follows is a whole frame. Before that the stream may have started in the middle of one
        self._escaped = False            # the last byte was FESC
        self._skipping = False           # this frame is lost: wait for its closing FEND

    def feed(self, data: bytes) -> list[KissFrame]:
        frames: list[KissFrame] = []
        for byte in data:
            if byte == FEND:
                self._end_of_frame(frames)
            elif not self._synced or self._skipping:
                continue
            elif self._escaped:
                self._escaped = False
                if byte == TFEND:
                    self._add(FEND)
                elif byte == TFESC:
                    self._add(FESC)
                else:
                    self._drop()
            elif byte == FESC:
                self._escaped = True
            else:
                self._add(byte)
        return frames

    def _add(self, byte: int) -> None:
        if len(self._buf) >= self.max_frame:
            self._drop()
        else:
            self._buf.append(byte)

    def _drop(self) -> None:
        self.dropped += 1
        self._buf.clear()
        self._skipping = True

    def _end_of_frame(self, frames: list[KissFrame]) -> None:
        if self._escaped and self._synced and not self._skipping:
            self._drop()                 # FESC then FEND: an escape that never finished
        if self._synced and not self._skipping and self._buf:
            command = self._buf[0]
            frames.append(KissFrame(port=command >> 4, command=command & 0x0F, payload=bytes(self._buf[1:])))
        self._buf.clear()
        self._escaped = False
        self._skipping = False
        self._synced = True
