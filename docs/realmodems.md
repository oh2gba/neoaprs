# The real modems on virtual cables

`.github/workflows/realmodems.yml` runs five NeoAPRS daemons on one GitHub runner, each starting the Direwolf and the Mercury that NeoAPRS carries, built by the
scripts the release builds them with (`scripts/build-direwolf --install`, `scripts/build-mercury --install`). The stations are joined by three virtual sound cables
instead of radios, and the tests of `tests/realmodems/` drive them through their page sockets as an operator would.

| station | radios | cable |
|---|---|---|
| A `OH2AA` | Packet, sound card, 1200 | VHF |
| G `OH2GW` | Packet, sound card, 1200 and Mercury, sound card; the pair of the two on, its call `OH2GW-12` | VHF and HF |
| B `OH2BB` | Mercury, sound card | HF |
| H1 `OH2HA`, H2 `OH2HB` | Packet, sound card, 300 | HF at 300 baud |

## What it proves

- A message from A to B with the pair's call as its path reaches B over Mercury, and B's ack comes back to A by way of the pair's call.
- The same from B to A.
- A beacon of A with only `WIDE1-1` in its path is heard by G and nothing of it goes out on G's Mercury or reaches B.
- A message addressed to G itself is acked by G and is not passed on to HF.
- A beacon of A with the pair's call in its path is heard by B.
- A message from H1 reaches H2 at 300 baud and H2's ack comes back, and both Direwolfs take the `MODEM 300` line the daemon writes without a
  complaint.
- The Mercury pinned now and the one pinned before (`PREVIOUS_*` of `neoaprs/mercury.py`, built by `scripts/build-mercury --previous --install`)
  carry a message from A to B and its ack, and one from B to A and its ack, once with B's daemon on the old Mercury and once with G's
  (`test_old_and_new.py`, A, G and B alone; the old station's daemon runs from a virtual environment whose `tools/mercury` is the old build).
- The real Mercury, started with the daemon's command line and configuration on the two ends of the HF cable, writes the lines the daemon
  reads: its start lines, `IAMALIVE`, `PTT ON` and `PTT OFF` for a frame, `BUSY ON`, `BUSY OFF` and `SN` at the other end with the frame
  handed over, `PTT ON` and `PTT OFF` for `TUNE` and `TUNE OFF`, and the line of a sound card that is not there; its four ports answer on
  127.0.0.1 and are refused from the runner's own address (`test_mercury_program.py`). It also records DATAC3 frames for the Windows job.

After the stations the job runs the suite's tests of the real programs (`tests/test_direwolf_real.py`, `tests/test_mercury_leadin.py`,
`tests/test_mercury_scope_real.py`), which the suite's guard keeps from every other run. The job `windows` then runs `test_windows.py` on
GitHub's Windows runner with the builds for Windows: what proves what is in [modem-updates.md](modem-updates.md).

All of it runs through the real programs: Direwolf's AFSK 1200 and 300 modems and Mercury's DATAC3 modem encode and decode the audio, each on its own ALSA device, with
the configuration and command line the daemon writes for them.

## What it does not prove

- Keying: every radio is keyed by VOX into a cable, so no keying line, CM108 pin or serial port is used.
- Real radios and real sound cards: the levels, the card's own delays, a radio's VOX and squelch times, noise and fading. The cables are clean and without delay.
- Windows and macOS: the stations run on Linux, and the cables are PipeWire's; Windows decodes recordings only.
- ALSA hardware devices (`plughw:CARD=…`): the daemons are given the cables' ALSA device names as their sound cards, so the listing of cards (`mercury -z`) and
  the card's own volume controls are not used.

## The cables

The kernels of GitHub's runners carry no sound modules, so `snd-aloop` cannot be loaded: ubuntu-26.04, ubuntu-24.04 and the arm images run a 7.0 Azure or AWS
kernel with no `linux-modules-extra` package, and the 6.8 Azure kernel of ubuntu-22.04 has the package but no sound in it; ubuntu-26.04 has no `/proc/asound` at
all. The cables are PipeWire instead (`tests/realmodems/cables`, run by the workflow): PipeWire, WirePlumber and pipewire-pulse as the runner's user, a null sink
for what each end plays (`vhf_a_out` …) and a source that remaps that sink's monitor (`vhf_a_in` …). `tests/realmodems/asoundrc`, copied to `~/.asoundrc`, gives
each end an ALSA device of PipeWire's plugin (`vhf_a`, `vhf_g`, `hf_g`, `hf_b`, `p300_h1`, `p300_h2`) that plays into its own sink and records the other end's source, so a station
hears the other end and never itself. The workflow plays a tone into one end of the HF cable and checks that it is heard at the other before the stations start.

PulseAudio's ALSA plugin is not enough: Mercury opens its device with mmap access and reads it by `snd_pcm_avail_update` and `snd_pcm_mmap_begin`
(`audioio/ffaudio/ffaudio/alsa.c`), which the pulse plugin does not offer (`snd_pcm_hw_params_set_access` fails), and through a `plug` in front of it the capture
delivers nothing (Mercury: "capture stalled"). PipeWire's plugin offers mmap. Direwolf reads and writes, and runs over either.

The carried modems work over the plugin because the workflow builds them on the runner itself (`--install`, as ci.yml's job sim does): the bundled
`lib/libasound.so.2` and `share/alsa/` are the runner's own, so the system's plugin matches the library that loads it, and the bundled `alsa.conf` reads
`~/.asoundrc`.

## The refusal

The tests start real modems that would key a real radio on a real card, so they refuse to run anywhere but on such a runner:

- they are collected only with `NEOAPRS_REAL_MODEMS=1` (`tests/realmodems/conftest.py`); a normal run, `scripts/check` included, collects none of them;
- with the variable set, before any daemon starts, `tests/realmodems/stations.py` (`refusal`) ends the run unless the computer is Linux, has no sound card at all
  (`/proc/asound/cards` lists none, or the kernel has no sound), `~/.asoundrc` is the file of `tests/realmodems`, the sound server's sinks are its six null sinks
  and no other, and every radio of the stations is on one of its devices.

`tests/test_realmodems_guard.py`, in the normal suite, holds the refusal. The daemons run without the no-devices switch (it would refuse the modems), with no serial
port to find, no version page and no player.

## How to run it

```
gh workflow run realmodems.yml --ref master
gh run watch <id> --exit-status
```

or Actions, realmodems, Run workflow (a workflow that is not on master yet is dispatched by its number: `gh workflow run <workflow id> --ref <branch>`). It
also runs on every push to master and every night, and `scripts/release` waits for its run of the release commit. The folders of the stations (each
daemon's log and output, the modems' configurations) are the artifact `realmodems-stations` of every run, the recording for Windows
`realmodems-recordings`. Run it by hand on a branch after a change to the pair, the Mercury or Direwolf driver, or a modem's pin.
