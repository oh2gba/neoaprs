"""The layers of NeoAPRS and who may import whom, checked on the imports of every file of neoaprs/, neoaprs/web/ included (docs/ARCHITECTURE.md).

    foundation   clock signal kiss ax25 packet ...          pure: no I/O library, imports foundation only
    domain       config stationbook                         pure: no I/O library, imports foundation and domain
    adapters     source tasks serialport tnc                the world outside: the serial line, the TNC; imports foundation and domain
    persistence  store migrations db packetlog ...          the database file, on the database thread; imports foundation and domain
    services     neoaprs/services/ (the beacon)              stateful parts that use the layers below; built by neoaprs/app.py only; never the controller, never web
    app          controller app wiring                      the composition root (app builds, wiring connects, controller is the object of the parts)
    delivery     neoaprs/web/*, neoaprs/cli/*, neoaprs/desktop/*, neoaprs/daemon, neoaprs/__main__    the page, the commands, the desktop app and the process; only this layer may import neoaprs.web

Every violation that exists today is in ALLOWED with the reason it is there. The list can only shrink: a violation that is not in it fails the test, and so does an entry that is no
longer a violation (delete the line). A new module of neoaprs/ must be given its layer in LAYERS first. The checks are functions of a *tree* (path -> source), so the second half of
this file shows each rule failing on a made-up tree: a rule that has never been seen failing is a guess.
"""
import sys

import pytest

from tests.support.codemap import Import, Tree, connect_sites, find_cycle, forbidden_names, import_graph, load_tree, module_name, sql_sites, sql_strings

LAYERS: dict[str, list[str]] = {
    "foundation": ["neoaprs", "clock", "signal", "coded", "policy", "units", "recent", "callsign", "geo", "symbols", "kiss", "ax25", "aprsposition", "aprsmice", "aprsmiceout", "aprsmessage", "aprsparse", "aprsweather", "aprsthirdparty", "aprsisline", "aprsextension", "aprsfreq", "aprsstorm", "aprslocator", "aprstelemetry", "aprsnmea", "gpsfix", "smartbeacon", "packet", "packetcodec", "message", "bulletin", "decay", "tncmode", "tncprofile", "pref", "route", "reach", "chain", "mapstate", "radiosearch", "serialboards", "versions", "updateasset", "releasenotes", "device", "devicedata", "hourcount", "dummyroutes", "dummyframes", "dummyscene", "dummyqru", "igaterules"],
    "domain": ["alertcommand", "config", "configlegacy", "configstatus", "configtypes", "configvalues", "interlock", "station", "stationnotes", "stationbook", "aloha", "ownobject", "ownbulletin", "qrutext"],
    "adapters": ["source", "tasks", "serialport", "serialholders", "serialprobe", "btsdp", "btserial", "btle", "btpaired", "tnc", "tncport", "callbackport", "dummyline", "tncsearch", "tncwatchdog", "tncentry", "tncfollow", "tnclines", "tncreader", "childenv", "rigctld", "gpsfeed", "aprsis", "pmtilestool", "worldmap", "updatefetch", "updatedownload", "selfreplace"],
    "persistence": ["store", "migrations", "migrationlog", "migrationsteps1to11", "migrationsteps12to21", "migrationsteps22on", "backupfolder", "durable", "instancelock", "stopfile", "walcare", "dbfile", "dberror", "dbstats", "dbthread", "db", "dbopen", "storesql", "paths", "dblog", "packetsql", "packetlog", "messagesql", "messagelog", "bulletinsql", "bulletinlog", "weathersql", "weatherlog", "ownsql", "ownlog", "supportsql"],
    "services": [],
    "app": ["controller", "app", "wiring"],
    "delivery": ["__main__", "daemon"],
}
MAY_IMPORT: dict[str, set[str]] = {
    "foundation": {"foundation"},
    "domain": {"foundation", "domain"},
    "adapters": {"foundation", "domain", "adapters"},
    "persistence": {"foundation", "domain", "persistence"},
    "services": {"foundation", "domain", "adapters", "persistence", "services"},
    "app": {"foundation", "domain", "adapters", "persistence", "services", "app"},
    "delivery": {"foundation", "domain", "adapters", "persistence", "services", "app", "delivery"},
}
# Inside the adapters layer a feed may use the base every feed shares, and the few siblings named here; any other adapter-to-adapter import is a violation.
ADAPTER_BASES = {"neoaprs.source", "neoaprs.tasks"}
ADAPTER_SIBLINGS: set[tuple[str, str]] = {("neoaprs.tnc", "neoaprs.serialport"), ("neoaprs.tnc", "neoaprs.serialprobe"), ("neoaprs.tnc", "neoaprs.serialholders"), ("neoaprs.tnc", "neoaprs.tncsearch"), ("neoaprs.tnc", "neoaprs.tncwatchdog"), ("neoaprs.tnc", "neoaprs.tncentry"), ("neoaprs.tnc", "neoaprs.tncreader"), ("neoaprs.tncreader", "neoaprs.tncentry"), ("neoaprs.tncreader", "neoaprs.tncport"), ("neoaprs.tncreader", "neoaprs.tncwatchdog"), ("neoaprs.tnc", "neoaprs.tncfollow"), ("neoaprs.tncfollow", "neoaprs.serialprobe"), ("neoaprs.tncfollow", "neoaprs.serialport"), ("neoaprs.tnc", "neoaprs.tnclines"), ("neoaprs.tnc", "neoaprs.tncport"), ("neoaprs.tnc", "neoaprs.dummyline"), ("neoaprs.tncport", "neoaprs.callbackport"), ("neoaprs.gpsfeed", "neoaprs.callbackport"), ("neoaprs.callbackport", "neoaprs.serialport"), ("neoaprs.dummyline", "neoaprs.tncport"), ("neoaprs.dummyline", "neoaprs.serialport"), ("neoaprs.tncsearch", "neoaprs.serialport"), ("neoaprs.tncsearch", "neoaprs.serialprobe"), ("neoaprs.serialprobe", "neoaprs.serialport"), ("neoaprs.serialprobe", "neoaprs.serialholders"), ("neoaprs.serialholders", "neoaprs.serialport"), ("neoaprs.gpsfeed", "neoaprs.serialport"), ("neoaprs.serialport", "neoaprs.btserial"), ("neoaprs.serialport", "neoaprs.btle"), ("neoaprs.btserial", "neoaprs.btsdp"), ("neoaprs.serialprobe", "neoaprs.btpaired"), ("neoaprs.worldmap", "neoaprs.pmtilestool")}      # (importer, imported): the TNC reads the serial line, and its search and watchdog are parts of it
DELIVERY_PACKAGES = ("neoaprs.web", "neoaprs.cli", "neoaprs.desktop")
WIRE_ASSEMBLERS = {"neoaprs.web.protocol"}
PURE = {"foundation", "domain"}
# pyserial ("serial") counts as an I/O library beside the terminal modules it stands on: the protocol modules never see a descriptor.
IO_LIBRARIES = {"asyncio", "sqlite3", "socket", "subprocess", "tornado", "serial", "bleak", "termios", "pty", "fcntl", "os", "shutil", "tempfile", "ssl", "select", "selectors", "urllib.request", "http.client", "http.server"}
# The desktop app's toolkits (the extra `app` of pyproject.toml) are imported by the shells and by nothing else: everything else of neoaprs/desktop/ runs without them (and is tested without them).
TOOLKITS = {"PySide6", "shiboken6", "webview", "pystray", "PIL"}
TOOLKIT_HOMES: set[str] = {"neoaprs.desktop.qtshell", "neoaprs.desktop.qtwindow", "neoaprs.desktop.winshell"}
BLEAK_HOMES: set[str] = {"neoaprs.btle"}                        # bleak (the extra `ble` of pyproject.toml) only in the BLE port, which imports it when a ble:// port is opened
TORNADO_HOMES: set[str] = set()                                # Tornado only in neoaprs/web/ (CONVENTIONS.md)
PYDANTIC_HOMES: set[str] = {"neoaprs.web.wirebase", "neoaprs.web.hostwire", "neoaprs.web.hubwire", "neoaprs.web.stationwire", "neoaprs.web.packetwire", "neoaprs.web.tncwire", "neoaprs.web.configwire", "neoaprs.web.beaconwire", "neoaprs.web.igatewire", "neoaprs.web.qruwire", "neoaprs.web.messagewire", "neoaprs.web.bulletinwire", "neoaprs.web.prefwire", "neoaprs.web.weatherwire", "neoaprs.web.historywire", "neoaprs.web.portwire", "neoaprs.web.mapwire", "neoaprs.web.ownwire", "neoaprs.web.updatewire", "neoaprs.web.gpswire", "neoaprs.web.supportwire", "neoaprs.web.protocol", "neoaprs.web.dispatch", "neoaprs.web.outbound"}      # the core knows nothing of the wire format; these check or describe what comes in and what goes out

# Today's violations: (importer, imported) -> why it is there and what removes it. Only ever shrinks.
ALLOWED: dict[tuple[str, str], str] = {}

# Signal.connect is wiring and wiring is in one place: the composition root and the page's API. A file that is neither is listed with how many connects it still has.
COMPOSITION_ROOTS: set[str] = {"neoaprs/wiring.py", "neoaprs/web/topics.py", "neoaprs/cli/capturecmd.py", "neoaprs/desktop/qtshell.py", "neoaprs/desktop/qtwindow.py"}            # neoaprs/web/topics.py connects the daemon's signals to the page's hub; the capture command makes one serial port and wires it to a file; the Qt shell connects Qt's own signals (of its tray, its menu and its timers: not neoaprs.signal)
SERVICE_BUILDERS = {"neoaprs.app", "neoaprs.cli.mapcmd"}            # the root builds the services; the map command is the command line of the base map's service (the page's Download button, as a command)
CONNECTS: dict[str, tuple[int, str]] = {}


# SQL is written in one place: every statement of the daemon is a function of a connection that the database thread (neoaprs/db.py) runs. A file of neoaprs/ or neoaprs/web/ that
# imports sqlite3 or calls `.execute(` is listed here, and nothing else may.
SQL_HOMES: dict[str, str] = {              # the permanent homes of SQL: no count, the code that is SQL is meant to be here
    "neoaprs/db.py": "the database actor: the one connection, the one thread",
    "neoaprs/dbthread.py": "the thread of the actor: BEGIN, COMMIT, SAVEPOINT and the settings of its connection",
    "neoaprs/dberror.py": "the names of SQLite's connection and errors, taken from here by every class that uses the thread, so that none of them imports sqlite3",
    "neoaprs/dbfile.py": "how a connection is set up (WAL, synchronous=FULL, the busy time) and the whole checked copy",
    "neoaprs/storesql.py": "the statements of the settings: functions of a connection that the thread runs",
    "neoaprs/packetsql.py": "the statements of the packet log and the station cache: functions of a connection that the thread runs",
    "neoaprs/messagesql.py": "the statements of the message table: functions of a connection that the thread runs",
    "neoaprs/bulletinsql.py": "the statements of the bulletin table (the message board): functions of a connection that the thread runs",
    "neoaprs/ownsql.py": "the statements of the tables of our own objects and bulletins (what we send of our own accord): functions of a connection that the thread runs",
    "neoaprs/weathersql.py": "the statements of the weather table (every observation of every weather station) and the read of the packets it is made from: functions of a connection that the thread runs",
    "neoaprs/supportsql.py": "the statements of the support bundle: functions of a read-only connection that the bundle's own thread runs (the file's version and sizes, the rows of each table, the latest packets)",
    "neoaprs/walcare.py": "the limits of the write-ahead log (journal_size_limit and the automatic checkpoint): a function of the connection, run by the thread",
    "neoaprs/migrationsteps12to21.py": "the migrations 12 to 21, frozen beside migrations.py: migration code",
    "neoaprs/migrationsteps22on.py": "the migrations from 22 on, frozen beside migrations.py: migration code",
    "neoaprs/migrationsteps1to11.py": "the migrations 1 to 11, frozen beside migrations.py: migration code",
    "neoaprs/migrations.py": "the opening of the file, before the thread opens it, and in the tools, and the runner of the migrations (their history, the copy taken before them)",
}
# Everything else that still imports sqlite3 or calls execute, with how many calls: (imports sqlite3, calls of execute, why). The numbers are exact: a file that does less than its entry says
# fails until the entry is lowered or deleted, so the list only shrinks. A new entry is not the way to get a change through: the statement belongs in a function of storesql.py or a module beside it.
SQL_ELSEWHERE: dict[str, tuple[bool, int, str]] = {}


def sql_outside_the_homes(sites: dict[str, tuple[bool, int]]) -> dict[str, str]:
    """Why each file that touches SQL outside SQL_HOMES is not allowed to, or is allowed to less than it does."""
    found: dict[str, str] = {}
    for rel, (imports, calls) in sorted(sites.items()):
        if rel in SQL_HOMES:
            continue
        allowed = SQL_ELSEWHERE.get(rel)
        if allowed is None:
            found[rel] = f"imports sqlite3: {imports}, calls execute: {calls}; it is not in SQL_HOMES or SQL_ELSEWHERE"
        elif (imports, calls) != (allowed[0], allowed[1]):
            found[rel] = f"does (imports sqlite3: {imports}, execute calls: {calls}) but its entry says ({allowed[0]}, {allowed[1]}): lower the entry (never raise it)"
    return found


def sql_text_outside_the_homes(strings: dict[str, list[int]]) -> dict[str, list[int]]:
    """The files that hold a string that begins like a statement and are neither a home of SQL nor one of the listed files that touch it: a statement built in one place and run in another passes
    the check on `execute(` and is found here."""
    return {rel: lines for rel, lines in sorted(strings.items()) if rel not in SQL_HOMES and rel not in SQL_ELSEWHERE}


def stale_sql_entries(sites: dict[str, tuple[bool, int]]) -> list[str]:
    """Entries of the two tables that name a file that no longer touches SQL (or does not exist)."""
    return sorted(rel for rel in [*SQL_HOMES, *SQL_ELSEWHERE] if rel not in sites)


def is_delivery_package(module: str) -> bool:
    """The packages that are the delivery layer whole: the page's server and the commands (everything under them is delivery, whatever its name)."""
    return any(module == package or module.startswith(package + ".") for package in DELIVERY_PACKAGES)


def is_web(module: str) -> bool:
    return module == "neoaprs.web" or module.startswith("neoaprs.web.")


def layer_of(module: str) -> str | None:
    if is_delivery_package(module):
        return "delivery"
    if module == "neoaprs.services" or module.startswith("neoaprs.services."):
        return "services"
    for layer, names in LAYERS.items():
        if module in {"neoaprs" if n == "neoaprs" else f"neoaprs.{n}" for n in names}:
            return layer
    return None


def violations(graph: dict[str, list[Import]]) -> dict[tuple[str, str], str]:
    """(importer, imported) -> the rule it breaks, for every import of the tree."""
    found: dict[tuple[str, str], str] = {}
    for importer, imports in graph.items():
        mine = layer_of(importer)
        for imp in imports:
            key = (importer, imp.top if imp.top in {"tornado", "pydantic"} else imp.target)
            if imp.internal and imp.target != importer:
                theirs = layer_of(imp.target)
                if mine is None or theirs is None:
                    continue                                # an unclassified module is reported by test_every_module_has_a_layer
                if theirs not in MAY_IMPORT[mine]:
                    found[key] = f"{mine} imports {theirs}"
                elif mine == theirs == "adapters" and imp.target not in ADAPTER_BASES and (importer, imp.target) not in ADAPTER_SIBLINGS:
                    found[key] = "an adapter imports a sibling adapter"
            elif not imp.internal:
                if mine in PURE and (imp.target in IO_LIBRARIES or imp.top in IO_LIBRARIES):
                    found[key] = f"{mine} (pure code) imports the I/O library {imp.target}"
                elif imp.top == "serial" and mine != "adapters":
                    found[key] = "pyserial outside the adapters layer"
                elif imp.top == "bleak" and importer not in BLEAK_HOMES:
                    found[key] = "bleak outside neoaprs/btle.py"
                elif imp.top == "tornado" and importer not in TORNADO_HOMES and not is_web(importer):
                    found[key] = "Tornado outside neoaprs/web/"
                elif imp.top == "pydantic" and importer not in PYDANTIC_HOMES:
                    found[key] = "pydantic outside the wire modules of neoaprs/web/"
                elif imp.top in TOOLKITS and importer not in TOOLKIT_HOMES:
                    found[key] = "a GUI toolkit outside the shells of neoaprs/desktop/"
    return found


def unplaced(tree: Tree) -> list[str]:
    return sorted(m for m in map(module_name, tree) if layer_of(m) is None)


def stale_layers(tree: Tree) -> list[str]:
    modules = {module_name(rel) for rel in tree}
    return sorted(f"neoaprs.{n}" for names in LAYERS.values() for n in names if n != "neoaprs" and f"neoaprs.{n}" not in modules)


def neoaprs_imports_of_web(graph: dict[str, list[Import]]) -> list[tuple[str, str]]:
    return sorted((m, i.target) for m, imps in graph.items() if layer_of(m) != "delivery" for i in imps if i.internal and is_web(i.target))


def service_imports_above(graph: dict[str, list[Import]]) -> list[tuple[str, str]]:
    """What neoaprs/services/ must never import: the controller, the admin tools, the process, the web layer."""
    return sorted((m, i.target) for m, imps in graph.items() if layer_of(m) == "services" for i in imps
                  if i.internal and (layer_of(i.target) in {"app", "delivery"}))


def services_imported_outside_the_root(graph: dict[str, list[Import]]) -> list[tuple[str, str]]:
    """Only the composition root builds the services of neoaprs/services/ (rule 7); another module that imports one is making its own."""
    return sorted((m, i.target) for m, imps in graph.items() if m not in SERVICE_BUILDERS and not m.startswith("neoaprs.services") for i in imps
                  if i.internal and (i.target == "neoaprs.services" or i.target.startswith("neoaprs.services.")))


def wire_imports_of_a_sibling(graph: dict[str, list[Import]]) -> list[tuple[str, str]]:
    """A wire module (`neoaprs/web/*wire.py`) imports `neoaprs.web.wirebase` and no sibling: what two areas share is in the base. `neoaprs.web.configwire` puts the groups of the areas into the one settings model, and `neoaprs.web.protocol` lists
    every model; both import the wire modules by their task."""
    return sorted((m, i.target) for m, imps in graph.items() if is_web(m) and m.endswith("wire") and m not in WIRE_ASSEMBLERS for i in imps
                  if i.internal and is_web(i.target) and i.target != "neoaprs.web.wirebase")


def wiring_outside_the_root(counts: dict[str, int]) -> dict[str, int]:
    return {rel: n for rel, n in counts.items() if rel not in COMPOSITION_ROOTS}


# ---- the real tree ------------------------------------------------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real_tree() -> Tree:
    return load_tree()


@pytest.fixture(scope="module")
def graph(real_tree: Tree) -> dict[str, list[Import]]:
    return import_graph(real_tree)


def test_every_module_has_a_layer_and_every_listed_module_exists(real_tree: Tree) -> None:
    assert unplaced(real_tree) == [], "a new module of neoaprs/ must be given its layer in LAYERS (tests/test_architecture.py) before it can be imported by anything"
    assert stale_layers(real_tree) == [], "LAYERS names a module that is gone: delete it from LAYERS"


def test_the_layers_run_one_way_and_the_only_violations_are_the_listed_ones(graph: dict[str, list[Import]]) -> None:
    found = violations(graph)
    new = {k: v for k, v in found.items() if k not in ALLOWED}
    assert not new, "new violations of the layering (fix the import; ALLOWED is only for what already existed):\n" + "\n".join(f"  {a} -> {b}: {why}" for (a, b), why in sorted(new.items()))
    stale = sorted(k for k in ALLOWED if k not in found)
    assert not stale, "ALLOWED lists imports that are no longer violations: delete these lines:\n" + "\n".join(f"  {a} -> {b}" for a, b in stale)


def test_every_allowed_violation_says_why() -> None:
    assert all(len(reason) > 30 for reason in ALLOWED.values())
    assert all(len(reason) > 30 for _, reason in CONNECTS.values())


def test_there_is_no_import_cycle(graph: dict[str, list[Import]]) -> None:
    assert find_cycle(graph) == [], "import cycle: " + " -> ".join(find_cycle(graph))


def test_neoaprs_never_imports_web(graph: dict[str, list[Import]]) -> None:
    assert neoaprs_imports_of_web(graph) == []


def test_services_never_import_the_controller_or_the_page(graph: dict[str, list[Import]]) -> None:
    assert service_imports_above(graph) == []


def test_a_wire_module_imports_the_wire_base_and_no_sibling(graph: dict[str, list[Import]]) -> None:
    assert wire_imports_of_a_sibling(graph) == []


def test_a_wire_module_that_imports_a_sibling_is_found_and_the_assemblers_are_not() -> None:
    g = import_graph({"neoaprs/web/stationwire.py": "from .packetwire import PacketRow\nfrom .wirebase import _Model\n", "neoaprs/web/packetwire.py": "", "neoaprs/web/wirebase.py": "", "neoaprs/web/protocol.py": "from .tncwire import TncState\n", "neoaprs/web/tncwire.py": ""})
    assert wire_imports_of_a_sibling(g) == [("neoaprs.web.stationwire", "neoaprs.web.packetwire")]


def test_only_the_composition_root_imports_the_services(graph: dict[str, list[Import]]) -> None:
    assert services_imported_outside_the_root(graph) == []


def test_signals_are_connected_in_the_composition_root_only(real_tree: Tree) -> None:
    counts = connect_sites(real_tree)
    for root in COMPOSITION_ROOTS:
        assert counts.get(root), f"{root} is listed as a place for wiring but connects nothing: delete it from COMPOSITION_ROOTS (and name the new root)"
    elsewhere = wiring_outside_the_root(counts)
    expected = {rel: n for rel, (n, _why) in CONNECTS.items()}
    assert elsewhere == expected, "Signal.connect outside the composition root (move the wiring there; the allowlist CONNECTS only shrinks and its counts are exact):\n" + repr(elsewhere)


# ---- every rule fails on a violation ------------------------------------------------------------------------------------------------------------------------

def tree_of(**files: str) -> Tree:
    return {f"neoaprs/{name}.py": source for name, source in files.items()}


def graph_of(**files: str) -> dict[str, list[Import]]:
    return import_graph(tree_of(**files))


def test_a_pure_module_that_imports_an_io_library_is_found() -> None:
    g = graph_of(clock="import sqlite3\nfrom urllib.request import urlopen\nimport json\nimport serial\n", signal="import os.path\nimport serial.tools.list_ports\n")
    assert violations(g) == {
        ("neoaprs.clock", "sqlite3"): "foundation (pure code) imports the I/O library sqlite3",
        ("neoaprs.clock", "urllib.request"): "foundation (pure code) imports the I/O library urllib.request",
        ("neoaprs.clock", "serial"): "foundation (pure code) imports the I/O library serial",
        ("neoaprs.signal", "os.path"): "foundation (pure code) imports the I/O library os.path",
        ("neoaprs.signal", "serial.tools.list_ports"): "foundation (pure code) imports the I/O library serial.tools.list_ports",
    }


def test_pyserial_is_for_the_adapters_and_nobody_else() -> None:
    g = graph_of(source="import serial\n", store="import serial\n", controller="from serial import Serial\n")
    assert violations(g) == {("neoaprs.store", "serial"): "pyserial outside the adapters layer", ("neoaprs.controller", "serial"): "pyserial outside the adapters layer"}


def test_a_lower_layer_that_imports_a_higher_one_is_found() -> None:
    g = graph_of(clock="from neoaprs import controller\nfrom neoaprs.source import Source\n", controller="", source="", signal="from .clock import utcnow\nfrom .store import Store\n", store="from neoaprs.db import Db\n", db="")
    found = violations(g)
    assert found[("neoaprs.clock", "neoaprs.controller")] == "foundation imports app"
    assert found[("neoaprs.clock", "neoaprs.source")] == "foundation imports adapters"
    assert found[("neoaprs.signal", "neoaprs.store")] == "foundation imports persistence"       # a relative import is resolved
    assert ("neoaprs.signal", "neoaprs.clock") not in found
    assert ("neoaprs.store", "neoaprs.db") not in found                                          # inside persistence anything goes


def test_adapters_and_persistence_do_not_import_each_other_and_siblings_only_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(LAYERS, "adapters", [*LAYERS["adapters"], "gps", "nmealine"])          # (two adapters made up here; tnc -> serialport is the real, allowed pair)
    g = graph_of(gps="from neoaprs.store import Store\nfrom neoaprs.nmealine import NmeaLine\nfrom neoaprs.source import Source\nfrom neoaprs.tasks import TaskSet\n", store="", nmealine="", source="", tasks="",
                 tnc="from neoaprs.serialport import SerialPort\n", serialport="")
    assert violations(g) == {
        ("neoaprs.gps", "neoaprs.store"): "adapters imports persistence",
        ("neoaprs.gps", "neoaprs.nmealine"): "an adapter imports a sibling adapter",      # the bases every feed shares (source, tasks) and the named siblings may be imported
    }


def test_bleak_is_kept_to_the_ble_port() -> None:
    g = graph_of(btle="def import_bleak():\n    import bleak\n", btserial="import bleak\n", clock="from bleak import BleakClient\n")
    assert violations(g) == {
        ("neoaprs.btserial", "bleak"): "bleak outside neoaprs/btle.py",
        ("neoaprs.clock", "bleak"): "foundation (pure code) imports the I/O library bleak",
    }


def test_tornado_and_pydantic_are_kept_to_their_homes() -> None:
    g = graph_of(source="from tornado.httpclient import HTTPRequest\n", store="import pydantic\n")
    g.update(import_graph({"neoaprs/web/server.py": "import tornado.web\n", "neoaprs/web/hub.py": "import pydantic\n", "neoaprs/web/stationwire.py": "import pydantic\n"}))
    assert violations(g) == {
        ("neoaprs.source", "tornado"): "Tornado outside neoaprs/web/",
        ("neoaprs.store", "pydantic"): "pydantic outside the wire modules of neoaprs/web/",
        ("neoaprs.web.hub", "pydantic"): "pydantic outside the wire modules of neoaprs/web/",       # (neoaprs.web.stationwire is one of the homes)
    }


def test_the_desktop_toolkits_are_kept_to_the_shells() -> None:
    g = import_graph({"neoaprs/desktop/qtshell.py": "from PySide6.QtCore import QObject\n", "neoaprs/desktop/winshell.py": "import pystray\nfrom PIL import Image\n", "neoaprs/desktop/menu.py": "import webview\nfrom PySide6 import QtWidgets\n",
                      "neoaprs/store.py": "import pystray\n", "neoaprs/desktop/__init__.py": ""})
    assert violations(g) == {
        ("neoaprs.desktop.menu", "webview"): "a GUI toolkit outside the shells of neoaprs/desktop/",
        ("neoaprs.desktop.menu", "PySide6"): "a GUI toolkit outside the shells of neoaprs/desktop/",
        ("neoaprs.store", "pystray"): "a GUI toolkit outside the shells of neoaprs/desktop/",
    }


def test_a_module_nobody_placed_and_a_layer_entry_without_a_file_are_found() -> None:
    assert unplaced(tree_of(clock="", brand_new="")) == ["neoaprs.brand_new"]
    assert unplaced({"neoaprs/web/anything.py": "", "neoaprs/services/x.py": ""}) == []                  # neoaprs/web/ is delivery, neoaprs/services/ is services
    assert "neoaprs.signal" in stale_layers(tree_of(clock=""))


def test_the_page_the_commands_and_the_process_are_the_delivery_layer_whole() -> None:
    for module in ("neoaprs.web", "neoaprs.web.server", "neoaprs.web.anything", "neoaprs.cli", "neoaprs.cli.doctor", "neoaprs.cli.anything", "neoaprs.desktop", "neoaprs.desktop.cmd", "neoaprs.daemon", "neoaprs.__main__"):
        assert layer_of(module) == "delivery", module
    assert layer_of("neoaprs.webs") is None and layer_of("neoaprs.client") is None, "a name that only begins like a delivery package is not one"
    g = import_graph({"neoaprs/clock.py": "from neoaprs.cli import doctor\n", "neoaprs/cli/doctor.py": "from neoaprs.web import server\nfrom neoaprs.db import Db\n", "neoaprs/cli/__init__.py": "", "neoaprs/web/server.py": "", "neoaprs/db.py": ""})
    assert violations(g) == {("neoaprs.clock", "neoaprs.cli.doctor"): "foundation imports delivery"}, "a command may import every layer and the page's server; the foundation may not import a command"
    assert neoaprs_imports_of_web(g) == [], "the commands are delivery, which may name the page's server"
    assert neoaprs_imports_of_web(import_graph({"neoaprs/store.py": "import neoaprs.web.api\n", "neoaprs/web/api.py": ""})) == [("neoaprs.store", "neoaprs.web.api")]


def test_a_cycle_is_found_and_a_chain_is_not() -> None:
    assert find_cycle(graph_of(a="import neoaprs.b\n", b="from neoaprs import c\n", c="from neoaprs.a import x\n")) == ["neoaprs.a", "neoaprs.b", "neoaprs.c", "neoaprs.a"]
    assert find_cycle(graph_of(a="import neoaprs.b\n", b="import neoaprs.c\n", c="")) == []
    assert find_cycle(import_graph({"neoaprs/a.py": "def f():\n    import neoaprs.b\n", "neoaprs/b.py": "import neoaprs.a\n"})) == ["neoaprs.a", "neoaprs.b", "neoaprs.a"]   # a lazy import counts


def test_neoaprs_importing_web_and_a_service_importing_the_controller_are_found() -> None:
    g = import_graph({"neoaprs/clock.py": "import neoaprs.web.api\n", "neoaprs/daemon.py": "from neoaprs.web.server import WebServer\n", "neoaprs/cli/doctor.py": "import neoaprs.web.server\n", "neoaprs/web/api.py": "", "neoaprs/web/server.py": "",
                      "neoaprs/services/beacon.py": "from neoaprs.controller import Controller\nfrom neoaprs.clock import utcnow\n", "neoaprs/controller.py": ""})
    assert neoaprs_imports_of_web(g) == [("neoaprs.clock", "neoaprs.web.api")]                  # the process (daemon.py) and the commands (cli/) are delivery: they may start the web server
    assert service_imports_above(g) == [("neoaprs.services.beacon", "neoaprs.controller")]
    assert violations(g)[("neoaprs.services.beacon", "neoaprs.controller")] == "services imports app"


def test_a_module_that_builds_a_service_of_its_own_is_found_and_the_root_and_the_services_themselves_are_not() -> None:
    g = import_graph({"neoaprs/app.py": "from .services.beacon import Beacon\n", "neoaprs/services/messaging.py": "from .beacon import Beacon\n", "neoaprs/services/beacon.py": "", "neoaprs/services/__init__.py": "",
                      "neoaprs/store.py": "from neoaprs.services.messaging import Messaging\n", "neoaprs/web/api.py": "from neoaprs import services\n"})
    assert services_imported_outside_the_root(g) == [("neoaprs.store", "neoaprs.services.messaging"), ("neoaprs.web.api", "neoaprs.services")]


def test_connect_is_counted_per_file_and_sqlite_a_socket_and_an_awaited_connect_are_not_a_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.modules[__name__], "COMPOSITION_ROOTS", {"neoaprs/wiring.py"})
    tree = {"neoaprs/a.py": "import sqlite3\ndb = sqlite3.connect('x')\nsock.connect(('h', 1))\nsig.connect(f)\nself.client.message.connect(g)\nasync def f():\n    await client.connect()\n", "neoaprs/wiring.py": "s.connect(h)\n", "neoaprs/web/api.py": "pass\n"}
    assert connect_sites(tree) == {"neoaprs/a.py": 2, "neoaprs/wiring.py": 1}
    assert wiring_outside_the_root(connect_sites(tree)) == {"neoaprs/a.py": 2}


def test_sql_is_in_the_homes_of_sql_and_the_list_of_the_rest_only_shrinks(real_tree: Tree) -> None:
    sites = sql_sites(real_tree)
    assert sql_outside_the_homes(sites) == {}, "sqlite3 or execute( outside the homes of SQL (docs/ARCHITECTURE.md, 'The database actor'): write the statement as a function of a connection in storesql.py (or a module beside it):\n" + \
        "\n".join(f"  {rel}: {why}" for rel, why in sql_outside_the_homes(sites).items())
    assert stale_sql_entries(sites) == [], "these files no longer touch SQL: delete them from SQL_HOMES / SQL_ELSEWHERE"
    assert not set(SQL_HOMES) & set(SQL_ELSEWHERE), "a file is in SQL_HOMES or in SQL_ELSEWHERE, not both"
    assert all(len(why) > 30 for why in SQL_HOMES.values()) and all(len(why) > 30 for *_, why in SQL_ELSEWHERE.values())


def test_no_statement_is_written_outside_the_homes_of_sql(real_tree: Tree) -> None:
    found = sql_text_outside_the_homes(sql_strings(real_tree))
    assert found == {}, "a string that begins like a SQL statement outside the homes of SQL: write it as a function of a connection in storesql.py (or a module beside it):\n" + \
        "\n".join(f"  {rel}: lines {lines}" for rel, lines in found.items())


def test_nothing_reaches_the_file_but_through_the_database_thread(real_tree: Tree) -> None:
    assert forbidden_names(real_tree) == {}, "_flush and before_write are gone with the single writer (neoaprs/db.py): every read and write is an operation of the database thread"


def test_the_homes_of_sql_are_in_the_persistence_layer() -> None:
    assert all(layer_of(rel.removesuffix(".py").replace("/", ".")) == "persistence" for rel in SQL_HOMES)


def test_sql_in_a_file_that_is_not_a_home_is_found_and_the_list_of_the_rest_only_shrinks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(SQL_HOMES, "neoaprs/stationsql.py", "a made-up home of SQL, to show that a home is not looked at")
    monkeypatch.setitem(SQL_ELSEWHERE, "neoaprs/tool.py", (True, 6, "a made-up tool with a connection of its own, to show that the count is exact"))
    tree = {"neoaprs/clock.py": "import sqlite3\n", "neoaprs/tool.py": "import sqlite3\ndef f(c):\n    c.execute('x')\n    c.executemany('y', [])\n", "neoaprs/stationsql.py": "import sqlite3\n",
            "neoaprs/new.py": "def f(c):\n    c.executescript('z')\n", "neoaprs/signal.py": "x = 1\n", "neoaprs/web/h.py": "from sqlite3 import Row\n", "neoaprs/rel.py": "from . import sqlite3\n"}
    sites = sql_sites(tree)
    assert sites == {"neoaprs/clock.py": (True, 0), "neoaprs/tool.py": (True, 2), "neoaprs/stationsql.py": (True, 0), "neoaprs/new.py": (False, 1), "neoaprs/web/h.py": (True, 0)}
    found = sql_outside_the_homes(sites)
    assert set(found) == {"neoaprs/clock.py", "neoaprs/tool.py", "neoaprs/new.py", "neoaprs/web/h.py"}          # stationsql.py is a home; the tool does 2 and its entry says 6
    assert "its entry says (True, 6)" in found["neoaprs/tool.py"]
    assert "neoaprs/stationsql.py" not in found
    assert "neoaprs/migrations.py" in stale_sql_entries(sites)                                         # an entry for a file that does not touch SQL (here: any) is stale


def test_a_statement_written_outside_the_homes_is_found_and_prose_is_not(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(SQL_HOMES, "neoaprs/stationsql.py", "a made-up home of SQL, to show that a home is not looked at")
    monkeypatch.setitem(SQL_ELSEWHERE, "neoaprs/tool.py", (True, 0, "a made-up tool with a connection of its own, to show that it is not looked at either"))
    tree = {"neoaprs/stationbook.py": 'def f(c, cols):\n    s = f"UPDATE station SET {cols} WHERE call = ?"\n    t = "SELECT " + "call"\n    c.go(s, t)\n',
            "neoaprs/stationsql.py": 'def g():\n    return "DELETE FROM station"\n', "neoaprs/tool.py": 'x = "INSERT INTO settings VALUES (?)"\n',
            "neoaprs/prose.py": '"""SELECT the stations: a docstring."""\ndef h():\n    """UPDATE the book: a docstring"""\n    # INSERT INTO station is a comment\n    "DELETE FROM station: a bare string"\n    return "an update of the SELECT list, and select * from a lower case word"\n'}
    strings = sql_strings(tree)
    assert strings == {"neoaprs/stationbook.py": [2, 3], "neoaprs/stationsql.py": [2], "neoaprs/tool.py": [1]}
    assert sql_text_outside_the_homes(strings) == {"neoaprs/stationbook.py": [2, 3]}                   # stationsql.py is a home, tool.py is a listed file that touches SQL


def test_a_flush_and_a_before_write_are_found_wherever_they_hide() -> None:
    tree = {"neoaprs/a.py": "def _flush(self):\n    pass\n", "neoaprs/b.py": "def f(store):\n    store._flush()\n", "neoaprs/c.py": "def g(s):\n    s.before_write = 1\n", "neoaprs/d.py": "flush = 1\n_flush = 2\n",
            "neoaprs/e.py": "def flush_now(): pass\n"}
    assert forbidden_names(tree) == {"neoaprs/a.py": [1], "neoaprs/b.py": [2], "neoaprs/c.py": [2], "neoaprs/d.py": [2]}
