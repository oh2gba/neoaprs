"""Windows: a sound card's own levels (soundmixer.py) as the master volume of its playing device and of its recording device, through Core Audio by ctypes (no package of its own: the COM interfaces are
called by their tables of functions). A card of the radio's settings is the pair of the two devices' ids the HF modem's list gives it (mercurycards.PAIR, `{0.0.1.00000000}.{…}|{0.0.0.00000000}.{…}`),
and those ids are Core Audio's own endpoint ids: `IMMDeviceEnumerator::GetDevice` takes them as they are. Every device has a master volume, so a card has both levels where it has both devices; a device
that is not there (unplugged) has none.

`Windows` does the reading of the pair and the percent, `CoreAudio` the calls; a test gives `Windows` a stand-in for `CoreAudio`, as the tests of the WinMM lists stand in for WinMM: no Windows machine the
project can reach has a real sound card, so the calls themselves are proven only on an operator's."""
import logging
from typing import Any, Protocol

from .mercurycards import WASAPI_CAPTURE, WASAPI_PLAYBACK, endpoints
from .soundmixer import Levels

log = logging.getLogger("neoaprs.soundmixer")

CLSID_ENUMERATOR = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"           # MMDeviceEnumerator
IID_ENUMERATOR = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"             # IMMDeviceEnumerator
IID_ENDPOINT_VOLUME = "{5CDF2C82-841E-4546-9722-0CF74078229A}"        # IAudioEndpointVolume
CLSCTX_ALL = 23
GET_DEVICE, ACTIVATE, RELEASE = 5, 3, 2                               # the places in the tables: IMMDeviceEnumerator::GetDevice, IMMDevice::Activate, IUnknown::Release
SET_SCALAR, GET_SCALAR = 7, 9                                         # IAudioEndpointVolume::SetMasterVolumeLevelScalar, GetMasterVolumeLevelScalar


class Volumes(Protocol):
    def get(self, device: str) -> float | None:
        """The device's master volume, 0.0 to 1.0; None where it cannot be had."""
        ...

    def put(self, device: str, scalar: float) -> None:
        """Sets it (nothing where it cannot be)."""
        ...


class Windows:
    """The card's two devices' master volumes (`volumes`: Core Audio, or a test's stand-in)."""

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
    """The master volume of a device by its endpoint id, each call in a COM apartment of its own thread (the daemon calls from a worker thread)."""

    def get(self, device: str) -> float | None:
        import ctypes
        level = ctypes.c_float()
        return level.value if self._with_volume(device, lambda volume, call: call(volume, GET_SCALAR, ctypes.POINTER(ctypes.c_float))(volume, ctypes.byref(level)) == 0) else None

    def put(self, device: str, scalar: float) -> None:
        import ctypes
        self._with_volume(device, lambda volume, call: call(volume, SET_SCALAR, ctypes.c_float, ctypes.c_void_p)(volume, scalar, None) == 0)

    def _with_volume(self, device: str, use: Any) -> bool:
        """`use(volume, call)` on the device's IAudioEndpointVolume; False where there is none (no such device, no COM) or `use` said it failed."""
        import ctypes
        try:
            ole = ctypes.WinDLL("ole32")                                                     # type: ignore[attr-defined, unused-ignore]
        except (OSError, AttributeError) as e:
            log.debug("no COM here: %s", e)
            return False
        started = ole.CoInitializeEx(None, 0) in (0, 1)                                      # (S_OK, S_FALSE; a thread already in another apartment goes on in it)
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
        if ole.CoCreateInstance(ctypes.byref(guid(CLSID_ENUMERATOR)), None, CLSCTX_ALL, ctypes.byref(guid(IID_ENUMERATOR)), ctypes.byref(enumerator)) != 0:
            return False
        try:
            if call(enumerator, GET_DEVICE, ctypes.c_wchar_p, ctypes.c_void_p)(enumerator, device, ctypes.byref(endpoint)) != 0:
                return False
            if call(endpoint, ACTIVATE, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p)(endpoint, ctypes.byref(guid(IID_ENDPOINT_VOLUME)), CLSCTX_ALL, None, ctypes.byref(volume)) != 0:
                return False
            return bool(use(volume, call))
        finally:
            for obj in (volume, endpoint, enumerator):
                if obj.value:
                    call(obj, RELEASE)(obj)
