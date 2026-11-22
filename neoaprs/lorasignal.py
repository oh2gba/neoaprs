"""What a LoRa APRS board says of a packet besides the packet: its signal and its origin.
Pure code for DL9SAU path elements, esp32_loraprs command 7, CA2RXU console lines and list keys.
"""

import math
import re
import struct
from dataclasses import replace

from . import ax25
from .reading import Reading

# DL9SAU's element: SNR 0..99 as two digits, -1..-99 as letter (tens, from A) and digit;
# RSSI -1..-99 as two digits, from -100 a letter from K.
_ELEMENT = re.compile(r"Q([0-9A-J])([0-9])([0-9K-Z])([0-9])")
_CONSOLE = re.compile(
    rb"<--- LoRa Packet Rx (?:\(RSSI:(-?\d+) \| SNR:(-?\d+(?:\.\d+)?) \| FreqErr:-?\d+(?:\.\d+)?\) )?: (.*)", re.S
)
# APRS-IS's own path words and q-constructs, which ax25 reads in capitals
_INTERNET = re.compile(r"TCPIP|TCPXX|Q[A-Z]{2}")
_ADDRESS = 7  # the bytes of an AX.25 address
# destination, source and eight digipeaters
_ADDRESSES = 2 + ax25.MAX_PATH


def element_reading(call: str, ssid: int) -> Reading | None:
    """Return the reading of one DL9SAU path element, or None if it is not one."""
    found = _ELEMENT.fullmatch(call) if ssid == 0 else None
    if found is None:
        return None
    tens, ones, rtens, rones = found.groups()
    snr = (ord(tens) - ord("0")) * 10 + int(ones) if tens.isdigit() else -((ord(tens) - ord("A")) * 10 + int(ones))
    rssi = (
        -((ord(rtens) - ord("0")) * 10 + int(rones))
        if rtens.isdigit()
        else -((ord(rtens) - ord("A")) * 10 + int(rones))
    )
    return Reading(snr=float(snr), rssi=float(rssi))


def path_reading(frame: ax25.Frame) -> tuple[ax25.Frame, Reading | None]:
    """Return the frame without DL9SAU's path elements and the reading of the first, or None."""
    readings = [(i, element_reading(a.call, a.ssid)) for i, a in enumerate(frame.path)]
    found = [reading for _, reading in readings if reading is not None]
    if not found:
        return frame, None
    return replace(
        frame, path=tuple(a for (_, reading), a in zip(readings, frame.path, strict=True) if reading is None)
    ), found[0]


def ninth_element(payload: bytes) -> tuple[bytes, Reading] | None:
    """Return a frame's bytes without DL9SAU's ninth path element, and its reading; else None."""
    end = (_ADDRESSES + 1) * _ADDRESS
    if (
        len(payload) < end
        or any(payload[i * _ADDRESS + _ADDRESS - 1] & 1 for i in range(_ADDRESSES))
        or not payload[end - 1] & 1
    ):
        return None
    element = payload[end - _ADDRESS : end]
    reading = element_reading(
        bytes(b >> 1 for b in element[:6]).decode("latin-1").rstrip(" "), (element[6] >> 1) & 0x0F
    )
    if reading is None:
        return None
    return payload[: end - _ADDRESS - 1] + bytes([payload[end - _ADDRESS - 1] | 1]) + payload[end:], reading


def signal_report(payload: bytes) -> Reading | None:
    """Return the reading of esp32_loraprs's KISS command 7 (RSSI, SNR x 100), else None."""
    if len(payload) != 4:
        return None
    rssi, snr = struct.unpack(">hh", payload)
    return Reading(snr=snr / 100, rssi=float(rssi))


def console_line(line: bytes) -> tuple[bytes, Reading | None] | None:
    """Return the packet text of a CA2RXU iGate log line and its reading if any; else None."""
    found = _CONSOLE.fullmatch(line)
    if found is None:
        return None
    rssi, snr, text = found.groups()
    reading = None if rssi is None else Reading(snr=float(snr), rssi=float(rssi))
    return text, reading if reading is not None and math.isfinite(reading.snr or 0.0) and math.isfinite(
        reading.rssi or 0.0
    ) else None


def from_internet(frame: ax25.Frame) -> bool:
    """Return whether the path says the frame came from APRS-IS (TCPIP, TCPXX or a q-construct)."""
    return any(_INTERNET.fullmatch(a.call) for a in frame.path)


def list_key(text: bytes) -> str:
    """Return a packet's text as the iGate's list writes it: bytes below 32 and 127 become "."."""
    return bytes(0x2E if b < 32 or b == 127 else b for b in text).decode("utf-8", "replace")
