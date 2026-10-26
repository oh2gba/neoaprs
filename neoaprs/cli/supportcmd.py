"""`neoaprs support [--data DIR] [--out FOLDER] [--show] [--pause]`: makes the support bundle, one zip with the logs and the facts a developer needs to see what is wrong at your station, and says where it is.

The bundle is made from the data folder, without the daemon: it works when the daemon will not start, and it does not matter whether one runs (the summary says whether one holds the folder). The state that
only a running daemon knows (the radio's latest lines, the GPS, the beacon) is in the bundle that the page's Support button makes. Nothing in the data folder is changed or sent: the file goes to your Desktop (the home folder when there is none) or the
folder of `--out`, and the command prints its path and what to do with it.

`--show` opens the file manager at the file. `--pause` waits for Enter before it ends when it runs in a console (what the Windows Start menu entry "NeoAPRS support logs" does, so that its window stays to be read)."""
import argparse
import sys
from pathlib import Path

from neoaprs.paths import default_data_dir

from .output import say
from .supportmake import Made, desktop_dir, make_bundle, made_text, show_file
from .supportreadme import MAIL, SEND_WORDS


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="neoaprs support", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", default=str(default_data_dir()), help="the data folder to make the bundle of; default %(default)s")
    p.add_argument("--out", default="", metavar="FOLDER", help="the folder the file goes to; default your Desktop folder if there is one, else your home folder")
    p.add_argument("--show", action="store_true", help="open the file manager at the file")
    p.add_argument("--pause", action="store_true", help="wait for Enter before ending, when this runs in a console")
    return p


def tell(made: Made) -> None:
    print(made.path)
    say(f"support file made ({made_text(made)}): {made.path}\n\nSend it to {MAIL} with a few words: {SEND_WORDS}.\nOpen README.txt in it first if you want to see what is in it.")


def pause() -> None:
    """Waits for Enter, but only where a person is at a console to press it."""
    if sys.stdin is not None and sys.stdin.isatty():
        try:
            input("Press Enter to close ")
        except (EOFError, KeyboardInterrupt):
            pass


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    data = Path(args.data).expanduser().resolve()
    out = Path(args.out).expanduser() if args.out else desktop_dir()
    try:
        made = make_bundle(data, out)
    except OSError as e:
        say(f"support: the file could not be written to {out}: {e}\nGive another folder with --out.")
        code = 1
    else:
        tell(made)
        if args.show and not show_file(made.path):
            say(f"support: the file manager could not be started; the file is {made.path}")
        code = 0
    if args.pause:
        pause()
    return code
