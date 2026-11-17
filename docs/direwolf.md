# Direwolf in NeoAPRS

For developers: every number NeoAPRS fixes for the radio type **Sound card**, whose modem is the Direwolf that NeoAPRS carries and starts, where each comes from, and how the program is built, started and checked. The source was read at the tag 1.8.1 (commit `a231971a652bfb574a4bae9a5d875fbce53d2267`), and the file and line references below are to that tree.

## What it is

A radio of the type is an FM radio behind a sound-card interface (a Digirig, an AIOC, a USB sound card). NeoAPRS starts the Direwolf it carries for it, with a configuration it writes at every start in the
radio's own folder (`radios/<id>/`), and reaches it on its KISS port as it reaches any KISS server over TCP. The code: `neoaprs/direwolf.py` (pure: the pins, the configuration, the command line, the
keying proposed, what the program prints), `neoaprs/direwolfprogram.py` (one run of the program), `neoaprs/direwolfmodem.py` and `neoaprs/direwolftune.py` (the supervisor: the claims, the restarts, Tune and the
keying test), `neoaprs/direwolfdriver.py` (the radio's driver), `neoaprs/winmm.py` (the WinMM devices on Windows), `neoaprs/radiotypes/soundcard.py` (the type). What it shares with the Mercury modem is
`neoaprs/childprogram.py` (the run of a program, its stop, a run left behind, the kernel's table of sockets) and `scripts/buildtool.py` (the parts of the build that are not one program's).

The sound cards are listed by the bundled Mercury (`mercury -z`), so the two types name a card by the same id and one card is one resource of the station: a Sound card radio and a Mercury radio on one card are refused
with the holder's name. Every installer that carries Direwolf carries Mercury too; an installation without Mercury lists no card, and the radio's card is then the one its setting names. With no card named and none
listed that is a radio's (`direwolf.own_card`: the one that stands out, else the system's default when it names itself as a radio's or an interface's), the radio waits for one (the reason `sound_card`) and no Direwolf
starts: the system's default device may be the computer's speakers.

## The configuration and the command line

`radios/<id>/direwolf.conf`, rewritten at every start (`direwolf.conf_text`):

| line | why |
|---|---|
| `ADEVICE <card>` | the card's id (Linux: its stable ALSA name, `plughw:CARD=CODEC,DEV=0`; never `default`); on Windows the WinMM numbers of its input and output (`ADEVICE 1 3`) |
| `ACHANNELS 1`, `CHANNEL 0`, `MODEM 1200` | one channel of AFSK 1200; one stereo card as two radios is not offered, the claims hold a card whole |
| `PTT CM108`, `PTT <port> RTS`, `PTT <port> DTR`, none | the keying `cm108`, `rts:PORT`, `dtr:PORT`, `vox`; after ADEVICE, because `PTT CM108` looks up the HID of the output device set before it (`config.c:2140-2145`) |
| `KISSPORT 0`, `KISSPORT <port>` | slot 0 holds 8001 until it is cleared, and a new port takes the first empty slot (`config.c:877-884`, `4985-5020`) |
| `AGWPORT 0`, `DNSSD 0` | no AGW server (`server.c:468-472`), no announcement on the LAN (`dns_sd_enabled = 1` by default, `config.c:889`) |

No `MYCALL`: Direwolf asks for it only before it digipeats or gates (`config.c:5690-5720`), and sends KISS frames as given, so a change of the station's call restarts no radio. TXDELAY, TXTAIL, SLOTTIME and PERSIST
are Direwolf's defaults (300 ms, 100 ms, 100 ms and 63, `audio.h:497-500`); whether 300 ms suits a VOX radio is to be looked at on the air.

The command (`direwolf.command`): `direwolf -c <conf> -t 0 -q d -a 2 -R 100 -d on -Q -G <pct>`. `-t 0` no colours; `-q d` no description of each packet (NeoAPRS decodes); `-a 2` the audio statistics every two seconds
(the log, DEBUG, and the radio's row: its `rx_level`); `-R 100` the receive level every 100 ms of audio read, `RXLEVEL 0 = N` (rxlevel.patch), which never reaches the log; `-d o` prints `PTT 0 = 1/0` at each key and unkey, VOX too (`ptt.c:1341-1343`), and `DCD 0 = 1/0` at each carrier; `-d n` prints each frame the line hands it ("<<< Data frame from KISS client application",
`kiss_frame.c:464`), which the daemon counts and does not log; `-Q`, `-G` and `-R` are NeoAPRS's patches. The working folder is the program's own (`direwolfprogram.working_folder`), so it reads the `data/tocalls.yaml` and
`data/symbols-new.txt` it carries before any of a system Direwolf (`deviceid.c:229-243`, `symbols.c:267-279`).

## The numbers

| number | value | from |
|---|---|---|
| the first KISS port | 8002 | 8001 is Direwolf's default, where an operator's own Direwolf may listen; from there up, the first that no other radio's modem holds (the claims, kind `modem_ports`) and that is free; kept for a program started again |
| the ports tried | 50 | below Mercury's 8100 |
| the level of a packet heard | 0 to 200 | Direwolf's own scale: "cranking the input level way up produces 199" (`direwolf.c:1329`) |
| too low, too high | under 5, over 110 | Direwolf's own warnings (`direwolf.c:1336-1349`) |
| the good band | 30 to 70 | round Direwolf's "most stations are around 50"; a choice, not a measurement, as Mercury's good range is |
| the transmit level | -20 to 0 dB | Direwolf's amplitude as a percentage, 100·10^(dB/20) (`-G`, txlevel.patch; the constant was 100, `direwolf.c:183`) |
| Tune | 10 s | the alternating mark and space tones (`-x a`), long enough to read the deviation off a meter |
| the keying test | 1 s | the PTT alone (`-x p`); the mark tone (`-x m`) on VOX, which silence does not key |
| the stop | 3 s, then SIGINT, 3 s, then the kill | its cleanup sleeps one second (`direwolf.c:1695-1699`) |

The level shown is the level as it is now. The radio's row in the topic `radios`, which every page has, carries Direwolf's audio statistics every two seconds (`-a 2`) and each packet's own level when one is heard;
null while Direwolf does not run. A page whose Receive level row is in view asks for more (`radio_level`): the level Direwolf says every 100 ms (`-R 100`), sent to that page alone, in the pattern of the scope's feed
(`neoaprs/web/levelfeed.py`: the level now at once, then each change; a page that is behind is skipped; nothing is sent, and the level is not followed, while no page looks). Between packets it is the channel's noise,
or nothing with the radio's squelch closed or the radio off, which is what the bar is for: it shows that audio arrives, and at once when a card is chosen, a plug is moved or the radio's volume is turned. (Until 0.20.1
it was the latest packet's level, which stood on the bar for ever.)

All three numbers are `demod_get_audio_level` of channel 0 (`demod.c:1069`): half of the peak to peak of the samples read (`demod_process_sample`, `demod.c:986-997`), 100 for a quarter of full scale. The transmit
level does not scale it: `-G` reaches the tone generators alone (`gen_tone_init`, `dtmf_init`, `morse_init`, `direwolf.c`), and the same audio read at `-G 30` and `-G 100` gives the same number
(`tests/test_direwolf_real.py`). A level that differs after a change of the Transmit level is the card's or the radio's: each change starts Direwolf again, which opens the card anew (a card with an automatic gain of its own
may settle at another level from there; not proven on the FTX-1).

## Running it

- **The lines.** Direwolf's lines carry no severity: the first 30 of a run go to the log at INFO, the error texts the driver reads at INFO counted the first, the tenth and every hundredth time, the rest at DEBUG. The
  frames of `-d n` and the level of `-R` are read and never logged, nor counted among the first lines of a run or kept among its last.
- **Running** once it says "Ready to accept KISS TCP client application 0 on port N" (`kissnet.c:606`). Then the kernel's table must show the port on 127.0.0.1 alone, or it is ended and not run again.
- **Its port taken** ("Bind failed", "Some other application is probably already using port N", `kissnet.c:567-574`): it runs on with no KISS, so it is ended and started on another port, and the line follows it.
- **A sound card that cannot be opened** ("Could not open audio device", "Pointless to continue without audio device", `audio.c:355`, `direwolf.c:1005-1011`) is the reason `sound_card`; **a keying device** ("ERROR can't open device", `ptt.c:945`) the reason `keying`, and so is a CM108 pin that keys nothing: `PTT CM108` with no chip on the card ("Could not determine USB Audio GPIO PTT device", `config.c:2185`: Direwolf would run on unkeyed) or a HID it cannot open or write at a key ("Could not open /dev/hidrawN for write", "Write to … failed", `cm108.c:1013`, `1059`: on Linux the rights of `/dev/hidraw*`), whose run is ended though `PTT 0 = 1` was said. All are started again after the back-off.
- **Windows.** Direwolf opens a WinMM device by number and runs on the system's default when the number names none (`audio_win.c:336-338`, `386-390`): the daemon finds the numbers itself (one input and one output whose names are the card's friendly names cut to 31 characters, `winmm.py`), and a run whose lists star another device, or that says a device does not match, is ended before its KISS port exists (`audio_open` runs before `kissnet_init`). On Windows Direwolf keys any CM108-class chip, the last of several (`cm108.c:785-817`): `cm108` is one claim for the station there, and "There are multiple USB Audio Devices with GPIO capability" ends the run (the reason `keying`). That WinMM names are the WASAPI friendly names cut short is proven on a Windows machine, not by a source.
- **The stop.** Its input is a pipe: closing it ends the program as a Ctrl-C does (`-Q`: "QRT", every keying output set to 0, a second, exit 0); then SIGINT on POSIX; then the kill (`taskkill /T /F` on Windows). A daemon that dies closes the pipe too. A run of ours left behind is ended at the next start by its id in `direwolf.pid`, when that process is still ours: its command line names the radio's configuration after `-c` (on Windows, where a command line cannot be read, its program file is the shipped one), so that an operator's own Direwolf, whose id a stale file may come to name, is left alone.
- **Tune and the keying test** are Direwolf's own calibration runs, which key the radio before any port opens (`direwolf.c:1056-1110`): the radio's Direwolf is stopped cleanly, the run keys the radio and is ended by closing its input, and the radio's Direwolf is started again on the same port; the line is told at once. Before the stop the frames
the line handed it go (it keyed after the last one counted by `-d n` and is unkeyed again; 5 s at most), so that none is lost; a new transmit level waits the same. One swap of the program at a time, and a swap is given
up when the radio was stopped or started again while it waited: no calibration run is ever started beside the radio's own. A new transmit level during the keying test leaves the test its second. The box shows the test and no problem meanwhile; the services wait as for any radio that is not free.
- **The keying the daemon chooses** when the setting leaves it (`direwolf.choose_keying`): an AIOC's CM108 pin whatever other cable is plugged in; else RTS of the one USB serial port that is part of the card's
  interface (on Linux the port on the card's own USB device or hub, `neoaprs/usbtie.py`; elsewhere the computer's one such port, when the card names itself as an interface's or a radio's); else VOX. A port that is not
  the card's (a programming cable, another radio's interface) is never keyed.
- **Under the no-devices switch** no Direwolf is started, no card is listed, and the radio's line has no port.

## The build

`scripts/build-direwolf` builds the pinned source with CMake (Release, no unit tests, no DNS-SD, gpsd, hamlib or libgpiod: the module names are those of `cmake/modules/Find*.cmake`), after six patches of
`packaging/direwolf/`, each held in the source after it:

| patch | what |
|---|---|
| `loopback.patch` | the KISS and AGW listeners (`kissnet.c`, `server.c`) and the UDP audio input (`audio.c`, `audio_win.c`) bind 127.0.0.1: they have no password, and Windows Firewall would ask the operator |
| `flush.patch` | `dw_printf` flushes each line (`textcolor.c`): on Windows the C runtime buffers a pipe |
| `quit.patch` | `-Q`: a thread reads standard input to its end and runs the cleanup; started after the keying is set up, before the `-x` run and before any port opens; inert when the audio is read from standard input |
| `txlevel.patch` | `-G pct`: the transmit level, 1 to 100 |
| `rxlevel.patch` | `-R ms`: the receive level of channel 0 every ms milliseconds (10 to 60000) of audio read, as `RXLEVEL 0 = N` on a line of its own (`audio_stats.c`, called with each buffer read on Linux and on Windows): the samples are counted, no timer of the system; the number is the statistics line's |
| `confpath.patch` | the path given with `-c` has room for 4095 characters (`direwolf.c`, `config_file[100]` cut it at 99: "Could not open configuration file", and a data folder with a long path started no Sound card radio). On Windows the path is then held to Windows's own 259 (`_fullpath` into `PATH_MAX`, `config.c:971`) |

Linux (Ubuntu 22.04, x86-64 and arm64): RUNPATH `$ORIGIN/lib`, `lib/libasound.so.2` and `lib/libudev.so.1` of the build machine (CM108 keying on Linux needs udev, `cm108.c:818-848`), `share/alsa/` without `ucm`,
`ucm2` and `topology`; `dev/` holds `gen_packets`, `atest` and `cm108` for the tests. The build runs the program: the banner must say the pinned release with `cm108-ptt` as its one optional part, its usage must list `-R`, and a quit run on
the UDP audio input must listen on 127.0.0.1 alone and end with "QRT" and exit 0 within 3 s of its input closing. Windows (cross-built in Debian trixie with MinGW-w64, `packaging/direwolf/mingw-w64.cmake`,
linked `-static -s`): the import table must name Windows's own DLLs alone, no MinGW DLL and no `dsound.dll`, and the file must hold the banner's format string `Dire Wolf Release %d.%d.%d, November 2025` (the
version is not a literal in the program). The release's Windows job asks the frozen app for its Direwolf (`neoaprs.exe db radios add direwolf`, refused with 2 where `direwolfprogram.find()` does not find it), and the install proof
(`scripts/check-windows --install`, step `direwolf`) asks the installed app the same and runs the installed `direwolf.exe -h`. The run checks on Windows belong to the Windows 11 N VM: a clean install, the start, `netstat -ano`, the WinMM match, the stop at the end of its input, a CM108 key.

The folder shipped, `direwolf/`: the program, `data/tocalls.yaml` (CC BY-SA 2.0 per its header) and `data/symbols-new.txt`, `LICENSE` (GPL-2.0-or-later), `LICENSE-geotranz.txt`, `LICENSE-misc.txt` (the OpenBSD and
NetBSD notices of `strlcpy` and `strlcat`), `SOURCE.txt` (the source offer, every patch, the GEOTRANS credit); on Windows also the licences of `external/hidapi` and `external/regex`; on Linux the two libraries and the
ALSA configuration. The AppImage and the .deb take it with `--direwolf TARBALL`, the Windows installer with `packaging/windows/bundle_tool.py direwolf`. Each of the three refuses Direwolf without Mercury, which lists the sound cards. A Mac carries no
Direwolf, nor does a wheel installed with pip or a checkout: the type is not offered there (the status's `unavailable_types`, `radioregistry.unavailable_types`), but under the no-devices switch it is, for a bench.

## Not confirmed

The SHA-256 of the source archive (taken once by the maintainer: [MAINTAINING.md](MAINTAINING.md#moving-the-direwolf-pin)); that the MinGW cross-build configures and links; that `winmm.dll` and `hid.dll` are on
Windows 11 N; that WinMM names are the WASAPI names cut to 31 characters; that Ubuntu 22.04's libudev reads a newer system's udev database; the name ALSA and Windows give an AIOC; whether 300 ms of TXDELAY suits a
VOX radio; the sizes the build prints.
