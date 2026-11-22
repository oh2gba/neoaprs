"""The Direwolf of the Windows app, as the release workflow's Windows job checks it:
`smoke_direwolf.py PROGRAM` starts the program the way it says who it is (`-h`: its banner, the
optional parts it holds, its options), and the program must be the pinned release, with `cm108-ptt`
as its one optional part, and know NeoAPRS's options -Q, -G and -R. Only that: the runner has no
sound device to count on, and Direwolf ends before it listens when it cannot open one, so the
listening on this computer only, the WinMM devices, the stop at the end of its input and a CM108 key
are the Windows VM's (docs/direwolf.md). Run with the Python that has NeoAPRS installed."""
import subprocess
import sys
from pathlib import Path

from neoaprs import direwolf

TIMEOUT_SEC = 60


def check(text: str) -> list[str]:
    """What is wrong with what the program said; nothing when it is the pinned Direwolf that NeoAPRS
    builds."""
    wrong = []
    if direwolf.BANNER.replace("%d.%d.%d", direwolf.VERSION) not in text:
        wrong.append(f"it is not Direwolf {direwolf.VERSION}")
    optional = next((line.split(":", 1)[1].split() for line in text.splitlines() if line.startswith("Includes optional support for:")), [])
    if optional != ["cm108-ptt"]:
        wrong.append(f"its optional parts are {' '.join(optional) or 'none'}, not cm108-ptt alone")
    for option in ("-Q ", "-G pct", "-R ms"):
        if option not in text:
            wrong.append(f"it has no option {option.split()[0]} (packaging/direwolf/quit.patch, txlevel.patch and rxlevel.patch)")
    return wrong


def main() -> int:
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_file():
        print(__doc__)
        return 2
    done = subprocess.run([sys.argv[1], "-h"], capture_output=True, text=True, errors="replace", timeout=TIMEOUT_SEC, check=False)
    said = done.stdout + done.stderr
    print(said)
    wrong = check(said)
    for line in wrong:
        print(f"smoke_direwolf: {line}", file=sys.stderr)
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
