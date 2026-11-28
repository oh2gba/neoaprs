# What proves a modem update

NeoAPRS carries two programs of other projects: Rhizomatica's Mercury (the HF modem) and WB2OSZ's Direwolf (the sound-card
modem for 1200 and 300 baud). Their pins are the constants at the head of `neoaprs/mercury.py` and `neoaprs/direwolf.py`;
[MAINTAINING.md](MAINTAINING.md) has the steps of moving one. This page says which runs prove a new version, and what is still
proven by hand or not at all, so that an update is a change of the pins and a green run of these workflows:

- `ci.yml`: the suite on Linux and Windows, and the job `sim` (the HF net of `scripts/mercury-sim` on the real Mercury);
- `realmodems.yml`: on every push to master, every night and by hand; the release waits for it (`scripts/release`, step
  `realmodems`). Linux: the stations on virtual cables ([realmodems.md](realmodems.md)), the program tests of
  `tests/realmodems/test_mercury_program.py`, the suite's tests of the real programs; Windows: `tests/realmodems/test_windows.py`
  on the builds for Windows;
- `release.yml`: the builds for every system, and the smoke tests of the installed programs.

## The table

Linux x86-64 is GitHub's `ubuntu-26.04`, arm64 its `ubuntu-24.04-arm`, Windows `windows-2025`, macOS `macos-26`. NeoAPRS carries no
Direwolf on macOS.

| modem | what | Linux x86-64 | Windows | macOS | Linux arm64 |
|---|---|---|---|---|---|
| Mercury | builds, every patch applies and is found in the source | realmodems, sim, release | realmodems (`windows-builds`), release | release | release |
| Mercury | starts and ends cleanly | realmodems (`test_mercury_program`), sim | realmodems: ends in order on Ctrl-Break, the daemon's way | release: `mercury -V` | release: `-V` and its sockets |
| Mercury | carries frames between two stations | realmodems: the daemons on two ALSA ends of a cable; sim: daemons on the fifo backend | one way: decodes the frames the Linux build recorded | no | no |
| Mercury | the pinned version against the previous, both ways | realmodems (`test_old_and_new`: G new and B old, then G old and B new; a message and its ack each way) | no | no | no |
| Mercury | the patches hold | loopback: refused from the runner's own address, and the build reads the socket table; lead-in: `tests/test_mercury_leadin.py`; ffcpu: the build links on Ubuntu 26.04 | loopback: `smoke_mercury.py` (realmodems, release); sigbreak and flush: `test_windows`; dsound: the build refuses a program that imports dsound.dll | the build | the build, and the socket table |
| Mercury | the lines NeoAPRS reads still appear | realmodems (`test_mercury_program`): the start lines, `PTT ON` and `OFF`, `BUSY ON` and `OFF`, `SN`, `IAMALIVE`, `TUNE` and `TUNE OFF`, a sound card that is not there | no | no | no |
| Direwolf | builds, every patch applies and is found in the source | realmodems, release | realmodems (with `atest.exe`), release | — | release |
| Direwolf | starts and ends cleanly | the build's quit run, `tests/test_direwolf_real.py` (realmodems) | release: `direwolf -h` | — | the build's quit run |
| Direwolf | carries frames between two stations | realmodems: 1200 baud (A and G) and 300 baud (H1 and H2) | its demodulator decodes `tests/fixtures/audio/` (`atest.exe`) | — | no |
| Direwolf | the pinned version against the previous | the pinned build decodes audio made by Direwolf 1.8.1 (`tests/fixtures/audio/`), exact counts | the same, on Windows | — | no |
| Direwolf | the patches hold | loopback, quit, rxlevel and confpath: `tests/test_direwolf_real.py`; txlevel and flush: the build reads the source | the build reads the source; `-h` names `-Q`, `-G`, `-R` | — | the build |
| Direwolf | the lines NeoAPRS reads still appear | partly: `test_direwolf_real` (ready, level), realmodems (`Channel 0: 300 baud`, no `Line N:` complaint) | no | — | no |

## What is still by hand, or not proven

- **Windows, two stations live.** A virtual sound cable would let the daemons carry frames between two stations on the Windows
  runner, which has no sound device. VB-CABLE is donationware whose terms ask a paid licence for professional use and for use
  in an organisation, so the job installs none: the Windows job proves the builds by recordings
  instead (Mercury decodes the Linux Mercury's DATAC3 frames, Direwolf's demodulator the recorded audio), and the transmit side
  on Windows is not heard by anything. The installed programs on real sound cards are the Windows 11 N VM's (`scripts/check-windows`,
  [direwolf.md](direwolf.md)).
- **Mercury's lines of a lost sound card** (`the capture device delivers no audio`, `is no longer listed`, a reopen that fails with
  `AUDCLNT_E_DEVICE_INVALIDATED`) and **`Buffer full in capture buffer!`** come only from real hardware; `-z` (the list of cards)
  needs real cards. They are compared by hand with the source of a new version (MAINTAINING.md).
- **macOS and arm64** are built and started, never carrying frames.
- **Direwolf against an older Direwolf on the air**: the recordings prove the new demodulator on the old modulator's audio, not
  the new modulator heard by an old demodulator (there is one pinned Direwolf; Direwolf has had no release since 1.8.1).
- **The measured figures** of [mercury.md](mercury.md) (`scripts/mercury-measure`) are measured again by hand when a new
  Mercury changes the waveform, the busy detector or the gain.

## The recordings

`tests/fixtures/audio/` holds what Direwolf 1.8.1's `gen_packets` played of the frames NeoAPRS sends (a position, a message,
its ack and a status) at 1200 and at 300 baud, and 20 frames of 1200 baud under rising noise. The pinned Direwolf must decode
the four frames of each file unchanged and 5 of the 20. When a new Direwolf decodes more of the noisy ones, the count in
`tests/support/direwolfaudio.py` moves up with it; fewer is a finding. `python -m tests.support.direwolfaudio GEN_PACKETS FOLDER`
makes the files again. The Mercury recording is made fresh by each run of the Linux job (`NEOAPRS_RECORDINGS`) and passed to the
Windows job.

## The previous Mercury

`PREVIOUS_VERSION`, `PREVIOUS_COMMIT` and `PREVIOUS_SHA256` in `neoaprs/mercury.py` are the Mercury pinned before the current one;
`scripts/build-mercury --previous --install` builds it into `.venv/tools/mercury-previous` with the same patches. Moving the pin
moves the old values there. A patch that no longer applies to the old source keeps its old form, under the same name, in a
folder `previous` beside the patches, which the old build takes first.
