"""Every module that reads what comes from outside (the air, a device, a modem, a server, the page, a
setting) has a random-input test: a tests/test_properties_*.py file imports it; a module with a
function named as a reader is in the list below or says why it reads nothing from outside.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROPERTY_FILES = sorted(ROOT.glob("tests/test_properties_*.py")) + [
    ROOT / "tests" / "test_tnc2text.py",
    ROOT / "tests" / "test_settings_reach.py",
]
READER_PREFIXES = ("parse", "decode", "read_", "from_line", "loads", "split_")

PARSERS = """
    aisdecode aisstream aprsextension aprsfreq aprsisline aprslocator aprsmessage aprsmice aprsmiceout aprsnmea
    aprsparse aprsposition aprsstorm aprstelemetry aprsthirdparty aprsweather ax25 btle btserial btsdp callsign chat
    configvalues digitraffic direwolf gpsfeed gpsfix kiss loraboard loralist mercury mercurycards mercuryscope packet
    packetcodec pmtilesarchive pmtilesformat qrutext radarcape readsb rigctld route satellitelist satellites skeds
    tcplisten tnc2line tnc2text tncmode tnctextreader updateasset versions web.confighandlers web.dispatch
    web.scopefeed
""".split()

# Modules with a function named as a reader that reads nothing from outside, each with why.
NOT_OUTSIDE = {
    "cli.": "the command line's own options (argparse)",
    "desktop.cmd": "the desktop app's own options (argparse)",
    "desktop.gtkenv": "the environment the app was started with",
    "cli.logfile": "our own log files",
    "cli.supportgather": "our own database, read for the support file",
    "storesql": "our own database",
    "services.mapcli": "the map command's own options (argparse)",
}


def imported_by_property_tests() -> set[str]:
    names: set[str] = set()
    for path in PROPERTY_FILES:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "neoaprs":
                package = node.module.removeprefix("neoaprs").removeprefix(".")
                names.add(package)
                names.update(f"{package}.{alias.name}".removeprefix(".") for alias in node.names)
            elif isinstance(node, ast.Import):
                names.update(alias.name.removeprefix("neoaprs.") for alias in node.names)
    return names


def modules_with_readers() -> set[str]:
    found = set()
    for path in (ROOT / "neoaprs").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(isinstance(node, ast.FunctionDef) and node.name.startswith(READER_PREFIXES) for node in tree.body):
            found.add(".".join(path.relative_to(ROOT / "neoaprs").with_suffix("").parts))
    return found


def test_every_parser_has_a_random_input_test() -> None:
    missing = sorted(set(PARSERS) - imported_by_property_tests())
    assert missing == [], f"no tests/test_properties_*.py imports {missing}"


def test_every_module_with_a_reader_is_a_parser_or_says_why_not() -> None:
    def explained(module: str) -> bool:
        return module in PARSERS or any(module.startswith(prefix) for prefix in NOT_OUTSIDE)

    assert sorted(module for module in modules_with_readers() if not explained(module)) == []


def test_the_lists_name_modules_that_are_there() -> None:
    for module in PARSERS:
        assert (ROOT / "neoaprs" / (module.replace(".", "/") + ".py")).is_file(), module
