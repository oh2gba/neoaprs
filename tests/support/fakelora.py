"""A LoRa APRS board as its firmware speaks to the computer, for the tests of the LoRa types (aprs-reference/lora-plan.md section 4, step L1): the bytes are the firmwares' own, ported from their C++
(kept under work/par/studies/lora/src/), not made by our encoder, so that a test with our code on one end cannot hide a mismatch.

    board = Board("igate")                 # the CA2RXU LoRa APRS iGate (commit 1591d9f7): KISS on its TNC server, or TNC2 lines (kiss=False), its list of heard packets
    Board("tracker")                       # the CA2RXU LoRa APRS Tracker (commit 5bb2adce), classic Bluetooth: TNC2 lines until a client writes a KISS frame, then KISS
    Board("tracker-ble")                   # the same over Bluetooth LE: KISS on the aprs.fi service in notifications of up to 512 bytes, its input a buffer of 1024 cut at FEND; or TNC2 on its Nordic UART
                                           # (kiss=False), a byte per notification, and every write keyed as a packet
    Board("dl9sau")                        # DL9SAU's T-Beam tracker (master 5defe5d): KISS, an element with the SNR and the RSSI appended to the path (encode_snr_rssi_in_path, its own); the KISS
                                           # around it is CA2RXU's encodeKISS, a port from another firmware: DL9SAU's own KISS encoder is not among the kept sources
    Board("esp32")                         # esp32_loraprs (commit 0207ddf8): KISS, the AX.25 air form, KISS command 7 after each frame; or text mode (kiss=False), bare TNC2 lines
    Board("console")                       # the CA2RXU iGate on USB with its TNC off: the log line of each packet heard, with its signal; it reads nothing

    board.air(b"OH2ABC-7>APLRT1,WIDE1-1:!6010.00N/02456.00E>", rssi=-97, snr=6.25)    # a station heard on LoRa: what the board writes to its client
    board.internet(b"OH2XYZ>APRS,TCPIP*,qAC,T2FINLAND:>hi")                            # the iGate's APRS bridge hands on a line of APRS-IS
    board.battery(4.1)                     # esp32_loraprs's KISS command 9
    board.log("New TNC client connected")  # a line of the board's log
    board.transmitted                      # what the board keyed: the LoRa packet with its header (or the AX.25 bytes of esp32_loraprs's air form)

The ends: `BoardOnTcp(board)` is the board behind a TCP server on the loopback (the iGate's port 8001, or a serial line as `socket://`); `board_on_ble(monkeypatch, board)` behind `FakeBle`;
`ListServer(board)` is its web server, which answers `GET /received-packets.json` as the iGate does (or refuses, 401, 404, no JSON, no answer)."""
import asyncio
import json
import struct
from collections.abc import Callable

import pytest

from neoaprs import ax25, kiss
from neoaprs.tnc2line import frame_of
from tests.support.fakeble import NUS, NUS_NOTIFY, NUS_WRITE, FakeBle, Services
from tests.support.fakeradio import FakeRadio
from tests.support.loopbackserver import LoopbackServer

HEADER = b"\x3c\xff\x01"
MAX_KISS_BUFFER = 1024                 # tracker-ble_utils.cpp: the Tracker's KISS input over Bluetooth LE
FEND, FESC, TFEND, TFESC = 0xC0, 0xDB, 0xDC, 0xDD
HAS_BEEN_DIGIPITED, IS_LAST = 0b10000000, 0b1
MOBILINKD = "00000001-ba2a-46c9-ae49-01b0961f68bb"
TRACKER_KISS: Services = {MOBILINKD: [("00000002-ba2a-46c9-ae49-01b0961f68bb", ["write", "write-without-response"]), ("00000003-ba2a-46c9-ae49-01b0961f68bb", ["read", "notify"])]}
TRACKER_UART: Services = {NUS: [(NUS_WRITE, ["read", "notify"]), (NUS_NOTIFY, ["write", "write-without-response"])]}      # (tracker-ble_utils.cpp 37-39: TX is 6E400002, RX 6E400003, the other way round of Nordic's)


# ---- CA2RXU's kiss_utils.cpp (the iGate's and the Tracker's are the same functions)

def encode_address(address: bytes) -> bytes:
    """encodeAddressAX25: six characters shifted, the call cut to six without a word, the SSID after "-" by toInt (a trailing "*" read along), the star as the H bit."""
    digipeated = b"*" in address
    if b"-" not in address:
        if digipeated:
            address = address[:-1]
        address += b"-0"
    separator = address.index(b"-")
    digits = bytes(c for c in address[separator + 1:].split(b"*")[0] if 0x30 <= c <= 0x39)
    ssid = int(digits or b"0")
    out = bytes((address[i] if i < separator and i < len(address) else 0x20) << 1 & 0xFF for i in range(6))
    return out + bytes([(ssid << 1) & 0xFF | 0b01100000 | (HAS_BEEN_DIGIPITED if digipeated else 0)])


def encapsulate(ax25_frame: bytes, cmd: int = 0) -> bytes:
    out = bytearray([FEND, cmd & 0x0F])
    for c in ax25_frame:
        out += bytes([FESC, TFEND]) if c == FEND else bytes([FESC, TFESC]) if c == FESC else bytes([c])
    return bytes(out + bytes([FEND]))


def encode_kiss(text: bytes) -> bytes:
    """encodeKISS: the TNC2 text as an AX.25 frame in a KISS data frame (the destination written first, the last address marked, control 0x03, PID 0xF0, the information as it is)."""
    frame = b""
    if b":" in text and b">" in text:
        colon = text.index(b":")
        address, destination_written = b"", False
        for c in text[:colon + 1]:
            if c in b":>,":
                if not destination_written and c in b",:":
                    frame = encode_address(address) + frame
                    destination_written = True
                else:
                    frame += encode_address(address)
                address = b""
            else:
                address += bytes([c])
        frame = frame[:-1] + bytes([frame[-1] | IS_LAST]) + b"\x03\xf0" + text[colon + 1:]
    return encapsulate(frame)


def _decode_address(field: bytes, relay: bool) -> tuple[bytes, bool]:
    call = bytes(c >> 1 for c in field[:6] if c >> 1 != 0x20)
    ssid = (field[6] >> 1) & 0x0F
    return call + (b"-%d" % ssid if ssid else b"") + (b"*" if relay and field[6] & HAS_BEEN_DIGIPITED else b""), bool(field[6] & IS_LAST)


def decapsulate(frame: bytes) -> bytes:
    out, i = bytearray(), 2
    while i < len(frame) - 1:
        if frame[i] == FESC:
            out += bytes([FEND]) if frame[i + 1] == TFEND else bytes([FESC]) if frame[i + 1] == TFESC else b""
            i += 2
        else:
            out.append(frame[i])
            i += 1
    return bytes(out)


def decode_kiss(frame: bytes) -> tuple[bool, bytes]:
    """decodeKISS: whether it is a data frame, and the TNC2 text of it (the frame as it is for any other command)."""
    if not (frame[:1] == bytes([FEND]) and frame[-1:] == bytes([FEND])):
        return False, b""
    if frame[1] != 0:
        return False, frame
    body = decapsulate(frame)
    destination, _ = _decode_address(body[0:7], False)
    source, last = _decode_address(body[7:14], False)
    text, index = source + b">" + destination, 14
    while not last and index + 7 < len(body):
        digi, last = _decode_address(body[index:index + 7], True)
        text += b"," + digi
        index += 7
    return True, text + b":" + body[index + 2:]


def sanitize(text: bytes) -> str:
    """lora_utils.cpp sanitizeForWeb: every byte below 32 and 127 a "." (the JSON library writes the rest as it is)."""
    return bytes(0x2E if c < 32 or c == 127 else c for c in text).decode("utf-8", "replace")


# ---- DL9SAU's encode_snr_rssi_in_path (TTGO_T-Beam_LoRa_APRS.ino 4930-4958)

def q_element(snr: int, rssi: int) -> bytes:
    snr = max(-99, min(99, snr))
    rssi = max(-259, min(0, rssi))
    first = chr((abs(snr) // 10) + (ord("0") if snr >= 0 else ord("A")))
    third = chr((-rssi // 10) + (ord("0") if rssi > -100 else ord("A")))
    return f"Q{first}{abs(snr) % 10}{third}{-rssi % 10}".encode()


class Board:
    def __init__(self, firmware: str, *, kiss: bool = True, call: bytes = b"OH2LRG-10", tx_active: bool = True, accept_own: bool = False) -> None:
        self.firmware, self.kiss, self.call, self.tx_active, self.accept_own = firmware, kiss and firmware != "tracker", call, tx_active, accept_own
        self.out: Callable[[bytes], None] = lambda data: None        # what the board writes to its client (set by the end it sits behind)
        self.transmitted: list[bytes] = []                             # what it keyed on LoRa
        self.writes: list[bytes] = []                                  # every buffer a client wrote, as it came
        self.received: list[dict[str, object]] = []                    # the iGate's list of heard packets, the last 10 (web_utils.cpp 160-176)
        self._input = b""
        self._heard = 0                                                # the packets heard, for the time of each in the list

    # ---- the air and the internet
    def air(self, text: bytes, rssi: int = -97, snr: float = 6.25) -> None:
        """A station heard on LoRa, its packet `HEADER + text`; what the board does with it toward its client."""
        packet = HEADER + text
        if self.firmware in ("igate", "console"):
            self._heard += 1
            self.received = [*self.received, {"rxDate": "2026-11-15", "rxTime": f"12:{self._heard // 60:02d}:{self._heard % 60:02d}", "packet": sanitize(packet[3:]), "RSSI": rssi, "SNR": snr}][-10:]
        if self.firmware == "console":
            return self.out(b"<--- LoRa Packet Rx (RSSI:%d | SNR:%.2f | FreqErr:-123) : " % (rssi, snr) + text + b"\r\n")
        if self.firmware == "dl9sau":
            colon = text.index(b":")
            return self.out(encode_kiss(text[:colon] + b"," + q_element(round(snr), rssi) + text[colon:]))
        if self.firmware == "esp32":
            if not self.kiss:
                return self.out(text + b"\n")
            frame = ax25.encode(frame_of(text))                                                # (its air form is AX.25: the sending station's bytes, made by our encoder as any station's)
            return self.out(encapsulate(frame) + encapsulate(struct.pack(">hh", rssi, int(snr * 100)), 7))
        self._to_client(text)

    def internet(self, text: bytes) -> None:
        """aprs_is_utils.cpp 349-351: with the APRS bridge on, a line of APRS-IS to the clients, as it came (no header to strip)."""
        self._to_client(text)

    def _to_client(self, text: bytes) -> None:
        if self.firmware == "tracker-ble" and not self.kiss:
            for c in text:
                self.out(bytes([c]))                                                            # (a byte per notification, then the line end: ble_utils.cpp)
            return self.out(b"\n")
        self.out(encode_kiss(text) if self.kiss else text + b"\r\n")

    def battery(self, volts: float) -> None:
        """esp32_loraprs's telemetry, KISS command 9, every 60 s in client mode."""
        self.out(encapsulate(struct.pack(">h", int(volts * 100)), 9))

    def log(self, line: str) -> None:
        self.out(line.encode() + b"\r\n")

    def json(self) -> bytes:
        return json.dumps(self.received).encode()

    def restart(self, *, kiss: bool) -> None:
        """The board restarts with its TNC set to KISS or to TNC2 (its configuration saved on its page): what its input held is gone."""
        self.kiss, self._input = kiss, b""

    # ---- what a client writes
    def hear(self, data: bytes) -> None:
        self.writes.append(data)
        if self.firmware == "console":
            return                                                                             # (the log is no TNC: enableSerial is off, the line is not read)
        if self.firmware == "tracker":
            return self._tracker_buffer(data)
        if self.firmware == "esp32":
            for frame in kiss.KissDecoder().feed(data):
                if frame.command == 0:
                    self.transmitted.append(frame.payload)
            return
        if self.firmware == "tracker-ble":
            return self._ble_kiss(data) if self.kiss else self._ble_tnc2(data)
        for c in data:
            self._kiss_char(c) if self.kiss else self._tnc2_char(c)

    def _kiss_char(self, c: int) -> None:
        """tnc_utils.cpp handleInputDataKISS: a buffer that begins with FEND, read at each FEND past three bytes, cleared past 255."""
        if not self._input and c != FEND:
            return
        self._input += bytes([c])
        if c == FEND and len(self._input) > 3:
            data, text = decode_kiss(self._input)
            if data:
                self._take(text)
            self._input = b""
        if len(self._input) > 255:
            self._input = b""

    def _tnc2_char(self, c: int) -> None:
        if c == 0x0D:
            return
        if c == 0x0A:
            line, self._input = self._input.strip(), b""
            if b":" in line and b">" in line:
                self._take(line)
            return
        self._input += bytes([c])
        if len(self._input) > 255:
            self._input = b""

    def _tracker_buffer(self, data: bytes) -> None:
        """bluetooth_utils.cpp 103-137: a buffer that begins and ends with FEND is KISS (and the answers turn to KISS), any other buffer turns them back to TNC2; it is sent when its text is TNC2."""
        text = data
        if data[:1] == bytes([FEND]) and data[-1:] == bytes([FEND]):
            _, text = decode_kiss(data)
            self.kiss = True
        else:
            self.kiss = False
        if b":" in text and b">" in text and text.index(b":") > text.index(b">"):
            self.transmitted.append(HEADER + text)

    def _ble_tnc2(self, data: bytes) -> None:
        """tracker-ble_utils.cpp onWrite, TNC2: every write is the packet, whatever it holds, and sendNewPacket keys it with the header (RadioLib's transmit of a String ends it at a NUL)."""
        self.transmitted.append(HEADER + data.split(b"\x00", 1)[0])

    def _ble_kiss(self, data: bytes) -> None:
        """tracker-ble_utils.cpp onWrite, KISS: the write is added to a buffer that is cleared past 1024 bytes; up to ten frames are cut from it at FEND (bytes before a FEND thrown away), each of four bytes
        or more decoded into BLEToLoRaPacket (a command frame too, as itself), and once a data frame came, what BLEToLoRaPacket holds last is keyed (sendToLoRa sends one packet)."""
        self._input += data
        if len(self._input) > MAX_KISS_BUFFER:
            self._input = b""
            return
        packet, send = b"", False
        for _ in range(10):
            if not self._input:
                break
            if self._input[0] != FEND:
                first = self._input.find(bytes([FEND]))
                self._input = b"" if first == -1 else self._input[first:]
                if first == -1:
                    break
                continue
            end = self._input.find(bytes([FEND]), 1)
            if end == -1:
                break
            frame, self._input = self._input[:end + 1], self._input[end + 1:]
            if len(frame) >= 4:
                is_data, packet = decode_kiss(frame)
                send = send or is_data
        if send:
            self.transmitted.append(HEADER + packet.split(b"\x00", 1)[0])

    def _take(self, text: bytes) -> None:
        """processInputFrame: a frame from the board's own call is dropped unless acceptOwn; it is keyed only with txActive."""
        if (self.accept_own or text.split(b">", 1)[0] != self.call) and self.tx_active:
            self.transmitted.append(HEADER + text)


class BoardOnTcp(FakeRadio):
    """The board behind a TCP server on the loopback: the iGate's TNC server, or a serial line written as `socket://`."""

    def __init__(self, board: Board) -> None:
        super().__init__()
        self.board = board
        board.out = self.feed

    def heard_bytes(self, data: bytes) -> None:
        super().heard_bytes(data)
        self.board.hear(data)


def board_on_ble(monkeypatch: pytest.MonkeyPatch, board: Board) -> FakeBle:
    """The Tracker behind Bluetooth LE: its KISS service, or its Nordic UART with the roles swapped; what it notifies in pieces of at most 512 bytes; each write of the link is a buffer it reads."""
    ble = FakeBle(monkeypatch, TRACKER_KISS if board.kiss else TRACKER_UART, chunk=512)

    def notify(data: bytes) -> None:
        for i in range(0, len(data), 512):
            ble.feed(data[i:i + 512])

    board.out = notify
    original = ble.BleakClient.write_gatt_char

    async def written(client: object, char: object, data: bytes, response: bool) -> None:
        await original(client, char, data, response)       # type: ignore[arg-type]
        board.hear(bytes(data))

    monkeypatch.setattr(ble.BleakClient, "write_gatt_char", written)
    return ble


class ListServer(LoopbackServer):
    """The iGate's web server: `GET /received-packets.json` answers the board's list; `answer` "list", "401", "404", "junk" or "hang"; `requests` counts what was asked, by path."""

    def __init__(self, board: Board) -> None:
        self.board, self.answer = board, "list"
        self.requests: list[str] = []

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1")
            path = head.split(" ")[1]
            self.requests.append(path)
            if self.answer == "hang":
                await reader.read()
                return
            status, body = (b"200 OK", self.board.json()) if self.answer == "list" and path == "/received-packets.json" else \
                (b"200 OK", b"<html>not JSON</html>") if self.answer == "junk" else (b"401 Unauthorized" if self.answer == "401" else b"404 Not Found", b"")
            writer.write(b"HTTP/1.1 " + status + b"\r\nContent-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(body) + body)
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, asyncio.CancelledError):
            pass
        finally:
            writer.close()
