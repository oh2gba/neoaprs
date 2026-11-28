"""The families of flaky tests that can be told from the source, refused (tests/README.md, "Waiting",
and docs/flakes.md): a fixed port, a sleep in a test's body, a thread found dead without a generous
join, and a wait for something expected that gives up within seconds.

An exception is an entry of ALLOWED with its reason; an entry that no longer matches fails too.
"""

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from tests.conftest import ROOT
from tests.support.patience import PATIENCE_SEC

# The least a test may wait for what it expects (a negative check, that something does not happen,
# may wait less: a stall cannot make it fail)
FLOOR_SEC = 10.0
PORTS = range(1024, 65536)
# The calls that bind, listen or connect, whose literal port is the machine's to give or take
SOCKET_CALLS = frozenset(
    {
        "bind",
        "connect",
        "connect_ex",
        "create_connection",
        "create_server",
        "start_server",
        "open_connection",
        "HTTPServer",
        "ThreadingHTTPServer",
        "TCPServer",
        "ThreadingTCPServer",
        "UDPServer",
        "listen",
        "serve",
    }
)
# Where a block of ports is laid out on purpose, with a check that each is free
PORT_HELPERS = frozenset({"tests/support/webports.py", "tests/support/modemports.py"})
UNTIL = frozenset({"until", "until_async", "until_started", "until_connected", "until_sent"})
TIMEOUT_EXCEPTIONS = ("TimeoutError", "TimeoutExpired", "Empty")

# (file, function, rule): why the pattern is right there
ALLOWED: dict[tuple[str, str, str], str] = {
    (
        "tests/test_aisfeed.py",
        "test_under_the_no_devices_switch_a_receiver_that_is_not_this_computer_is_refused_as_a_server_that_is_not_there",
        "port",
    ): "the switch refuses the connection before any socket is made",
    (
        "tests/test_aisfeed.py",
        "test_under_the_no_devices_switch_a_port_a_real_modem_may_listen_on_is_refused_even_on_this_computer",
        "port",
    ): "the switch refuses a real modem's port before any socket is made",
    (
        "tests/test_guards.py",
        "test_a_connect_of_the_windows_loop_which_goes_past_socket_connect_is_refused_too",
        "port",
    ): "the guard refuses the connection before it reaches the network",
    (
        "tests/test_desktop_logic.py",
        "test_a_watch_that_is_given_nothing_to_follow_runs_only_for_a_daemon_the_app_owns",
        "alive",
    ): "the watch's thread is never started, so it cannot be alive at any moment",
    (
        "tests/test_direwolf_real.py",
        "test_closing_its_input_ends_it_cleanly_and_it_listens_on_this_computer_only",
        "sleep",
    ): "polls the kernel's table of sockets until Direwolf listens, with a deadline of 30 s",
    (
        "tests/test_dummy_hf.py",
        "test_the_speakers_audio_paces_silence_into_mercurys_capture_pipe_and_hands_what_mercury_plays_to_the_player",
        "sleep",
    ): "reads the pipes between polls until the blocks have come, with a deadline",
    (
        "tests/test_dummy_hf.py",
        "test_the_speakers_audio_says_once_when_there_is_no_player_and_plays_nothing",
        "sleep",
    ): "reads the pipes between polls until the blocks have come, with a deadline",
    (
        "tests/test_hfchannel.py",
        "test_the_thread_keeps_the_pace_of_the_clock_and_delivers",
        "sleep",
    ): "drains the pipes between polls until fifteen blocks have come, with a deadline",
    (
        "tests/test_main.py",
        "test_a_second_daemon_on_the_same_data_folder_refuses_to_start_and_the_first_is_not_disturbed",
        "sleep",
    ): "polls the log while the daemon must stay up, with a deadline of 30 s",
    (
        "tests/test_mercury_loopback.py",
        "test_the_shipped_mercury_listens_on_the_loopback_only",
        "sleep",
    ): "polls the kernel's table of sockets until Mercury listens, with a deadline of 30 s",
    (
        "tests/test_migration_waits.py",
        "test_a_start_while_another_neoaprs_migrates_the_file_waits_for_it_says_so_once_and_comes_up_at_the_newest_version",
        "sleep",
    ): "a window past the busy time in which the start must still wait: a stall only lengthens it",
    (
        "tests/test_migration_waits.py",
        "test_a_migration_that_stops_showing_it_is_at_it_while_waited_for_is_refused_after_the_busy_time",
        "sleep",
    ): "a window past the busy time in which the start must still wait: a stall only lengthens it",
    (
        "tests/test_package.py",
        "test_the_installed_package_finds_its_page_and_unit_template_and_its_daemon_serves_the_page",
        "sleep",
    ): "polls for the page's address file while the daemon runs, with a deadline of 60 s",
    (
        "tests/test_scripts.py",
        "test_the_replay_on_a_pseudo_terminal_ends_on_ctrl_c_and_says_what_it_does",
        "sleep",
    ): "a window in which nothing may be sent before a port opens: a stall only lengthens it",
    (
        "tests/test_skeds_php.py",
        "test_a_refresh_writes_the_board_only_when_what_it_says_has_changed",
        "sleep",
    ): "the next second of the file's time stamp, which a write would change",
    ("tests/test_mercury_leadin.py", "<module>", "port"): "the base from which free pairs of ports are probed",
    ("tests/test_mercury_scope_real.py", "<module>", "port"): "the base from which free pairs of ports are probed",
}


@dataclass(frozen=True)
class Found:
    file: str
    function: str
    rule: str
    line: int
    text: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line} ({self.function}) {self.rule}: {self.text}"


def number(node: ast.AST | None) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    return None


def name_of(call: ast.Call) -> str:
    return call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, "id", "")


def timeout_of(call: ast.Call) -> float | None:
    for keyword in call.keywords:
        if keyword.arg in ("timeout", "timeout_sec", "seconds"):
            return number(keyword.value)
    name = name_of(call)
    if name in ("join", "wait", "spin") and call.args:
        return number(call.args[0])
    if (name == "wait_for" or name in UNTIL) and len(call.args) >= 2:
        return number(call.args[1])
    return None


def constants_of(tree: ast.Module) -> dict[str, float]:
    """The module's names bound once to a number."""
    found: dict[str, float] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            value = number(node.value)
            if value is not None:
                found[node.targets[0].id] = value
    return found


class Reader(ast.NodeVisitor):
    """Walks one file, keeping the function it is in and whether it is in a negative check."""

    def __init__(self, file: str, tree: ast.Module) -> None:
        self.file, self.constants = file, constants_of(tree)
        self.function = "<module>"
        self.in_test_body = False
        self.negative = 0
        self.found: list[Found] = []

    def add(self, rule: str, node: ast.AST) -> None:
        self.found.append(Found(self.file, self.function, rule, getattr(node, "lineno", 0), ast.unparse(node)[:120]))

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        outer = (self.function, self.in_test_body)
        top = self.function == "<module>" or self.function[0].isupper()
        if top:
            self.function = node.name
        self.in_test_body = top and node.name.startswith("test")
        self.check_blocks(node)
        self.generic_visit(node)
        self.function, self.in_test_body = outer

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        outer = self.function
        self.function = node.name
        self.generic_visit(node)
        self.function = outer

    def visit_Lambda(self, node: ast.Lambda) -> None:
        outer = self.in_test_body
        self.in_test_body = False
        self.generic_visit(node)
        self.in_test_body = outer

    def negated(self, node: ast.AST, holds: bool) -> None:
        self.negative += holds
        self.generic_visit(node)
        self.negative -= holds

    def visit_With(self, node: ast.With | ast.AsyncWith) -> None:
        self.negated(node, any("raises" in ast.unparse(item.context_expr) for item in node.items))

    visit_AsyncWith = visit_With  # type: ignore[assignment]

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        self.negated(node, isinstance(node.op, ast.Not))

    def visit_Try(self, node: ast.Try) -> None:
        catches = any(
            h.type is not None and any(t in ast.unparse(h.type) for t in TIMEOUT_EXCEPTIONS) for h in node.handlers
        )
        self.negative += catches
        for statement in node.body:
            self.visit(statement)
        self.negative -= catches
        for part in (*node.handlers, *node.orelse, *node.finalbody):
            self.visit(part)

    def visit_Assert(self, node: ast.Assert) -> None:
        for call in (sub for sub in ast.walk(node.test) if isinstance(sub, ast.Call)):
            if name_of(call) in ("wait", "join") and not self.under_not(node.test, call):
                seconds = timeout_of(call)
                if seconds is not None and seconds < FLOOR_SEC:
                    self.add("short wait", node)
        self.generic_visit(node)

    @staticmethod
    def under_not(test: ast.AST, call: ast.Call) -> bool:
        return any(
            isinstance(sub, ast.UnaryOp) and isinstance(sub.op, ast.Not) and call in ast.walk(sub.operand)
            for sub in ast.walk(test)
        )

    def visit_Call(self, node: ast.Call) -> None:
        name = name_of(node)
        if self.in_test_body and ast.unparse(node.func) == "time.sleep":
            self.add("sleep", node)
        if (name in UNTIL or name == "wait_for") and not self.negative:
            seconds = timeout_of(node)
            if seconds is not None and seconds < FLOOR_SEC:
                self.add("short wait", node)
        if name in SOCKET_CALLS and self.file not in PORT_HELPERS and self.literal_port(node):
            self.add("port", node)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """A port's name given a number of its own: a port a program of the test is started on."""
        for target in node.targets:
            pairs = (
                zip(target.elts, node.value.elts)
                if isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple)
                else [(target, node.value)]
            )
            for name, value in pairs:
                seconds = number(value)
                if "port" in ast.unparse(name).lower() and seconds is not None and int(seconds) in PORTS:
                    if self.file not in PORT_HELPERS:
                        self.add("port", node)
        self.generic_visit(node)

    def literal_port(self, call: ast.Call) -> bool:
        for arg in [*call.args, *(k.value for k in call.keywords if k.arg in ("port", "address", None))]:
            for part in arg.elts if isinstance(arg, ast.Tuple) else [arg]:
                value = number(part) if not isinstance(part, ast.Name) else self.constants.get(part.id)
                if value is not None and int(value) in PORTS and value == int(value):
                    return True
        return False

    def check_blocks(self, function: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """A thread asserted dead needs a join without a timeout, or a generous one, just before; a
        short join right before an assertion on what it joined is a short wait."""
        for block in blocks_of(function):
            for i, statement in enumerate(block):
                if isinstance(statement, ast.Assert):
                    for joined in dead_threads(statement.test):
                        if not any(generous_join(earlier, joined) for earlier in block[max(0, i - 3) : i]):
                            self.add("alive", statement)
                if i + 1 < len(block) and isinstance(block[i + 1], ast.Assert):
                    for call in short_joins(statement):
                        if ast.unparse(call.func.value) in ast.unparse(block[i + 1].test):  # type: ignore[attr-defined]
                            self.add("short wait", statement)


def blocks_of(function: ast.AST) -> Iterator[list[ast.stmt]]:
    for node in ast.walk(function):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if isinstance(block, list) and block and isinstance(block[0], ast.stmt):
                yield block
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                yield handler.body


def dead_threads(test: ast.AST) -> list[str]:
    return [
        ast.unparse(sub.operand.func.value)
        for sub in ast.walk(test)
        if isinstance(sub, ast.UnaryOp)
        and isinstance(sub.op, ast.Not)
        and isinstance(sub.operand, ast.Call)
        and isinstance(sub.operand.func, ast.Attribute)
        and sub.operand.func.attr == "is_alive"
    ]


def generous_join(statement: ast.stmt, joined: str) -> bool:
    for sub in ast.walk(statement):
        if isinstance(sub, ast.Call) and name_of(sub) == "join" and isinstance(sub.func, ast.Attribute):
            if ast.unparse(sub.func.value) == joined:
                seconds = timeout_of(sub)
                if seconds is None or seconds >= FLOOR_SEC:
                    return True
    return False


def short_joins(statement: ast.stmt) -> list[ast.Call]:
    if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
        return []
    call = statement.value
    seconds = timeout_of(call)
    if name_of(call) in ("join", "wait") and isinstance(call.func, ast.Attribute) and seconds is not None:
        return [call] if seconds < FLOOR_SEC else []
    return []


def sources() -> Iterator[Path]:
    yield from sorted((ROOT / "tests").glob("test_*.py"))
    yield from sorted((ROOT / "tests" / "support").glob("*.py"))


def found_in_the_suite() -> list[Found]:
    found: list[Found] = []
    for path in sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        reader = Reader(path.relative_to(ROOT).as_posix(), tree)
        reader.visit(tree)
        found += reader.found
    return found


def test_no_test_has_a_fixed_port_a_sleep_in_its_body_a_thread_found_dead_at_a_moment_or_a_short_wait() -> None:
    found = found_in_the_suite()
    refused = [str(f) for f in found if (f.file, f.function, f.rule) not in ALLOWED]
    assert not refused, (
        "patterns of flaky tests (docs/flakes.md): wait for the thing itself with until(...) and the suite's "
        f"patience ({PATIENCE_SEC:g} s), take a port the system gives, or add an entry with its reason to "
        "ALLOWED:\n" + "\n".join(refused)
    )
    used = {(f.file, f.function, f.rule) for f in found}
    assert not [key for key in ALLOWED if key not in used], "an entry of ALLOWED that matches nothing any more"


def test_every_exception_says_why() -> None:
    assert all(len(reason.split()) >= 4 for reason in ALLOWED.values())


def lint(source: str) -> list[str]:
    tree = ast.parse(source)
    reader = Reader("tests/test_x.py", tree)
    reader.visit(tree)
    return sorted(f"{f.function} {f.rule}" for f in reader.found)


def test_the_rules_find_each_pattern_and_leave_its_right_forms_alone() -> None:
    assert lint(
        """
import socket, threading, time, asyncio
PORT = 8001
def test_a():
    socket.socket().bind(("127.0.0.1", 21500))
    socket.create_connection(("127.0.0.1", PORT))
    time.sleep(0.5)
    t = threading.Thread(target=print)
    t.start()
    t.join(1)
    assert not t.is_alive()
    assert done.wait(2)
async def test_b():
    await until(lambda: True, 5.0)
    await asyncio.wait_for(x, 3)
    assert not t.is_alive()
"""
    ) == [
        "<module> port",
        "test_a alive",
        "test_a port",
        "test_a port",
        "test_a short wait",
        "test_a short wait",
        "test_a sleep",
        "test_b alive",
        "test_b short wait",
        "test_b short wait",
    ]
    assert (
        lint(
            """
import socket, threading, time, asyncio
def helper():
    time.sleep(0.01)
def test_c():
    socket.socket().bind(("127.0.0.1", 0))
    t.join()
    assert not t.is_alive()
    t.join(30)
    assert not t.is_alive()
    assert not gone.wait(0.2)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(asyncio.wait_for(x, 0.1))
    run([sys.executable, "-c", "import time; time.sleep(1)"])
    poll(lambda: time.sleep(0.01))
async def test_d():
    await until(lambda: True)
    try:
        await asyncio.wait_for(x, 0.5)
    except TimeoutError:
        pass
"""
        )
        == []
    )
