"""`README.txt` of the support bundle: what the file is, what to do with it, what is in it and what was left out. It is written for the person who made the bundle first (they may look in before they send it) and for the developer second."""
from datetime import datetime

from .supportbundle import Member
from .supportsummary import stamp

MAIL = "neoaprs@oh2gba.eu"
SEND_WORDS = "what you did, what you expected, what happened instead, and roughly when (the time finds it in the log)"

FILE_HELP: dict[str, str] = {
    "README.txt": "this file",
    "summary.txt": "the one screen to read first: version, system, station, radio, GPS, web page, database, and the last warnings and errors",
    "logs/neoaprs.log": "the log of the program (and neoaprs.log.1 and so on, the rotated ones, newest first); the newest lines are kept within a size budget",
    "logs/neoaprs-app.log": "the log of the desktop app (its window and tray icon), when there is one",
    "logs/journal.txt": "the last 3000 lines of what the system's journal has of the NeoAPRS service (Linux)",
    "settings.json": "every setting with its value; the access key is only said to be set",
    "state.json": "what the running daemon knows now: the radio and its latest lines, the GPS, the beacon, the base map, the update, the serial ports and who holds them, the size of the process",
    "doctor.txt": "the checks of `neoaprs doctor`: Python, folders, database, call, serial ports, the daemon, the map, the service",
    "database.txt": "the version of the database, its migrations, the rows of each table, the sizes of the files and whether SQLite finds the file sound",
    "packets.txt": "the last 1000 packets the radio heard and sent, and the last 200 that could not be decoded",
    "page.json": "what the page (the browser) told about itself when it asked for this bundle",
    "page-errors.json": "the errors the page reported to the daemon (up to 100, newest last)",
}

LEFT_OUT: tuple[tuple[str, str], ...] = (
    ("The access key", "it lets a device on your network into the page. The settings show it only as \"(set, N characters)\", and it is taken out of every file of the bundle."),
    ("The key and the certificates of the secure connection", "the private key is a secret, and nothing is wrong in them that the log does not say."),
    ("Your messages as the program keeps them", "they are yours, and a fault is found without them."),
    ("The database file itself", "it holds all of your messages and the history of your positions. database.txt says what is in it, and packets.txt has the latest packets."),
    ("The base map", "it is large and a fault is not in it."),
)


def listing(members: list[Member]) -> list[tuple[str, str]]:
    """Each file of the bundle with its line; the rotated logs are one with the log they belong to."""
    rows = [("README.txt", FILE_HELP["README.txt"])]
    for member in members:
        name = member.name
        if name in FILE_HELP:
            rows.append((name, FILE_HELP[name]))
        elif name.endswith(".error.txt"):
            rows.append((name, f"{name[:-len('.error.txt')]} could not be made; this file says why"))
    return rows


def readme_text(members: list[Member], made_at: datetime, version: str, by: str) -> str:
    lines = [
        "NeoAPRS support bundle", "======================", "",
        f"Made by NeoAPRS {version} on {stamp(made_at)} (UTC) by {by}. It is one zip of plain text files that lets the developer see what happens at your station. Nothing has been sent anywhere: the file is on your computer, and you may open it and read every file before you send it.",
        "",
        f"Send it to {MAIL} with a few words: {SEND_WORDS}.",
        "",
        "What is in it (open summary.txt first):", "",
    ]
    lines.extend(f"  {name}\n      {what}" for name, what in listing(members))
    lines += ["", "What was left out, and why:", ""]
    lines += [f"  {what}\n      {why}" for what, why in LEFT_OUT]
    lines += [
        "", "What is in it that you should know:", "",
        "  The log and packets.txt hold the packets the radio heard and sent. On APRS those are public, they went out over the air, and they include the texts of messages to and from other stations, with their calls.",
        "  The log also has the calls and the addresses of the devices that opened the page, and your station's call.",
        "  settings.json has every setting, the position of your station among them (the one your beacon sends, which is public too).",
        "",
    ]
    return "\n".join(lines)
