"""Five real NeoAPRS daemons with the real Direwolf and Mercury on three virtual sound cables (PipeWire null
sinks, tests/realmodems/cables), for .github/workflows/realmodems.yml: the refusal that keeps them off a computer with a
sound card, the settings of each station, and the page socket each test drives it by. docs/realmodems.md.
"""

import os
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from neoaprs.bundled import tools_dir
from tests.support.realmercury import Page, stop, wait_for_page

ENV = "NEOAPRS_REAL_MODEMS"
CARDS = Path("/proc/asound/cards")
ASOUNDRC = Path(__file__).with_name("asoundrc")  # the workflow copies it to ~/.asoundrc
PAIR_SSID = 12
START_SEC = 180.0  # a daemon up and its modems running
_CARD_LINE = re.compile(r"^\s*(\d+) \[(\S+)\s*\]: (\S+) - ")
_DEVICE = re.compile(r"^pcm\.(\w+) \{", re.M)
_SINK = re.compile(r'playback_node "(\w+)"')


@dataclass(frozen=True)
class Radio:
    type: str  # `db radios add` TYPE
    sound_card: str  # an ALSA device of ASOUNDRC


@dataclass(frozen=True)
class Station:
    call: str
    lat: float
    lon: float
    radios: tuple[Radio, ...]
    live: dict[str, str] = field(default_factory=dict)  # set on the page once it is up (`db set` has no pairs)


A = Station("OH2AA", 60.17, 24.94, (Radio("direwolf", "vhf_a"),))
G = Station(
    "OH2GW",
    60.20,
    24.90,
    (Radio("direwolf", "vhf_g"), Radio("mercury", "hf_g")),
    live={"pair/1/2/enabled": "true", "pair/1/2/ssid": str(PAIR_SSID)},
)
B = Station("OH2BB", 61.50, 23.80, (Radio("mercury", "hf_b"),))
# classic APRS at 300 baud on HF, on a cable of their own
H1 = Station("OH2HA", 60.45, 22.27, (Radio("direwolf-300", "p300_h1"),))
H2 = Station("OH2HB", 62.24, 25.75, (Radio("direwolf-300", "p300_h2"),))
STATIONS = (A, G, B, H1, H2)
PAIR_CALL = f"{G.call}-{PAIR_SSID}"


def cards(text: str) -> dict[str, str]:
    """The driver of each sound card by its id, from the text of /proc/asound/cards."""
    return {m.group(2): m.group(3) for line in text.splitlines() if (m := _CARD_LINE.match(line))}


def sinks(text: str) -> set[str]:
    """The names of the sound server's sinks, from `pactl list short sinks`."""
    return {f[1] for line in text.splitlines() if len(f := line.split()) >= 2}


@dataclass(frozen=True)
class Machine:
    """What the refusal reads of the computer; None for what could not be read."""

    cards: str | None
    sinks: str | None
    asoundrc: str | None
    platform: str = sys.platform


def refusal(environ: Mapping[str, str], machine: Machine, stations: tuple[Station, ...] = STATIONS) -> str:
    """Why the daemons must not start here, or "" when they may: only with the variable, on Linux with
    no sound card at all, ASOUNDRC as ~/.asoundrc, no sink but its null sinks and every station on
    its devices."""
    if environ.get(ENV) != "1":
        return f"{ENV}=1 is not set: these tests start real modems and run only in .github/workflows/realmodems.yml"
    if not machine.platform.startswith("linux"):
        return "this is not Linux"
    # no /proc/asound at all is a kernel without sound: no card either
    if real := sorted(cards(machine.cards or "")):
        return f"this computer has sound cards ({', '.join(real)}): a modem could go on the air"
    ours = ASOUNDRC.read_text(encoding="utf-8")
    if machine.asoundrc != ours:
        return "~/.asoundrc is not the asoundrc of tests/realmodems"
    found, wanted = sinks(machine.sinks or ""), set(_SINK.findall(ours))
    if found != wanted:
        return f"the sound server's sinks are not the null sinks {sorted(wanted)} alone: {sorted(found)}"
    if stray := sorted({r.sound_card for s in stations for r in s.radios} - set(_DEVICE.findall(ours))):
        return f"a station is given a device that is not a virtual one: {', '.join(stray)}"
    return ""


def _text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def read_machine() -> Machine:
    try:
        listed: str | None = subprocess.run(
            ["pactl", "list", "short", "sinks"], capture_output=True, text=True, timeout=30, check=True
        ).stdout
    except (OSError, subprocess.SubprocessError):
        listed = None
    return Machine(_text(CARDS), listed, _text(Path.home() / ".asoundrc"))


def programs() -> list[Path]:
    return [tools_dir() / "mercury" / "mercury", tools_dir() / "direwolf" / "direwolf"]


def daemon_env() -> dict[str, str]:
    """A daemon with its modems on the virtual cables and nothing else of the computer: no serial
    port, no version page, no player, no desktop."""
    dropped = {"NEOAPRS_DATA_DIR", "NEOAPRS_DEBUG", "NEOAPRS_NO_DEVICES", "NEOAPRS_ALSA_ROOT", "NEOAPRS_PSKREPORTER"}
    dropped |= {"DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "XAUTHORITY"}
    env = {k: v for k, v in os.environ.items() if k not in dropped}
    env["NEOAPRS_SERIAL_PATTERN"] = "/dev/neoaprs-realmodems-no-such-port*"
    env["NEOAPRS_UPDATE_CHECK"] = "0"
    env["NEOAPRS_PLAYER_PATH"] = "/nonexistent/neoaprs-realmodems-players"
    return env


def db(data: Path, *args: str) -> None:
    # the settings are written under the no-devices switch: `db` opens nothing either way
    env = {**daemon_env(), "NEOAPRS_NO_DEVICES": "1"}
    done = subprocess.run(
        [sys.executable, "-m", "neoaprs", "db", "--data", str(data), *args], capture_output=True, text=True, env=env
    )
    if done.returncode != 0:
        raise RuntimeError(f"neoaprs db {' '.join(args)}: {done.stdout}{done.stderr}")


def write_settings(data: Path, station: Station) -> None:
    """The radios in order (ids 1, 2 ...), each keyed by VOX on its virtual device, then the station."""
    for radio in station.radios:
        db(data, "radios", "add", radio.type)
    rows = {
        "station/call": station.call,
        "station/lat": str(station.lat),
        "station/lon": str(station.lon),
        "beacon/interval_min": "0",
        "messages/alert": "false",
    }
    for number, radio in enumerate(station.radios, 1):
        rows[f"radio/{number}/sound_card"] = radio.sound_card
        rows[f"radio/{number}/keying"] = "vox"
    for key, value in rows.items():
        db(data, "set", key, value)


class StationPage(Page):
    """The page socket of one station, with the answers to `set_config` that carry an id."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.saved: set[int] = set()
        self._next_id = 0

    def _apply(self, message: dict[str, Any]) -> None:
        if message.get("type") == "saved":
            self.saved.add(int(message["id"]))
        super()._apply(message)

    async def set_config(self, values: dict[str, str], seconds: float = 30.0) -> None:
        self._next_id += 1
        number = self._next_id
        await self.send({"cmd": "set_config", "values": values, "id": number})
        await self.until(f"the settings {values} saved", lambda: number in self.saved, seconds)

    async def set_path(self, call: str, path: str, seconds: float = 30.0) -> None:
        """The station's own path on radio 1."""
        await self.send({"cmd": "set_station_path", "call": call, "path": path, "radio": 1})
        await self.until(
            f"the path {path} for {call}",
            lambda: (self.topics.get("station_prefs") or {}).get(call, {}).get("path") == path,
            seconds,
        )

    def radios_up(self) -> bool:
        rows = [r for r in (self.topics.get("radios") or {}).values() if r.get("enabled") and not r.get("removed")]
        return bool(rows) and all(
            r.get("state") == "connected" and (r.get("modem") or {}).get("state") == "running" for r in rows
        )

    def radio_id(self, kind: str) -> int:
        return int(self.radio(kind)["id"])

    def packets(self, after: int = -1, **match: object) -> list[dict[str, Any]]:
        """The packets of the topic after the id `after` whose fields have these values."""
        rows = (self.topics.get("packets") or {}).values()
        return sorted(
            (p for p in rows if p["id"] > after and all(p.get(k) == v for k, v in match.items())),
            key=lambda p: int(p["id"]),
        )

    def last_packet(self) -> int:
        return max((int(p["id"]) for p in (self.topics.get("packets") or {}).values()), default=-1)

    def message(self, direction: str, text: str) -> dict[str, Any] | None:
        return next(
            (m for m in self.messages().values() if m.get("direction") == direction and m.get("text") == text), None
        )

    def state_of(self, text: str) -> str:
        found = self.message("out", text)
        return "" if found is None else str(found.get("state"))


class World:
    """The stations: each daemon on its own data folder under `folder`, its output beside it."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.daemons: dict[str, subprocess.Popen[bytes]] = {}
        self.pages: dict[str, StationPage] = {}

    def start(self) -> dict[str, str]:
        bases: dict[str, str] = {}
        for station in STATIONS:
            data = self.folder / station.call.lower()
            write_settings(data, station)
            out = (self.folder / f"{station.call.lower()}.out").open("wb")
            self.daemons[station.call] = subprocess.Popen(
                [sys.executable, "-m", "neoaprs", "--data", str(data), "--web-port", "0"],
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=subprocess.STDOUT,
                env=daemon_env(),
            )
        for station in STATIONS:
            bases[station.call] = wait_for_page(
                self.daemons[station.call], self.folder / station.call.lower(), START_SEC
            )
        return bases

    async def open(self, bases: dict[str, str]) -> None:
        for call, base in bases.items():
            page = self.pages[call] = StationPage(call)
            await page.open(base)
        for station in STATIONS:
            page = self.pages[station.call]
            if station.live:
                await page.set_config(station.live)
            await page.until("every radio connected to its running modem", page.radios_up, START_SEC)

    def close_pages(self) -> None:
        """On the event loop the pages were opened on."""
        for page in self.pages.values():
            page.close()

    def stop(self) -> None:
        for daemon in self.daemons.values():
            stop(daemon, 60.0)

    def __getitem__(self, call: str) -> StationPage:
        return self.pages[call]
