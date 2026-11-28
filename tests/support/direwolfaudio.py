"""Recorded audio of Direwolf's modulator, for the regression check of its demodulator
(tests/test_direwolf_real.py) and the Windows job of .github/workflows/realmodems.yml: the frames
NeoAPRS sends, as Direwolf's gen_packets plays them at 1200 and 300 baud, and a series of 1200 baud
frames under rising noise. `python -m tests.support.direwolfaudio GEN_PACKETS FOLDER` makes the files
again; tests/fixtures/audio/ holds the ones made with Direwolf 1.8.1 (docs/modem-updates.md)."""

import re
import subprocess
import sys
import wave
from pathlib import Path

from neoaprs import TOCALL
from neoaprs.aprsmessage import format_ack, format_message
from tests.conftest import ROOT

FIXTURES = ROOT / "tests" / "fixtures" / "audio"
RATE = 11025
# gen_packets's own frame under rising noise, and how many of them Direwolf 1.8.1's atest decodes
NOISE_FRAMES = 20
NOISE_DECODED = 5
FRAMES = (
    f"OH2AA>{TOCALL},WIDE1-1:!6010.20N/02456.40E-NeoAPRS recorded audio",
    f"OH2AA>{TOCALL}::" + format_message("OH2BB", "recorded audio", "1").decode("ascii"),
    f"OH2BB>{TOCALL}::" + format_ack("OH2AA", "1").decode("ascii"),
    f"OH2AA>{TOCALL}:>NeoAPRS",
)
# file name: gen_packets options
FILES = {
    "direwolf-1200.wav": ("-B", "1200"),
    "direwolf-300.wav": ("-B", "300"),
}
NOISE_FILE = "direwolf-1200-noise.wav"
_COLOUR = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def decoded(atest: str, path: Path) -> list[str]:
    """The frames Direwolf's atest decodes of the file, as TNC2 text, at the file's own baud rate."""
    baud = "300" if "-300" in path.name else "1200"
    done = subprocess.run([atest, "-B", baud, str(path)], check=True, capture_output=True, timeout=120)
    text = _COLOUR.sub("", done.stdout.decode("utf-8", errors="replace"))
    return [line[4:].rstrip() for line in text.splitlines() if line.startswith("[0] ")]


def make(gen_packets: str, folder: Path) -> list[Path]:
    """Write the files of FILES with FRAMES, and NOISE_FILE, into `folder`."""
    folder.mkdir(parents=True, exist_ok=True)
    made = []
    for name, options in FILES.items():
        parts = []
        for number, line in enumerate(FRAMES):
            # gen_packets sends a line's end with it, so each frame is a file of one line without one
            text, part = folder / f"frame-{number}.txt", folder / f"frame-{number}.wav"
            text.write_text(line, encoding="ascii")
            subprocess.run([gen_packets, *options, "-r", str(RATE), "-o", str(part), str(text)], check=True)
            with wave.open(str(part), "rb") as read:
                parts.append((read.getparams(), read.readframes(read.getnframes())))
            text.unlink()
            part.unlink()
        with wave.open(str(folder / name), "wb") as out:
            out.setparams(parts[0][0])
            for _, frames in parts:
                out.writeframes(frames)
        made.append(folder / name)
    subprocess.run(
        [gen_packets, "-B", "1200", "-r", str(RATE), "-n", str(NOISE_FRAMES), "-o", str(folder / NOISE_FILE)],
        check=True,
    )
    return [*made, folder / NOISE_FILE]


if __name__ == "__main__":
    for path in make(sys.argv[1], Path(sys.argv[2])):
        print(path, path.stat().st_size)
