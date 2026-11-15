"""What a LoRa APRS board says of a packet besides the packet: the signal it measured, and whether the packet came from the internet and not from the air. Each firmware says the signal in its own way
(aprs-reference/lora-plan.md sections 2.4 and 3.5); a CA2RXU Tracker and the CA2RXU iGate's KISS and TNC2 lines say none.

- DL9SAU's tracker appends an element to the path of what it hands over in KISS: `Q`, the SNR in two characters and the RSSI in two (`QA7L2`: -7 dB, -112 dBm), from its `encode_snr_rssi_in_path`.
  Left in, it would show as a digipeater, go to APRS-IS and be repeated; `path_reading` takes every such element off and reads the first, and `ninth_element` the one after eight digipeaters, which
  no AX.25 frame can hold.
- esp32_loraprs sends a KISS command 7 right after each data frame: two big-endian 16-bit integers, the RSSI in dBm and the SNR times 100 (`signal_report`).
- The CA2RXU iGate, with its TNC off on USB, writes a line of its log for each packet: `<--- LoRa Packet Rx (RSSI:-73 | SNR:9.50 | FreqErr:120) : text` (`console_line`).
- The CA2RXU iGate's APRS bridge hands its clients what it took from APRS-IS as well: a path with TCPIP, TCPXX or a q-construct is the internet's, not the air's (`from_internet`).
- Its list of heard packets names a packet by its text, with every byte below 32 and 127 written as "." (`list_key`).

Pure code."""
import math
import re
import struct
from dataclasses import replace

from . import ax25
from .reading import Reading

_ELEMENT = re.compile(r"Q([0-9A-J])([0-9])([0-9K-Z])([0-9])")       # DL9SAU's: SNR 0 to 99 by two digits, -1 to -99 by a letter from A (the tens) and a digit; RSSI -1 to -99 by two digits, from -100 a letter from K
_CONSOLE = re.compile(rb"<--- LoRa Packet Rx (?:\(RSSI:(-?\d+) \| SNR:(-?\d+(?:\.\d+)?) \| FreqErr:-?\d+(?:\.\d+)?\) )?: (.*)", re.S)
_INTERNET = re.compile(r"TCPIP|TCPXX|Q[A-Z]{2}")                    # the internet's words in a path: APRS-IS's own, and its q-constructs (qAC, qAR, ...), which ax25 reads in capitals
_ADDRESS = 7                                                        # the bytes of an AX.25 address
_ADDRESSES = 2 + ax25.MAX_PATH                                      # the most an AX.25 frame holds: the destination, the source and eight digipeaters


def element_reading(call: str, ssid: int) -> Reading | None:
    """The reading of one DL9SAU path element; None for an element that is no such one."""
    found = _ELEMENT.fullmatch(call) if ssid == 0 else None
    if found is None:
        return None
    tens, ones, rtens, rones = found.groups()
    snr = (ord(tens) - ord("0")) * 10 + int(ones) if tens.isdigit() else -((ord(tens) - ord("A")) * 10 + int(ones))
    rssi = -((ord(rtens) - ord("0")) * 10 + int(rones)) if rtens.isdigit() else -((ord(rtens) - ord("A")) * 10 + int(rones))
    return Reading(snr=float(snr), rssi=float(rssi))


def path_reading(frame: ax25.Frame) -> tuple[ax25.Frame, Reading | None]:
    """The frame without DL9SAU's elements in its path, and the reading of the first of them; the frame as it is and None when its path has none."""
    readings = [(i, element_reading(a.call, a.ssid)) for i, a in enumerate(frame.path)]
    found = [reading for _, reading in readings if reading is not None]
    if not found:
        return frame, None
    return replace(frame, path=tuple(a for (_, reading), a in zip(readings, frame.path, strict=True) if reading is None)), found[0]


def ninth_element(payload: bytes) -> tuple[bytes, Reading] | None:
    """A frame DL9SAU's tracker appended its element to after eight digipeaters, which makes one address more than AX.25 holds: its bytes without that element (the address before it marked the last)
    and the element's reading; None for any other bytes."""
    end = (_ADDRESSES + 1) * _ADDRESS
    if len(payload) < end or any(payload[i * _ADDRESS + _ADDRESS - 1] & 1 for i in range(_ADDRESSES)) or not payload[end - 1] & 1:
        return None
    element = payload[end - _ADDRESS:end]
    reading = element_reading(bytes(b >> 1 for b in element[:6]).decode("latin-1").rstrip(" "), (element[6] >> 1) & 0x0F)
    if reading is None:
        return None
    return payload[:end - _ADDRESS - 1] + bytes([payload[end - _ADDRESS - 1] | 1]) + payload[end:], reading


def signal_report(payload: bytes) -> Reading | None:
    """The reading of esp32_loraprs's KISS command 7 (the RSSI in dBm, then the SNR times 100, each a big-endian 16-bit integer); None for a payload that is not four bytes."""
    if len(payload) != 4:
        return None
    rssi, snr = struct.unpack(">hh", payload)
    return Reading(snr=snr / 100, rssi=float(rssi))


def console_line(line: bytes) -> tuple[bytes, Reading | None] | None:
    """The packet's text of a CA2RXU iGate's log line of a packet it heard, with the reading when the line has one (a board in its eco mode writes none); None for any other line of its log."""
    found = _CONSOLE.fullmatch(line)
    if found is None:
        return None
    rssi, snr, text = found.groups()
    reading = None if rssi is None else Reading(snr=float(snr), rssi=float(rssi))
    return text, reading if reading is not None and math.isfinite(reading.snr or 0.0) and math.isfinite(reading.rssi or 0.0) else None     # (digits past a float's range are no reading)


def from_internet(frame: ax25.Frame) -> bool:
    """Whether the frame's path says it came from APRS-IS (a LoRa iGate's bridge hands it on): TCPIP, TCPXX or a q-construct in it."""
    return any(_INTERNET.fullmatch(a.call) for a in frame.path)


def list_key(text: bytes) -> str:
    """A packet's text as the CA2RXU iGate's list of heard packets writes it: every byte below 32 and 127 a ".", read as UTF-8 (what is no UTF-8 as the same replacement on both sides)."""
    return bytes(0x2E if b < 32 or b == 127 else b for b in text).decode("utf-8", "replace")
