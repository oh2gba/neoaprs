"""The CA2RXU LoRa APRS iGate's list of the packets it heard last, each with its RSSI and SNR: the one place where that firmware tells a client the signal of a packet (aprs-reference/lora-plan.md
section 3.5). It is asked of the board itself, on the address its KISS server is reached at, at `GET /received-packets.json` on port 80: a JSON list of at most 10 entries, oldest first, each
`{"rxDate", "rxTime", "packet", "RSSI", "SNR"}`, the packet's text with every byte below 32 and 127 written as "." (lorasignal.list_key).

Nothing else of the board is ever asked for: its configuration (`/configuration.json`) holds the WiFi passwords and the APRS-IS passcode, and a write of it rebuilds every setting and restarts the board."""
import asyncio
import json
import math
from dataclasses import dataclass
from typing import Any

from .reading import Reading

PATH = "/received-packets.json"
PORT = 80                               # the board's web server (CA2RXU's web_utils.cpp): fixed, the same address as its KISS server
ANSWER_SEC = 2.0                        # the whole request: a board on the local network answers in far less; one that does not is taken as having no list
MAX_BODY = 64 * 1024                    # ten entries are under 3 kB


class ListError(OSError):
    """The board's list cannot be read: refused, no answer in time, not 200, not the list."""


@dataclass(frozen=True)
class Heard:
    """One entry of the list: what names it (the date, the time and the text, as the board wrote them) and its reading."""
    key: str
    when: str
    reading: Reading


async def fetch(host: str) -> list[Heard]:
    """The board's list, oldest first, asked of the host on PORT within ANSWER_SEC. ListError when it cannot be read."""
    answer_sec = ANSWER_SEC
    try:
        return await asyncio.wait_for(_fetch(host, PORT), answer_sec)
    except TimeoutError:
        raise ListError(f"no answer within {answer_sec:g} s") from None


async def _fetch(host: str, port: int) -> list[Heard]:
    try:
        reader, writer = await asyncio.open_connection(host, port)
    except OSError as e:
        raise ListError(f"cannot connect: {e}") from None
    try:
        writer.write(f"GET {PATH} HTTP/1.0\r\nHost: {host}\r\nAccept: application/json\r\n\r\n".encode("ascii", "replace"))
        await writer.drain()
        answer = await reader.read(MAX_BODY)
        while chunk := await reader.read(MAX_BODY):
            answer += chunk
            if len(answer) > MAX_BODY:
                raise ListError("the answer is longer than a list of heard packets")
    except OSError as e:
        raise ListError(f"the connection failed: {e}") from None
    finally:
        writer.close()
    return parse(answer)


def parse(answer: bytes) -> list[Heard]:
    """The entries of an HTTP answer with the list in its body, an entry that is not one of the list passed over; ListError for an answer that is not 200 or whose body is not a list."""
    head, _, body = answer.partition(b"\r\n\r\n")
    status = head.split(b"\r\n", 1)[0].split()
    if len(status) < 2 or status[1] != b"200":
        raise ListError(f"the answer is {b' '.join(status[1:]).decode('latin-1') or 'not HTTP'}")
    try:
        entries = json.loads(body.decode("utf-8", "replace"))
    except (ValueError, RecursionError) as e:
        raise ListError(f"the answer is not the list of heard packets: {type(e).__name__}") from None
    if not isinstance(entries, list):
        raise ListError("the answer is not the list of heard packets: not a list")
    return [heard for heard in map(_entry, entries) if heard is not None]


def _entry(e: Any) -> Heard | None:
    """One entry of the list; None for one that is not an entry with a packet's text and two finite readings (a reading of NaN or infinity is no measurement, and JSON cannot carry it on)."""
    if not isinstance(e, dict) or not isinstance(e.get("packet"), str):
        return None
    try:
        snr, rssi = float(e["SNR"]), float(e["RSSI"])
    except (ValueError, TypeError, KeyError, OverflowError):
        return None
    return Heard(e["packet"], f"{e.get('rxDate', '')} {e.get('rxTime', '')}", Reading(snr=snr, rssi=rssi)) if math.isfinite(snr) and math.isfinite(rssi) else None
