"""Windows sound card levels (see soundmixer.py) as master volumes through Core Audio and ctypes.

COM is called through function tables, so no package is needed. A card is the pair of Core Audio
endpoint ids the HF modem lists (mercurycards.PAIR); an unplugged device has no level.
"""

import logging
from typing import Any, Protocol

from .mercurycards import WASAPI_CAPTURE, WASAPI_PLAYBACK, endpoints
from .soundmixer import Levels

log = logging.getLogger("neoaprs.soundmixer")

# MMDeviceEnumerator, IMMDeviceEnumerator and IAudioEndpointVolume.
CLSID_ENUMERATOR = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
IID_ENUMERATOR = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"
IID_ENDPOINT_VOLUME = "{5CDF2C82-841E-4546-9722-0CF74078229A}"
CLSCTX_ALL = 23
# Function table indexes: IMMDeviceEnumerator::GetDevice, IMMDevice::Activate, IUnknown::Release.
GET_DEVICE, ACTIVATE, RELEASE = 5, 3, 2
# IAudioEndpointVolume::SetMasterVolumeLevelScalar and GetMasterVolumeLevelScalar.
SET_SCALAR, GET_SCALAR = 7, 9


class Volumes(Protocol):
    def get(self, device: str) -> float | None:
        """Return the device's master volume, 0.0 to 1.0, or None if unavailable."""
        ...

    def put(self, device: str, scalar: float) -> None:
        """Set the volume; do nothing if the device is unavailable."""
        ...


class Windows:
    """The master volumes of the card's two devices, through `volumes` (Core Audio by default)."""

    def __init__(self, volumes: Volumes | None = None) -> None:
        self._volumes = volumes or CoreAudio()

    def read(self, card: str) -> Levels:
        return self.write(card, None, None)

    def write(self, card: str, tx: int | None, rx: int | None) -> Levels:
        capture, playback = endpoints(card)
        playing = playback if playback.startswith(WASAPI_PLAYBACK) else ""
        recording = capture if capture.startswith(WASAPI_CAPTURE) else ""
        for device, value in ((playing, tx), (recording, rx)):
            if device and value is not None:
                self._volumes.put(device, max(0, min(100, value)) / 100)
        return Levels(self._percent(playing), self._percent(recording))

    def _percent(self, device: str) -> int | None:
        scalar = self._volumes.get(device) if device else None
        return None if scalar is None else max(0, min(100, round(scalar * 100)))


class CoreAudio:
    """The master volume of a device by endpoint id; calls use the thread's COM apartment."""

    def get(self, device: str) -> float | None:
        import ctypes

        level = ctypes.c_float()
        return (
            level.value
            if self._with_volume(
                device,
                lambda volume, call: (
                    call(volume, GET_SCALAR, ctypes.POINTER(ctypes.c_float))(volume, ctypes.byref(level)) == 0
                ),
            )
            else None
        )

    def put(self, device: str, scalar: float) -> None:
        import ctypes

        self._with_volume(
            device,
            lambda volume, call: call(volume, SET_SCALAR, ctypes.c_float, ctypes.c_void_p)(volume, scalar, None) == 0,
        )

    def _with_volume(self, device: str, use: Any) -> bool:
        """Run `use(volume, call)` on the device's IAudioEndpointVolume; False if none or failed."""
        import ctypes

        try:
            ole = ctypes.WinDLL("ole32")  # type: ignore[attr-defined, unused-ignore]
        except (OSError, AttributeError) as e:
            log.debug("no COM here: %s", e)
            return False
        # S_OK or S_FALSE; a thread already in another apartment goes on in it.
        started = ole.CoInitializeEx(None, 0) in (0, 1)
        try:
            found = self._volume_of(ctypes, ole, device, use)
            if not found:
                log.debug("the master volume of %s could not be had", device)
            return found
        finally:
            if started:
                ole.CoUninitialize()

    @staticmethod
    def _volume_of(ctypes: Any, ole: Any, device: str, use: Any) -> bool:
        def guid(text: str) -> Any:
            made = (ctypes.c_byte * 16)()
            ole.CLSIDFromString(ctypes.c_wchar_p(text), ctypes.byref(made))
            return made

        def call(obj: Any, index: int, *argtypes: Any) -> Any:
            table = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(table[index])

        enumerator, endpoint, volume = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        if (
            ole.CoCreateInstance(
                ctypes.byref(guid(CLSID_ENUMERATOR)),
                None,
                CLSCTX_ALL,
                ctypes.byref(guid(IID_ENUMERATOR)),
                ctypes.byref(enumerator),
            )
            != 0
        ):
            return False
        try:
            if (
                call(enumerator, GET_DEVICE, ctypes.c_wchar_p, ctypes.c_void_p)(
                    enumerator, device, ctypes.byref(endpoint)
                )
                != 0
            ):
                return False
            if (
                call(endpoint, ACTIVATE, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p)(
                    endpoint, ctypes.byref(guid(IID_ENDPOINT_VOLUME)), CLSCTX_ALL, None, ctypes.byref(volume)
                )
                != 0
            ):
                return False
            return bool(use(volume, call))
        finally:
            for obj in (volume, endpoint, enumerator):
                if obj.value:
                    call(obj, RELEASE)(obj)
