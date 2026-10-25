"""A Bluetooth Low Energy KISS TNC as a pyserial-like port: `ble://AA:BB:CC:DD:EE:FF`, or `ble://AA:BB:CC:DD:EE:FF/nus` with the profile named (a profile name, or the UUID of a GATT service; on macOS the address is the UUID that
CoreBluetooth gives the device). It has the small part of pyserial's interface that `serialport.py` uses: `open`, `read` with the timeout, `in_waiting`, `write`, `cancel_read`, `cancel_write` and `close`, so that the line is read and written by
its two threads as every other port is, and a lost link is an exception of the read or the write that the TNC answers by opening the port again.

The BLE library, bleak, runs on a thread of its own with its own event loop (it is asyncio, and the daemon's loop is not to be shared with a Bluetooth stack). What the device notifies is queued and `read` hands it out; `write` is given to that loop and
waits until it is written, in pieces of what one write takes. bleak is an optional extra (`pip install 'neoaprs[ble]'`) and is imported only when a `ble://` port is opened.

A BLE KISS device offers a GATT service with one characteristic that is written (the host's bytes to the TNC) and one that notifies (the TNC's bytes to the host); the bytes are the KISS stream, in pieces as long as the link takes, so a frame may span
several notifications and one notification may hold several frames (`kiss.KissDecoder` takes a stream). The profiles known are in `PROFILES`. Without one in the URL the services of the connected device are looked at in that order and the first
that is there is used; the log says which."""
import asyncio
import concurrent.futures
import logging
import re
import threading
import time
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, TypeVar

import serial  # type: ignore[import-untyped]

log = logging.getLogger("neoaprs.btle")

SCHEME = "ble://"
INSTALL_HINT = "Bluetooth LE ports (ble://) need the bleak library: install it with `pip install 'neoaprs[ble]'` (or `uv tool install 'neoaprs[ble]'`)"
SCAN_SEC = 10.0                      # how long the device is looked for before it is said to be out of reach
CONNECT_SEC = 15.0                   # the connection and the discovery of the device's services
OPEN_LIMIT_SEC = SCAN_SEC + CONNECT_SEC + 5.0
CLOSE_SEC = 5.0                      # a disconnect that takes longer is given up (the stack drops the link by itself)
JOIN_SEC = 1.0
WRITE_TIMEOUT_SEC = 5.0              # when the port has no write timeout of its own
MIN_CHUNK_BYTES = 20                 # what any link takes in one write (the default ATT payload)
MAX_CHUNK_BYTES = 512                # a write with a response is never longer than this
ATT_HEADER_BYTES = 3                 # the part of the link's MTU that is not data
_MAC = r"[0-9A-F]{2}(?:[:-][0-9A-F]{2}){5}"
_UUID = r"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}"
_URL = re.compile(rf"^ble://({_MAC}|{_UUID})(?:/([^/\s]+))?/?$", re.IGNORECASE)
_SHORT_UUID = re.compile(r"^[0-9a-f]{4}$", re.IGNORECASE)
T = TypeVar("T")


@dataclass(frozen=True)
class Profile:
    """A GATT service that carries a KISS stream. `write` and `notify` are the UUIDs of its two characteristics, or None to take the first that can be written and the first that notifies (a service named by its UUID)."""
    name: str
    title: str
    service: str
    write: str | None
    notify: str | None


PROFILES = (
    Profile("mobilinkd", "BLE KISS service of the Mobilinkd TNC3 and TNC4 and the aprs.fi apps", "00000001-ba2a-46c9-ae49-01b0961f68bb", "00000002-ba2a-46c9-ae49-01b0961f68bb", "00000003-ba2a-46c9-ae49-01b0961f68bb"),
    Profile("nus", "Nordic UART Service", "6e400001-b5a3-f393-e0a9-e50e24dcca9e", "6e400002-b5a3-f393-e0a9-e50e24dcca9e", "6e400003-b5a3-f393-e0a9-e50e24dcca9e"),
)


def is_ble(path: str) -> bool:
    return path.strip().lower().startswith(SCHEME)


def profile_for(selector: str) -> Profile:
    """The profile a name in the URL means: one of `PROFILES` by its name, or a GATT service by its UUID (16 or 128 bits), whose characteristics are found by what they can do."""
    for profile in PROFILES:
        if selector.lower() == profile.name:
            return profile
    if _SHORT_UUID.match(selector):
        selector = f"0000{selector}-0000-1000-8000-00805f9b34fb"
    try:
        return Profile("custom", f"GATT service {uuid.UUID(selector)}", str(uuid.UUID(selector)), None, None)
    except ValueError:
        names = ", ".join(p.name for p in PROFILES)
        raise ValueError(f"{selector!r} is neither a BLE KISS profile ({names}) nor a service UUID") from None


def parse_url(path: str) -> tuple[str, Profile | None]:
    """The device address (upper case; with colons for a Bluetooth address) and the profile (None: not given, the device's services are looked at) of a `ble://` port; ValueError says what is wrong."""
    match = _URL.match(path.strip())
    if match is None:
        raise ValueError(f"{path!r} is not a Bluetooth LE port: write ble://AA:BB:CC:DD:EE:FF, or ble://AA:BB:CC:DD:EE:FF/nus with the profile ({', '.join(p.name for p in PROFILES)}) or a service UUID")
    address = match.group(1).upper()
    if len(address) == 17:                                # a Bluetooth address may be written with dashes; a UUID has its own
        address = address.replace("-", ":")
    return address, profile_for(match.group(2)) if match.group(2) else None


def import_bleak() -> Any:
    """The bleak library; an OSError that names the extra to install when it is not there."""
    try:
        import bleak  # type: ignore[import-not-found, unused-ignore]
    except ImportError as e:
        raise OSError(INSTALL_HINT) from e
    return bleak


def _find(services: Any, profile: Profile) -> tuple[Any, Any] | None:
    """The characteristic to write and the one to listen to of the profile's service, or None when the device has no such service or it lacks them."""
    service = next((s for s in services if s.uuid == profile.service), None)
    if service is None:
        return None
    if profile.write and profile.notify:
        pair = (service.get_characteristic(profile.write), service.get_characteristic(profile.notify))
    else:
        pair = (next((c for c in service.characteristics if {"write", "write-without-response"} & set(c.properties)), None),
                next((c for c in service.characteristics if {"notify", "indicate"} & set(c.properties)), None))
    return None if pair[0] is None or pair[1] is None else pair


def _pick(services: Any, wanted: Profile | None) -> tuple[Profile, Any, Any]:
    """The profile to use, with its two characteristics: the one named, else the first of `PROFILES` that the device has. OSError when there is none."""
    for profile in [wanted] if wanted else PROFILES:
        if (pair := _find(services, profile)) is not None:
            return profile, pair[0], pair[1]
    offered = ", ".join(s.uuid for s in services) or "none"
    lacks = f"it has no {wanted.title}" if wanted else "it has none of: " + ", ".join(p.title for p in PROFILES)
    raise OSError(f"the device has no BLE KISS service ({lacks}); its services: {offered}")


class _Loop:
    """A thread with an event loop of its own, where bleak runs."""

    def __init__(self, name: str) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_forever()
        finally:
            pending = asyncio.all_tasks(self.loop)
            for task in pending:
                task.cancel()
            self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            self.loop.close()

    def submit(self, coroutine: Coroutine[Any, Any, T]) -> "concurrent.futures.Future[T]":
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop)

    def call(self, coroutine: Coroutine[Any, Any, T], timeout: float | None) -> T:
        """Runs the coroutine on the loop and waits for it; one that takes longer than `timeout` is cancelled and raises TimeoutError."""
        future = self.submit(coroutine)
        try:
            return future.result(timeout)
        except TimeoutError:
            future.cancel()
            raise

    def stop(self) -> None:
        try:
            self.loop.call_soon_threadsafe(self.loop.stop)
        except RuntimeError:                              # the loop has ended already
            pass
        self._thread.join(JOIN_SEC)


class _Link:
    """The connected device, used on the BLE thread: its client and the characteristic that is written, with how."""

    def __init__(self, client: Any, write: Any) -> None:
        self.client, self.write = client, write
        self.response = "write-without-response" not in write.properties           # write without a response is faster and is what the KISS devices ask for; a characteristic that has only the other is written with one

    def chunk(self) -> int:
        size = self.client.mtu_size - ATT_HEADER_BYTES if self.response else self.write.max_write_without_response_size
        return min(max(int(size), MIN_CHUNK_BYTES), MAX_CHUNK_BYTES)

    async def send(self, data: bytes) -> None:
        size = self.chunk()
        for start in range(0, len(data), size):
            await self.client.write_gatt_char(self.write, data[start:start + size], response=self.response)

    async def disconnect(self) -> None:
        await self.client.disconnect()


async def open_link(bleak: Any, address: str, wanted: Profile | None, on_data: Callable[[bytes], None], on_lost: Callable[[str], None]) -> _Link:
    """Finds the device, connects, picks the service (the profile named, else the first of `PROFILES` that the device has) and starts listening to its notifications. Nothing is left connected when it fails."""
    device = await bleak.BleakScanner.find_device_by_address(address, timeout=SCAN_SEC)
    if device is None:
        raise TimeoutError(f"{address} was not seen in {SCAN_SEC:.0f} s")
    client = bleak.BleakClient(device, disconnected_callback=lambda _client: on_lost("the device disconnected"), timeout=CONNECT_SEC)
    try:
        await client.connect()
        profile, write, notify = _pick(client.services, wanted)
        await client.start_notify(notify, lambda _char, data: on_data(bytes(data)))
    except BaseException:
        await _disconnect_quietly(client)
        raise
    log.info("%s: connected, using the %s%s", address, profile.title, "" if wanted else " (none was named)")
    return _Link(client, write)


async def _disconnect_quietly(client: Any) -> None:
    try:
        await client.disconnect()
    except Exception as e:                                # a disconnect that fails leaves nothing to do but say so
        log.info("disconnecting: %s", e)


class BleSerial(serial.SerialBase):  # type: ignore[misc]
    """The port: pyserial's SerialBase, which keeps the parameters it is given (a BLE link has no speed to set and no control lines to hold) over a BLE connection."""

    is_open: bool

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._cond = threading.Condition()
        self._buffer = bytearray()
        self._failure: str | None = None                  # why the link is gone, once it is; what was received before is still read
        self._cancelled = False
        self._loop: _Loop | None = None
        self._link: _Link | None = None
        self._writing: concurrent.futures.Future[None] | None = None

    def open(self) -> None:
        if self._port is None:
            raise serial.SerialException("Port must be configured before it can be used.")
        if self.is_open:
            raise serial.SerialException("Port is already open.")
        try:
            address, wanted = parse_url(self.portstr)
            bleak = import_bleak()
        except (OSError, ValueError) as e:
            raise self._cannot_open(e) from e
        self._buffer.clear()
        self._failure, self._cancelled = None, False
        loop = _Loop(f"ble {address}")
        try:
            self._link = loop.call(open_link(bleak, address, wanted, self._received, self._lost), OPEN_LIMIT_SEC)
        except (OSError, ValueError, bleak.BleakError) as e:
            loop.stop()
            raise self._cannot_open(e) from e
        except BaseException:
            loop.stop()
            raise
        self._loop = loop
        self.is_open = True

    def _cannot_open(self, e: BaseException) -> "serial.SerialException":
        why = "the device does not answer (is it switched on, in range and not connected to a phone?)" if isinstance(e, TimeoutError) else str(e)
        return serial.SerialException(f"Could not open port {self.portstr}: {why}")

    def _received(self, data: bytes) -> None:
        with self._cond:
            self._buffer.extend(data)
            self._cond.notify_all()

    def _lost(self, reason: str) -> None:
        with self._cond:
            self._failure = self._failure or reason
            self._cond.notify_all()

    @property
    def in_waiting(self) -> int:
        if not self.is_open:
            raise serial.PortNotOpenError()
        with self._cond:
            return len(self._buffer)

    def read(self, size: int = 1) -> bytes:
        """Up to `size` bytes, waiting for them as long as the timeout allows (for ever without one); fewer (none) at the end of the time, or when `cancel_read` ends the wait. A link that is lost raises, once what had come before is read."""
        if not self.is_open:
            raise serial.PortNotOpenError()
        deadline = None if self.timeout is None else time.monotonic() + self.timeout
        with self._cond:
            while len(self._buffer) < size and self._failure is None and not self._cancelled and self.is_open:
                left = None if deadline is None else deadline - time.monotonic()
                if left is not None and left <= 0:
                    break
                self._cond.wait(left)
            self._cancelled = False
            data = bytes(self._buffer[:size])
            del self._buffer[:size]
            if not data and self._failure is not None:
                raise serial.SerialException(f"BLE link lost: {self._failure}")
            return data

    def write(self, data: bytes) -> int:
        if not self.is_open or self._loop is None or self._link is None:
            raise serial.PortNotOpenError()
        if self._failure is not None:
            raise serial.SerialException(f"BLE link lost: {self._failure}")
        self._writing = future = self._loop.submit(self._link.send(bytes(data)))
        try:
            future.result(self.write_timeout or WRITE_TIMEOUT_SEC)
        except TimeoutError:
            future.cancel()
            raise serial.SerialTimeoutException("Write timeout") from None
        except (concurrent.futures.CancelledError, asyncio.CancelledError):
            raise serial.SerialException("the write was cancelled") from None
        except Exception as e:                            # BleakError, or the link gone under the write
            self._lost(str(e) or type(e).__name__)
            raise serial.SerialException(f"BLE write failed: {e}") from e
        finally:
            self._writing = None
        return len(data)

    def cancel_read(self) -> None:
        with self._cond:
            self._cancelled = True
            self._cond.notify_all()

    def cancel_write(self) -> None:
        if (future := self._writing) is not None:
            future.cancel()

    def reset_input_buffer(self) -> None:
        with self._cond:
            self._buffer.clear()

    def reset_output_buffer(self) -> None:
        pass

    def flush(self) -> None:
        pass

    def close(self) -> None:
        if not self.is_open:
            return
        with self._cond:
            self.is_open = False
            self._cond.notify_all()
        loop, link, self._loop, self._link = self._loop, self._link, None, None
        if loop is None:
            return
        try:
            if link is not None:
                loop.call(link.disconnect(), CLOSE_SEC)
        except Exception as e:                            # a link that does not let go is dropped with the loop
            log.info("%s: closing: %s", self.portstr, e)
        loop.stop()

    def _reconfigure_port(self) -> None:
        pass

    def _update_dtr_state(self) -> None:
        pass

    def _update_rts_state(self) -> None:
        pass
