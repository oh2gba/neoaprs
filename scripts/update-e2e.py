#!/usr/bin/env python3
"""The end-to-end test of Update now, with the real files of a release: the old version is installed (the Windows installer, run silently) or put in a folder (the AppImage), its daemon runs on a data folder of
its own against a fake KISS TNC, a fake version page announces the new version and a fake release server on the loopback serves its file and SHA256SUMS the way GitHub does (`v<version>/<file>`). Over the
page's WebSocket, as the page does it, the test asks the update check, sends `update_now` and follows the topic `update`; then the new daemon must come up by itself on the same data folder.

  scripts/update-e2e.py windows OLD/NeoAPRS-Setup-A.exe NEW/NeoAPRS-Setup-B.exe [--work DIR]
  scripts/update-e2e.py appimage OLD/NeoAPRS-A-x86_64.AppImage NEW/NeoAPRS-B-x86_64.AppImage [--work DIR] [--extract-and-run]

The versions are read from the names of the files, and B must be newer than A. The daemon gets `NEOAPRS_UPDATE_TEST=1` and `NEOAPRS_UPDATE_FROM` (the fake server: CONVENTIONS.md), so that it updates for real
from the loopback; nothing leaves the loopback and no radio or serial device is used. What is asserted:
  both     the hello of A says A and the install kind; the update check finds B; update_now goes through the steps and never to `error`; SHA256SUMS and then the file of B were fetched; a daemon comes up by
           itself on the same data folder, says B in its hello, connects to the same fake TNC on the same page port (the settings are read from the data folder), and keeps the packets; the settings are
           still there after it is stopped; the log has A's start, A's end and B's start, and ends with `NeoAPRS ended`
  windows  the installer of B ran silently (its log in `update/` of the data folder: the command line of Update now, `Installation process succeeded`), A's daemon ended with exit code 0, the installed
           neoaprs.exe is B, Windows' list of programs says B, and the update changed nothing else: the start at sign-in, the Start menu entries, the desktop, the default data folder; no NeoAPRS program
           or installer is left running at the end
  appimage the file in the same place is now B (its SHA-256), executable, no `.old` or `.part` is left beside it once B runs, the same process (the test's child) went on as B, and nothing was written to
           the home folder; with --extract-and-run the file is started the way a system without FUSE starts it
This runs an installer and replaces files: run it on a CI runner, never on a computer of your own (the release workflow runs it; docs/development.md, "Update now"). Run it with a Python that has Tornado.
Exit code 0: all is well; 1: the first thing that was not, said on stderr; the work folder keeps the logs.
"""
import argparse
import asyncio
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke import FIXTURE, Failure, FakeTnc, apply  # noqa: E402

WINDOWS = sys.platform == "win32"
LOG = "neoaprs.log"
NAMES = {"windows": re.compile(r"NeoAPRS-Setup-(.+)\.exe"), "appimage": re.compile(r"NeoAPRS-(.+)-x86_64\.AppImage")}
KINDS = {"windows": "windows-installer", "appimage": "appimage"}
APP_ID = "{5AE53960-2902-4F1B-99E1-03E486EA7B36}_is1"        # the AppId of packaging/windows/neoaprs.iss, as Windows' list of programs has it
PAGE_SEC = 120.0
UPDATE_SEC = 300.0
NEW_DAEMON_SEC = 300.0


def say(text: str) -> None:
    print(f"update-e2e: {text}", flush=True)


def version_of(kind: str, file: Path) -> str:
    found = NAMES[kind].fullmatch(file.name)
    if not found:
        raise Failure(f"{file.name} is not named like the {kind} file of a release")
    return found.group(1)


def newer(a: str, b: str) -> bool:
    """Is `a` newer than `b`, as the daemon compares them (neoaprs/versions.py; enough of it for two versions of a release)?"""
    def parts(v: str) -> list[int | str]:
        return [int(p) if p.isdigit() else p for p in re.split(r"[.\-+]", v)]
    left, right = parts(a), parts(b)
    for x, y in zip(left + [0] * (len(right) - len(left)), right + [0] * (len(left) - len(right))):
        if x != y:
            if isinstance(x, int) and isinstance(y, int):
                return x > y
            return isinstance(x, int)
    return False


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


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
    """The version page and the release folder of GitHub on one port of the loopback: `/version.php` names the new version, `/v<version>/<file>` and `/v<version>/SHA256SUMS` are its files."""

    def __init__(self, version: str, file: Path) -> None:
        self.version = version
        self.file = file
        self.sums = f"{hashlib.sha256(b'other').hexdigest()}  install.sh\n{sha256(file)}  {file.name}\n".encode()
        self.requests: list[str] = []
        release = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:                        # noqa: N802  (http.server's name)
                release.requests.append(self.path)
                path = self.path.split("?", 1)[0]
                if path == "/version.php":
                    self._send(json.dumps({"version": release.version, "url": "https://github.com/oh2gba/neoaprs/releases", "message": ""}).encode(), "application/json")
                elif path == f"/v{release.version}/SHA256SUMS":
                    self._send(release.sums, "text/plain")
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

            def log_message(self, format: str, *args: Any) -> None:      # noqa: A002
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class Page:
    """The page's WebSocket: the hello, the topics as the page keeps them, the latest status, and the other messages."""

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
    async def of_version(cls, port: int, version: str, seconds: float) -> "Page":
        """The page of the daemon of `version` on `port`, waiting for it to come up (a page of another version is closed and asked again)."""
        deadline = time.monotonic() + seconds
        seen = ""
        while time.monotonic() < deadline:
            try:
                page = await cls.open(port)
            except (OSError, TimeoutError, Failure) as e:
                seen = seen or f"no page ({e.__class__.__name__})"
                await asyncio.sleep(1)
                continue
            if page.hello.get("version") == version:
                return page
            seen = f"the page of {page.hello.get('version')}"
            page.close()
            await asyncio.sleep(1)
        raise Failure(f"no daemon of {version} on port {port} within {seconds:g} s ({seen})")

    def send(self, command: dict[str, Any]) -> None:
        self.connection.write_message(json.dumps(command))

    async def until(self, condition: Callable[["Page"], bool], seconds: float, what: str, on_change: Callable[["Page"], None] | None = None) -> None:
        """Reads messages until `condition` holds; Failure when the time is up, or the socket closes first."""
        deadline = asyncio.get_running_loop().time() + seconds
        while not condition(self):
            left = deadline - asyncio.get_running_loop().time()
            if left <= 0:
                raise Failure(f"{what}: not within {seconds:g} s (tnc {(self.topics.get('tnc') or {}).get('state')}, update {self.topics.get('update')}, {self.status.get('packets')} packets)")
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
    return (page.topics.get("tnc") or {}).get("state") == "connected" and int(page.status.get("packets") or 0) > 0


class Install:
    """The kind of install the test updates: how the old version is put in place, how its commands and its daemon are run, and what is checked of the machine around it."""
    kind = ""

    def __init__(self, work: Path, old: Path, new: Path) -> None:
        self.work, self.old, self.new = work, old, new

    def put_old(self) -> None: ...
    def command(self) -> list[str]: return []
    def start(self, data: Path, env: dict[str, str]) -> subprocess.Popen[bytes]: raise NotImplementedError
    def check_hello(self, hello: dict[str, Any]) -> None: ...
    def outside(self) -> dict[str, Any]: return {}
    def old_ended(self, daemon: subprocess.Popen[bytes], data: Path) -> None: ...
    def check_new(self, daemon: subprocess.Popen[bytes], data: Path, new_version: str) -> None: ...
    def stop(self, daemon: subprocess.Popen[bytes], data: Path) -> None: ...
    def leftovers(self) -> list[str]: return []
    def env(self, env: dict[str, str]) -> dict[str, str]: return env

    def run(self, *args: str, timeout: float = 120) -> subprocess.CompletedProcess[str]:
        return subprocess.run([*self.command(), *args], capture_output=True, text=True, timeout=timeout, env=self.env(dict(os.environ)), stdin=subprocess.DEVNULL)

    def out(self, name: str) -> Any:
        return (self.work / name).open("ab")


class WindowsInstall(Install):
    kind = "windows"

    def __init__(self, work: Path, old: Path, new: Path) -> None:
        super().__init__(work, old, new)
        local = Path(os.environ["LOCALAPPDATA"])
        self.app = local / "Programs" / "NeoAPRS"
        self.default_data = local / "NeoAPRS"
        self.menu = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "NeoAPRS"
        self.desktops = [Path(os.environ["USERPROFILE"]) / "Desktop", Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop"]

    def put_old(self) -> None:
        if (self.app / "neoaprs.exe").exists():
            raise Failure(f"NeoAPRS is installed in {self.app} already: the test needs a machine without it")
        # no task: no start at sign-in, no desktop shortcut (an update keeps the tasks of the install it updates)
        done = subprocess.run([str(self.old), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/CURRENTUSER", "/NORESTART", "/TASKS=", f"/LOG={self.work / 'install-old.log'}"], stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
        if done.returncode != 0:
            raise Failure(f"the installer of the old version ended with {done.returncode} (install-old.log)")
        for name in ("neoaprs.exe", "neoaprsw.exe", "neoaprs-app.exe"):
            if not (self.app / name).is_file():
                raise Failure(f"{name} is not in {self.app} after the install of the old version")

    def command(self) -> list[str]:
        return [str(self.app / "neoaprs.exe")]

    def start(self, data: Path, env: dict[str, str]) -> subprocess.Popen[bytes]:
        # what the Start menu's app or the start at sign-in starts on its own: the daemon with no console, on the data folder (the update starts it again the same way: packaging/windows/neoaprs.iss)
        return subprocess.Popen([str(self.app / "neoaprsw.exe"), "run", "--data", str(data)], stdin=subprocess.DEVNULL, stdout=self.out("daemon-old.out"), stderr=subprocess.STDOUT, env=env)

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
        found["the desktop shortcuts"] = sorted(str(p) for d in self.desktops if d.is_dir() for p in d.iterdir() if "neoaprs" in p.name.lower())
        found["the default data folder"] = sorted((str(p.relative_to(self.default_data)), p.stat().st_size, p.stat().st_mtime_ns) for p in self.default_data.rglob("*") if p.is_file()) if self.default_data.is_dir() else None
        return found

    def displayed_version(self) -> str:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}") as key:
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
        for flag in ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", "/NEOAPRSRESTART=daemon", f"/NEOAPRSDATA={data}"):
            if flag.lower() not in command.lower():
                raise Failure(f"the installer of the update was not run with {flag}: {command.strip()!r}")
        if "Installation process succeeded" not in text:
            raise Failure(f"the installer's log does not say 'Installation process succeeded' ({log})")
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

    def __init__(self, work: Path, old: Path, new: Path, extract_and_run: bool) -> None:
        super().__init__(work, old, new)
        self.extract_and_run = extract_and_run
        self.folder = work / "Applications"
        self.file = self.folder / old.name                        # (it keeps its name after the update: the user's file is replaced where it is)
        self.home = work / "home"
        self.pid = 0

    def env(self, env: dict[str, str]) -> dict[str, str]:
        tmp = self.work / "tmp"
        tmp.mkdir(exist_ok=True)
        env.update(HOME=str(self.home), XDG_DATA_HOME=str(self.home / ".local" / "share"), XDG_CONFIG_HOME=str(self.home / ".config"), XDG_CACHE_HOME=str(self.home / ".cache"), TMPDIR=str(tmp))
        for name in ("APPIMAGE", "APPDIR", "ARGV0", "OWD", "APPIMAGE_EXTRACT_AND_RUN"):
            env.pop(name, None)
        return env

    def put_old(self) -> None:
        if not self.extract_and_run and (not Path("/dev/fuse").exists() or not (shutil.which("fusermount") or shutil.which("fusermount3"))):
            raise Failure("no FUSE here (/dev/fuse and fusermount): install it, or give --extract-and-run")
        self.folder.mkdir(parents=True)
        self.home.mkdir(parents=True)
        shutil.copy2(self.old, self.file)
        os.chmod(self.file, 0o755)

    def command(self) -> list[str]:
        return [str(self.file), "--appimage-extract-and-run"] if self.extract_and_run else [str(self.file)]

    def start(self, data: Path, env: dict[str, str]) -> subprocess.Popen[bytes]:
        daemon = subprocess.Popen([*self.command(), "run", "--data", str(data)], stdin=subprocess.DEVNULL, stdout=self.out("daemon.out"), stderr=subprocess.STDOUT, env=self.env(env))
        self.pid = daemon.pid
        return daemon

    def check_hello(self, hello: dict[str, Any]) -> None:
        if hello["install"]["kind"] != "appimage" or hello["install"]["appimage"] != str(self.file):
            raise Failure(f"the daemon says it is {hello['install']}, not the AppImage {self.file}")

    def outside(self) -> dict[str, Any]:
        return {"the home folder": sorted(str(p.relative_to(self.home)) for p in self.home.rglob("*")),
                "the folder of the AppImage": sorted(p.name for p in self.folder.iterdir())}

    def old_ended(self, daemon: subprocess.Popen[bytes], data: Path) -> None:
        wait_until(lambda: "NeoAPRS ended" in read_log(data) or daemon.poll() is not None, 120, "the old daemon's end in the log")
        if daemon.poll() is not None:
            raise Failure(f"the process ended with exit code {daemon.returncode} instead of starting the new version (daemon.out)")
        say("the old daemon ended and the process went on")

    def check_new(self, daemon: subprocess.Popen[bytes], data: Path, new_version: str) -> None:
        if daemon.poll() is not None or daemon.pid != self.pid:
            raise Failure("the new version does not run in the process the old one ran in")
        if sha256(self.file) != sha256(self.new):
            raise Failure(f"{self.file} is not the new AppImage")
        mode = self.file.stat().st_mode
        if not mode & stat.S_IXUSR:
            raise Failure(f"{self.file} is not executable after the update: {stat.filemode(mode)}")
        wait_until(lambda: not (self.folder / (self.file.name + ".old")).exists(), 60, "the old AppImage kept as .old deleted once the new one runs")
        if (left := sorted(p.name for p in self.folder.iterdir())) != [self.file.name]:
            raise Failure(f"the folder of the AppImage holds {left}, not the AppImage alone")
        say(f"{self.file.name} is now the AppImage of {new_version} ({stat.filemode(mode)}), the .old is gone, and the same process {daemon.pid} runs it")

    def stop(self, daemon: subprocess.Popen[bytes], data: Path) -> None:
        (data / "neoaprs.stop").write_text("stop\n", encoding="ascii")          # (neoaprs/stopfile.py: what `neoaprs stop` writes; a second run of the file would unpack it again beside the daemon's)
        try:
            code = daemon.wait(60)
        except subprocess.TimeoutExpired:
            raise Failure("the new daemon did not end within 60 s of the stop") from None
        if code != 0:
            raise Failure(f"the process ended with exit code {code}, not 0")
        version = self.run("--version").stdout.strip()
        if version != f"NeoAPRS {version_of('appimage', self.new)}":
            raise Failure(f"{self.file.name} --version says {version!r}")


def daemon_env(release: Release) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in ("NEOAPRS_DATA_DIR", "NEOAPRS_DEBUG", "NEOAPRS_INSTALL_KIND")}
    env.update(NEOAPRS_UPDATE_TEST="1", NEOAPRS_UPDATE_FROM=release.url, NEOAPRS_UPDATE_CHECK="0", NEOAPRS_SERIAL_PATTERN="/dev/neoaprs-update-e2e-no-such-port*")
    return env


async def update(install: Install, data: Path, web_port: int, old_version: str, new_version: str, release: Release, daemon: subprocess.Popen[bytes]) -> int:
    """The old daemon's page up, the update check, update_now and its steps until the daemon lets go of the socket; the number of packets it had."""
    page = await Page.of_version(web_port, old_version, PAGE_SEC)
    install.check_hello(page.hello)
    say(f"the daemon of {old_version} is up: {page.hello['install']}")
    await page.until(lambda p: connected(p) and bool((p.topics.get("update") or {}).get("supported")), PAGE_SEC, "the fake TNC connected, a packet, and Update now offered")
    packets = int(page.status["packets"])
    say(f"the fake TNC is connected, {packets} packets, Update now is offered")
    page.send({"cmd": "update_check"})
    await page.until(lambda p: any(m.get("type") == "update_result" for m in p.messages), 60, "the answer to update_check")
    result = next(m for m in page.messages if m.get("type") == "update_result")
    if (result["outcome"], result["version"]) != ("newer", new_version):
        raise Failure(f"the update check said {result}, not newer {new_version}")
    await page.until(lambda p: (p.status.get("update") or {}).get("version") == new_version, 30, "the status naming the new version")
    say(f"the update check found {new_version}")
    states: list[str] = []

    def follow(p: Page) -> None:
        state = (p.topics.get("update") or {}).get("state")
        if state and (not states or states[-1] != state):
            states.append(state)
            say(f"update: {state} {(p.topics.get('update') or {}).get('percent')}%" if state == "downloading" else f"update: {state}")
        if state == "error":
            raise Failure(f"Update now failed: {p.topics['update']['problem']}: {p.topics['update']['detail']}")
        if p.errors():
            raise Failure(f"the daemon refused: {p.errors()[0]}")
    page.send({"cmd": "update_now", "version": new_version})
    try:
        await page.until(lambda p: p.closed, UPDATE_SEC, "the update and the old daemon's end", follow)
    finally:
        page.close()
    if "restarting" not in states:
        raise Failure(f"the update went {states}, never to restarting")
    asked = [r for r in release.requests if r.startswith(f"/v{new_version}/")]
    if asked != [f"/v{new_version}/SHA256SUMS", f"/v{new_version}/{install.new.name}"]:
        raise Failure(f"the release server was asked for {asked}, not SHA256SUMS and then {install.new.name}")
    say(f"the update went {' -> '.join(states)}; SHA256SUMS and {install.new.name} were fetched from the fake release")
    install.old_ended(daemon, data)
    return packets


async def after(install: Install, data: Path, web_port: int, new_version: str, packets: int, daemon: subprocess.Popen[bytes]) -> None:
    page = await Page.of_version(web_port, new_version, NEW_DAEMON_SEC)
    try:
        install.check_hello(page.hello)
        say(f"a daemon of {new_version} is up on the same page port")
        await page.until(connected, PAGE_SEC, "the new daemon connected to the fake TNC of the settings")
        if int(page.status["packets"]) < packets:
            raise Failure(f"the new daemon has {page.status['packets']} packets, fewer than the {packets} of the old one")
        say(f"the new daemon is connected to the fake TNC and has {page.status['packets']} packets")
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
    data = work / "data folder"                              # (a blank in the path, as a user's may have)
    install: Install = WindowsInstall(work, old, new) if args.kind == "windows" else AppImageInstall(work, old, new, args.extract_and_run)
    tnc = FakeTnc(FIXTURE.read_bytes())
    release = Release(new_version, new)
    daemon: subprocess.Popen[bytes] | None = None
    try:
        say(f"{args.kind}: {old.name} -> {new.name}")
        install.put_old()
        say(f"the old version is in place: {' '.join(install.command())}")
        web_port = free_port()
        settings = {"serial/port": tnc.url, "web/port": str(web_port), "update/url": f"{release.url}/version.php", "station/comment": "update e2e", "map/radius_km": "42"}
        for key, value in settings.items():
            done = install.run("db", "--data", str(data), "set", key, value)
            if done.returncode != 0:
                raise Failure(f"db set {key}: {done.stdout.strip()} {done.stderr.strip()}")
        before = install.outside()
        daemon = install.start(data, daemon_env(release))
        packets = asyncio.run(update(install, data, web_port, old_version, new_version, release, daemon))
        asyncio.run(after(install, data, web_port, new_version, packets, daemon))
        install.stop(daemon, data)
        wait_until(lambda: read_log(data).rstrip().endswith("NeoAPRS ended"), 60, "'NeoAPRS ended' as the last line of the log after the stop")
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
        say(f"the settings are still there: {', '.join(settings)}")
        if (later := install.outside()) != before:
            changed = [name for name in before if before[name] != later.get(name)]
            raise Failure(f"the update changed {', '.join(changed)}: {[(before[n], later.get(n)) for n in changed]}")
        say(f"nothing else changed: {', '.join(before)}")
        try:
            wait_until(lambda: not install.leftovers(), 60, "no program of NeoAPRS left running after the stop")
        except Failure:
            raise Failure(f"still running after the stop: {install.leftovers()}") from None
    except Failure as e:
        print(f"update-e2e: FAILED: {e}\n--- the end of the log ---\n{read_log(data)[-6000:]}\n--- the fake release was asked for ---\n{release.requests}", file=sys.stderr)
        raise
    finally:
        if daemon is not None and daemon.poll() is None:
            if data.is_dir():
                (data / "neoaprs.stop").write_text("stop\n", encoding="ascii")
            try:
                daemon.wait(30)
            except subprocess.TimeoutExpired:
                daemon.kill()
        tnc.close()
        release.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="The end-to-end test of Update now with the real files of a release (on a CI runner only: it installs and replaces files).")
    parser.add_argument("kind", choices=("windows", "appimage"))
    parser.add_argument("old", help="the installer or the AppImage of the version that is updated")
    parser.add_argument("new", help="the one of the newer version, which the fake release serves")
    parser.add_argument("--work", default="update-e2e", help="an empty folder for the data folder, the AppImage, the home and the logs; default %(default)s")
    parser.add_argument("--extract-and-run", action="store_true", help="AppImage: start it with --appimage-extract-and-run, as a system without FUSE does")
    args = parser.parse_args()
    if args.kind == "windows" and not WINDOWS:
        parser.error("windows runs on Windows only")
    try:
        run(args)
    except Failure:
        return 1
    say("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
