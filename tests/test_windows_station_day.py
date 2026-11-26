"""A day of a Windows station that sent its support file (Windows 10, 0.23.3), in seconds, against
a whole daemon and a page on its socket: its six serial ports, a radio on the incoming Bluetooth
port, a port whose writes time out, an AIS source that is a web server, and a Mercury (a real child
process) whose capture buffer stays full; then the support file of it all."""

import asyncio
import io
import json
import logging
import re
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

import pytest
import serial  # type: ignore[import-untyped]

from neoaprs import mercurymodem, mercurystall, serialport, serialprobe
from neoaprs.cli import doctor
from neoaprs.mercury import CAPTURE_FULL
from neoaprs.serialprobe import PortInfo
from neoaprs.services import layerships
from neoaprs.web import supportstate
from neoaprs.source import Backoff
from tests.support import aissentences as ais
from tests.support.env import Env, until
from tests.support.loopbackserver import LoopbackServer
from tests.support.modemports import own_ports
from tests.support.wsclient import WsClient

# the tree: tests/ (or the folder this was written in) lies inside it
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "neoaprs" / "__init__.py").is_file())
LONG = 60.0  # a slow Windows runner is five times slower than this machine
PAGE = {"build": "index-sim.js", "browser": "a test"}

# ---- his station as his support file has it


def his_ports() -> list[PortInfo]:
    """The six ports of his state.json, as pyserial listed them on his Windows."""
    return [
        PortInfo("COM1", "Puerto de comunicaciones (COM1)", "ACPI\\PNP0501\\0", None, None),
        PortInfo("COM3", "USB Serial Port (COM3)", "USB VID:PID=0403:6015 SER=DN05XXXXA", 0x0403, 0x6015),
        PortInfo(
            "COM7",
            "Serie estándar sobre el vínculo Bluetooth (COM7)",
            "BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&000B\\8&C3F3ED0&0&000CBF18376C_C00000000",
            None,
            None,
        ),
        PortInfo(
            "COM8",
            "Serie estándar sobre el vínculo Bluetooth (COM8)",
            "BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0000\\8&C3F3ED0&0&000000000000_00000000",
            None,
            None,
        ),
        PortInfo(
            "COM10",
            "Silicon Labs Dual CP2105 USB to UART Bridge: Enhanced COM Port (COM10)",
            "USB VID:PID=10C4:EA70 SER=AH057M5M220252 LOCATION=1-1:x.0",
            0x10C4,
            0xEA70,
        ),
        PortInfo(
            "COM11",
            "Silicon Labs Dual CP2105 USB to UART Bridge: Standard COM Port (COM11)",
            "USB VID:PID=10C4:EA70 SER=AH057M5M220252 LOCATION=1-1:x.1",
            0x10C4,
            0xEA70,
        ),
    ]


# What `mercury -z` printed on his Windows (one line per recording and per playing device), made
# back from the 71 cards of his summary.txt, which NeoAPRS pairs into those 71 again.
MERCURY_LIST = """\
playback devices:
device: name: 'Voicemeeter In 3 (VB-Audio Voicemeeter VAIO)'  id: '{0.0.0.00000000}.{0645e225-154b-46a3-9690-2b1cdcb995bc}'
device: name: 'Voicemeeter In 2 (VB-Audio Voicemeeter VAIO)'  id: '{0.0.0.00000000}.{26de5ae7-1fa1-4385-8e4a-272a42c8f358}'
device: name: 'Voicemeeter In 1 (VB-Audio Voicemeeter VAIO)'  id: '{0.0.0.00000000}.{43f76c7b-3b73-4b1e-9be7-ab596ea710a1}'
device: name: 'Voicemeeter VAIO3 Input (VB-Audio Voicemeeter VAIO)'  id: '{0.0.0.00000000}.{5896d3f0-9155-42b7-a948-8cea708efe01}'
device: name: 'Voicemeeter Input (VB-Audio Voicemeeter VAIO)'  id: '{0.0.0.00000000}.{803be2d4-e36b-418a-91cd-5cfcf8db18a4}'
device: name: 'Voicemeeter In 4 (VB-Audio Voicemeeter VAIO)'  id: '{0.0.0.00000000}.{9e826648-0d7e-4c59-8338-678378dc3d86}'
device: name: 'Voicemeeter In 5 (VB-Audio Voicemeeter VAIO)'  id: '{0.0.0.00000000}.{ad12d985-d9c5-447e-be4d-18635bf61aab}'
device: name: 'Voicemeeter AUX Input (VB-Audio Voicemeeter VAIO)'  id: '{0.0.0.00000000}.{bd0829ee-0c8e-4478-a2a4-fc1bd8ceee4e}'
device: name: '5 - 2260WG5 (AMD High Definition Audio Device)'  id: '{0.0.0.00000000}.{4e607808-2755-4efe-9924-8655cf31ce0e}'
device: name: 'Altavoces (High Definition Audio Device)'  id: '{0.0.0.00000000}.{60dc5c8a-29f0-49a0-b5f4-40486b24dd26}'  (system default)
device: name: 'Altavoces (S/PDIF) (High Definition Audio Device)'  id: '{0.0.0.00000000}.{6709fd47-bf06-4e31-80b6-c90a187ca06f}'
device: name: 'Altavoces (USB Audio CODEC )'  id: '{0.0.0.00000000}.{708d9480-1de9-4996-b6e5-75263c6c41cd}'
device: name: 'Altavoces (VB-Audio Virtual Cable)'  id: '{0.0.0.00000000}.{be3ae171-2c2b-46dd-a4fd-8e99c49dd296}'
device: name: 'Altavoces (USB Audio Device)'  id: '{0.0.0.00000000}.{df0c1155-1216-48a4-a6dc-06b77825c8f5}'
capture devices:
device: name: 'Voicemeeter Out B1 (VB-Audio Voicemeeter VAIO)'  id: '{0.0.1.00000000}.{0953c03e-e748-4862-ad94-e5dd3bd441ad}'
device: name: 'Voicemeeter Out A2 (VB-Audio Voicemeeter VAIO)'  id: '{0.0.1.00000000}.{4690fe51-0a3c-4271-8930-edfe86b0e12b}'
device: name: 'Voicemeeter Out A1 (VB-Audio Voicemeeter VAIO)'  id: '{0.0.1.00000000}.{4ef06556-4926-4342-845e-2d87a77b60c2}'
device: name: 'Voicemeeter Out B2 (VB-Audio Voicemeeter VAIO)'  id: '{0.0.1.00000000}.{80fb6e8e-4f6c-4f59-806c-7dee30308802}'
device: name: 'Voicemeeter Out A5 (VB-Audio Voicemeeter VAIO)'  id: '{0.0.1.00000000}.{ba13f389-cd13-4231-8456-d06ee4b1f021}'
device: name: 'Voicemeeter Out A4 (VB-Audio Voicemeeter VAIO)'  id: '{0.0.1.00000000}.{c9a57b16-7f85-4682-ae25-ba151507197f}'
device: name: 'Voicemeeter Out B3 (VB-Audio Voicemeeter VAIO)'  id: '{0.0.1.00000000}.{d063d4cb-032f-40a7-8256-6077755a4cc3}'
device: name: 'Voicemeeter Out A3 (VB-Audio Voicemeeter VAIO)'  id: '{0.0.1.00000000}.{d7bae169-15c2-43b6-a5dc-682b3d4c2cd5}'
device: name: 'Micrófono (High Definition Audio Device)'  id: '{0.0.1.00000000}.{d6ea461f-b327-4e94-aec0-e0cff6831795}'  (system default)
device: name: 'Micrófono (S/PDIF) (High Definition Audio Device)'  id: '{0.0.1.00000000}.{3f37084f-e379-482a-bbc0-4e18b69f00ee}'
device: name: 'Micrófono (USB Audio CODEC )'  id: '{0.0.1.00000000}.{37ef7499-fdd2-43a7-8f15-2b2634b72b1a}'
device: name: 'Micrófono (VB-Audio Virtual Cable)'  id: '{0.0.1.00000000}.{54493ecd-e216-4887-8c54-a4df7666a2c0}'
device: name: 'Micrófono (USB Audio Device)'  id: '{0.0.1.00000000}.{1991b373-7a89-4d20-bc68-c9b0e715a475}'
device: name: 'Micrófono (Logi C525 HD WebCam)'  id: '{0.0.1.00000000}.{b97fd3c9-2678-47f8-b3ae-79455b73e54e}'
"""


FAKE = """
import sys, threading, time
sys.path.insert(0, {root!r})
from tests.support import fakemercury
if "-z" in sys.argv:
    sys.stdout.buffer.write(open({cards!r}, "rb").read())
    sys.stdout.buffer.flush()
    sys.exit(0)
for line in (
    "[INF] [audio-play] I/O playback ({{0.0.0.00000000}}.{{708d9480-1de9-4996-b6e5-75263c6c41cd}} 'Altavoces (USB Audio CODEC )') int32 / 48000Hz / 2ch / 40ms buffer",
    "[INF] [audio-cap] I/O capture ({{0.0.1.00000000}}.{{37ef7499-fdd2-43a7-8f15-2b2634b72b1a}} 'Micrófono (USB Audio CODEC )') float32 / 48000Hz / 1ch / 40ms buffer",
    "[INF] [radio-io] Initializing PTT (method=serial, device=COM10)",
    "[INF] [radio-io] PTT method: serial RTS (device COM10)",
):
    fakemercury.say(line)
def flood():
    while True:  # (in fives: Windows sleeps 15.6 ms at the least)
        for _ in range(5):
            fakemercury.say({warning!r})
        time.sleep(0.02)
threading.Thread(target=flood, daemon=True).start()
sys.exit(fakemercury.main())
"""


def deaf_mercury(folder: Path) -> list[str]:
    """A Mercury that stands in for his: the made-up program (tests/support/fakemercury.py) with his
    sound cards and his line of a full capture buffer, about 200 a second."""
    cards = folder / "cards.txt"
    cards.write_bytes(MERCURY_LIST.encode("utf-8"))
    script = folder / "deaf_mercury.py"
    script.write_text(FAKE.format(root=str(ROOT), cards=str(cards), warning=CAPTURE_FULL), encoding="utf-8")
    return [sys.executable, str(script)]


class TimingOut:
    """His COM8 as pyserial sees it: it opens, nothing comes, and each write gives up after its write
    timeout until `takes`."""

    def __init__(self) -> None:
        self.takes = False
        self.in_waiting = 0
        self.writes = 0

    def open(self) -> None:
        pass

    def read(self, size: int = 1) -> bytes:
        time.sleep(0.01)
        return b""

    def write(self, data: bytes) -> int:
        self.writes += 1
        if not self.takes:
            raise serial.SerialTimeoutException("Write timeout")
        return len(data)

    def close(self) -> None:
        pass


class WebServer(LoopbackServer):
    """OpenWebRX's port 8073 as an AIS source: one HTTP answer to what is no request, then the end."""

    def __init__(self) -> None:
        self.connections = 0

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1
        writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
        await writer.drain()
        writer.close()


class AisSource(LoopbackServer):
    """A receiver that keeps the line open and sends `lines` (none: a receiver with no ship in range)."""

    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.go = asyncio.Event()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await self.go.wait()
        writer.write("".join(line + "\r\n" for line in self.lines).encode())
        await writer.drain()
        try:
            await reader.read()
        except ConnectionError:
            pass
        writer.close()


def row(page: WsClient, id: int) -> dict[str, Any]:
    return page.topics.get("radios", {}).get(str(id)) or {}


def ships(page: WsClient) -> str | None:
    for layer in (page.topics.get("map") or {}).get("layers") or []:
        if layer.get("layer") == "ships":
            return (layer.get("receiver") or {}).get("state")
    return None


def said(caplog: pytest.LogCaptureFixture, text: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if text in r.getMessage()]


async def added(page: WsClient, type: str, name: str) -> int:
    before = len(page.of("radio_added"))
    await page.send({"cmd": "radio_add", "type": type, **({"name": name} if name else {})})
    await page.until(lambda: len(page.of("radio_added")) > before or len(page.of("error")) > 0, LONG)
    assert not page.of("error"), page.of("error")
    id = int(page.of("radio_added")[-1]["id"])
    await page.until(lambda: str(id) in page.topics["radios"], LONG)
    return id


async def set_values(page: WsClient, values: dict[str, str]) -> None:
    await page.send({"cmd": "set_config", "values": values})


@pytest.fixture(autouse=True)
def _ports_of_this_test(monkeypatch: pytest.MonkeyPatch) -> None:
    own_ports(monkeypatch)


async def test_a_day_of_a_windows_station_with_four_faults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    # ---- his computer: the ports Windows lists, his COM8, his Mercury
    for module in (serialprobe, doctor, supportstate):
        monkeypatch.setattr(module, "available_ports", his_ports)
    monkeypatch.setattr(serialprobe, "_on_windows", lambda: True)  # (only Windows makes the incoming port)
    stuck = TimingOut()
    opened: list[str] = []
    build = serialport._build

    def his_port(path: str, baud: int) -> Any:
        """His COM ports only: the line to the Mercury program is a real socket."""
        if not path.startswith("COM"):
            return build(path, baud)
        opened.append(path)
        return stuck

    monkeypatch.setattr(serialport, "_build", his_port)
    monkeypatch.setattr(mercurymodem, "find", lambda: deaf_mercury(tmp_path))
    # the watcher's times, shortened: a stall is 2 s of the warning, restarts come at once
    monkeypatch.setattr(mercurystall, "STALL_SEC", 2.0)
    monkeypatch.setattr(mercurymodem, "STALL_SEC", 2.0)
    monkeypatch.setattr(mercurystall, "GAP_SEC", 1.5)
    monkeypatch.setattr(mercurystall, "RESTART_EVERY_SEC", 0.0)
    monkeypatch.setattr(layerships, "AIS_RETRY_SEC", (0.05, 0.2))

    e = Env(tmp_path / "data", radio=False, web=True, settings={"fm/enabled": "false"})
    await e.start(connected=False)
    page = await e.ws()
    try:
        # ---- 1. the ports: COM7 offered, COM8 not; a radio on COM8 waits with its own problem
        lora = await added(page, "kiss", "X1C5Plus")
        await page.send({"cmd": "list_ports", "radio": lora})
        offered = [p["device"] for p in (await page.expect("ports", timeout=LONG))["ports"]]
        assert "COM7" in offered and "COM8" not in offered
        await set_values(page, {f"radio/{lora}/port": "COM8", f"radio/{lora}/baud": "9600"})
        await page.until(lambda: (row(page, lora).get("problem") or {}).get("code") == "radio.incoming_port", LONG)
        assert row(page, lora)["problem"]["params"] == {"port": "COM8"} and opened == [], "COM8 is never opened"

        # ---- 2. a port that opens and takes no data: COM7 standing in for his COM8
        await set_values(page, {f"radio/{lora}/port": "COM7"})
        await page.until(lambda: row(page, lora).get("state") == "connected", LONG)
        await page.send({"cmd": "beacon_now"})
        timeout = {"code": "radio.write_timeout", "params": {"seconds": serialport.WRITE_TIMEOUT_SEC}}
        await page.until(lambda: row(page, lora).get("problem") == timeout, LONG)
        line = e.ctl.radios.get(lora).line  # type: ignore[union-attr]
        await page.until(lambda: line.stats.opens >= 2 and row(page, lora).get("problem") == timeout, LONG)
        assert row(page, lora).get("state") == "waiting", "the bare reopen is not connected"
        assert said(caplog, "serial port COM7 write timed out: the device did not take the data within 2 s") == [
            "serial port COM7 write timed out: the device did not take the data within 2 s"
        ]
        assert not said(caplog, "the line is gone") and not said(caplog, "SerialTimeoutException")
        stuck.takes = True
        await page.send({"cmd": "beacon_now"})
        await page.until(
            lambda: row(page, lora).get("state") == "connected" and row(page, lora).get("problem") is None, LONG
        )

        # ---- 3. the ships: a web server, a silent receiver, then one with a ship
        web = await WebServer().start()
        await set_values(page, {"map/ships": "receiver", "map/ships_host": f"127.0.0.1:{web.port}"})
        await page.until(lambda: ships(page) == "no_ais" and web.connections >= 4, LONG)
        assert len(said(caplog, "no AIS comes from it")) == 1 and not said(caplog, "127.0.0.1: receiving")
        assert said(caplog, "no AIS comes from it")[0].endswith("it sent 'HTTP/1.1 400 Bad Request'")
        await web.stop()
        receiver = await AisSource(ais.sentences(ais.class_a(224123450, 28.4, -16.3))).start()
        await set_values(page, {"map/ships_host": f"127.0.0.1:{receiver.port}"})
        await page.until(lambda: ships(page) == "connected", LONG)
        receiver.go.set()
        await page.until(lambda: ships(page) == "receiving", LONG)

        # ---- 4. Mercury: a capture buffer that stays full
        hf = await added(page, "mercury", "")  # (his has no name of its own: "Mercury")
        modem = e.ctl.radios.get(hf).driver.modem  # type: ignore[union-attr]
        assert isinstance(modem, mercurymodem.Mercury)
        modem.backoff = Backoff([0.2])  # (the program is started again at once, not after 5 s and more)
        await until(lambda: modem.pid is not None, LONG)
        first = modem.pid
        await until(lambda: modem.stall.restarts >= 1, LONG)
        # keyed from the restart on (a stand-in: the flag the modem's PTT events set): what comes
        # meanwhile counts for nothing, for long enough that the run reaches its 1000th line
        modem.keyed = True
        stalls = modem.stall.stalls
        await until(lambda: modem.pid not in (None, first) and modem.state == "running", LONG)
        await until(lambda: len(said(caplog, "(the 1000th time)")) == 1, LONG)
        assert modem.stall.stalls == stalls and modem.stall.restarts == 1, "no stall while the radio transmits"
        modem.keyed = False
        await page.until(lambda: (row(page, hf).get("modem") or {}).get("reason") == "receive_stalled", LONG)
        assert modem.stall.restarts == 3 and not modem.running
        await page.until(lambda: (row(page, hf).get("problem") or {}).get("code") == "modem.receive_stalled", LONG)
        # each run of the program says the warning the 1st, 10th, 100th (1000th) time and how many
        # times when it ends: a handful of lines for thousands
        flood = [r.getMessage() for r in caplog.records if CAPTURE_FULL in r.getMessage()]
        assert sum(m.endswith("Buffer full in capture buffer!") for m in flood) == 4, "the 1st time of each run"
        assert len(said(caplog, "(the 10th time)")) == 4 and len(said(caplog, "(the 1000th time)")) == 1
        assert len(flood) <= 4 * 5, f"thinned: {len(flood)} lines"
        assert len(said(caplog, "Mercury hears nothing: its capture buffer has been full")) == 4

        # ---- 5. the support file of the station, as Download logs and Send logs make it
        answer = await e.fetch("/support/bundle", method="POST", body=json.dumps({"page": PAGE}))
        assert answer.code == 200
        with zipfile.ZipFile(io.BytesIO(answer.body)) as z:
            summary = z.read("summary.txt").decode("utf-8")
            checks = z.read("doctor.txt").decode("utf-8")
        assert re.search(r"Hears nothing:\s+4 times, the last \S+", summary)
        assert re.search(r"Restarted for it:\s+3 times, the last \S+", summary)
        assert "'VB-Audio Voicemeeter VAIO': 64 of its combinations (state.json lists them)" in summary
        assert "Micrófono (Logi C525 HD WebCam)" in summary and "MicrÃ³fono" not in summary
        assert "PTT method: serial RTS (device COM10)" in summary
        assert re.search(r"Ships:\s+receiver, receiving since \S+", summary)
        assert "(Bluetooth: the port that reaches the device 000CBF18376C)" in checks
        assert "(the computer's incoming Bluetooth port: it reaches no device, and NeoAPRS does not offer it)" in checks
    finally:
        await e.stop()
