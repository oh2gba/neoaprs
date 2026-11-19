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

The last table is not about imports: REACHES_OUT is the list of the modules that start a program, run a shell line, put another program in the place of this one, open a URL or the system's browser, or hand a string to
pyserial, each with why it may. It is exact, so that a new way out of the process is looked at by a person the day it is written.
"""
import ast
import re
import sys
from fnmatch import fnmatchcase

import pytest

from neoaprs.radiotype import KINDS
from tests.support.codemap import Import, Tree, connect_sites, find_cycle, forbidden_names, import_graph, load_tree, module_name, sql_sites, sql_strings

LAYERS: dict[str, list[str]] = {
    "foundation": ["neoaprs", "clock", "signal", "coded", "policy", "units", "recent", "callsign", "geo", "pmtilesformat", "symbols", "kiss", "ax25", "aprsposition", "aprsmice", "aprsmiceout", "aprsmessage", "aprsparse", "aprsweather", "aprsthirdparty", "aprsisline", "aprsextension", "aprsfreq", "aprsstorm", "aprslocator", "aprstelemetry", "aprsnmea", "gpsfix", "smartbeacon", "packet", "packetcodec", "message", "bulletin", "decay", "tncmode", "tncprofile", "pref", "route", "crossrule", "reach", "chain", "mapstate", "radiosearch", "serialboards", "versions", "skeds", "updateasset", "releasenotes", "device", "devicedata", "airports", "airportdata", "hourcount", "dummyroutes", "dummyframes", "dummyscene", "dummyhfscene", "dummyqru", "igaterules", "cipher", "mercury", "mercurycards", "mercuryscope", "channelbusy", "reading", "bundled", "radiotype", "direwolf", "tnc2line", "tnc2text", "dummylorascene", "lorasignal", "layerthing", "readsb", "radarcape", "aisdecode", "digitraffic", "shiptable"],
    "domain": ["alertcommand", "config", "configlayers", "configlegacy", "configstatus", "configtypes", "configvalues", "interlock", "station", "stationnotes", "stationbook", "aloha", "ownobject", "ownbulletin", "qrutext", "configradios", "radiospec", "messagerule", "beaconrule", "emailrule", "sendonrule", "claims", "stationchoices", "pairsetting"],
    "adapters": ["source", "tasks", "serialport", "serialholders", "serialprobe", "btsdp", "btserial", "btle", "btpaired", "tnc", "tncport", "callbackport", "dummyline", "dummyworlds", "tncsearch", "tncwatchdog", "tncentry", "tncfollow", "tnclines", "tncreader", "tnctextreader", "childenv", "rigctld", "gpsfeed", "aprsis", "pmtilesarchive", "pmtilesplan", "pmtilesrange", "pmtilescut", "worldmap", "updatefetch", "updatedownload", "selfreplace", "childprogram", "mercuryhelper", "mercurystale", "mercurycontrol", "mercurymodem", "mercuryclaims", "mercurychannel", "mercuryscoping", "mercuryui", "websocketclient", "mercuryspeaker", "mercurytune", "httpstrust", "nodevices", "radiodriver", "tncdriver", "mercurydriver", "winmm", "soundmixer", "winmixer", "cardlevels", "direwolfprogram", "modemstate", "direwolfmodem", "direwolftune", "direwolfdriver", "usbtie", "loraboard", "loralist", "aisfeed"],
    "persistence": ["store", "migrations", "migrationlog", "migrationsteps1to11", "migrationsteps12to21", "migrationsteps22on", "backupfolder", "durable", "instancelock", "stopfile", "walcare", "dbfile", "dberror", "dbstats", "dbthread", "db", "dbopen", "storesql", "paths", "dblog", "packetsql", "packetlog", "packetstatsql", "packetstats", "messagesql", "messagelog", "bulletinsql", "bulletinlog", "weathersql", "weatherlog", "ownsql", "ownlog", "supportsql", "stationsql", "radiosql", "migrationsteps31", "migrationsteps32", "migrationsteps34", "migrationsteps35"],
    "services": [],
    "app": ["controller", "app", "wiring", "radioregistry", "radioedits"],
    "delivery": ["__main__", "daemon"],
}
# The modules that are placed before they are written (the map's layers: work/par/r5/layers/contract.md, section 5: a later piece adds no layer line); a name leaves this set when its module exists.
PLANNED: set[str] = set()
# The packages that are one layer whole, by their folder: the services, and the descriptions of the types of radio (one module for each family, the registry in its __init__.py).
PACKAGE_LAYERS: dict[str, str] = {"neoaprs.services": "services", "neoaprs.radiotypes": "domain"}
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
ADAPTER_BASES = {"neoaprs.source", "neoaprs.tasks", "neoaprs.nodevices"}      # (nodevices: the switch every adapter that opens a device or a connection asks first)
ADAPTER_SIBLINGS: set[tuple[str, str]] = {("neoaprs.tnc", "neoaprs.serialport"), ("neoaprs.tnc", "neoaprs.serialprobe"), ("neoaprs.tnc", "neoaprs.serialholders"), ("neoaprs.tnc", "neoaprs.tncsearch"), ("neoaprs.tnc", "neoaprs.tncwatchdog"), ("neoaprs.tnc", "neoaprs.tncentry"), ("neoaprs.tnc", "neoaprs.tncreader"), ("neoaprs.tnc", "neoaprs.tnctextreader"), ("neoaprs.tnctextreader", "neoaprs.tncreader"), ("neoaprs.tnctextreader", "neoaprs.tncport"), ("neoaprs.tncreader", "neoaprs.tncentry"), ("neoaprs.tncreader", "neoaprs.tncport"), ("neoaprs.tncreader", "neoaprs.tncwatchdog"), ("neoaprs.tnc", "neoaprs.tncfollow"), ("neoaprs.tncfollow", "neoaprs.serialprobe"), ("neoaprs.tncfollow", "neoaprs.serialport"), ("neoaprs.tnc", "neoaprs.tnclines"), ("neoaprs.tnc", "neoaprs.tncport"), ("neoaprs.tnc", "neoaprs.dummyline"), ("neoaprs.tncport", "neoaprs.callbackport"), ("neoaprs.gpsfeed", "neoaprs.callbackport"), ("neoaprs.callbackport", "neoaprs.serialport"), ("neoaprs.dummyline", "neoaprs.tncport"), ("neoaprs.dummyline", "neoaprs.serialport"), ("neoaprs.tncsearch", "neoaprs.serialport"), ("neoaprs.tncsearch", "neoaprs.serialprobe"), ("neoaprs.serialprobe", "neoaprs.serialport"), ("neoaprs.serialprobe", "neoaprs.serialholders"), ("neoaprs.serialholders", "neoaprs.serialport"), ("neoaprs.gpsfeed", "neoaprs.serialport"), ("neoaprs.serialport", "neoaprs.btserial"), ("neoaprs.serialport", "neoaprs.btle"), ("neoaprs.btserial", "neoaprs.btsdp"), ("neoaprs.serialprobe", "neoaprs.btpaired"), ("neoaprs.worldmap", "neoaprs.pmtilesarchive"), ("neoaprs.updatefetch", "neoaprs.updatedownload"), ("neoaprs.mercurymodem", "neoaprs.mercuryhelper"), ("neoaprs.mercurymodem", "neoaprs.mercuryclaims"), ("neoaprs.mercuryclaims", "neoaprs.mercuryhelper"), ("neoaprs.mercuryclaims", "neoaprs.mercurystale"), ("neoaprs.mercurymodem", "neoaprs.mercurystale"), ("neoaprs.mercurystale", "neoaprs.mercuryhelper"), ("neoaprs.mercurystale", "neoaprs.childprogram"), ("neoaprs.mercuryclaims", "neoaprs.mercuryspeaker"), ("neoaprs.mercurydriver", "neoaprs.mercuryclaims"), ("neoaprs.mercurymodem", "neoaprs.mercurycontrol"), ("neoaprs.mercurymodem", "neoaprs.mercuryspeaker"), ("neoaprs.mercuryhelper", "neoaprs.childprogram"), ("neoaprs.childprogram", "neoaprs.childenv"), ("neoaprs.mercurymodem", "neoaprs.serialprobe"), ("neoaprs.mercurymodem", "neoaprs.mercuryfirewall"), ("neoaprs.mercurymodem", "neoaprs.mercurytune"), ("neoaprs.mercurymodem", "neoaprs.mercurychannel"), ("neoaprs.mercurymodem", "neoaprs.mercuryscoping"), ("neoaprs.mercuryscoping", "neoaprs.mercuryui"), ("neoaprs.mercuryui", "neoaprs.websocketclient"), ("neoaprs.mercurymodem", "neoaprs.mercuryallow"), ("neoaprs.mercuryfirewall", "neoaprs.winelevate"), ("neoaprs.updatefetch", "neoaprs.httpstrust"), ("neoaprs.updatedownload", "neoaprs.httpstrust"), ("neoaprs.pmtilesarchive", "neoaprs.httpstrust"), ("neoaprs.pmtilesrange", "neoaprs.pmtilesarchive"), ("neoaprs.pmtilesrange", "neoaprs.httpstrust"), ("neoaprs.pmtilesplan", "neoaprs.pmtilesrange"), ("neoaprs.pmtilescut", "neoaprs.pmtilesarchive"), ("neoaprs.pmtilescut", "neoaprs.pmtilesplan"), ("neoaprs.pmtilescut", "neoaprs.pmtilesrange"), ("neoaprs.radiodriver", "neoaprs.tnc"), ("neoaprs.radiodriver", "neoaprs.mercurymodem"), ("neoaprs.tncdriver", "neoaprs.tnc"), ("neoaprs.mercurydriver", "neoaprs.mercurymodem"), ("neoaprs.mercurydriver", "neoaprs.tnc"), ("neoaprs.tncdriver", "neoaprs.radiodriver"), ("neoaprs.mercurydriver", "neoaprs.radiodriver"), ("neoaprs.mercurydriver", "neoaprs.mercuryhelper"), ("neoaprs.tncdriver", "neoaprs.serialprobe"), ("neoaprs.tncdriver", "neoaprs.dummyline"), ("neoaprs.mercurydriver", "neoaprs.dummyline"), ("neoaprs.direwolfprogram", "neoaprs.childprogram"), ("neoaprs.direwolftune", "neoaprs.childprogram"), ("neoaprs.direwolftune", "neoaprs.direwolfprogram"), ("neoaprs.direwolfmodem", "neoaprs.direwolfprogram"), ("neoaprs.direwolfmodem", "neoaprs.direwolftune"), ("neoaprs.direwolfmodem", "neoaprs.modemstate"), ("neoaprs.mercurymodem", "neoaprs.modemstate"), ("neoaprs.direwolfmodem", "neoaprs.winmm"), ("neoaprs.direwolfmodem", "neoaprs.mercuryclaims"), ("neoaprs.direwolfmodem", "neoaprs.mercuryhelper"), ("neoaprs.direwolfmodem", "neoaprs.mercurymodem"), ("neoaprs.direwolfmodem", "neoaprs.serialprobe"), ("neoaprs.direwolfdriver", "neoaprs.direwolfmodem"), ("neoaprs.direwolfdriver", "neoaprs.mercurymodem"), ("neoaprs.direwolfdriver", "neoaprs.radiodriver"), ("neoaprs.direwolfdriver", "neoaprs.tnc"), ("neoaprs.direwolfdriver", "neoaprs.mercurydriver"), ("neoaprs.radiodriver", "neoaprs.direwolfmodem"), ("neoaprs.direwolfmodem", "neoaprs.usbtie"), ("neoaprs.winmixer", "neoaprs.soundmixer"), ("neoaprs.cardlevels", "neoaprs.soundmixer"), ("neoaprs.cardlevels", "neoaprs.winmixer"), ("neoaprs.direwolfdriver", "neoaprs.cardlevels"), ("neoaprs.direwolfdriver", "neoaprs.soundmixer"), ("neoaprs.mercurydriver", "neoaprs.cardlevels"), ("neoaprs.mercurydriver", "neoaprs.soundmixer"), ("neoaprs.radiodriver", "neoaprs.cardlevels"), ("neoaprs.tnc", "neoaprs.dummyworlds"), ("neoaprs.dummyworlds", "neoaprs.dummyline"), ("neoaprs.dummyworlds", "neoaprs.serialport"), ("neoaprs.dummyworlds", "neoaprs.tncport"), ("neoaprs.tncreader", "neoaprs.loraboard"), ("neoaprs.loraboard", "neoaprs.loralist"), ("neoaprs.loraboard", "neoaprs.tncport"), ("neoaprs.loraboard", "neoaprs.tncwatchdog"), ("neoaprs.loraboard", "neoaprs.btle")}      # (importer, imported): the TNC reads the serial line, and its search and watchdog are parts of it
DELIVERY_PACKAGES = ("neoaprs.web", "neoaprs.cli", "neoaprs.desktop")
WIRE_ASSEMBLERS = {"neoaprs.web.protocol"}
WIRE_PAIRS = {("neoaprs.web.mapwire", "neoaprs.web.layerwire")}       # (importer, imported) wire modules beside the assemblers: the topic `map` carries the layers of traffic of layerwire
PURE = {"foundation", "domain"}
# pyserial ("serial") counts as an I/O library beside the terminal modules it stands on: the protocol modules never see a descriptor.
IO_LIBRARIES = {"asyncio", "sqlite3", "socket", "subprocess", "tornado", "serial", "bleak", "termios", "pty", "fcntl", "os", "shutil", "tempfile", "ssl", "select", "selectors", "urllib.request", "http.client", "http.server"}
# The desktop app's toolkits (the extra `app` of pyproject.toml) are imported by the shells and by nothing else: everything else of neoaprs/desktop/ runs without them (and is tested without them).
TOOLKITS = {"PySide6", "shiboken6", "webview", "pystray", "PIL", "gi", "PyObjCTools", "Foundation", "AppKit", "WebKit"}
TOOLKIT_HOMES: set[str] = {"neoaprs.desktop.qtshell", "neoaprs.desktop.qtwindow", "neoaprs.desktop.webshell", "neoaprs.desktop.webdesk"}
BLEAK_HOMES: set[str] = {"neoaprs.btle"}                        # bleak (the extra `ble` of pyproject.toml) only in the BLE port, which imports it when a ble:// port is opened
TORNADO_HOMES: set[str] = set()                                # Tornado only in neoaprs/web/ (CONVENTIONS.md)
PYDANTIC_HOMES: set[str] = {"neoaprs.web.wirebase", "neoaprs.web.hostwire", "neoaprs.web.hubwire", "neoaprs.web.stationwire", "neoaprs.web.packetwire", "neoaprs.web.tncwire", "neoaprs.web.configwire", "neoaprs.web.beaconwire", "neoaprs.web.igatewire", "neoaprs.web.qruwire", "neoaprs.web.generalwire", "neoaprs.web.messagewire", "neoaprs.web.bulletinwire", "neoaprs.web.prefwire", "neoaprs.web.weatherwire", "neoaprs.web.historywire", "neoaprs.web.replaywire", "neoaprs.web.portwire", "neoaprs.web.mapwire", "neoaprs.web.ownwire", "neoaprs.web.updatewire", "neoaprs.web.skedwire", "neoaprs.web.gpswire", "neoaprs.web.supportwire", "neoaprs.web.radiowire", "neoaprs.web.layerwire", "neoaprs.web.protocol", "neoaprs.web.dispatch", "neoaprs.web.outbound"}      # the core knows nothing of the wire format; these check or describe what comes in and what goes out

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
    "neoaprs/radiosql.py": "the statements of the radios and their own settings: functions of a connection that the thread runs",
    "neoaprs/packetsql.py": "the statements of the packet log and the station cache: functions of a connection that the thread runs",
    "neoaprs/packetstatsql.py": "the statements of the statistics card's counts of the packet log, by the hour: functions of a connection that the thread runs",
    "neoaprs/stationsql.py": "the statements of what each radio heard of a station and of a station's path on a radio: functions of a connection that the thread runs",
    "neoaprs/messagesql.py": "the statements of the message table: functions of a connection that the thread runs",
    "neoaprs/bulletinsql.py": "the statements of the bulletin table (the message board): functions of a connection that the thread runs",
    "neoaprs/ownsql.py": "the statements of the tables of our own objects and bulletins (what we send of our own accord): functions of a connection that the thread runs",
    "neoaprs/weathersql.py": "the statements of the weather table (every observation of every weather station) and the read of the packets it is made from: functions of a connection that the thread runs",
    "neoaprs/supportsql.py": "the statements of the support bundle: functions of a read-only connection that the bundle's own thread runs (the file's version and sizes, the rows of each table, the latest packets)",
    "neoaprs/walcare.py": "the limits of the write-ahead log (journal_size_limit and the automatic checkpoint): a function of the connection, run by the thread",
    "neoaprs/migrationsteps12to21.py": "the migrations 12 to 21, frozen beside migrations.py: migration code",
    "neoaprs/migrationsteps22on.py": "the migrations from 22 on, frozen beside migrations.py: migration code",
    "neoaprs/migrationsteps35.py": "migration 35, the map's radius at most 300 km, frozen: migration code",
    "neoaprs/migrationsteps31.py": "migration 31, the radios as rows, frozen beside migrations.py: migration code",
    "neoaprs/migrationsteps32.py": "migrations 32 and 33, frozen: the air rows' radio as an id, the stations' history and paths by radio, the objects' radios",
    "neoaprs/migrationsteps34.py": "migration 34, frozen: no main radio, the ticks it stood for written, a bulletin's radios",
    "neoaprs/migrationsteps1to11.py": "the migrations 1 to 11, frozen beside migrations.py: migration code",
    "neoaprs/migrations.py": "the opening of the file, before the thread opens it, and in the tools, and the runner of the migrations (their history, the copy taken before them)",
}
# Everything else that still imports sqlite3 or calls execute, with how many calls: (imports sqlite3, calls of execute, why). The numbers are exact: a file that does less than its entry says
# fails until the entry is lowered or deleted, so the list only shrinks. A new entry is not the way to get a change through: the statement belongs in a function of storesql.py or a module beside it.
SQL_ELSEWHERE: dict[str, tuple[bool, int, str]] = {}

# The ways out of the process, by kind: what a file names (through whatever name it imported it by) to start a program, to give a line to a shell, to put another program in the place of this one, to open a URL, to hand
# an address to the system's browser, or to hand a string to pyserial, which opens whatever kind of port the string names. A name that is only a type (`process: subprocess.Popen[str]`) starts nothing and is not counted.
# A plain connection to a host and a port (asyncio.open_connection: APRS-IS, gpsd, rigctld, the Mercury modem) is not a kind here: this list does not hold the modules that make one.
REACH: dict[str, tuple[str, ...]] = {
    "program": ("subprocess.run", "subprocess.Popen", "subprocess.call", "subprocess.check_call", "subprocess.check_output", "asyncio.create_subprocess_exec", "asyncio.subprocess.create_subprocess_exec",
                "os.spawn*", "os.posix_spawn*", "os.startfile", "pty.spawn", "tornado.process.*"),
    "shell": ("asyncio.create_subprocess_shell", "asyncio.subprocess.create_subprocess_shell", "os.system", "os.popen", "subprocess.getoutput", "subprocess.getstatusoutput"),
    "exec": ("os.exec*",),
    "url": ("urllib.request.urlopen", "urllib.request.urlretrieve", "urllib.request.build_opener", "urllib.request.OpenerDirector", "http.client.HTTPConnection", "http.client.HTTPSConnection", "tornado.httpclient.*"),
    "browser": ("webbrowser.*",),
    "serial": ("serial.serial_for_url", "serial.Serial"),
}
REACH_METHODS = {"subprocess_exec": "program", "subprocess_shell": "shell"}          # the event loop's own two, which are methods of an object and have no module to be known by
# Every file of neoaprs/ that names one of them: (the kinds, in the order of REACH; why it may). Exact both ways: a file that reaches out and is not here fails the test, and so does an entry that says more or other than its
# file does. A new entry is the moment to ask what the place starts or opens, and whether a text from the air, from the page or from a setting can get into it.
REACHES_OUT: dict[str, tuple[str, str]] = {
    "neoaprs/btpaired.py": ("program", "asks BlueZ which devices are paired, with busctl or bluetoothctl: two commands written in the module, whose answer is only read"),
    "neoaprs/cli/daemonstate.py": ("url", "a command asks whether the daemon's page answers, at the loopback address the daemon wrote into its data folder, past any proxy"),
    "neoaprs/cli/hostcheck.py": ("program", "`neoaprs doctor` asks flatpak about a Firefox installed that way; the arguments are written in the module and the answer is only read"),
    "neoaprs/cli/opencmd.py": ("program browser", "`neoaprs open`: starts the daemon as a process of its own, from this program's own path and the data folder, and hands the page's loopback address to the system's browser"),
    "neoaprs/cli/servicelaunchd.py": ("program", "`neoaprs service` on macOS: launchctl, with the label and the file this program wrote"),
    "neoaprs/cli/servicesystemd.py": ("program", "`neoaprs service` on Linux: systemctl --user and loginctl, with the unit this program wrote and the user's own name"),
    "neoaprs/cli/servicewindows.py": ("program", "`neoaprs service` on Windows: starts the daemon now, detached, with the command it also writes for the start at login"),
    "neoaprs/cli/supportgather.py": ("program", "the support bundle reads the service's lines of the user's journal with journalctl, a command written in the module"),
    "neoaprs/cli/supportmake.py": ("program", "shows the finished support bundle in the system's file manager (explorer, open, xdg-open), at a path this program made"),
    "neoaprs/desktop/cmd.py": ("browser", "the app where no window can be made: the daemon's page, a loopback address, in the system's browser"),
    "neoaprs/desktop/gtkenv.py": ("program", "the web window on Linux tries bubblewrap once, a fixed command of the module, to see whether WebKit's sandbox can start here"),
    "neoaprs/desktop/links.py": ("browser", "a link of the page to somebody else's site goes to the system's browser, after `route` has let only http, https and mailto through"),
    "neoaprs/desktop/menu.py": ("browser", "the tray's Open in browser: the daemon's page, a loopback address"),
    "neoaprs/desktop/qtshell.py": ("browser", "the Qt shell without a web engine: the daemon's page, a loopback address, in the system's browser"),
    "neoaprs/desktop/webshell.py": ("browser", "the web shell without a window: the daemon's page, a loopback address, in the system's browser"),
    "neoaprs/childprogram.py": ("program", "starts a program that ships with NeoAPRS (the Mercury modem, Direwolf) from a list of arguments the daemon made, and on Windows ends its process tree with taskkill"),
    "neoaprs/mercuryhelper.py": ("program", "asks the Mercury modem that ships with the program for the sound cards, with an argument written in the module"),
    "neoaprs/mercuryspeaker.py": ("program", "the Dummy HF radio's sound: the system's player (pw-play, paplay or aplay) with arguments written in the module, fed through its standard input"),
    "neoaprs/pmtilesarchive.py": ("url", "asks build.protomaps.com which daily build is there (a HEAD request for each of the last days)"),
    "neoaprs/pmtilesrange.py": ("url", "reads the bytes of the map out of the archive of the whole world with range requests, from the address the settings or the daily build give"),
    "neoaprs/selfreplace.py": ("exec", "Update now for an AppImage: the new file, whose checksum was checked, is started in the place of this process with the arguments the daemon had, and the desktop app that owned that daemon after it, with its own (neoaprs/desktop/renew.py)"),
    "neoaprs/serialport.py": ("serial", "the one place a port is made: the address of the radio's or the GPS's port goes to pyserial here and nowhere else"),
    "neoaprs/services/alerts.py": ("program shell", "the alert command: the operator's own line, given to the shell (on Windows to PowerShell, a program that reads the line from its standard input), with what came from the air in environment variables only; taskkill ends its tree on Windows"),
    "neoaprs/services/selfinstall.py": ("program", "Update now on Windows: runs the downloaded installer, whose checksum was checked, silently and detached from the daemon"),
    "neoaprs/updatedownload.py": ("url", "the downloads of Update now: https and GitHub's hosts only, every redirect checked against the same rule"),
    "neoaprs/updatefetch.py": ("url", "the update check, the changelog, the suggested frequencies, the sked board, Send logs and the map's layers of traffic (the aircraft and ships services, an own aircraft receiver): http or https only, to the project's server, to the address of update/url, to the services' addresses written in neoaprs/layerthing.py or to the receiver's address of map/aircraft_host"),
}
SHELL_LINES = {"neoaprs/services/alerts.py": 1}         # the places a shell is given a line to run, with how many: the alert command and nothing else, ever

# The wall round the map's layers of traffic (aircraft and ships): nothing of a layer reaches the station book, the database, the packets, the statistics, the replay, the iGate or a radio. The modules of the layers
# import none of WALLED (a name that is one or begins with one), and outside them only LAYER_IMPORTERS import a module of the layers: the settings' rows, the composition root, and the page's topic, command and wire.
LAYER_MODULES = frozenset({"neoaprs.layerthing", "neoaprs.web.layerwire", "neoaprs.readsb", "neoaprs.radarcape", "neoaprs.services.layers", "neoaprs.services.layerasked", "neoaprs.web.layerfeed", "neoaprs.web.layerhandlers",
                           "neoaprs.aisdecode", "neoaprs.digitraffic", "neoaprs.shiptable", "neoaprs.aisfeed", "neoaprs.services.layerships"})
WALLED = ("neoaprs.station", "neoaprs.packet", "neoaprs.store", "neoaprs.db", "neoaprs.aprsis", "neoaprs.tnc", "neoaprs.radioregistry", "neoaprs.radiodriver", "neoaprs.services.igate", "neoaprs.services.sender",
          "neoaprs.services.common", "neoaprs.services.heard", "neoaprs.web.packetwindow", "neoaprs.web.replaywire", "neoaprs.web.stationwire", "neoaprs.web.packetwire", "neoaprs.dbstats")
LAYER_IMPORTERS = frozenset({"neoaprs.configlayers", "neoaprs.app", "neoaprs.wiring", "neoaprs.controller", "neoaprs.web.topics", "neoaprs.web.api", "neoaprs.web.dispatch", "neoaprs.web.mapwire", "neoaprs.web.mapview",
                             "neoaprs.web.protocol"})

# A radio is named by its id and asks its type what it may do (plan §2): `fm` and `hf` are words of a kind, and they name one only in the descriptions of the types (TYPE_MODULES). Anywhere else the word
# as a string ("hf"), the ids of the two radios of before (FM_ID, HF_ID) or a name with fm or hf as one of its parts (`hf_port`, `fm_enabled`, `HF_PROFILES`) is a radio or a kind named where the radio
# should have been asked: a third kind would have to be written into that place. So is the word "lora" as a string, and radio 1 or 2 named by its number. RADIO_WORDS is every file where that is so
# today, with how many (exact, so it only shrinks), who takes them out, and why: "W3" takes out what the steps of the round kept for the page and the code of before (the files of W3's entry: its aliases,
# views, old fields, topics, the rules of a kind beside its type, the set of two radios and the stand-in); "open" is the same kind of thing in a file W3's entry does not name (radio 1 as the default where nothing names a radio, the run's
# overrides of radios 1 and 2), whose owner the coordinator gives (W3, or the pass over the whole code); "kept" is what stays for good (the frozen migration steps read the words the database of before stored).
TYPE_MODULES = ("neoaprs/radiotype.py", "neoaprs/radiotypes/")
NOT_A_RADIO = {"hf_dial", "HF_DIAL", "DUMMY_HF"}         # the dial of the HF tests the version page names (services/updatecheck.py), a band's; the Dummy HF type's profile, a type's own name
RADIO_WORDS: dict[str, tuple[int, str, str]] = {
    "neoaprs/app.py": (4, "W3", "radio 1 and 2's lines and Mercury made by the process before the settings are read (`hf`, `hf_port`, FM_ID, HF_ID)"),
    "neoaprs/config.py": (7, "W3", "the flat key hf/profile, the state row hf/beacon_last_sent_at, radio 1's serial/last_port and beacon_path_calls (radio 1's own path, which the frozen tests read) by FM_ID"),
    "neoaprs/configradios.py": (40, "W3", "the flat keys' view of radios 1 and 2 (FLAT_HOMES, FLAT_KINDS, FLAT_ON, the default radios)"),
    "neoaprs/configvalues.py": (3, "W3", "the parser of the flat key hf/profile"),
    "neoaprs/controller.py": (10, "W3", "the names of radio 1 and 2's task and beacon, _hf_settings, hf_port"),
    "neoaprs/daemon.py": (1, "open", "--hf-port, the Mercury of radio 2 that something else runs"),
    "neoaprs/dummyhfscene.py": (2, "kept", "the Dummy HF type's own world, with the random pause of its kind's beacons"),
    "neoaprs/mercurydriver.py": (4, "open", "the run override hf_port and the profiles by kind (HF_BY_KEY)"),
    "neoaprs/mercurymodem.py": (4, "open", "radio 2 as the default holder of the modem's claims and of the folder of the one HF radio of before"),
    "neoaprs/messagelog.py": (3, "open", "radio 1 as the default radio of a station's path (FM_ID)"),
    "neoaprs/messagesql.py": (2, "open", "radio 1 as the default radio of a station's entry read and kept (radio_id=1)"),
    "neoaprs/migrationsteps31.py": (35, "kept", "the frozen step 31 reads the flat keys and the words of before (fm, hf) and makes radios 1 and 2 of them"),
    "neoaprs/migrationsteps32.py": (3, "kept", "the frozen step 32 maps the stored words of before to the radios' ids"),
    "neoaprs/migrationsteps34.py": (2, "kept", "the frozen step 34 names the types that sent in 0.20.0 (dummy-hf) and the kinds a mail went on (fm, lora)"),
    "neoaprs/ownbulletin.py": (3, "W3", "radio 1 as a bulletin's default set (FM_ID), as an object's"),
    "neoaprs/ownobject.py": (3, "W3", "radio 1 as an object's default set (FM_ID)"),
    "neoaprs/radiodriver.py": (3, "open", "RunOverrides.hf_port, and radio 2 as the radio it is given to in a RunOverrides made by hand (HF_ID)"),
    "neoaprs/radioedits.py": (3, "open", "the run's ports (--port radio 1's, --hf-port), which the start's log tells of"),
    "neoaprs/radioregistry.py": (4, "W3", "the log's words of radios 1 and 2's lines, `tnc` and `hf radio` (id in (FM_ID, HF_ID))"),
    "neoaprs/radiospec.py": (5, "open", "the re-exports of FM_ID and HF_ID, and the kinds' English words by kind (KIND_WORDS, whose place is beside KINDS)"),
    "neoaprs/services/answers.py": (4, "open", "radios 1 and 2 named by their kind in an answer (radio.id in (FM_ID, HF_ID))"),
    "neoaprs/services/beaconframe.py": (11, "W3", "the line of before (OldLine: a Tnc's kind as its radio's), radio 1's path for a radio of a kind with none"),
    "neoaprs/services/common.py": (11, "W3", "Radio and RadioSet of before (of('fm'), FM_ALLOWED or HF_ALLOWED by kind, radio 1's path)"),
    "neoaprs/services/digipeater.py": (2, "open", "a packet with no radio counted as radio 1's"),
    "neoaprs/sendonrule.py": (2, "open", "radio 1 as what a new object or bulletin starts with while the station has no radio that sends (FM_ID)"),
    "neoaprs/services/ownobjects.py": (2, "open", "radio 1's path for an object of no path whose radios are none (FM_ID)"),
    "neoaprs/services/prefbook.py": (13, "open", "radio 1's path kept in the station's entry of before (FM_ID as the default radio, and radio 1's own path for a radio with none)"),
    "neoaprs/services/radiofinder.py": (2, "open", "radio 1 when the page names no radio"),
    "neoaprs/stationbook.py": (2, "open", "radio 1 as the radio of a packet with none"),
    "neoaprs/stationnotes.py": (2, "open", "a packet with no radio as radio 1's"),
    "neoaprs/tnc.py": (10, "W3", "a Tnc's kind decides Mercury's station messages, the log's words and its label, and its radio before its driver names one (rules.kind == 'hf', FM_ID, HF_ID)"),
    "neoaprs/tncdriver.py": (3, "open", "radio 1's port of the run and serial/last_port (FM_ID)"),
    "neoaprs/tncmode.py": (3, "open", "radio 1 as the default radio of a frame read"),
    "neoaprs/tncprofile.py": (8, "W3", "the profiles by kind (HF_PROFILES, HF_BY_KEY, hf_profile_of, HF_DEFAULT)"),
    "neoaprs/tncsearch.py": (2, "open", "radio 1 as the default holder of a search"),
    "neoaprs/web/handlers.py": (4, "W3", "radio 1 where the page names none: Find my radio's and a station's path (FM_ID, imported and used three times)"),
    "neoaprs/web/tncwire.py": (3, "W3", "RadioRow.kind spells the three kinds out (fm, hf, lora) where radiotype.Kind would do"),
    "neoaprs/wiring.py": (2, "open", "only radio 1 remembers the port its search found (FM_ID)"),
}


def _imported_names(module: ast.Module) -> dict[str, str]:
    """What each name the file imported stands for: `import urllib.request` gives urllib, `import subprocess as sp` gives sp for subprocess, `from os import execv as go` gives go for os.execv. An import inside a function counts."""
    names: dict[str, str] = {}
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names[alias.asname or alias.name.split(".")[0]] = alias.name if alias.asname else alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            for alias in node.names:
                names[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return names


def _full_name(node: ast.AST, names: dict[str, str]) -> str:
    """`sp.Popen` as subprocess.Popen: the dotted name with the import it begins with written out; "" for anything that does not begin with an imported name."""
    if isinstance(node, ast.Name):
        return names.get(node.id, "")
    if isinstance(node, ast.Attribute):
        base = _full_name(node.value, names)
        return f"{base}.{node.attr}" if base else ""
    return ""


def _type_notes(module: ast.Module) -> set[int]:
    """The nodes that are part of an annotation."""
    notes = [node.annotation for node in ast.walk(module) if isinstance(node, (ast.arg, ast.AnnAssign)) and node.annotation is not None]
    notes += [node.returns for node in ast.walk(module) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None]
    return {id(part) for note in notes for part in ast.walk(note)}


def _reach_of(node: ast.AST, names: dict[str, str]) -> str | None:
    """The kind of way out the node names, if any. A name counts wherever it stands, called or not: `start: Callable[..., object] = subprocess.Popen` starts a program two lines later."""
    if isinstance(node, ast.keyword):
        return "shell" if node.arg == "shell" and not (isinstance(node.value, ast.Constant) and node.value.value is False) else None
    if not isinstance(node, (ast.Name, ast.Attribute)):
        return None
    full = _full_name(node, names)
    known = next((kind for kind, patterns in REACH.items() if any(fnmatchcase(full, pattern) for pattern in patterns)), None)
    return known or (REACH_METHODS.get(node.attr) if isinstance(node, ast.Attribute) else None)


def reaches_out(tree: Tree) -> dict[str, dict[str, int]]:
    """Per file that has any: how many times it names a way out of the process, by kind (REACH). `shell=True` (anything but `shell=False`) on any call is a shell line too."""
    found: dict[str, dict[str, int]] = {}
    for rel, source in tree.items():
        module = ast.parse(source)
        names, notes = _imported_names(module), _type_notes(module)
        counts: dict[str, int] = {}
        for node in ast.walk(module):
            kind = None if id(node) in notes else _reach_of(node, names)
            if kind is not None:
                counts[kind] = counts.get(kind, 0) + 1
        if counts:
            found[rel] = counts
    return found


def reach_not_as_listed(found: dict[str, dict[str, int]]) -> dict[str, str]:
    """Every file whose ways out are not what REACHES_OUT says of it, with what it does and what the list says; a listed file that no longer reaches out is among them."""
    does = {rel: " ".join(kind for kind in REACH if kind in counts) for rel, counts in found.items()}
    listed = {rel: kinds for rel, (kinds, _why) in REACHES_OUT.items()}
    return {rel: f"does: {does.get(rel) or 'nothing'}; REACHES_OUT says: {listed.get(rel) or 'nothing (it is not listed)'}" for rel in sorted({*does, *listed}) if does.get(rel) != listed.get(rel)}


def shell_lines(found: dict[str, dict[str, int]]) -> dict[str, int]:
    return {rel: counts["shell"] for rel, counts in found.items() if "shell" in counts}


_KIND_PART = re.compile(r"(?:^|_)(fm|hf)(?:_|$)", re.IGNORECASE)
_RADIO_ID = re.compile(r"^(?:id|radio|radio_id)$|_radio(?:_id)?$")      # a name that holds a radio or its id: `id`, `radio`, `radio_id`, `holder_radio_id` (a message's `msg_id` is no radio's)
_OLD_IDS = (1, 2)                                                        # the ids of the two radios of before, written as numbers where FM_ID and HF_ID would be found


def _radio_name(node: ast.AST) -> bool:
    name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None
    return name is not None and _RADIO_ID.search(name) is not None


def _old_id(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and type(node.value) is int and node.value in _OLD_IDS


def _a_radio_by_number(node: ast.AST) -> int:
    """How often the node names radio 1 or 2 by its number: a radio's name compared (==, !=, is, in) with 1 or 2, a choice between one and 1 or 2, or a parameter or a keyword of a radio's name that is 1
    or 2 when none is given (an order, `radio < 1`, is a check of an id, not a radio named)."""
    if isinstance(node, ast.Compare):
        sides = [node.left, *node.comparators]
        numbers = [e for side in sides for e in (side.elts if isinstance(side, (ast.Tuple, ast.List, ast.Set)) else [side])]
        return int(all(isinstance(op, (ast.Eq, ast.NotEq, ast.Is, ast.IsNot, ast.In, ast.NotIn)) for op in node.ops) and any(map(_old_id, numbers)) and any(map(_radio_name, sides)))
    if isinstance(node, ast.IfExp):
        return int((_old_id(node.body) or _old_id(node.orelse)) and any(_radio_name(n) for n in ast.walk(node.test)))
    if isinstance(node, ast.arguments):
        given = [*node.posonlyargs, *node.args]
        pairs = [*zip(given[len(given) - len(node.defaults):], node.defaults), *zip(node.kwonlyargs, node.kw_defaults)]
        return sum(_RADIO_ID.search(arg.arg) is not None and _old_id(default) for arg, default in pairs)
    if isinstance(node, ast.keyword):
        return int(node.arg is not None and _RADIO_ID.search(node.arg) is not None and _old_id(node.value))
    return 0


def _named(node: ast.AST) -> str | None:
    """The name a node gives or uses: a variable, an attribute, a function, a class, a parameter, a keyword of a call, an imported name as it is bound."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.arg):
        return node.arg
    if isinstance(node, ast.keyword):
        return node.arg
    if isinstance(node, ast.alias):
        return node.asname or node.name.split(".")[-1]
    return None


def radio_words(tree: Tree) -> dict[str, int]:
    """How often each file outside the type modules names a radio or a kind instead of asking it: a word of a kind as a string ("fm", "hf", "lora": KINDS, not in a docstring), a name with fm or hf as
    one of its parts (NOT_A_RADIO aside), or radio 1 or 2 by its number (`_a_radio_by_number`)."""
    out: dict[str, int] = {}
    for rel, source in tree.items():
        if rel.startswith(TYPE_MODULES):
            continue
        module = ast.parse(source)
        prose = {id(node.value) for node in ast.walk(module) if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)}
        count = 0
        for node in ast.walk(module):
            name = _named(node)
            count += (isinstance(node, ast.Constant) and node.value in KINDS and id(node) not in prose) or (name is not None and name not in NOT_A_RADIO and _KIND_PART.search(name) is not None)
            count += _a_radio_by_number(node)
        if count:
            out[rel] = count
    return out


def radio_words_not_as_listed(found: dict[str, int]) -> dict[str, str]:
    """Each file whose count differs from RADIO_WORDS, with both counts."""
    listed = {rel: n for rel, (n, _owner, _why) in RADIO_WORDS.items()}
    return {rel: f"names a radio by fm or hf {found.get(rel, 0)} times; RADIO_WORDS says {listed.get(rel, 0)}" for rel in sorted(set(found) | set(listed)) if found.get(rel, 0) != listed.get(rel, 0)}


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
    for package, layer in PACKAGE_LAYERS.items():
        if module == package or module.startswith(package + "."):
            return layer
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
    return sorted(f"neoaprs.{n}" for names in LAYERS.values() for n in names if n != "neoaprs" and f"neoaprs.{n}" not in modules and f"neoaprs.{n}" not in PLANNED)


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
    every model; both import the wire modules by their task. Beside them only the pairs of WIRE_PAIRS: `neoaprs.web.mapwire` imports `neoaprs.web.layerwire` and no other sibling."""
    return sorted((m, i.target) for m, imps in graph.items() if is_web(m) and m.endswith("wire") and m not in WIRE_ASSEMBLERS for i in imps
                  if i.internal and is_web(i.target) and i.target != "neoaprs.web.wirebase" and (m, i.target) not in WIRE_PAIRS)


def through_the_wall(graph: dict[str, list[Import]]) -> list[tuple[str, str]]:
    """Every import that breaks the wall round the layers of traffic: a module of the layers that imports one of WALLED, and a module outside them and outside LAYER_IMPORTERS that imports one of them."""
    return sorted((m, i.target) for m, imps in graph.items() for i in imps if i.internal and i.target != m and (
        (m in LAYER_MODULES and i.target.startswith(WALLED)) or (m not in LAYER_MODULES and m not in LAYER_IMPORTERS and i.target in LAYER_MODULES)))


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
    g = import_graph({"neoaprs/web/stationwire.py": "from .packetwire import PacketRow\nfrom .wirebase import _Model\n", "neoaprs/web/packetwire.py": "", "neoaprs/web/wirebase.py": "", "neoaprs/web/protocol.py": "from .tncwire import TncState\n", "neoaprs/web/tncwire.py": "",
                      "neoaprs/web/mapwire.py": "from .layerwire import MapLayer\nfrom .packetwire import PacketRow\n", "neoaprs/web/layerwire.py": ""})
    assert wire_imports_of_a_sibling(g) == [("neoaprs.web.mapwire", "neoaprs.web.packetwire"), ("neoaprs.web.stationwire", "neoaprs.web.packetwire")]


def test_nothing_of_a_layer_of_traffic_reaches_the_stations_the_database_the_packets_or_a_radio(graph: dict[str, list[Import]]) -> None:
    assert through_the_wall(graph) == [], "the wall round the map's layers of traffic: a module of the layers imports one of WALLED, or a module that is not one of LAYER_IMPORTERS imports a module of the layers"


def test_a_layer_module_that_imports_the_station_book_or_a_service_of_the_radios_and_a_module_that_takes_a_layer_into_the_stations_are_found() -> None:
    g = import_graph({"neoaprs/layerthing.py": "from .geo import distance_km\nfrom .stationbook import me_position\n", "neoaprs/services/layers.py": "from neoaprs.services.common import Radio\nfrom neoaprs.layerthing import Thing\n",
                      "neoaprs/web/layerfeed.py": "from neoaprs.web.packetwindow import PacketWindow\nfrom neoaprs.web.layerwire import LayerThing\n", "neoaprs/web/views.py": "from neoaprs.web.layerwire import LayerThing\n",
                      "neoaprs/wiring.py": "from neoaprs.services.layers import Layers\nfrom neoaprs.stationbook import StationBook\n", "neoaprs/configlayers.py": "from .layerthing import SHIP_SOURCES\n", "neoaprs/stationbook.py": "from neoaprs import shiptable\n",
                      "neoaprs/geo.py": "", "neoaprs/services/common.py": "", "neoaprs/web/packetwindow.py": "", "neoaprs/web/layerwire.py": "", "neoaprs/shiptable.py": ""})
    assert through_the_wall(g) == [("neoaprs.layerthing", "neoaprs.stationbook"), ("neoaprs.services.layers", "neoaprs.services.common"), ("neoaprs.stationbook", "neoaprs.shiptable"),
                                   ("neoaprs.web.layerfeed", "neoaprs.web.packetwindow"), ("neoaprs.web.views", "neoaprs.web.layerwire")]      # (the composition root, the settings' rows and one layer module of another are not)


def test_only_the_composition_root_imports_the_services(graph: dict[str, list[Import]]) -> None:
    assert services_imported_outside_the_root(graph) == []


def test_signals_are_connected_in_the_composition_root_only(real_tree: Tree) -> None:
    counts = connect_sites(real_tree)
    for root in COMPOSITION_ROOTS:
        assert counts.get(root), f"{root} is listed as a place for wiring but connects nothing: delete it from COMPOSITION_ROOTS (and name the new root)"
    elsewhere = wiring_outside_the_root(counts)
    expected = {rel: n for rel, (n, _why) in CONNECTS.items()}
    assert elsewhere == expected, "Signal.connect outside the composition root (move the wiring there; the allowlist CONNECTS only shrinks and its counts are exact):\n" + repr(elsewhere)


def test_the_ways_out_of_the_process_are_the_listed_ones_and_only_the_alert_command_is_a_shell_line(real_tree: Tree) -> None:
    found = reaches_out(real_tree)
    changed = reach_not_as_listed(found)
    assert changed == {}, "a module starts a program, runs a shell line, replaces the process, opens a URL or the system's browser, or hands a string to pyserial, and REACHES_OUT does not say so (or says what the module no longer does). " + \
        "Look at what the place starts or opens, and whether a text from the air, from the page or from a setting can get into it; then make the entry say it:\n" + "\n".join(f"  {rel}: {what}" for rel, what in changed.items())
    assert shell_lines(found) == SHELL_LINES, "a shell is given a line somewhere else than in the alert command (neoaprs/services/alerts.py), or a second time there: start the program from a list of arguments"
    assert all(len(why) > 30 for _kinds, why in REACHES_OUT.values())


def test_a_radio_is_named_by_fm_or_hf_only_in_the_descriptions_of_the_types_and_the_rest_is_listed_until_its_owner_takes_it_out(real_tree: Tree) -> None:
    changed = radio_words_not_as_listed(radio_words(real_tree))
    assert changed == {}, "a radio or a kind named by fm or hf outside the descriptions of the types (neoaprs/radiotypes/): ask the radio (its kind, its type's limits, allowed and can, its id) instead, " + \
        "so that a third kind needs no line here; a file that names fewer than RADIO_WORDS says lowers its count (an entry at 0 goes):\n" + "\n".join(f"  {rel}: {what}" for rel, what in changed.items())
    assert all(owner in ("W3", "open", "kept") and len(why) > 20 for _n, owner, why in RADIO_WORDS.values())


# ---- every rule fails on a violation ------------------------------------------------------------------------------------------------------------------------

def tree_of(**files: str) -> Tree:
    return {f"neoaprs/{name}.py": source for name, source in files.items()}


def graph_of(**files: str) -> dict[str, list[Import]]:
    return import_graph(tree_of(**files))


def test_the_sound_card_type_and_the_dummy_lora_type_are_described_in_the_type_modules_and_the_code_of_direwolf_names_no_radio_by_its_kind_or_number(real_tree: Tree) -> None:
    assert all(rel.startswith(TYPE_MODULES) for rel in ("neoaprs/radiotypes/soundcard.py", "neoaprs/radiotypes/dummylora.py")) and unplaced({"neoaprs/radiotypes/soundcard.py": ""}) == []
    direwolf = [rel for rel in real_tree if rel.startswith(("neoaprs/direwolf", "neoaprs/childprogram", "neoaprs/usbtie", "neoaprs/winmm"))]
    assert len(direwolf) == 8, direwolf
    found = radio_words(real_tree)
    assert {rel: found[rel] for rel in direwolf if rel in found} == {} and not set(direwolf) & set(RADIO_WORDS), "Direwolf's code asks its radio, as a third kind would need"


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
    g = import_graph({"neoaprs/desktop/qtshell.py": "from PySide6.QtCore import QObject\n", "neoaprs/desktop/webshell.py": "import pystray\nfrom PIL import Image\nimport gi\nfrom PyObjCTools import AppHelper\n", "neoaprs/desktop/menu.py": "import webview\nfrom PySide6 import QtWidgets\n",
                      "neoaprs/store.py": "import pystray\n", "neoaprs/desktop/__init__.py": "", "neoaprs/desktop/sizekeep.py": "from gi.repository import Gtk\n"})
    assert violations(g) == {
        ("neoaprs.desktop.sizekeep", "gi.repository"): "a GUI toolkit outside the shells of neoaprs/desktop/",
        ("neoaprs.desktop.menu", "webview"): "a GUI toolkit outside the shells of neoaprs/desktop/",
        ("neoaprs.desktop.menu", "PySide6"): "a GUI toolkit outside the shells of neoaprs/desktop/",
        ("neoaprs.store", "pystray"): "a GUI toolkit outside the shells of neoaprs/desktop/",
    }


def test_a_module_nobody_placed_and_a_layer_entry_without_a_file_are_found() -> None:
    assert unplaced(tree_of(clock="", brand_new="")) == ["neoaprs.brand_new"]
    assert unplaced({"neoaprs/web/anything.py": "", "neoaprs/services/x.py": ""}) == []                  # neoaprs/web/ is delivery, neoaprs/services/ is services
    assert "neoaprs.signal" in stale_layers(tree_of(clock=""))


def test_the_planned_modules_are_placed_and_not_stale_and_the_types_of_radio_are_the_domain_whole() -> None:
    assert PLANNED <= {f"neoaprs.{n}" for names in LAYERS.values() for n in names}, "a planned module has its layer in LAYERS"
    assert not set(stale_layers(tree_of(clock=""))) & PLANNED, "a planned module that is not written yet is not a stale entry"
    assert layer_of("neoaprs.radiotypes") == layer_of("neoaprs.radiotypes.mercury") == "domain"
    assert unplaced({"neoaprs/radiotypes/dummylora.py": ""}) == []                                     # a new family of types needs no layer line


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


def test_a_way_out_of_the_process_is_found_under_any_name_and_a_type_or_a_file_that_left_the_list_is_told_apart(monkeypatch: pytest.MonkeyPatch) -> None:
    tree = {"neoaprs/a.py": "import subprocess as sp\nfrom os import execv as go\nimport asyncio\n\ndef f(start=sp.Popen):\n    go('/bin/x', ['x'])\n\nasync def g(line):\n    await asyncio.create_subprocess_shell(line)\n",
            "neoaprs/b.py": "import subprocess\n\ndef f(process: subprocess.Popen[str], wait: float = subprocess.PIPE) -> subprocess.Popen[str]:\n    raise subprocess.TimeoutExpired('x', 1)\n",
            "neoaprs/c.py": "import urllib.request\nimport serial\n\ndef f(url):\n    import webbrowser\n    webbrowser.open(url)\n    serial.serial_for_url(url)\n    return urllib.request.build_opener().open(url)\n",
            "neoaprs/d.py": "from subprocess import run\n\ndef f(line, loop):\n    run(line, shell=True)\n    run(['ls'], shell=False)\n    loop.subprocess_exec(None, 'ls')\n",
            "neoaprs/e.py": "def f(os, subprocess):\n    return os.path.join(subprocess.run, 'b')\n"}
    found = reaches_out(tree)
    assert found == {"neoaprs/a.py": {"program": 1, "exec": 1, "shell": 1}, "neoaprs/c.py": {"browser": 1, "serial": 1, "url": 1}, "neoaprs/d.py": {"program": 3, "shell": 1}}      # b.py names a type, a constant and an error; e.py imported nothing
    assert shell_lines(found) == {"neoaprs/a.py": 1, "neoaprs/d.py": 1}
    monkeypatch.setattr(sys.modules[__name__], "REACHES_OUT", {"neoaprs/a.py": ("program shell exec", "a made-up file that is listed with all it does"), "neoaprs/c.py": ("url serial", "a made-up file that began to open the browser after it was listed"),
                                                               "neoaprs/gone.py": ("program", "a made-up file that starts nothing any more")})
    assert reach_not_as_listed(found) == {"neoaprs/c.py": "does: url browser serial; REACHES_OUT says: url serial", "neoaprs/d.py": "does: program shell; REACHES_OUT says: nothing (it is not listed)",
                                          "neoaprs/gone.py": "does: nothing; REACHES_OUT says: program"}


def test_a_flush_and_a_before_write_are_found_wherever_they_hide() -> None:
    tree = {"neoaprs/a.py": "def _flush(self):\n    pass\n", "neoaprs/b.py": "def f(store):\n    store._flush()\n", "neoaprs/c.py": "def g(s):\n    s.before_write = 1\n", "neoaprs/d.py": "flush = 1\n_flush = 2\n",
            "neoaprs/e.py": "def flush_now(): pass\n"}
    assert forbidden_names(tree) == {"neoaprs/a.py": [1], "neoaprs/b.py": [2], "neoaprs/c.py": [2], "neoaprs/d.py": [2]}


def test_a_radio_named_by_fm_or_hf_is_found_in_a_string_an_id_and_a_name_and_not_in_prose_a_type_module_another_word_or_the_band(monkeypatch: pytest.MonkeyPatch) -> None:
    tree = {"neoaprs/a.py": '"""Sent on the hf radio: prose."""\nfrom .radiotype import FM_ID\nif radio.kind == "hf" and radio.id == FM_ID:\n    ctl.hf_port.close()\n',
            "neoaprs/b.py": "def start_hf(fm, *, fm_count=0):\n    return HfScene, offhand, half, f'{kind} hf', 'HF', HF\n",
            "neoaprs/c.py": "x = updatecheck.hf_dial or HF_DIAL\n", "neoaprs/radiotypes/dummy.py": "TYPE = ('hf', HF_LIMITS)\n", "neoaprs/radiotype.py": "Kind = Literal['fm', 'hf']\n"}
    assert radio_words(tree) == {"neoaprs/a.py": 4, "neoaprs/b.py": 4}      # a: the alias and the use of FM_ID, "hf", hf_port; b: start_hf, fm, fm_count, HF (HfScene, half and the texts are no word of a kind)
    monkeypatch.setattr(sys.modules[__name__], "RADIO_WORDS", {"neoaprs/a.py": (4, "W3", "a made-up file that is listed as it is"), "neoaprs/b.py": (5, "W3", "a made-up file that named one more before"),
                                                               "neoaprs/gone.py": (2, "W3", "a made-up file that names none any more")})
    assert radio_words_not_as_listed(radio_words(tree)) == {"neoaprs/b.py": "names a radio by fm or hf 4 times; RADIO_WORDS says 5", "neoaprs/gone.py": "names a radio by fm or hf 0 times; RADIO_WORDS says 2"}
    tree["neoaprs/d.py"] = "LORA = rules.kind == 'fm'\n"
    assert radio_words_not_as_listed(radio_words(tree))["neoaprs/d.py"] == "names a radio by fm or hf 1 times; RADIO_WORDS says 0"


def test_the_word_lora_and_radio_1_or_2_by_its_number_are_found_and_an_order_of_ids_or_another_id_is_not() -> None:
    tree = {"neoaprs/a.py": "if k == 'lora' or radio.id == 2 or radio_id != 1 or spec.radio in (1, 2):\n    pass\n",
            "neoaprs/b.py": "def f(db, radio, *, radio_id=1, holder_radio_id=2):\n    return 1 if radio is None else radio\n",
            "neoaprs/c.py": "g(radio_id=2)\nok = radio < 1 or record.msg_id == 1 or n == 2 or radio_id == 3\nx = None if record.msg_id is None else 1\n'''lora'''\n",
            "neoaprs/radiotypes/x.py": "KIND = 'lora'\nif radio.id == 1:\n    pass\n"}
    assert radio_words(tree) == {"neoaprs/a.py": 4, "neoaprs/b.py": 3, "neoaprs/c.py": 1}      # a: 'lora' and three comparisons; b: two defaults and the choice; c: the keyword (an order, a message's id, a number of nothing, radio 3 and the prose are none)
