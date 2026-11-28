"""The sinks and sources of the sound server (PipeWire or PulseAudio) on Linux, as `pactl` lists them.

A setting names one as `pulse:DEVICE=<node>` (a source may add `,CHANNEL=<position>`); a modem opens it
by an ALSA name of `soundserver.conf`, and its streams are found again by the modem's process id.
"""

import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .childenv import child_environment
from .mercurycards import PAIR, SERVER, SoundCard, endpoints

log = logging.getLogger("neoaprs.soundserver")

CHANNEL = ",CHANNEL="
LIST_TIMEOUT_SEC = 2.0
CONF = Path(__file__).with_name("soundserver.conf")
# What an ALSA argument and a line of Direwolf's configuration carry without quotes.
_NAME = re.compile(r"^[A-Za-z0-9_.:@+-]+$")
# The order of the channels the ALSA plug-ins of both servers give a reader of 4, 5, 6 or 8 channels.
ALSA_ORDER = ("front-left", "front-right", "rear-left", "rear-right", "front-center", "lfe", "side-left", "side-right")
_PICKABLE = (4, 5, 6, 8)

Kind = Literal["sink", "source"]
Run = Callable[[Sequence[str]], str | None]


@dataclass(frozen=True)
class Plugin:
    file: str  # the ALSA plug-in of the server
    prefix: str  # the names of soundserver.conf that go through it


PLUGINS = {
    "pulse": Plugin("libasound_module_pcm_pulse.so", "neoaprs_pa"),
    "pipewire": Plugin("libasound_module_pcm_pipewire.so", "neoaprs_pw"),
}


@dataclass(frozen=True)
class Node:
    kind: Kind
    index: int
    name: str
    description: str
    positions: tuple[str, ...]
    card: int | None = None  # the ALSA card number behind it; None for a device a user made
    device: int = 0


def is_server(ident: str) -> bool:
    return ident.startswith(SERVER)


def server_id(name: str, channel: str = "") -> str:
    return f"{SERVER}{name}{CHANNEL}{channel}" if channel else f"{SERVER}{name}"


def parse_id(ident: str) -> tuple[str, str] | None:
    """Return the node name and channel position ("" for all) of a server id, else None."""
    if not is_server(ident):
        return None
    name, _, channel = ident[len(SERVER) :].partition(CHANNEL)
    return (name, channel) if _NAME.match(name) and (not channel or channel in ALSA_ORDER) else None


def uses_server(setting: str) -> bool:
    return any(is_server(half) for half in endpoints(setting))


def halves(setting: str) -> list[tuple[Kind, str]]:
    """Return the setting's (source, record device) and (sink, play device)."""
    capture, playback = endpoints(setting)
    return [("source", capture), ("sink", playback)]


def _number(value: object) -> int | None:
    return int(value) if isinstance(value, str) and value.isdigit() else None


def _props(entry: Mapping[str, Any]) -> Mapping[str, Any]:
    props = entry.get("properties")
    return props if isinstance(props, dict) else {}


def _node(kind: Kind, entry: Mapping[str, Any]) -> Node | None:
    props = _props(entry)
    name, index = entry.get("name"), entry.get("index")
    if not isinstance(name, str) or not _NAME.match(name) or not isinstance(index, int):
        return None
    if kind == "source" and (entry.get("monitor_source") or props.get("device.class") == "monitor"):
        return None
    description = next(
        (d for d in (entry.get("description"), props.get("node.nick")) if isinstance(d, str) and d and d != "(null)"),
        name,
    )
    positions = tuple(p for p in str(entry.get("channel_map") or "").split(",") if p)
    return Node(
        kind,
        index,
        name,
        description,
        positions,
        _number(props.get("alsa.card")),
        _number(props.get("alsa.device")) or 0,
    )


def parse_nodes(kind: Kind, text: str) -> list[Node]:
    """Return the sinks or sources of `pactl -f json list sinks|sources`; the monitors of sinks are left out."""
    try:
        entries = json.loads(text)
    except ValueError:
        return []
    if not isinstance(entries, list):
        return []
    return [n for n in (_node(kind, e) for e in entries if isinstance(e, dict)) if n is not None]


def pactl(args: Sequence[str]) -> str | None:
    """Return what `pactl -f json ARGS` writes; None without pactl, a server or an answer in time."""
    program = shutil.which("pactl") if sys.platform.startswith("linux") else None
    if program is None:
        return None
    try:
        done = subprocess.run(
            [program, "-f", "json", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=LIST_TIMEOUT_SEC,
            env=child_environment(),
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as e:
        log.info("pactl %s could not be run: %s", " ".join(args), e)
        return None
    if done.returncode != 0:
        log.debug("pactl %s: exit %d: %s", " ".join(args), done.returncode, done.stderr.strip()[-200:])
        return None
    return done.stdout


def list_nodes(run: Run | None = None) -> list[Node] | None:
    """Return the server's sinks and sources; None when no server answers. Blocks."""
    run = run or pactl
    sinks, sources = run(["list", "sinks"]), run(["list", "sources"])
    if sinks is None or sources is None:
        return None
    return parse_nodes("sink", sinks) + parse_nodes("source", sources)


def alsa_id(node: Node, card_names: Mapping[int, str]) -> str:
    """Return the ALSA id of the card behind the node (`plughw:CARD=CODEC,DEV=0`), "" if none."""
    name = None if node.card is None else card_names.get(node.card)
    return f"plughw:CARD={name},DEV={node.device}" if name else ""


def pickable(node: Node) -> bool:
    """Return whether one channel of the source can be read alone (its positions are the plug-ins' own)."""
    n = len(node.positions)
    return node.kind == "source" and n in _PICKABLE and sorted(node.positions) == sorted(ALSA_ORDER[:n])


def cards(nodes: Sequence[Node], card_names: Mapping[int, str]) -> list[SoundCard]:
    """Return the nodes as rows of the sound card list: one per sink and source, one per channel of a source of more."""
    out: list[SoundCard] = []
    for node in nodes:
        sink = node.kind == "sink"
        row = SoundCard(server_id(node.name), node.description, sink, not sink, alsa=alsa_id(node, card_names))
        out.append(row)
        if pickable(node):
            out += [
                SoundCard(server_id(node.name, p), node.description, False, True, alsa=row.alsa, channel=i + 1)
                for i, p in enumerate(node.positions)
            ]
    return out


def server_cards(card_names: Mapping[int, str], run: Run | None = None) -> list[SoundCard]:
    """Return the server's devices as sound card rows; none without a server. Blocks."""
    return cards(list_nodes(run) or [], card_names) if sys.platform.startswith("linux") else []


# ---- what a start needs


def find(nodes: Sequence[Node], kind: Kind, ident: str) -> Node | None:
    """Return the listed node of this kind that a server id names, its channel among its positions."""
    parsed = parse_id(ident)
    if parsed is None:
        return None
    name, channel = parsed
    node = next((n for n in nodes if n.kind == kind and n.name == name), None)
    return node if node is not None and (not channel or (pickable(node) and channel in node.positions)) else None


def missing(setting: str, nodes: Sequence[Node] | None) -> str:
    """Return why a setting that names a server device cannot be started on, "" when it can."""
    if not all(half for _, half in halves(setting)):
        return "a sound device of the sound server needs one to record from and one to play to"
    if nodes is None:
        return "no sound server answers"
    for kind, half in halves(setting):
        if is_server(half) and find(nodes, kind, half) is None:
            return f"the sound server lists no {kind} {half}"
    return ""


def plugin_dir(env: Mapping[str, str] | None = None, roots: Sequence[Path] | None = None) -> Path | None:
    """Return the system's folder of ALSA plug-ins that holds a server's plug-in, None if none does.

    The shipped libasound looks in Debian's folder only; Fedora, openSUSE and Arch keep them elsewhere."""
    env = os.environ if env is None else env
    if given := env.get("ALSA_PLUGIN_DIR"):
        return Path(given)
    arch = {"x86_64": "x86_64-linux-gnu", "aarch64": "aarch64-linux-gnu", "armv7l": "arm-linux-gnueabihf"}
    triple = arch.get(platform.machine(), "")
    for folder in roots or (
        Path(f"/usr/lib/{triple}/alsa-lib"),
        Path("/usr/lib64/alsa-lib"),
        Path("/usr/lib/alsa-lib"),
    ):
        if any((folder / p.file).is_file() for p in PLUGINS.values()):
            return folder
    return None


@dataclass(frozen=True)
class SystemAlsa:
    lib: Path  # the folder of the system's libasound.so.2
    conf: Path  # its alsa.conf


SYSTEM_CONF = Path("/usr/share/alsa/alsa.conf")


def system_alsa(plugins: Path | None = None, conf: Path = SYSTEM_CONF) -> SystemAlsa | None:
    """Return the system's ALSA library beside its plug-ins of the sound server, None without one.

    The plug-ins are built for that library: the shipped one may be older (Fedora's need ALSA_1.2.15)."""
    plugins = plugin_dir() if plugins is None else plugins
    lib = None if plugins is None else plugins.parent
    return SystemAlsa(lib, conf) if lib is not None and (lib / "libasound.so.2").is_file() and conf.is_file() else None


def plugin(folder: Path | None) -> str:
    """Return the server plug-in an ALSA name goes through: Pulse's where it is, else PipeWire's."""
    have = {name for name, p in PLUGINS.items() if folder is not None and (folder / p.file).is_file()}
    return "pipewire" if have == {"pipewire"} else "pulse"


def alsa_name(half: str, kind: Kind, nodes: Sequence[Node], via: str) -> str:
    """Return the ALSA name a modem opens for one half of the setting; an ALSA card's id stays as it is.

    The device goes by its index of this listing: Direwolf opens only the first 29 characters of a name."""
    node = find(nodes, kind, half) if is_server(half) else None
    if node is None:
        return half
    parsed = parse_id(half)
    channel, prefix = parsed[1] if parsed else "", PLUGINS[via].prefix
    if channel:
        return f"{prefix}_ch{ALSA_ORDER.index(channel)}:{node.index},{len(node.positions)}"
    return f"{prefix}:{node.index}"


def alsa_setting(setting: str, nodes: Sequence[Node], via: str) -> str:
    """Return the setting with each server half replaced by the ALSA name the modem opens."""
    if not uses_server(setting):
        return setting
    return PAIR.join(alsa_name(half, kind, nodes, via) for kind, half in halves(setting))


def behind(setting: str, nodes: Sequence[Node], card_names: Mapping[int, str]) -> str:
    """Return the ALSA card a setting sits on, for its levels and its USB tie; "" when none or two."""
    if not uses_server(setting):
        return setting
    found = {
        alsa_id(node, card_names)
        if (node := find(nodes, kind, half)) is not None
        else ("" if is_server(half) else half)
        for kind, half in halves(setting)
    }
    return found.pop() if len(found) == 1 else ""


def claims(setting: str, nodes: Sequence[Node], card_names: Mapping[int, str]) -> list[str]:
    """Return what a setting holds: each half's ALSA card where it has one, else the device by name."""
    if not uses_server(setting):
        return [setting]
    held: list[str] = []
    for kind, half in halves(setting):
        node = find(nodes, kind, half) if is_server(half) else None
        value = (alsa_id(node, card_names) or server_id(node.name)) if node is not None else half
        if value and value not in held:
            held.append(value)
    return held


# ---- where a modem's streams sit


NO_INDEX = 0xFFFFFFFF  # PA_INVALID_INDEX: a stream not linked to a device yet
_STREAMS: dict[Kind, str] = {"sink": "sink-inputs", "source": "source-outputs"}


def _entries(text: str | None) -> list[dict[str, Any]] | None:
    try:
        entries = json.loads(text) if text is not None else None
    except ValueError:
        return None
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else None


def clients_of(text: str | None, pid: int) -> set[str]:
    """Return the indexes of the process's clients (`list clients`), as the streams name them."""
    return {str(e.get("index")) for e in _entries(text) or [] if _props(e).get("application.process.id") == str(pid)}


def stream_targets(text: str | None, pid: int, field: Kind, clients: Collection[str] = ()) -> list[int] | None:
    """Return the sinks or sources the process's streams sit on (`list sink-inputs|source-outputs`).

    A stream of PipeWire's own ALSA plug-in has no process id of its own; its client, one of `clients`, has."""
    entries = _entries(text)
    if entries is None:
        return None
    return [
        e[field]
        for e in entries
        if isinstance(e.get(field), int)
        and e[field] != NO_INDEX
        and (_props(e).get("application.process.id") == str(pid) or str(e.get("client")) in clients)
    ]


def misplaced(setting: str, pid: int, run: Run | None = None) -> str:
    """Return how the process's streams stray from the setting's devices (another device, one gone), "" if not."""
    run = run or pactl
    nodes = list_nodes(run)
    if nodes is None:
        return ""
    if why := missing(setting, nodes):
        return why
    clients = clients_of(run(["list", "clients"]), pid)
    for kind, half in halves(setting):
        node = find(nodes, kind, half) if is_server(half) else None
        if node is None:
            continue
        on = stream_targets(run(["list", _STREAMS[kind]]), pid, kind, clients)
        if on and any(i != node.index for i in on):
            return f"the {kind} stream of process {pid} is not on {node.name} but on {sorted(set(on) - {node.index})}"
    return ""
