#!/usr/bin/env python3
"""End-to-end test of Update now with the real files of a release, against fake servers (CI only).
scripts/update-e2e.py windows OLD.exe NEW.exe [--work DIR] [--known-old]
scripts/update-e2e.py appimage OLD.AppImage NEW.AppImage [--work DIR] [--extract-and-run] [--app]
                      [--known-old]"""

import argparse
import asyncio
import base64
import contextlib
import hashlib
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke import FIXTURE, Failure, FakeTnc, apply, radio_state

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from neoaprs.updateasset import sign

WINDOWS = sys.platform == "win32"
LOG = "neoaprs.log"
NAMES = {"windows": re.compile(r"NeoAPRS-Setup-(.+)\.exe"), "appimage": re.compile(r"NeoAPRS-(.+)-x86_64\.AppImage")}
KINDS = {"windows": "windows-installer", "appimage": "appimage"}
# The AppId of packaging/windows/neoaprs.iss, as Windows' list of programs has it.
APP_ID = "{5AE53960-2902-4F1B-99E1-03E486EA7B36}_is1"
PAGE_SEC = 120.0
UPDATE_SEC = 300.0
NEW_DAEMON_SEC = 300.0
# What a daemon that ends to be restarted leaves in the data folder (neoaprs/stopfile.py).
RESTART_NOTES = ("neoaprs.restarting", "neoaprs.restart-port")
# The ports after its setting's that a daemon tries when that is taken (neoaprs/web/listen.py).
PORT_TRIES = 10


def say(text: str) -> None:
    print(f"update-e2e: {text}", flush=True)


def version_of(kind: str, file: Path) -> str:
    found = NAMES[kind].fullmatch(file.name)
    if not found:
        raise Failure(f"{file.name} is not named like the {kind} file of a release")
    return found.group(1)


def newer(a: str, b: str) -> bool:
    """Return whether `a` is newer than `b`, as the daemon compares them (neoaprs/versions.py)."""

    def parts(v: str) -> list[int | str]:
        return [int(p) if p.isdigit() else p for p in re.split(r"[.\-+]", v)]

    left, right = parts(a), parts(b)
    for x, y in zip(left + [0] * (len(right) - len(left)), right + [0] * (len(left) - len(right))):
        if x != y:
            if isinstance(x, int) and isinstance(y, int):
                return x > y
            return isinstance(x, int)
    return False


def sha256(file: Path) -> str:
    digest = hashlib.sha256()
    with file.open("rb") as f:
        while piece := f.read(1 << 20):
            digest.update(piece)
    return digest.hexdigest()


def wait_until(condition: Callable[[], bool], seconds: float, what: str) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        if time.monotonic() > deadline:
            raise Failure(f"{what}: not within {seconds:g} s")
        time.sleep(0.25)


def read_log(data: Path) -> str:
    try:
        return (data / LOG).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


class Release:
    """The version page and GitHub's release folder on one loopback port; a test key signs the
    list."""

    def __init__(self, version: str, file: Path) -> None:
        self.version = version
        self.file = file
        self.sums = f"{hashlib.sha256(b'other').hexdigest()}  install.sh\n{sha256(file)}  {file.name}\n".encode()
        seed = os.urandom(32)
        self.signature = sign(self.sums, version, seed).encode()
        self.public_key = base64.b64encode(
            Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        ).decode()
        self.requests: list[str] = []
        release = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                release.requests.append(self.path)
                path = self.path.split("?", 1)[0]
                if path == "/version.php":
                    self._send(
                        json.dumps(
                            {
                                "version": release.version,
                                "url": "https://github.com/oh2gba/neoaprs/releases",
                                "message": "",
                            }
                        ).encode(),
                        "application/json",
                    )
                elif path == f"/v{release.version}/SHA256SUMS":
                    self._send(release.sums, "text/plain")
                elif path == f"/v{release.version}/SHA256SUMS.sig":
                    self._send(release.signature, "text/plain")
                elif path == f"/v{release.version}/{release.file.name}":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(release.file.stat().st_size))
                    self.end_headers()
                    with release.file.open("rb") as f:
                        shutil.copyfileobj(f, self.wfile, 1 << 20)
                else:
                    self.send_error(404)

            def _send(self, body: bytes, kind: str) -> None:
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        # A connection gone between the question and the taking would hang shutdown for ever.
        self.server.socket.settimeout(1.0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class Page:
    """The page's WebSocket: the hello, the topics, the latest status and the other messages."""

    def __init__(self, connection: Any, hello: dict[str, Any]) -> None:
        self.connection = connection
        self.hello = hello
        self.topics: dict[str, Any] = {}
        self.status: dict[str, Any] = {}
        self.messages: list[dict[str, Any]] = []
        self.closed = False

    @classmethod
    async def open(cls, port: int) -> "Page":
        from tornado.websocket import websocket_connect

        connection = await websocket_connect(f"ws://127.0.0.1:{port}/ws", connect_timeout=5)
        raw = await asyncio.wait_for(connection.read_message(), 15)
        hello = json.loads(raw) if raw is not None else {}
        if hello.get("type") != "hello":
            connection.close()
            raise Failure(f"the first message of the socket is not hello: {raw!r}")
        return cls(connection, hello)

    @classmethod
    async def among(
        cls, ports: range, version: str, seconds: float, alive: Callable[[], bool] = lambda: True
    ) -> tuple["Page", int]:
        """Wait for the page of the daemon of `version` on one of `ports`; return (page, port).

        A page of another version is closed and asked again; Failure at once if `alive` is False."""
        from tornado.httpclient import HTTPClientError

        deadline = time.monotonic() + seconds
        seen = "no page"
        while time.monotonic() < deadline:
            for port in ports:
                try:
                    page = await cls.open(port)
                except (OSError, TimeoutError, HTTPClientError, Failure):
                    continue
                if page.hello.get("version") == version:
                    return page, port
                seen = f"the page of {page.hello.get('version')} on port {port}"
                page.close()
            if not alive():
                raise Failure(
                    f"no daemon of {version} on the ports {ports.start} to {ports[-1]}: the program ended ({seen})"
                )
            await asyncio.sleep(1)
        raise Failure(f"no daemon of {version} on the ports {ports.start} to {ports[-1]} within {seconds:g} s ({seen})")

    def send(self, command: dict[str, Any]) -> None:
        self.connection.write_message(json.dumps(command))

    async def until(
        self,
        condition: Callable[["Page"], bool],
        seconds: float,
        what: str,
        on_change: Callable[["Page"], None] | None = None,
    ) -> None:
        """Read messages until `condition` holds; Failure if time is up or the socket closes."""
        deadline = asyncio.get_running_loop().time() + seconds
        while not condition(self):
            left = deadline - asyncio.get_running_loop().time()
            if left <= 0:
                raise Failure(
                    f"{what}: not within {seconds:g} s (the FM radio {radio_state(self.topics, 'fm')}, update {self.topics.get('update')}, {self.status.get('packets')} packets)"
                )
            if self.closed:
                raise Failure(f"{what}: the daemon closed the socket first")
            try:
                raw = await asyncio.wait_for(self.connection.read_message(), left)
            except TimeoutError:
                continue
            if raw is None:
                self.closed = True
                continue
            message = json.loads(raw)
            if message.get("type") == "status":
                self.status = message
            elif message.get("type") in ("state", "patch"):
                apply(self.topics, message)
            else:
                self.messages.append(message)
            if on_change is not None:
                on_change(self)

    def errors(self) -> list[dict[str, Any]]:
        return [m for m in self.messages if m.get("type") == "error"]

    def close(self) -> None:
        self.connection.close()


def connected(page: Page) -> bool:
    """Return the FM radio's state and packet count, from the topic `radios` (old release: `tnc`).

    This is the one reader of the old release's wire; smoke.py reads `radios` alone."""
    state = radio_state(page.topics, "fm") or (page.topics.get("tnc") or {}).get("state")
    return state == "connected" and int(page.status.get("packets") or 0) > 0


# The first release whose daemon starts the new AppImage the way it ran and says where its page is.
KEPT_FROM = (0, 20, 2)


def numbers(version: str) -> tuple[int, ...]:
    """Return the three numbers of a version, ignoring a suffix (`0.20.2-e2e`); (0, 0, 0) if
    none."""
    found = re.match(r"(\d+)\.(\d+)\.(\d+)", version)
    return tuple(int(n) for n in found.groups()) if found else (0, 0, 0)


def held_port() -> tuple[socket.socket, int]:
    """Return (socket, port): a loopback port this test holds, listening, with the next port
    free."""
    for _ in range(50):
        holder = socket.socket()
        try:
            holder.bind(("127.0.0.1", 0))
            holder.listen()
            port = int(holder.getsockname()[1])
            if port + PORT_TRIES > 65535:
                raise OSError("too near the last port")
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", port + 1))
        except OSError:
            holder.close()
            continue
        return holder, port
    raise Failure("no port of the loopback with a free one after it")


def descendants(pid: int, proc: Path = Path("/proc")) -> list[int]:
    """Return `pid` and every process under it, newest last (Linux: parents are read from
    `stat`)."""
    parents: dict[int, int] = {}
    for entry in proc.iterdir():
        if entry.name.isdigit():
            try:
                parents[int(entry.name)] = int(
                    (entry / "stat").read_text(encoding="utf-8", errors="replace").rsplit(")", 1)[1].split()[1]
                )
            except (OSError, ValueError, IndexError):
                continue  # a process that ended while it was read
    found, generation = [pid], [pid]
    while generation:
        generation = sorted(child for child, parent in parents.items() if parent in generation and child not in found)
        found += generation
    return found


def environ_of(pid: int, proc: Path = Path("/proc")) -> dict[str, str]:
    """Return the environment a process was started with; empty if unreadable."""
    try:
        raw = (proc / str(pid) / "environ").read_bytes()
    except OSError:
        return {}
    return dict(item.split("=", 1) for item in raw.decode("utf-8", errors="replace").split("\0") if "=" in item)


def program_folder(pid: int, appimage: str, proc: Path = Path("/proc")) -> str:
    """Return `$APPDIR` (mount or unpack folder) of the newest process under `pid` from the file.

    Older processes of the old version still name the old folder after an update."""
    for one in reversed(descendants(pid, proc)):
        env = environ_of(one, proc)
        if env.get("APPIMAGE") == appimage and env.get("APPDIR"):
            return env["APPDIR"]
    return ""


def how(mounted: bool) -> str:
    return "mounted" if mounted else "unpacked"


# The FM radio's port: the flat key before radios were separate, its own key after.
PORT_KEYS = ("serial/port", "radio/1/port")
# The first release whose Update now asks for SHA256SUMS.sig; older ones use the checksum alone.
SIGNATURE_FROM = (0, 20, 0)
# Radio 1 made on a fresh folder, which newer versions lack: the FM type older ones had by default.
FIRST_RADIO = ("radios", "add", "kiss")


def set_port(install: "Install", data: Path, url: str) -> str:
    """Set the FM radio's port with the first of PORT_KEYS the old version takes; return that key.

    A newer version on a fresh folder has no radio 1, so it is added; all refused is a Failure."""
    answers = []
    for key in PORT_KEYS:
        done = install.run("db", "--data", str(data), "set", key, url)
        if done.returncode == 0:
            return key
        answers.append(f"{key}: {done.stdout.strip()} {done.stderr.strip()}")
    added = install.run("db", "--data", str(data), *FIRST_RADIO)
    answers.append(f"{' '.join(FIRST_RADIO)}: {added.stdout.strip()} {added.stderr.strip()}")
    if added.returncode == 0:
        done = install.run("db", "--data", str(data), "set", PORT_KEYS[1], url)
        if done.returncode == 0:
            return PORT_KEYS[1]
        answers.append(f"then {PORT_KEYS[1]}: {done.stdout.strip()} {done.stderr.strip()}")
    raise Failure(f"db set of the FM radio's port refused: {'; '.join(answers)}")


def get_port(install: "Install", data: Path) -> str:
    """Return the new version's FM radio port: its own key first, else the flat key."""
    for key in reversed(PORT_KEYS):
        done = install.run("db", "--data", str(data), "get", key)
        if done.returncode == 0:
            return done.stdout.strip()
    return ""


class Install:
    """The kind of install the test updates: how the old version is placed, run and checked."""

    kind = ""

    def __init__(self, work: Path, old: Path, new: Path, known_old: bool = False) -> None:
        self.work, self.old, self.new = work, old, new
        # --known-old, for an old version known to have quirks.
        self.known_old = known_old and numbers(version_of(self.kind, old)) < KEPT_FROM
        # What is outside the data folder before the update, compared at the end.
        self.before: dict[str, Any] = {}

    def put_old(self) -> None: ...
    def before_update(self, data: Path) -> None: ...
    def command(self) -> list[str]:
        return []

    def start(self, data: Path, env: dict[str, str]) -> subprocess.Popen[bytes]:
        raise NotImplementedError

    def check_hello(self, hello: dict[str, Any]) -> None: ...
    def old_runs(self, daemon: subprocess.Popen[bytes]) -> None: ...
    def outside(self) -> dict[str, Any]:
        return {}

    def old_ended(self, daemon: subprocess.Popen[bytes], data: Path) -> None: ...
    def check_new(self, daemon: subprocess.Popen[bytes], data: Path, new_version: str) -> None: ...
    def stop(self, daemon: subprocess.Popen[bytes], data: Path) -> None: ...
    def leftovers(self) -> list[str]:
        return []

    def env(self, env: dict[str, str]) -> dict[str, str]:
        return env

    # Where the page is looked for.
    def page_ports(self, data: Path, ports: range, alive: Callable[[], bool]) -> range:
        return ports

    # After a failure: what the test left running.
    def clean_up(self) -> None: ...

    def run(self, *args: str, timeout: float = 120) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*self.command(), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=self.env(dict(os.environ)),
            stdin=subprocess.DEVNULL,
        )

    def out(self, name: str) -> Any:
        return (self.work / name).open("ab")


class WindowsInstall(Install):
    kind = "windows"

    def __init__(self, work: Path, old: Path, new: Path, known_old: bool = False) -> None:
        super().__init__(work, old, new, known_old)
        local = Path(os.environ["LOCALAPPDATA"])
        self.app = local / "Programs" / "NeoAPRS"
        self.default_data = local / "NeoAPRS"
        self.menu = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "NeoAPRS"
        self.desktops = [
            Path(os.environ["USERPROFILE"]) / "Desktop",
            Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop",
        ]

    def put_old(self) -> None:
        if (self.app / "neoaprs.exe").exists():
            raise Failure(f"NeoAPRS is installed in {self.app} already: the test needs a machine without it")
        # No task: no start at sign-in, no desktop shortcut (an update keeps the install's tasks).
        done = subprocess.run(
            [
                str(self.old),
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/CURRENTUSER",
                "/NORESTART",
                "/TASKS=",
                f"/LOG={self.work / 'install-old.log'}",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=300,
        )
        if done.returncode != 0:
            raise Failure(f"the installer of the old version ended with {done.returncode} (install-old.log)")
        for name in ("neoaprs.exe", "neoaprsw.exe", "neoaprs-app.exe"):
            if not (self.app / name).is_file():
                raise Failure(f"{name} is not in {self.app} after the install of the old version")

    def command(self) -> list[str]:
        return [str(self.app / "neoaprs.exe")]

    def before_update(self, data: Path) -> None:
        (data / "update").mkdir(parents=True, exist_ok=True)
        # Which this update deletes.
        (data / "update" / "NeoAPRS-Setup-0.0.1.exe").write_bytes(b"MZ the installer of an earlier update")

    def start(self, data: Path, env: dict[str, str]) -> subprocess.Popen[bytes]:
        # What the Start menu's app or the start at sign-in starts: the daemon with no console, on
        # the data folder (the update restarts it so: packaging/windows/neoaprs.iss).
        return subprocess.Popen(
            [str(self.app / "neoaprsw.exe"), "run", "--data", str(data)],
            stdin=subprocess.DEVNULL,
            stdout=self.out("daemon-old.out"),
            stderr=subprocess.STDOUT,
            env=env,
        )

    def check_hello(self, hello: dict[str, Any]) -> None:
        if hello["install"]["kind"] != "windows-installer":
            raise Failure(f"the installed daemon says it is {hello['install']['kind']!r}, not windows-installer")

    def outside(self) -> dict[str, Any]:
        import winreg

        found: dict[str, Any] = {}
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            values = {}
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                except OSError:
                    break
                values[name] = value
                i += 1
        found["the start at sign-in (the Run key)"] = values
        found["the Start menu entries"] = sorted(p.name for p in self.menu.iterdir()) if self.menu.is_dir() else []
        found["the desktop shortcuts"] = sorted(
            str(p) for d in self.desktops if d.is_dir() for p in d.iterdir() if "neoaprs" in p.name.lower()
        )
        found["the default data folder"] = (
            sorted(
                (str(p.relative_to(self.default_data)), p.stat().st_size, p.stat().st_mtime_ns)
                for p in self.default_data.rglob("*")
                if p.is_file()
            )
            if self.default_data.is_dir()
            else None
        )
        return found

    def displayed_version(self) -> str:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}"
        ) as key:
            return str(winreg.QueryValueEx(key, "DisplayVersion")[0])

    def old_ended(self, daemon: subprocess.Popen[bytes], data: Path) -> None:
        try:
            code = daemon.wait(120)
        except subprocess.TimeoutExpired:
            raise Failure("the old daemon did not end within 120 s of the restart") from None
        if code != 0:
            raise Failure(f"the old daemon ended with exit code {code}, not 0")
        say("the old daemon ended with exit code 0")

    def check_new(self, daemon: subprocess.Popen[bytes], data: Path, new_version: str) -> None:
        log = data / "update" / "install.log"
        text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
        if not text:
            raise Failure(f"the installer of the update wrote no log at {log}")
        command = next((line for line in text.splitlines() if "Setup command line:" in line), "")
        for flag in (
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/CURRENTUSER",
            "/NEOAPRSRESTART=daemon",
            f"/NEOAPRSDATA={data}",
        ):
            if flag.lower() not in command.lower():
                raise Failure(f"the installer of the update was not run with {flag}: {command.strip()!r}")
        if "Installation process succeeded" not in text:
            raise Failure(f"the installer's log does not say 'Installation process succeeded' ({log})")
        if (kept := sorted(p.name for p in log.parent.iterdir())) != sorted(
            [f"NeoAPRS-Setup-{new_version}.exe", "install.log"]
        ):
            raise Failure(
                f"update/ of the data folder holds {kept}: the installer of the earlier update was not deleted, or something else is left"
            )
        say(f"the installer ran silently: {command.split('Setup command line:', 1)[1].strip()}")
        version = self.run("--version").stdout.strip()
        if version != f"NeoAPRS {new_version}":
            raise Failure(f"the installed neoaprs.exe says {version!r}, not NeoAPRS {new_version}")
        if (shown := self.displayed_version()) != new_version:
            raise Failure(f"Windows' list of programs says NeoAPRS {shown}, not {new_version}")
        say(f"the installed neoaprs.exe and Windows' list of programs say {new_version}")

    def stop(self, daemon: subprocess.Popen[bytes], data: Path) -> None:
        done = self.run("stop", "--data", str(data))
        if done.returncode != 0:
            raise Failure(f"neoaprs stop ended with {done.returncode}: {done.stdout.strip()} {done.stderr.strip()}")

    def leftovers(self) -> list[str]:
        listing = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=60).stdout
        names = [line.split('","', 1)[0].strip('"') for line in listing.splitlines() if line.strip()]
        return [n for n in names if n.lower().startswith(("neoaprs", "neoaprs-setup"))]


class AppImageInstall(Install):
    kind = "appimage"

    def __init__(self, work: Path, old: Path, new: Path, extract_and_run: bool, known_old: bool = False) -> None:
        super().__init__(work, old, new, known_old)
        self.extract_and_run = extract_and_run
        self.folder = work / "Applications"
        # It keeps its name after the update: the user's file is replaced where it is.
        self.file = self.folder / old.name
        self.home = work / "home"
        self.pid = 0
        # Where the old version's program ran from: its mount or unpack folder.
        self.old_folder = ""

    def temporary(self) -> list[str]:
        """Return the test's temporary folder, where the AppImage runtime's mounts and unpacks
        are made."""
        try:
            return sorted(p.name for p in (self.work / "tmp").iterdir())
        except OSError:
            return []

    unpack_way = "--appimage-extract-and-run"  # starts the file unpacked

    def old_runs(self, daemon: subprocess.Popen[bytes]) -> None:
        """With the old daemon up, check its program runs from where the test started it."""
        self.old_folder = program_folder(daemon.pid, str(self.file))
        if not self.old_folder:
            raise Failure(
                f"no process under the test's child {daemon.pid} says it was started from {self.file} (its APPIMAGE and APPDIR)"
            )
        self.held_start("daemon", self.old_folder)

    def held_start(self, who: str, folder: str) -> None:
        """Check the old version's `who` runs from `folder` as started: mounted or unpacked."""
        mounted = os.path.ismount(folder)
        if mounted == self.extract_and_run:
            raise Failure(
                f"the old {who} runs {how(mounted)} from {folder}, though the test started it {'with' if self.extract_and_run else 'without'} {self.unpack_way}"
            )
        say(f"the old {who} runs {how(mounted)}, from {folder}")

    def env(self, env: dict[str, str]) -> dict[str, str]:
        tmp = self.work / "tmp"
        tmp.mkdir(exist_ok=True)
        env.update(
            HOME=str(self.home),
            XDG_DATA_HOME=str(self.home / ".local" / "share"),
            XDG_CONFIG_HOME=str(self.home / ".config"),
            XDG_CACHE_HOME=str(self.home / ".cache"),
            TMPDIR=str(tmp),
        )
        for name in ("APPIMAGE", "APPDIR", "ARGV0", "OWD", "APPIMAGE_EXTRACT_AND_RUN"):
            env.pop(name, None)
        return env

    def put_old(self) -> None:
        if not self.extract_and_run and (
            not Path("/dev/fuse").exists() or not (shutil.which("fusermount") or shutil.which("fusermount3"))
        ):
            raise Failure("no FUSE here (/dev/fuse and fusermount): install it, or give --extract-and-run")
        self.folder.mkdir(parents=True)
        self.home.mkdir(parents=True)
        shutil.copy2(self.old, self.file)
        os.chmod(self.file, 0o755)  # noqa: S103  (an AppImage is a program: world-readable and executable)

    def command(self) -> list[str]:
        return [str(self.file), "--appimage-extract-and-run"] if self.extract_and_run else [str(self.file)]

    def start(self, data: Path, env: dict[str, str]) -> subprocess.Popen[bytes]:
        daemon = subprocess.Popen(
            [*self.command(), "run", "--data", str(data)],
            stdin=subprocess.DEVNULL,
            stdout=self.out("daemon.out"),
            stderr=subprocess.STDOUT,
            env=self.env(env),
        )
        self.pid = daemon.pid
        return daemon

    def check_hello(self, hello: dict[str, Any]) -> None:
        if hello["install"]["kind"] != "appimage" or hello["install"]["appimage"] != str(self.file):
            raise Failure(f"the daemon says it is {hello['install']}, not the AppImage {self.file}")

    def outside(self) -> dict[str, Any]:
        return {
            "the home folder": sorted(str(p.relative_to(self.home)) for p in self.home.rglob("*")),
            "the folder of the AppImage": sorted(p.name for p in self.folder.iterdir()),
        }

    def old_ended(self, daemon: subprocess.Popen[bytes], data: Path) -> None:
        wait_until(
            lambda: "NeoAPRS ended" in read_log(data) or daemon.poll() is not None,
            120,
            "the old daemon's end in the log",
        )
        if daemon.poll() is not None:
            raise Failure(
                f"the process ended with exit code {daemon.returncode} instead of starting the new version (daemon.out)"
            )
        say("the old daemon ended and the process went on")

    def check_new(self, daemon: subprocess.Popen[bytes], data: Path, new_version: str) -> None:
        if daemon.poll() is not None or daemon.pid != self.pid:
            raise Failure("the new version does not run in the process the old one ran in")
        self.check_file(new_version)
        say(f"the same process {daemon.pid} runs it")
        self.check_how_it_runs(daemon)

    def check_file(self, new_version: str) -> None:
        """Check the file in place is the new one, executable, alone in its folder."""
        if sha256(self.file) != sha256(self.new):
            raise Failure(f"{self.file} is not the new AppImage")
        mode = self.file.stat().st_mode
        if not mode & stat.S_IXUSR:
            raise Failure(f"{self.file} is not executable after the update: {stat.filemode(mode)}")
        wait_until(
            lambda: not (self.folder / (self.file.name + ".old")).exists(),
            60,
            "the old AppImage kept as .old deleted once the new one runs",
        )
        if (left := sorted(p.name for p in self.folder.iterdir())) != [self.file.name]:
            raise Failure(f"the folder of the AppImage holds {left}, not the AppImage alone")
        say(f"{self.file.name} is now the AppImage of {new_version} ({stat.filemode(mode)}) and the .old is gone")

    def check_how_it_runs(self, daemon: subprocess.Popen[bytes]) -> None:
        """Check the new daemon runs as the old one did: mounted if it was mounted, else
        unpacked."""
        self.held_how("daemon", program_folder(daemon.pid, str(self.file)), self.old_folder)
        say(
            f"the temporary folder holds {self.temporary() or 'nothing'} while the new daemon runs; the old version's {Path(self.old_folder).name} is {'still there' if Path(self.old_folder).exists() else 'gone'}"
        )

    def held_how(self, who: str, folder: str, old_folder: str) -> None:
        """Check the new version's `who` runs from `folder` as the old one ran from `old_folder`."""
        if not folder or folder == old_folder:
            raise Failure(
                f"the new {who}'s process does not say where it runs from (its APPDIR is {folder!r}; the old one's was {old_folder!r})"
            )
        mounted, wanted = os.path.ismount(folder), not self.extract_and_run
        if mounted == wanted:
            say(f"the new {who} runs {how(mounted)}, as the old one did, from {folder}")
        elif self.known_old and wanted:
            say(
                f"known of {version_of('appimage', self.old)} (--known-old): the new {who} runs unpacked, from {folder}, though the old one was mounted"
            )
        else:
            raise Failure(
                f"the new {who} runs {how(mounted)}, from {folder}, though the old one ran {how(wanted)}, from {old_folder}"
            )

    def stop(self, daemon: subprocess.Popen[bytes], data: Path) -> None:
        # (neoaprs/stopfile.py: what `neoaprs stop` writes; a second run would unpack again.)
        (data / "neoaprs.stop").write_text("stop\n", encoding="ascii")
        try:
            code = daemon.wait(60)
        except subprocess.TimeoutExpired:
            raise Failure("the new daemon did not end within 60 s of the stop") from None
        if code != 0:
            raise Failure(f"the process ended with exit code {code}, not 0")
        say(f"the temporary folder holds {self.temporary() or 'nothing'} after the stop")
        version = self.run("--version").stdout.strip()
        if version != f"NeoAPRS {version_of('appimage', self.new)}":
            raise Failure(f"{self.file.name} --version says {version!r}")


# ---- the desktop app in the place of the daemon (--app) ----
APP_LOG = "neoaprs-app.log"
# The app's own files in the data folder (neoaprs/desktop/single.py).
APP_PID, APP_PORT, APP_LOCK = "neoaprs-app.pid", "neoaprs-app.port", "neoaprs-app.lock"
DAEMON_LOCK = "neoaprs.lock"  # neoaprs/instancelock.py
# Where the daemon says its page is, which the app follows (neoaprs/cli/logfile.py).
PAGE_FILE = "neoaprs-web.url"
# What the app restarted after Update now is started with (neoaprs/desktop/renew.py).
OWNS_DAEMON = "--owns-daemon"
# The app's log once its window is up (neoaprs/desktop/qtshell.py).
SHELL_RUNS = "the Qt shell runs ("
# The app's session log line, which says whose daemon it shows (neoaprs/desktop/shell.py).
APP_SESSION = "NeoAPRS app on "
OWN_DAEMON = " its own daemon;"
# The old app's last line (neoaprs/desktop/renew.py).
RENEWS = "NeoAPRS was updated: the app starts again as the new version"
# The last release whose app does not start again as the new version (no renew.py).
LAST_WITHOUT_RENEW = (0, 20, 2)
# Qt with no display (scripts/smoke-appimage starts the app so too).
APP_ENV = {"QT_QPA_PLATFORM": "offscreen", "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu"}
EXTRACT_AND_RUN = "APPIMAGE_EXTRACT_AND_RUN"
# What the runtime of an unpacked file says when its folder was removed before it removed it.
RUNTIME_CLEANUP = "Failed to clean up cache directory"
# New daemon to new app window: two 2 s looks of the app's watch, the window's end, the exec.
RENEW_SEC = 120.0
# How long an app that does not restart is watched staying the old program (six looks).
STAYS_SEC = 12.0
# `app --quit` waits 40 s for the app (neoaprs/desktop/cmd.py QUIT_WAIT_SEC).
QUIT_SEC = 60.0
MOUNTS_SEC = 30.0
# What an update may write into the home folder that is NeoAPRS's: data, sign-in start, menus.
OUR_FILE = re.compile(r"neoaprs|autostart|\.desktop$", re.IGNORECASE)


@dataclass(frozen=True)
class Running:
    """A NeoAPRS program of the data folder, read from its process; role "app" or "run" (daemon)."""

    pid: int
    parent: int
    role: str
    args: tuple[str, ...]  # follows `-m neoaprs`
    folder: str  # its $APPDIR
    appimage: str  # its $APPIMAGE
    exe: str  # the program file it runs

    def describe(self) -> str:
        return f"{'the app' if self.role == 'app' else 'the daemon'} {self.pid} ({version_in(self.folder) or 'no version'} from {self.folder or 'no APPDIR'})"


def read_proc(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        return b""


def state_of(pid: int, proc: Path = Path("/proc")) -> tuple[str, int]:
    """(its state, its parent); ("", 0) for a process that is gone."""
    fields = read_proc(proc / str(pid) / "stat").decode("utf-8", errors="replace").rsplit(")", 1)
    parts = fields[1].split() if len(fields) == 2 else []
    return (parts[0], int(parts[1])) if len(parts) > 1 and parts[1].isdigit() else ("", 0)


def exe_of(pid: int, proc: Path = Path("/proc")) -> str:
    try:
        return os.readlink(proc / str(pid) / "exe")
    except OSError:
        return ""


def neoaprs_processes(data: Path, proc: Path = Path("/proc")) -> list[Running]:
    """Return the app and daemon processes of the data folder `data`, by command line.

    Excluded: `--quit` commands, other commands, and zombies."""
    wanted = os.path.realpath(data)
    found = []
    for entry in sorted(proc.iterdir(), key=lambda e: (len(e.name), e.name)):
        if not entry.name.isdigit():
            continue
        # Each argument ends with a NUL.
        line = [
            a.decode("utf-8", errors="replace") for a in read_proc(entry / "cmdline").removesuffix(b"\0").split(b"\0")
        ]
        at = next((i for i in range(len(line) - 1) if line[i] == "-m" and line[i + 1] == "neoaprs"), None)
        args = tuple(line[at + 2 :] if at is not None else ())
        if not args or args[0] not in ("app", "run") or "--quit" in args or "--data" not in args[:-1]:
            continue
        if os.path.realpath(args[args.index("--data") + 1]) != wanted:
            continue
        state, parent = state_of(int(entry.name), proc)
        if state in ("", "Z", "X"):
            continue
        env = environ_of(int(entry.name), proc)
        found.append(
            Running(
                int(entry.name),
                parent,
                args[0],
                args,
                env.get("APPDIR", ""),
                env.get("APPIMAGE", ""),
                exe_of(int(entry.name), proc),
            )
        )
    return found


def version_in(folder: str) -> str:
    """Return the VERSION of the NeoAPRS in an AppImage folder (the line `--retag` changes), or
    ""."""
    for init in sorted(Path(folder).glob("usr/lib/python3.*/site-packages/neoaprs/__init__.py")) if folder else []:
        found = re.search(r'^VERSION = "([^"]+)"', init.read_text(encoding="utf-8", errors="replace"), re.MULTILINE)
        if found:
            return found.group(1)
    return ""


def listening(port: int, proc: Path = Path("/proc")) -> set[int]:
    """Return the inodes of the sockets listening on loopback `port` (`/proc/net/tcp`, `tcp6`)."""
    inodes = set()
    for name in ("tcp", "tcp6"):
        for line in read_proc(proc / "net" / name).decode("ascii", errors="replace").splitlines()[1:]:
            fields = line.split()
            if (
                len(fields) > 9
                and fields[3] == "0A"
                and ":" in fields[1]
                and int(fields[1].rsplit(":", 1)[1], 16) == port
                and fields[9].isdigit()
            ):
                inodes.add(int(fields[9]))
    return inodes


def sockets_of(pid: int, proc: Path = Path("/proc")) -> set[int]:
    """Return the inodes of the sockets a process holds."""
    found: set[int] = set()
    try:
        fds = list((proc / str(pid) / "fd").iterdir())
    except OSError:
        return found
    for fd in fds:
        try:
            target = os.readlink(fd)
        except OSError:
            continue
        if target.startswith("socket:[") and target.endswith("]") and target[8:-1].isdigit():
            found.add(int(target[8:-1]))
    return found


def lock_holders(path: Path, proc: Path = Path("/proc")) -> set[int]:
    """Return the processes holding a lock on `path`, from `/proc/locks`.

    Only the inode is matched: the device stat reports is not always the listed one (btrfs)."""
    try:
        inode = os.stat(path).st_ino
    except OSError:
        return set()
    holders = set()
    for line in read_proc(proc / "locks").decode("ascii", errors="replace").splitlines():
        fields = line.split()
        if len(fields) > 5 and fields[1] != "->" and fields[4].isdigit() and fields[5].rsplit(":", 1)[-1] == str(inode):
            holders.add(int(fields[4]))
    return holders


def mounts_under(folder: Path, proc: Path = Path("/proc")) -> list[str]:
    """Return the mount points inside `folder`, from `/proc/self/mountinfo`."""
    inside = os.path.realpath(folder) + os.sep
    points = []
    for line in read_proc(proc / "self" / "mountinfo").decode("utf-8", errors="replace").splitlines():
        fields = line.split()
        if len(fields) > 4:
            point = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), fields[4])
            if point.startswith(inside):
                points.append(point)
    return sorted(points)


def processes_from(work: Path, appimage: Path, proc: Path = Path("/proc")) -> list[str]:
    """Return "<pid> <command line>" of every process running from the work folder or the AppImage.

    This process and ended ones are left out."""
    inside = os.path.realpath(work) + os.sep
    found = []
    for entry in sorted(proc.iterdir(), key=lambda e: (len(e.name), e.name)):
        if (
            not entry.name.isdigit()
            or int(entry.name) == os.getpid()
            or state_of(int(entry.name), proc)[0] in ("", "Z", "X")
        ):
            continue
        line = [a.decode("utf-8", errors="replace") for a in read_proc(entry / "cmdline").split(b"\0") if a]
        if (
            exe_of(int(entry.name), proc).startswith(inside)
            or (line and line[0].startswith(inside))
            or environ_of(int(entry.name), proc).get("APPIMAGE") == str(appimage)
        ):
            found.append(f"{entry.name} {' '.join(line)}")
    return found


def runs_from(running: Running) -> bool:
    """Return whether the process's program file is inside its $APPDIR."""
    return bool(running.folder) and running.exe.startswith(os.path.realpath(running.folder) + os.sep)


def knows_renew(done: "subprocess.CompletedProcess[str]") -> bool:
    """Return whether the old app accepts `--owns-daemon` (True), or refuses it as unknown (False).

    Run as `app --owns-daemon --quit` on an empty folder; any other answer is a Failure."""
    if done.returncode == 0:
        return True
    if done.returncode == 2 and OWNS_DAEMON in done.stderr:
        return False
    raise Failure(
        f"the old app's answer to app {OWNS_DAEMON} --quit is neither: exit code {done.returncode}, {done.stdout.strip()} {done.stderr.strip()}"
    )


def page_port(data: Path) -> int | None:
    """Return the page port the daemon wrote in the data folder, as the app reads it, or None."""
    found = re.fullmatch(
        r"http://127\.0\.0\.1:(\d{1,5})/", read_proc(data / PAGE_FILE).decode("ascii", errors="replace").strip()
    )
    return int(found.group(1)) if found else None


def tail_of(file: Path, lines: int = 15) -> str:
    return "\n".join(read_proc(file).decode("utf-8", errors="replace").splitlines()[-lines:])


class AppImageAppInstall(AppImageInstall):
    """--app: the AppImage's desktop app, which starts its own daemon, in place of the bare
    daemon."""

    unpack_way = f"{EXTRACT_AND_RUN}=1"

    def __init__(self, work: Path, old: Path, new: Path, extract_and_run: bool, known_old: bool = False) -> None:
        super().__init__(work, old, new, extract_and_run, known_old)
        self.asked_known_old = known_old
        # The old app has no renew.py (--known-old): it stays the old program after the update.
        self.app_stays_old = False
        self.data = work
        self.old_app: Running | None = None
        self.old_app_folder = ""
        self.app: Running | None = None

    def app_env(self, env: dict[str, str]) -> dict[str, str]:
        env = self.env(env)
        env.update(APP_ENV)
        if self.extract_and_run:
            env[EXTRACT_AND_RUN] = "1"
        return env

    def home_files(self) -> list[str]:
        return sorted(str(p.relative_to(self.home)) for p in self.home.rglob("*"))

    def outside(self) -> dict[str, Any]:
        """Hold the home folder to what is NeoAPRS's alone; Qt and Chromium also write caches
        there."""
        found = super().outside()
        found["the home folder"] = [p for p in self.home_files() if OUR_FILE.search(p)]
        return found

    def app_log(self) -> str:
        return read_proc(self.data / APP_LOG).decode("utf-8", errors="replace")

    def app_command(self) -> list[str]:
        # (Unpacked by the variable of app_env, which reaches the daemon and the restarted app.)
        return [str(self.file)]

    def put_old(self) -> None:
        super().put_old()
        # Empty and never made: `--quit` looks for an app there and finds none.
        probe = self.work / "probe"
        renews = knows_renew(self.run("app", OWNS_DAEMON, "--quit", "--data", str(probe)))
        old_version = version_of("appimage", self.old)
        if renews:
            say(f"the old app takes {OWNS_DAEMON}: it starts again as the new version after Update now")
        elif self.asked_known_old and numbers(old_version) <= LAST_WITHOUT_RENEW:
            self.app_stays_old = True
            say(
                f"known of {old_version} (--known-old): its app refuses {OWNS_DAEMON}, it has no restart as the new version; held: the daemon comes back as the new version, the app goes on, Quit ends both"
            )
        else:
            raise Failure(
                f"the old app refuses {OWNS_DAEMON}: it does not start again as the new version after Update now"
                + (
                    ""
                    if numbers(old_version) <= LAST_WITHOUT_RENEW
                    else f", though {old_version} is after {'.'.join(map(str, LAST_WITHOUT_RENEW))}"
                )
                + " (--known-old is for a release of 0.20.2 or before)"
            )

    def start(self, data: Path, env: dict[str, str]) -> subprocess.Popen[bytes]:
        self.data = data
        app = subprocess.Popen(
            [*self.app_command(), "app", "--data", str(data)],
            stdin=subprocess.DEVNULL,
            stdout=self.out("app.out"),
            stderr=subprocess.STDOUT,
            env=self.app_env(env),
        )
        self.pid = app.pid
        say(
            f"the app is started on Qt's offscreen platform: {self.file.name} app --data DIR{' with ' + self.unpack_way if self.extract_and_run else ''}"
        )
        return app

    def page_ports(self, data: Path, ports: range, alive: Callable[[], bool]) -> range:
        """Return the port the daemon wrote into the data folder, one of `ports`."""
        wait_until(
            lambda: page_port(data) is not None or not alive(),
            NEW_DAEMON_SEC,
            f"the daemon's {PAGE_FILE} in the data folder",
        )
        port = page_port(data)
        if port is None:
            raise Failure(
                f"the app ended before its daemon wrote {PAGE_FILE} (app.out: {tail_of(self.work / 'app.out')})"
            )
        if port not in ports:
            raise Failure(f"{PAGE_FILE} names port {port}, none of {ports.start} to {ports[-1]}")
        say(f"{PAGE_FILE} in the data folder, which the app follows, names port {port}")
        # (A release before the fix may bring the page back on another port than the file says.)
        return ports if self.known_old else range(port, port + 1)

    def one_each(
        self, what: str, seconds: float, good: Callable[[Running, Running], bool] = lambda app, daemon: True
    ) -> tuple[Running, Running]:
        """Wait for exactly one app and one daemon on the data folder; return both, else a
        Failure."""
        seen: list[Running] = []

        def found() -> bool:
            seen[:] = neoaprs_processes(self.data)
            apps, daemons = [p for p in seen if p.role == "app"], [p for p in seen if p.role == "run"]
            return len(apps) == 1 and len(daemons) == 1 and good(apps[0], daemons[0])

        try:
            wait_until(found, seconds, what)
        except Failure as e:
            raise Failure(
                f"{e}; running on the data folder: {', '.join(p.describe() for p in seen) or 'nothing'}; the app's log ends: {tail_of(self.data / APP_LOG, 8)}"
            ) from None
        return next(p for p in seen if p.role == "app"), next(p for p in seen if p.role == "run")

    def check_app_files(self, app: Running, daemon: Running) -> None:
        """Check the app's pid, port and lock files are the running app's, and the daemon holds
        its lock."""

        def files() -> str:
            pid = read_proc(self.data / APP_PID).decode("ascii", errors="replace").strip()
            port = read_proc(self.data / APP_PORT).decode("ascii", errors="replace").strip()
            if pid != str(app.pid):
                return f"{APP_PID} says {pid or 'nothing'}"
            if not port.isdigit() or not listening(int(port)) & sockets_of(app.pid):
                return f"{APP_PORT} says {port or 'nothing'}, where the app {app.pid} does not listen"
            if (holders := lock_holders(self.data / APP_LOCK)) != {app.pid}:
                return f"{APP_LOCK} is held by {sorted(holders) or 'nothing'}"
            if daemon.pid not in lock_holders(self.data / DAEMON_LOCK):
                return f"{DAEMON_LOCK} is held by {sorted(lock_holders(self.data / DAEMON_LOCK)) or 'nothing'}"
            return ""

        wrong = [""]

        def right() -> bool:
            wrong[0] = files()
            return not wrong[0]

        try:
            # A lock inspected by a command is taken for a moment.
            wait_until(right, 15, "the app's files in the data folder")
        except Failure:
            raise Failure(
                f"the app's files in the data folder are not the ones of the app {app.pid} that runs: {wrong[0]}"
            ) from None
        say(
            f"{APP_PID}, {APP_PORT} and {APP_LOCK} are the app {app.pid}'s (its id, a socket it listens on, its lock); {DAEMON_LOCK} is held by the daemon {daemon.pid}"
        )

    def old_runs(self, daemon: subprocess.Popen[bytes]) -> None:
        """Check the old app is up with its window and daemon, run as started, with its own
        files."""
        wait_until(
            lambda: SHELL_RUNS in self.app_log() or daemon.poll() is not None, PAGE_SEC, f"'{SHELL_RUNS}' in {APP_LOG}"
        )
        if daemon.poll() is not None:
            raise Failure(
                f"the app ended with exit code {daemon.returncode} before its window ran (app.out: {tail_of(self.work / 'app.out')})"
            )
        log = self.app_log()
        session = next((line for line in reversed(log.splitlines()) if APP_SESSION in line), "")
        if OWN_DAEMON not in session:
            raise Failure(f"the app did not start its own daemon: {session.strip() or f'no session in {APP_LOG}'}")
        app, own = self.one_each("one app and one daemon on the data folder", 30)
        for running in (app, own):
            if running.appimage != str(self.file) or not runs_from(running):
                raise Failure(
                    f"{running.describe()} does not run from {self.file}: its APPIMAGE is {running.appimage!r}, its program {running.exe!r}"
                )
        self.held_start("app", app.folder)
        self.held_start("daemon", own.folder)
        self.check_app_files(app, own)
        self.old_app, self.old_app_folder, self.old_folder = app, app.folder, own.folder
        wrote = self.home_files()
        self.toolkits = set(wrote)
        self.before = self.outside()
        say(
            f"the app {app.pid} runs its window ({next(line for line in log.splitlines() if SHELL_RUNS in line).split(SHELL_RUNS, 1)[1].rstrip(')')}) with its own daemon {own.pid}; "
            f"its start wrote {', '.join(wrote[:12]) or 'nothing'}{' ...' if len(wrote) > 12 else ''} into the home folder; held from here on: nothing of NeoAPRS's (its data, its start at sign-in, its menu entries) is written there"
        )

    def old_ended(self, daemon: subprocess.Popen[bytes], data: Path) -> None:
        wait_until(
            lambda: "NeoAPRS ended" in read_log(data) or daemon.poll() is not None,
            120,
            "the old daemon's end in the log",
        )
        if daemon.poll() is not None:
            raise Failure(
                f"the app ended with exit code {daemon.returncode} when its daemon ended to start again (app.out: {tail_of(self.work / 'app.out')})"
            )
        say("the old daemon ended to start again; the app goes on")

    def check_new(self, daemon: subprocess.Popen[bytes], data: Path, new_version: str) -> None:
        assert self.old_app is not None
        self.check_file(new_version)
        new_daemon = lambda app, own: own.folder != self.old_folder and version_in(own.folder) == new_version  # noqa: E731
        if self.app_stays_old:
            app, own = self.check_app_stays(new_daemon)
        else:
            app, own = self.check_app_renewed(new_daemon, new_version)
        self.held_how("daemon", own.folder, self.old_folder)
        self.check_app_files(app, own)
        self.app = app
        self.check_mounts(app, own)

    def check_app_renewed(
        self, new_daemon: Callable[[Running, Running], bool], new_version: str
    ) -> tuple[Running, Running]:
        """Check the old app ended and ran the new file in place, as the daemon's owner."""
        assert self.old_app is not None
        old = self.old_app
        app, own = self.one_each(
            f"the app of {new_version} with {OWNS_DAEMON} and the daemon of {new_version}",
            RENEW_SEC,
            lambda app, own: (
                new_daemon(app, own)
                and app.folder != old.folder
                and version_in(app.folder) == new_version
                and OWNS_DAEMON in app.args
            ),
        )
        if not runs_from(app) or app.appimage != str(self.file):
            raise Failure(
                f"{app.describe()} does not run its program from its folder: its program is {app.exe!r}, its APPIMAGE {app.appimage!r}"
            )
        if not self.extract_and_run and app.pid != old.pid:
            raise Failure(
                f"the new app is the process {app.pid}, not {old.pid}, in whose place the old app was to run the new file (mounted, the same process goes on)"
            )
        if self.extract_and_run and app.parent != old.pid:
            raise Failure(
                f"the new app {app.pid} is a child of {app.parent}, not of {old.pid}, the old app's process, in which the new file's runtime was to run (unpacked, the runtime waits for its child)"
            )
        if RENEWS not in self.app_log():
            raise Failure(f"{APP_LOG} does not say '{RENEWS}'")
        wait_until(
            lambda: SHELL_RUNS in self.app_log().split(RENEWS, 1)[1],
            PAGE_SEC,
            f"the new app's window ('{SHELL_RUNS}' after '{RENEWS}' in {APP_LOG})",
        )
        after = self.app_log().split(RENEWS, 1)[1]
        session = next((line for line in after.splitlines() if APP_SESSION in line), "")
        if OWN_DAEMON not in session:
            raise Failure(
                f"the app started again does not own its daemon: {session.strip() or 'no session after the restart'}"
            )
        how_new = (
            "in the same process"
            if app.pid == old.pid
            else f"as the child {app.pid} of the old app's process {old.pid}, which runs the new file's runtime"
        )
        say(
            f"the old app ran the new file in its place ({RENEWS}): the app of {new_version} runs {how_new}, with {OWNS_DAEMON}, owning the daemon {own.pid}"
        )
        self.held_how("app", app.folder, old.folder)
        return app, own

    def check_app_stays(self, new_daemon: Callable[[Running, Running], bool]) -> tuple[Running, Running]:
        """--known-old, app without renew.py: the new daemon runs and the app stays the old
        program."""
        assert self.old_app is not None
        old = self.old_app
        app, own = self.one_each("the old app and the new daemon", RENEW_SEC, new_daemon)
        deadline = time.monotonic() + STAYS_SEC
        while time.monotonic() < deadline:
            app, own = self.one_each("the old app and the new daemon", 5, new_daemon)
            if (app.pid, app.folder) != (old.pid, old.folder):
                raise Failure(
                    f"the app of {version_of('appimage', self.old)} was to stay as it was, and is {app.describe()} now: the old app's question of {OWNS_DAEMON} was answered wrong"
                )
            time.sleep(1)
        say(
            f"known of {version_of('appimage', self.old)} (--known-old): the app {app.pid} stays the old program, from {app.folder}, beside the daemon {own.pid} of the new version"
        )
        return app, own

    def check_mounts(self, app: Running, own: Running) -> None:
        """Check every mount in the temporary folder belongs to the running app or daemon."""
        folders = {app.folder, own.folder} if not self.extract_and_run else set()
        tmp = self.work / "tmp"
        try:
            wait_until(lambda: set(mounts_under(tmp)) <= folders, MOUNTS_SEC, "the old version's mounts gone")
        except Failure:
            say(
                f"the temporary folder still has the mounts {sorted(set(mounts_under(tmp)) - folders)} {MOUNTS_SEC:g} s after the update, besides those of the programs that run (the old app's was {self.old_app_folder}, the old daemon's {self.old_folder}); "
                "held: none is left once the test has ended"
            )
            return
        say(
            f"the mounts in the temporary folder are {mounts_under(tmp) or 'none'}, of the programs that run, none of the old version's left beside them; it holds {self.temporary() or 'nothing'}, "
            f"the old app's {Path(self.old_app_folder).name} {'still there' if Path(self.old_app_folder).exists() else 'gone'}, the old daemon's {Path(self.old_folder).name} {'still there' if Path(self.old_folder).exists() else 'gone'}"
        )

    def stop(self, daemon: subprocess.Popen[bytes], data: Path) -> None:
        """Run `app --quit`: it must end the app and its daemon in time with exit code 0."""
        started = time.monotonic()
        with self.out("quit.out") as out:
            quit_ = subprocess.Popen(
                [*self.app_command(), "app", "--quit", "--data", str(data)],
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=subprocess.STDOUT,
                env=self.app_env(dict(os.environ)),
            )
        while quit_.poll() is None:
            # The app is the test's child: it is let go of at once, or `--quit` would still see it.
            daemon.poll()
            if time.monotonic() - started > QUIT_SEC:
                quit_.kill()
                raise Failure(f"app --quit did not end within {QUIT_SEC:g} s ({tail_of(self.work / 'quit.out')})")
            time.sleep(0.1)
        took = time.monotonic() - started
        said = tail_of(self.work / "quit.out")
        self.exit_code("app --quit", quit_.returncode, said)
        try:
            daemon.wait(30)
        except subprocess.TimeoutExpired:
            raise Failure(f"the app's process {daemon.pid} still runs 30 s after app --quit said: {said}") from None
        self.exit_code("the app", daemon.returncode, tail_of(self.work / "app.out"))
        if left := neoaprs_processes(data):
            raise Failure(
                f"after app --quit there still run on the data folder: {', '.join(p.describe() for p in left)}"
            )
        say(
            f"app --quit ended the app and its daemon in {took:.1f} s ({said.strip().splitlines()[-1] if said.strip() else 'it said nothing'})"
        )
        say(f"the temporary folder holds {self.temporary() or 'nothing'} after the stop")
        later = [p for p in self.home_files() if p not in self.toolkits]
        say(
            f"the toolkits wrote {', '.join(later[:12]) or 'nothing'}{' ...' if len(later) > 12 else ''} into the home folder since the old app was up; only NeoAPRS's own files there are held"
        )
        version = self.run("--version").stdout.strip()
        if version != f"NeoAPRS {version_of('appimage', self.new)}":
            raise Failure(f"{self.file.name} --version says {version!r}")

    def exit_code(self, what: str, code: int, said: str) -> None:
        """Return 0; or, unpacked, the runtime's 1 when its shared folder was removed first
        (reported)."""
        if code == 0:
            return
        if self.extract_and_run and code == 1 and RUNTIME_CLEANUP in said:
            say(
                f"{what} ended with exit code 1 from the unpacked file's runtime alone: '{RUNTIME_CLEANUP}' (another run of the same file, which shares the folder, had removed it first)"
            )
            return
        raise Failure(f"{what} ended with exit code {code}, not 0: {said}")

    def leftovers(self) -> list[str]:
        return processes_from(self.work, self.file) + [f"the mount {m}" for m in mounts_under(self.work)]

    def clean_up(self) -> None:
        """After a failure, end what the test left running (SIGTERM, then SIGKILL) and drop its
        mounts."""
        import signal

        for sig in (signal.SIGTERM, signal.SIGKILL):
            pids = [int(line.split(" ", 1)[0]) for line in processes_from(self.work, self.file)]
            if not pids:
                break
            say(f"ending what the test left running: {pids}")
            for pid in pids:
                with contextlib.suppress(OSError):
                    os.kill(pid, sig)
            with contextlib.suppress(Failure):
                wait_until(lambda: not processes_from(self.work, self.file), 10, "the test's processes ended")
        fusermount = shutil.which("fusermount3") or shutil.which("fusermount") or ""
        for point in mounts_under(self.work) if fusermount else []:
            subprocess.run(
                [fusermount, "-u", "-z", point], stdin=subprocess.DEVNULL, capture_output=True, timeout=30, check=False
            )


def daemon_env(release: Release) -> dict[str, str]:
    env = {
        k: v for k, v in os.environ.items() if k not in ("NEOAPRS_DATA_DIR", "NEOAPRS_DEBUG", "NEOAPRS_INSTALL_KIND")
    }
    env.update(
        NEOAPRS_UPDATE_TEST="1",
        NEOAPRS_UPDATE_FROM=release.url,
        NEOAPRS_UPDATE_KEY=release.public_key,
        NEOAPRS_UPDATE_CHECK="0",
        NEOAPRS_NO_DEVICES="1",
        NEOAPRS_SERIAL_PATTERN="/dev/neoaprs-update-e2e-no-such-port*",
    )
    return env


async def update(
    install: Install,
    data: Path,
    web_port: int,
    holder: socket.socket,
    old_version: str,
    new_version: str,
    release: Release,
    daemon: subprocess.Popen[bytes],
) -> tuple[int, int]:
    """Run the update check and `update_now` until the old daemon lets go of its socket.

    Return (packets it had, its page port). `holder` keeps the settings' port busy meanwhile."""
    alive = lambda: daemon.poll() is None  # noqa: E731
    # Not the port the test holds: nothing answers there.
    page, served = await Page.among(
        install.page_ports(data, range(web_port + 1, web_port + PORT_TRIES + 1), alive), old_version, PAGE_SEC, alive
    )
    install.check_hello(page.hello)
    install.old_runs(daemon)
    say(
        f"the daemon of {old_version} is up: {page.hello['install']}; its page is on port {served}, the port of its settings, {web_port}, being taken"
    )
    await page.until(
        lambda p: connected(p) and bool((p.topics.get("update") or {}).get("supported")),
        PAGE_SEC,
        "the fake TNC connected, a packet, and Update now offered",
    )
    packets = int(page.status["packets"])
    say(f"the fake TNC is connected, {packets} packets, Update now is offered")
    page.send({"cmd": "update_check"})
    await page.until(
        lambda p: any(m.get("type") == "update_result" for m in p.messages), 60, "the answer to update_check"
    )
    result = next(m for m in page.messages if m.get("type") == "update_result")
    if (result["outcome"], result["version"]) != ("newer", new_version):
        raise Failure(f"the update check said {result}, not newer {new_version}")
    await page.until(
        lambda p: (p.status.get("update") or {}).get("version") == new_version, 30, "the status naming the new version"
    )
    say(f"the update check found {new_version}")
    states: list[str] = []

    def follow(p: Page) -> None:
        state = (p.topics.get("update") or {}).get("state")
        if state and (not states or states[-1] != state):
            states.append(state)
            say(
                f"update: {state} {(p.topics.get('update') or {}).get('percent')}%"
                if state == "downloading"
                else f"update: {state}"
            )
        if state == "error":
            raise Failure(f"Update now failed: {p.topics['update']['problem']}: {p.topics['update']['detail']}")
        if p.errors():
            raise Failure(f"the daemon refused: {p.errors()[0]}")

    holder.close()
    say(f"port {web_port} is free again")
    page.send({"cmd": "update_now", "version": new_version})
    try:
        await page.until(lambda p: p.closed, UPDATE_SEC, "the update and the old daemon's end", follow)
    finally:
        page.close()
    if "restarting" not in states:
        raise Failure(f"the update went {states}, never to restarting")
    asked = [r for r in release.requests if r.startswith(f"/v{new_version}/")]
    # An older release checks the file by its checksum alone and asks for no signature.
    signed = numbers(old_version) >= SIGNATURE_FROM
    wanted = [
        f"/v{new_version}/SHA256SUMS",
        *([f"/v{new_version}/SHA256SUMS.sig"] if signed else []),
        f"/v{new_version}/{install.new.name}",
    ]
    if asked != wanted:
        raise Failure(
            f"the release server was asked for {asked}, not {', '.join(w.rsplit('/', 1)[1] for w in wanted)} in that order"
        )
    say(
        f"the update went {' -> '.join(states)}; SHA256SUMS, {'its signature ' if signed else ''}and {install.new.name} were fetched from the fake release"
    )
    install.old_ended(daemon, data)
    return packets, served


def check_port(install: Install, web_port: int, served: int, now: int, new_version: str) -> None:
    """Check the new daemon serves the page where the old one did; --known-old allows a
    difference."""
    if now == served:
        say(
            f"a daemon of {new_version} is up, its page on port {served} as before, though the port of the settings, {web_port}, is free"
        )
    elif install.known_old and (install.kind == "windows" or numbers(new_version) < KEPT_FROM):
        say(
            f"known of {version_of(install.kind, install.old)} (--known-old): the page of {new_version} is on port {now}, not on {served} where the old daemon served it"
        )
    else:
        raise Failure(
            f"the page of the new daemon is on port {now}, not on {served} where the old one served it: a page that was open does not find NeoAPRS again"
        )


async def after(
    install: Install,
    data: Path,
    web_port: int,
    served: int,
    new_version: str,
    packets: int,
    daemon: subprocess.Popen[bytes],
) -> None:
    page, now = await Page.among(
        install.page_ports(data, range(web_port, web_port + PORT_TRIES + 1), lambda: daemon.poll() is None),
        new_version,
        NEW_DAEMON_SEC,
    )
    try:
        install.check_hello(page.hello)
        check_port(install, web_port, served, now, new_version)
        await page.until(connected, PAGE_SEC, "the new daemon connected to the fake TNC of the settings")
        if int(page.status["packets"]) < packets:
            raise Failure(
                f"the new daemon has {page.status['packets']} packets, fewer than the {packets} of the old one"
            )
        say(f"the new daemon is connected to the fake TNC and has {page.status['packets']} packets")
        if left := [name for name in RESTART_NOTES if (data / name).exists()]:
            raise Failure(
                f"the data folder still holds {', '.join(left)} though the new daemon runs: the notes of a restart are read once"
            )
        install.check_new(daemon, data, new_version)
    finally:
        page.close()


def run(args: argparse.Namespace) -> None:
    old, new = Path(args.old).resolve(), Path(args.new).resolve()
    old_version, new_version = version_of(args.kind, old), version_of(args.kind, new)
    if not newer(new_version, old_version):
        raise Failure(f"{new_version} is not newer than {old_version}")
    work = Path(args.work).resolve()
    if work.exists() and any(work.iterdir()):
        raise Failure(f"the work folder {work} is not empty")
    work.mkdir(parents=True, exist_ok=True)
    data = work / "data folder"  # a blank in the path, as a user's
    install: Install = (
        WindowsInstall(work, old, new, args.known_old)
        if args.kind == "windows"
        else (AppImageAppInstall if args.app else AppImageInstall)(work, old, new, args.extract_and_run, args.known_old)
    )
    tnc = FakeTnc(FIXTURE.read_bytes())
    release = Release(new_version, new)
    daemon: subprocess.Popen[bytes] | None = None
    holder: socket.socket | None = None
    try:
        say(f"{args.kind}{' with the desktop app' if args.app else ''}: {old.name} -> {new.name}")
        install.put_old()
        say(f"the old version is in place: {' '.join(install.command())}")
        # The settings' port, which this test holds while the old daemon starts.
        holder, web_port = held_port()
        port_key = set_port(install, data, tnc.url)
        settings = {
            "web/port": str(web_port),
            "update/url": f"{release.url}/version.php",
            "station/comment": "update e2e",
            "map/radius_km": "42",
        }
        for key, value in settings.items():
            done = install.run("db", "--data", str(data), "set", key, value)
            if done.returncode != 0:
                raise Failure(f"db set {key}: {done.stdout.strip()} {done.stderr.strip()}")
        install.before_update(data)
        install.before = install.outside()
        daemon = install.start(data, daemon_env(release))
        packets, served = asyncio.run(
            update(install, data, web_port, holder, old_version, new_version, release, daemon)
        )
        asyncio.run(after(install, data, web_port, served, new_version, packets, daemon))
        install.stop(daemon, data)
        wait_until(
            lambda: read_log(data).rstrip().endswith("NeoAPRS ended"),
            60,
            "'NeoAPRS ended' as the last line of the log after the stop",
        )
        log = read_log(data)
        marks = [f"NeoAPRS {old_version} starting", "NeoAPRS ended", f"NeoAPRS {new_version} starting", "NeoAPRS ended"]
        at = 0
        for mark in marks:
            at = log.find(mark, at)
            if at < 0:
                raise Failure(f"the log does not have, in this order: {marks}")
            at += len(mark)
        say("the log has the start and the end of the old version, then of the new one")
        for key, value in settings.items():
            got = install.run("db", "--data", str(data), "get", key).stdout.strip()
            if value not in got:
                raise Failure(f"the setting {key} is {got!r} after the update, not {value!r}")
        if tnc.url not in (got := get_port(install, data)):
            raise Failure(f"the FM radio's port ({port_key} before the update) is {got!r} after it, not {tnc.url!r}")
        say(f"the settings are still there: the FM radio's port, {', '.join(settings)}")
        before = install.before
        if (later := install.outside()) != before:
            changed = [name for name in before if before[name] != later.get(name)]
            raise Failure(f"the update changed {', '.join(changed)}: {[(before[n], later.get(n)) for n in changed]}")
        say(f"nothing else changed: {', '.join(before)}")
        try:
            wait_until(lambda: not install.leftovers(), 60, "no program of NeoAPRS left running after the stop")
        except Failure:
            raise Failure(f"still running after the stop: {install.leftovers()}") from None
    except Failure as e:
        print(
            f"update-e2e: FAILED: {e}\n--- the end of the log ---\n{read_log(data)[-6000:]}\n--- the fake release was asked for ---\n{release.requests}",
            file=sys.stderr,
        )
        raise
    finally:
        if daemon is not None and daemon.poll() is None:
            if data.is_dir():
                (data / "neoaprs.stop").write_text("stop\n", encoding="ascii")
            try:
                daemon.wait(30)
            except subprocess.TimeoutExpired:
                daemon.kill()
        install.clean_up()
        if holder is not None:
            holder.close()
        tnc.close()
        release.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="The end-to-end test of Update now with the real files of a release (on a CI runner only: it installs and replaces files)."
    )
    parser.add_argument("kind", choices=("windows", "appimage"))
    parser.add_argument("old", help="the installer or the AppImage of the version that is updated")
    parser.add_argument("new", help="the one of the newer version, which the fake release serves")
    parser.add_argument(
        "--work",
        default="update-e2e",
        help="an empty folder for the data folder, the AppImage, the home and the logs; default %(default)s",
    )
    parser.add_argument(
        "--extract-and-run",
        action="store_true",
        help="AppImage: start it with --appimage-extract-and-run, as a system without FUSE does",
    )
    parser.add_argument(
        "--app",
        action="store_true",
        help="AppImage: the desktop app (on Qt's offscreen platform) in the place of the bare daemon: it starts its daemon, starts again as the new version after the update, and its --quit ends both",
    )
    parser.add_argument(
        "--known-old",
        action="store_true",
        help="the old file is a release of 0.20.1 or before: what is known of its restart (the new AppImage unpacked though the old one was mounted; no note of the page's port) is said and is not a failure; "
        "with --app, also one of 0.20.2 or before whose app does not start again as the new version",
    )
    args = parser.parse_args()
    if args.kind == "windows" and not WINDOWS:
        parser.error("windows runs on Windows only")
    if args.app and args.kind != "appimage":
        parser.error(
            "--app is for the AppImage (the Windows installer of Update now ends the app and starts it again itself)"
        )
    try:
        run(args)
    except Failure:
        return 1
    say("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
