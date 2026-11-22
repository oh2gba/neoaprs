"""Read the CA2RXU LoRa APRS iGate's list of recently heard packets with their RSSI and SNR.
Only `GET /received-packets.json` is requested; the board's configuration is never touched.
"""

import asyncio
import json
import math
from dataclasses import dataclass
from typing import Any

from .reading import Reading
from .tncmode import printable
from .tncprofile import bracketed

PATH = "/received-packets.json"
PORT = 80  # the board's web server, on the host of its KISS server
ANSWER_SEC = 2.0  # a slower board is treated as having no list
MAX_BODY = 64 * 1024


class ListError(OSError):
    """The board's list cannot be read: refused, no answer in time, not 200, not the list."""


@dataclass(frozen=True)
class Heard:
    """One list entry: the key, the board's date and time, and the signal reading."""

    key: str
    when: str
    reading: Reading


async def fetch(host: str) -> list[Heard]:
    """Return the board's list, oldest first; raise ListError if unreadable within ANSWER_SEC."""
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
        writer.write(
            f"GET {PATH} HTTP/1.0\r\nHost: {bracketed(host)}\r\nAccept: application/json\r\n\r\n".encode(
                "ascii", "replace"
            )
        )
        await writer.drain()
        answer = await reader.read(MAX_BODY)
        while chunk := await reader.read(MAX_BODY):
            answer += chunk
            if len(answer) > MAX_BODY:
                raise ListError("the answer is longer than a list of heard packets")
    except ListError:
        raise
    except OSError as e:
        raise ListError(f"the connection failed: {e}") from None
    finally:
        writer.close()
    return parse(answer)


def parse(answer: bytes) -> list[Heard]:
    """Return the entries of an HTTP answer, skipping malformed ones; ListError if not a list."""
    head, _, body = answer.partition(b"\r\n\r\n")
    status = head.split(b"\r\n", 1)[0].split()
    if len(status) < 2 or status[1] != b"200":
        # the board's bytes reach the log: control characters are removed
        raise ListError(f"the answer is {printable(b' '.join(status[1:]).decode('latin-1')) or 'not HTTP'}")
    try:
        entries = json.loads(body.decode("utf-8", "replace"))
    except (ValueError, RecursionError) as e:
        raise ListError(f"the answer is not the list of heard packets: {type(e).__name__}") from None
    if not isinstance(entries, list):
        raise ListError("the answer is not the list of heard packets: not a list")
    return [heard for heard in map(_entry, entries) if heard is not None]


def _entry(e: Any) -> Heard | None:
    """Return the entry, or None unless it has packet text and finite SNR and RSSI."""
    if not isinstance(e, dict) or not isinstance(e.get("packet"), str):
        return None
    try:
        snr, rssi = float(e["SNR"]), float(e["RSSI"])
    except (ValueError, TypeError, KeyError, OverflowError):
        return None
    return (
        Heard(e["packet"], f"{e.get('rxDate', '')} {e.get('rxTime', '')}", Reading(snr=snr, rssi=rssi))
        if math.isfinite(snr) and math.isfinite(rssi)
        else None
    )
