"""A Bluetooth LE device and the bleak library in front of it, for the tests of the BLE port (neoaprs/btle.py): no scan is made and no radio is touched (the guard of tests/support/guards.py puts a stand-in that refuses in place of bleak).
`FakeBle` is both the library (`BleakScanner`, `BleakClient`, `BleakError`, what `btle.import_bleak` returns) and the device behind it.

    ble = FakeBle(monkeypatch)                        # a device with the Mobilinkd/aprs.fi KISS service; FakeBle(monkeypatch, NUS) has the Nordic UART Service
    ...                                               # the code under test opens ble://00:11:22:33:44:55
    ble.feed(b"...")                                  # the device notifies
    ble.writes                                        # [(bytes, with_response), ...] what the code wrote, one entry per write of the link
    ble.drop()                                        # the device goes away: bleak calls the disconnected callback
    ble.connect_error = FakeBleakError("...")        # the next connections fail (None: they work again)
    ble.seen = False                                  # the scan does not find the device"""
import asyncio
from collections.abc import Callable
from typing import Any

import pytest

from neoaprs import btle

ADDRESS = "00:11:22:33:44:55"
MOBILINKD, MOBILINKD_WRITE, MOBILINKD_NOTIFY = "00000001-ba2a-46c9-ae49-01b0961f68bb", "00000002-ba2a-46c9-ae49-01b0961f68bb", "00000003-ba2a-46c9-ae49-01b0961f68bb"
NUS, NUS_WRITE, NUS_NOTIFY = "6e400001-b5a3-f393-e0a9-e50e24dcca9e", "6e400002-b5a3-f393-e0a9-e50e24dcca9e", "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
Services = dict[str, list[tuple[str, list[str]]]]
KISS_SERVICE: Services = {MOBILINKD: [(MOBILINKD_WRITE, ["write-without-response"]), (MOBILINKD_NOTIFY, ["read", "notify"])]}
UART_SERVICE: Services = {NUS: [(NUS_WRITE, ["write", "write-without-response"]), (NUS_NOTIFY, ["notify"])]}


class FakeBleakError(Exception):
    """bleak.BleakError"""


class FakeCharacteristic:
    def __init__(self, uuid: str, properties: list[str], max_write_without_response_size: int) -> None:
        self.uuid, self.properties, self.max_write_without_response_size = uuid, properties, max_write_without_response_size


class FakeService:
    def __init__(self, uuid: str, characteristics: list[FakeCharacteristic]) -> None:
        self.uuid, self.characteristics = uuid, characteristics

    def get_characteristic(self, uuid: str) -> FakeCharacteristic | None:
        return next((c for c in self.characteristics if c.uuid == uuid.lower()), None)


class FakeBle:
    BleakError = FakeBleakError

    def __init__(self, monkeypatch: pytest.MonkeyPatch, services: Services | None = None, *, address: str = ADDRESS, mtu: int = 23, chunk: int = 20) -> None:
        self.address, self.mtu = address, mtu
        self.services = [FakeService(s, [FakeCharacteristic(c, props, chunk) for c, props in chars]) for s, chars in (KISS_SERVICE if services is None else services).items()]
        self.seen = True                                             # the scan finds the device
        self.connect_error: Exception | None = None
        self.write_error: Exception | None = None                    # the next write fails with it
        self.hold_writes = False                                     # a write does not come back (the link is stuck)
        self.scans: list[str] = []
        self.connects, self.disconnects = 0, 0
        self.writes: list[tuple[bytes, bool]] = []
        self.notifying: str | None = None                            # the UUID of the characteristic that is listened to
        self.client: "FakeClient | None" = None
        self._notify: Callable[[Any, bytearray], None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        ble = self

        class BleakScanner:
            @staticmethod
            async def find_device_by_address(address: str, timeout: float = 10.0) -> str | None:
                ble.scans.append(address)
                return address if ble.seen and address.lower() == ble.address.lower() else None

        class BleakClient(FakeClient):
            def __init__(self, device: str, disconnected_callback: Callable[[Any], None] | None = None, timeout: float = 30.0) -> None:
                super().__init__(ble, device, disconnected_callback)

        self.BleakScanner, self.BleakClient = BleakScanner, BleakClient
        monkeypatch.setattr(btle, "import_bleak", lambda: self)

    def feed(self, data: bytes) -> None:
        """The device notifies `data`, on the loop of the BLE thread as bleak does."""
        assert self._loop is not None and self._notify is not None, "nothing is listening to the device"
        self._loop.call_soon_threadsafe(self._notify, None, bytearray(data))

    def drop(self) -> None:
        """The device goes out of range."""
        client = self.client
        assert client is not None and self._loop is not None
        self._loop.call_soon_threadsafe(client.lost)


class FakeClient:
    def __init__(self, ble: FakeBle, device: str, disconnected_callback: Callable[[Any], None] | None) -> None:
        self._ble, self._device, self._callback = ble, device, disconnected_callback
        self.is_connected = False

    @property
    def mtu_size(self) -> int:
        return self._ble.mtu

    @property
    def services(self) -> list[FakeService]:
        return self._ble.services

    async def connect(self) -> None:
        if self._ble.connect_error is not None:
            raise self._ble.connect_error
        self.is_connected = True
        self._ble.connects += 1
        self._ble.client = self

    async def disconnect(self) -> None:
        if self.is_connected:
            self.is_connected = False
            self._ble.disconnects += 1

    async def start_notify(self, char: FakeCharacteristic, callback: Callable[[Any, bytearray], None]) -> None:
        self._ble._notify, self._ble._loop, self._ble.notifying = callback, asyncio.get_running_loop(), char.uuid

    async def write_gatt_char(self, char: FakeCharacteristic, data: bytes, response: bool) -> None:
        if self._ble.write_error is not None:
            raise self._ble.write_error
        if not self.is_connected:
            raise FakeBleakError("Not connected")
        while self._ble.hold_writes:
            await asyncio.sleep(0.01)
        self._ble.writes.append((bytes(data), response))

    def lost(self) -> None:
        self.is_connected = False
        if self._callback is not None:
            self._callback(self)
