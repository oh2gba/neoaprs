# The Mercury numbers: where each one comes from

NeoAPRS decides a good deal for the operator of an HF radio with the Mercury modem: the mode, the frame, the ports, the sound card and the keying, how long a frame holds the radio, how long the
channel's busy signal is believed, the pace and the retries of messages, the beacon's floor and its random pause, and the frequencies the manual names. This page says, for every one of these values,
what it is, where it comes from, and whether it was measured or chosen. The constants live in `neoaprs/mercury.py`, `neoaprs/mercurymodem.py`, `neoaprs/radiorules.py` and the services; the simulators
that measured them are in `tests/support/hfchannel.py` and `scripts/mercury-measure`, and every measurement here can be made again with the command given. Mercury is Rhizomatica's program, version 1.9.21,
and "Mercury's source" below is that version's tree (the file names are its); the measurements were made on 2 November 2026 against the Mercury that NeoAPRS builds from it, on the simulated channel of
the suite, with no radio.

## The table

| value | what | where it comes from | measured or chosen |
|---|---|---|---|
| the mode: DATAC3 (`-m 1`) | the one mode every station is on; 9 carriers at 62.5 symbols a second, 562 Hz wide by Mercury's figure and 500 Hz by codec2's | Mercury's its document MODES (the `docs` folder of its source) and `modem/freedv/ofdm_mode.c`: the narrowest of its modes whose frame carries a whole APRS packet (DATAC4 carries 51 bytes, DATAC15 27, the MFSK modes 95); John's decision that the mode is fixed, since a station on another mode hears nothing and nothing on the air says which mode a station is on | a fact of the mode table and a decision |
| the frame: 126 bytes, 3 of them Mercury's, 123 for the packet | what a DATAC3 frame carries, and the longest AX.25 frame that goes whole; a longer one is cut by Mercury without a word to the client | Mercury's `datalink_broadcast/bcast_modes.h` (the frame), `modem/framer.h` (`HEADER_SIZE` 1, then a two-byte length) and `data_interfaces/tcp_interfaces.c` (the cut, with a warning in Mercury's own log only); its log on the bench: "Padding broadcast frame from 109 to 126 bytes" for a payload of 106 | a fact of the source, confirmed on the bench: a 140-byte frame came out as 123 (`scripts/mercury-bench`) |
| the frame's time on the air: 3.8 s (`FRAME_SEC`) | PTT ON to PTT OFF, whatever the payload's length (a frame is always its full size) | measured: 3.80 s over six frames; the audio itself is 3.41 s (27280 samples), and Mercury's `modem/modem.c` adds 10 ms of TX delay, 100 ms of silence, 110 ms of preamble and of postamble, 200 ms of tail and 100 ms more, 3.82 s by the code. (Mercury's its document MODES says the preamble is 0.66 s, which would make 4.9 s; the code and the measurement agree on 3.8.) | measured: `scripts/mercury-measure frame` |
| the delivery: 3.8 s (`DELIVERY_SEC`) | from the frame handed to Mercury to the packet at the far station's KISS port | measured: 3.68 s on average, 3.78 s at the slowest; 0.14 s from the hand-in to PTT ON (Mercury's transmit thread polls every 100 ms), and the far side decodes the frame 0.26 s before the sender's PTT OFF, while the postamble and the tail are still on the air. That is why an ack made at once collides with the sender's tail, and why acks wait for the channel (`services/acks.py`) | measured: `scripts/mercury-measure frame` |
| the ports: 8100 and 8300, the control port 200 above the KISS port | the first free pair from Mercury's defaults up for a Mercury the daemon starts, kept for a program started again in the place of one that died (the HF Tnc waits on its port and finds the modem where it left it; a pair that something else took meanwhile is the one case of another pair, and the Tnc is pointed at it); for one something else runs (`--hf-port`, the benches), the control port is taken to be 200 above the KISS port | Mercury's defaults (its its document TNC); the distance of 200 is an assumption of ours for a Mercury we did not start: Mercury's `-b` (broadcast) and `-p` (control; data is one above) are independent options, and only the defaults differ by 200 | a fact and an assumption, said in the code |
| the busy detector on, at 14 dB (`busy_detect = true` and `busy_threshold_db = 14` in the ini NeoAPRS writes, `BUSY_THRESHOLD_DB`) | Mercury's detector, off by default, says BUSY ON and BUSY OFF on the control port; NeoAPRS holds its frames while it says BUSY: the one carrier sense the broadcast plane has | Mercury's `common/channel_busy.c`: a spectrum every 50 ms, bands of 150 Hz over 300 to 2700 Hz, a threshold over the noise floor that Mercury's ini takes as `busy_threshold_db` (its default is 10 dB, NeoAPRS writes 14: the table below), 3 dB of hysteresis, 300 ms of debounce, a hang of 1500 ms; its its document TNC says it needs a receive filter of 1.8 kHz or more (a 500 Hz filter makes an empty channel read busy). Measured: BUSY ON 0.48 s after the other station's PTT ON, BUSY OFF 1.55 s after its PTT OFF | a fact of the source; the lag and the hang measured: `scripts/mercury-measure frame` |
| the hold on BUSY: 20 s at most (`BUSY_HOLD_MAX_SEC`) | after this long a BUSY holds nothing any more: traffic must not be stranded by a detector that misreads the noise. A frame of another station is 3.8 s on the air and the detector hangs on 1.5 s more, so 20 s is five frames' worth and a margin; it was a minute, and a normal morning on 40 m held the radio that long | Mercury's `channel_busy.c`: the noise floor rises slowly, so a wideband signal reads BUSY for 60 to 95 s and a step in the noise for 100 to 145 s (its own comment); measured below: a step of 20 dB held a receiver at 14 dB for 108 s of 120. In the simulation a step of 30 dB in the noise held the radio for 56 s before the first beacon went | the cap is chosen from the frame's time; the hold times measured: `scripts/mercury-measure busy` and `scripts/mercury-sim`, the poor-channel step |
| the hold on PTT: 12.6 s at most (`KEYED_MAX_SEC`, three frames' worth) | a PTT ON with no PTT OFF after this long is not believed | Mercury's own safety for a keyed transmitter is its TUNE command's 60 s; a frame keys the radio for 3.8 s, so a PTT that lasts three frames is a lost control line, not a transmission | chosen, not measured |
| the acks wait for a held radio, 60 s at most (`ACK_HOLD_MAX_SEC`) | an ack made while the radio is held (the far side decodes while the sender's tail is on the air, and the detector hangs on 1.55 s more) waits and goes at the next tick that finds the radio free | measured on the bench (every ack of the first round was lost before it) and in the simulation: a message is acked in 9.6 to 10.6 s; an ack that waited longer than the sender's first retry (32 s) would ack a copy that is on its way, so 60 s is the most it waits | measured: `scripts/mercury-measure acks` |
| a copy of a message is acked again after 30 s (`ACK_AGAIN_SEC`) | the sender's retry comes 32 s after the first attempt, so it is acked again, and the message is kept once | the FM rule (digipeaters drop a duplicate for 30 s); over HF the simulation's lost-ack step: the retry acked on attempt 2, one copy kept | measured: `scripts/mercury-sim` |
| the retry schedule: attempts at 0, 32, 64 and 128 s, then 240 s for the last answer | the same for both radios | the first wait of 32 s is the FM rule (not 30, the duplicate window); over HF the ack of a first attempt comes in 9.6 to 10.6 s on a flat channel (median 10.2 s, 20 of 20 messages) and 9.2 to 11.2 s on the poor fading channel at 6 dB (18 of 20 on the first attempt, the other two on a retry at 51 and 94 s): the slowest first-attempt ack is at 35 percent of the first wait. A wait that runs while the radio is held is moved on by that time, so our own frame adds its 3.8 s to each wait | measured: `scripts/mercury-measure acks` |
| the pace: 10 s between two attempts of ours (`services/pace.py`), on either radio | several messages written together never go out in a burst; a message on HF right after one on FM waits the 10 s too | the FM rule; over HF a message and its ack take the channel for about 10 s, so the next attempt of ours never goes before the last one's ack could have come | a fact of the measured ack delay |
| the beacon's floor: 30 minutes while the HF radio is on (`HF_BEACON_MIN_MIN`) | the one beacon interval of the station is raised to it | John's rule for a shared channel where a frame is 3.8 s; HF APRS practice is 10 to 30 minutes between position reports (the 300 baud network's thirty years) | chosen |
| the beacon's random pause: up to 300 s (`HF_BEACON_JITTER_SEC`) | added after every interval, so that fixed stations with stable clocks that started together do not key up together every time | measured by Monte Carlo over 20000 station-hours per point: on the 30-minute interval stations that started within one minute of each other lose 14 percent of their beacons without the pause when there are two of them, 23 percent when there are three and 43 percent when five; with the pause of 300 s they lose 0.8, 1.4 and 2.7 percent, within a point of what stations with random phases lose by chance (0.4, 0.8 and 1.6 percent, the floor, which the next beacon makes up for); a pause of 120 s leaves them at 1.3, 2.5 and 5.0 percent, and 600 s gains little more (0.6, 1.1 and 2.1) | measured: `scripts/mercury-measure beacons` |
| no SmartBeaconing, no path, no digipeater over HF (`radiorules.HF`) | a moving station sends its timed beacon with its fix; every frame goes direct | HF APRS practice (digipeating floods a channel every station hears; a path costs bytes of a frame that carries 123), and the frame's 3.8 s | chosen, with the practice as the ground |
| the sound card: the one USB sound card that records and plays, else the system's default | the daemon's proposal, which the page stores as the setting when it is empty | the names a radio's sound card gives itself (an IC-7300's "USB Audio CODEC", a DigiRig's or a dongle's C-Media "USB PnP Sound Device") against the computer's own ("HDA Intel"); nothing to measure without the hardware | chosen from the devices' documentation |
| the keying: RTS of the one USB serial port of a radio or an interface when the sound card is a USB one, else VOX | the daemon's proposal, which the page stores as the setting when it is empty | a DigiRig keys on RTS of its CP2102; an IC-7300 or an FT-710 with its USB cable keys on RTS when the radio's USB SEND is set to RTS, which their manuals say to do for digital modes; VOX every radio has. A CM108 chip could be keyed on its GPIO (`cm108`), but not every dongle wires the pin, so the serial line wins where there is one; on the Linux build CM108 keying talks to `/dev/hidrawN` directly (Mercury's `radio_io/cm108_ptt.c`, compiled in without hidapi) and needs the daemon's user to be allowed that device, and on the Windows build it goes through the hidapi that Mercury compiles into the program | chosen from the devices' documentation |
| the lead-in for VOX: 150 ms (`LEADIN_MS` (150 ms), the ini key `tx_leadin_ms`, written only when the keying is VOX) | a steady tone of 1 kHz (the pitch of TUNE) at the frame's RMS level, with 5 ms of ramp at each end, played just ahead of the preamble inside the keyed window, so that the radio's VOX has its attack behind it when the preamble begins; the frame is then 3.95 s on the air (`FRAME_SEC` stays 3.8: 4 percent) | the table below: the DATAC3 preamble is 110 ms; a VOX that loses 60 ms of a frame costs nothing, at 80 ms frames begin to fall (17 of 20 at 20 dB), at 100 ms none are heard at 20 dB and half at 10 dB; with 150 ms of tone nothing is lost up to 200 ms on any of the four channels. Mercury has no such option: `packaging/mercury/leadin.patch`, applied by `scripts/build-mercury`, adds it to the build on every system. | measured: `scripts/mercury-measure vox`; the 150 ms is chosen (the attack of a radio's VOX is not known to NeoAPRS) |
| the audio level: nothing set | NeoAPRS sets no level; the sound card's mixer is the operator's (the manual: the ALC must not move) | Mercury plays its OFDM at a peak of 16384 of 32768 (`-6 dBFS`; `tx_gain_db` 0 by default, its range ±20 dB, not used); measured on the fifo backend: peak 15739 (-6.4 dBFS), RMS 7276 (-13.1 dBFS), a crest factor of 6.7 dB. Mercury's TUNE is a 1 kHz tone at -15 dBFS for at most 60 s | measured: `scripts/mercury-measure frame` |
| the SNR in the status line | what Mercury's `SN` line says for the latest frame decoded, in dB | Mercury's estimate from the OFDM demodulator, scaled to 3 kHz and calibrated per mode on a flat channel (DATAC3: `1.154 × raw + 0.37`, fitted from -2.1 to 9.9 dB); it stops rising at about 12 dB. Measured: -0.7 dB reported at a true 0 dB, 11.0 dB reported at a true 33 dB. So "SNR 11 dB" means 11 or anything above, and the words beside it (listening, transmitting, channel busy) are the modem's states, not thresholds | measured: `scripts/mercury-measure decode` and `frame` |
| the frequencies: 10.1462, 7.0541 and 14.1070 MHz USB (the page shows the 40 m one, `DIAL_TEXT`, "7.0541 MHz USB", in the HF radio's box) | dial frequencies in the IARU Region 1 digimode segments, between the known neighbours | the band plan and community lists of the neighbours (the study of 2 November 2026); nothing on the air yet, so they are proposals until a listen on each band | chosen; to be confirmed on the air |
| the listeners on 127.0.0.1 only | the Mercury of every download, Linux, macOS and Windows, binds its control, data and KISS ports to the loopback (`packaging/mercury/loopback.patch`, applied by `scripts/build-mercury` to the source of each; the same two `bind` calls serve every system, Winsock's included, and the patch gives the socket of Mercury's own web page, off unless it is started with `-G`, the loopback too); `scripts/build-mercury` starts the program once on Linux and reads the kernel's table of sockets, and the release workflow's Windows job starts `mercury.exe` (`packaging/windows/smoke_mercury.py`) and reads `netstat -ano`, before and after the installer; the daemon ends a program of its own that listens elsewhere (`mercuryhelper.foreign_listeners`, where the system has a table to read) | Mercury 1.9.21 binds INADDR_ANY (`tcp_interfaces.c`) with no bind option and no password: any host on the LAN could key the radio with `TUNE -15` or a KISS frame, past every interlock of NeoAPRS; a bind option is asked of upstream. | a fact of Mercury's source, and our fix |
| the Linux build: `HAVE_HAMLIB=0 HAVE_HIDAPI=0 WS_TLS=0`, ALSA only | what `scripts/build-mercury` leaves out of Mercury | hamlib is CAT keying through a rig library, which NeoAPRS does not use (it keys the radio itself); hidapi is CM108 keying on Windows and macOS, which the Linux build does through `/dev/hidraw`; the TLS is `wss://` for Mercury's own UI, which NeoAPRS never starts; PulseAudio is stubbed out (`packaging/mercury/pulse_stub.c`) so that the bundle needs no sound server, PulseAudio and PipeWire both offering an ALSA device | a fact of Mercury's Makefile |
| the Windows build: `OS=Windows_NT CC=x86_64-w64-mingw32-gcc`, `HAVE_HAMLIB=0 WS_TLS=0`, hidapi in | `mercury.exe` alone: cross-compiled on Linux by `scripts/build-mercury --windows` (the release workflow's job `mercury-windows`, a `debian:trixie` container with `gcc-mingw-w64-x86-64 mingw-w64-x86-64-dev mingw-w64-common`, the packages of Rhizomatica's own release workflow) the way Mercury's `windows` target makes it, then stripped and linked `-static`, with the C runtime's threads (`libwinpthread.a`) and the compiler's runtime linked in, so that it imports the DLLs of Windows and no other (the script reads the import table of the file to see it); DirectSound and WASAPI are Windows's own, Mercury compiles its own copy of hidapi into it (CM108 keying), and the licences of Mercury, FreeDV and hidapi and `SOURCE.txt` travel beside it. A few megabytes, with no DLL beside it | a fact of Mercury's Makefile |
| `[store] enabled = false` and `keepalive_s = 10` in the ini | no message store, a quick heartbeat on the control port | Mercury's store is on by default and writes `~/.local/state/mercury/messages.jsonl` outside the data folder; its heartbeat is every 60 s by default (5 to 600) | a fact of `mercury.ini.example` |

## What `scripts/mercury-measure busy` measured: the busy threshold

Seven real Mercury instances, one for each threshold (`busy_threshold_db` 10, 12, 14, 16, 18, 20 and 24 dB), on one simulated channel with a transmitter; the noise stayed where it was while the frames' level changed (a link gain), so no detector was
disturbed by a step it was not asked about. Frames: 6 of each, the numbers are the frames whose BUSY ON came within the frame. The channel did not start a block late in 50,135 blocks.

| a frame at (SNR in 3 kHz) | 10 dB | 12 dB | **14 dB** | 16 dB | 18 dB | 20 dB | 24 dB |
|---|---|---|---|---|---|---|---|
| -3 dB | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 0 dB | 6 | 0 | 0 | 0 | 0 | 0 | 0 |
| 3 dB | 6 | 6 | 0 | 0 | 0 | 0 | 0 |
| 6 dB | 6 | 6 | **6** | 0 | 0 | 0 | 0 |
| 10 dB | 5 | 6 | 6 | 6 | 6 | 1 | 0 |
| 20 dB | 6 | 6 | 6 | 6 | 6 | 6 | 6 |

With no frame, the seconds a receiver read BUSY of the 60 (120 for the steps) it was listened to, after 20 s for the floor to settle:

| the channel | 10 dB | 12 dB | **14 dB** | 16 dB | 18 dB | 20 dB | 24 dB |
|---|---|---|---|---|---|---|---|
| white noise | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| noise through a receiver's 300 to 2700 Hz filter | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| three carriers 6 dB above the noise of their 150 Hz band | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| the same, 9 dB | 60 | 0 | 0 | 0 | 0 | 0 | 0 |
| the same, 12 dB | 60 | 60 | **0** | 0 | 0 | 0 | 0 |
| the same, 15 dB | 60 | 60 | 60 | 26 | 0 | 0 | 0 |
| a step of 10 dB in the white noise | 119 | 69 | **0** | 0 | 0 | 0 | 0 |
| a step of 20 dB | 120 | 120 | 108 | 87 | 66 | 54 | 0 |

A frame's level over its band is about 10 log (1 + 6 SNR): a frame at 6 dB SNR stands 13.5 dB over the noise of its 150 Hz bands (three or four of them), one at 0 dB 8.5 dB, which is why each 2 dB of threshold costs 3 dB of reach. 14 dB is the highest threshold at which a
frame at 6 dB SNR is still seen (DATAC3 delivers its frames from 3 dB on a flat channel and three of four from 6 dB on a poor one: a signal weaker than that is hardly a signal to wait for), and it is quiet on a carrier up to 12 dB over its band and on a step of 10 dB, which
Mercury's own 10 dB read as busy for the whole two minutes. A bigger step cannot be told from a wide signal at any threshold that still sees a frame, so the cap (`BUSY_HOLD_MAX_SEC`, 20 s) ends that hold. The noise is the channel's model, not a recording of a band:
a measurement of the real 40 m, with a receiver on the antenna, would say more about how often such steps happen.

## What `scripts/mercury-measure vox` measured: the VOX radio's attack and the lead-in

A radio keyed by VOX (`mercury/keying = vox`: no PTT line, the radio keys itself on the audio) starts to transmit only when its VOX has heard audio for its attack time, so the first part of what Mercury plays is not on the air. Mercury (`modem/modem.c`,
`send_modulated_data` and `key_and_play`) plays `ptt_on()` (nothing with no PTT line), a sleep of `tx_delay_ms` (10 ms), 100 ms of silence (`TX_HEAD_SILENCE_MS`: a VOX does not hear it), and then the frame's audio, which begins with the preamble that the
receiver acquires on. The DATAC3 preamble is one modem frame of the mode: 5 OFDM symbols of 22 ms (`ts` 16 ms and `tcp` 6 ms in `modem/freedv/ofdm_mode.c`, 176 samples each), 880 samples, **110 ms**; the postamble is as long, and the 29 modem frames
of data between them are 3.19 s (the audio is 3.41 s, 27280 samples). Mercury's receiver (`ofdm_sync_search_burst` in `modem/freedv/ofdm.c`) looks for the preamble and for the postamble, and decodes back from whichever it finds first, which is why a frame
whose preamble is cut is sometimes still heard.

The measurement (3 November 2026): two real Mercury instances on the simulated channel, the sender's link muted for the first N ms of every transmission, counted from the first sample of audio that is not zero (`Attack` in `tests/support/hfchannel.py`), 20 frames for each N, on a flat channel at 20, 10 and
3 dB SNR in 3 kHz and on the poor fading channel at 3 dB; frames delivered of 20, once with Mercury as it is and once with a lead-in of 150 ms (`tx_leadin_ms = 150`, the build with `packaging/mercury/leadin.patch`):

| the first N ms muted | flat 20 dB, as is | flat 20 dB, 150 ms lead-in | flat 10 dB, as is | flat 10 dB, 150 ms lead-in | flat 3 dB, as is | flat 3 dB, 150 ms lead-in | poor 3 dB, as is | poor 3 dB, 150 ms lead-in |
|---|---|---|---|---|---|---|---|---|
| 0 | 20 | 20 | 20 | 20 | 20 | 20 | 18 | 19 |
| 20 | 20 | 20 | 20 | 20 | 20 | 20 | 19 | 20 |
| 40 | 20 | 20 | 20 | 20 | 20 | 20 | 18 | 19 |
| 60 | 20 | 20 | 20 | 20 | 20 | 20 | 18 | 20 |
| 80 | 17 | 20 | 19 | 20 | 20 | 20 | 17 | 19 |
| 100 | 0 | 20 | 10 | 20 | 20 | 20 | 18 | 20 |
| 150 | 0 | 20 | 8 | 20 | 20 | 20 | 16 | 19 |
| 200 | 0 | 20 | 8 | 20 | 20 | 20 | 14 | 20 |
| 250 | 0 | 0 | 7 | 12 | 18 | 20 | 5 | 17 |
| 300 | 0 | 0 | 3 | 5 | 3 | 20 | 4 | 17 |

Reading it: with Mercury as it is, a VOX that loses up to 60 ms of a frame loses nothing, at 80 ms the loss begins on a strong signal (3 frames of 20 at 20 dB), at 100 ms none of the frames are heard at 20 dB and half at 10 dB, and a weak signal holds out longer
(3 dB flat loses nothing up to 200 ms). The poor channel loses a tenth of the frames at any N, the fading's own loss (18 of 20 with nothing muted), and more from 150 ms on. A weak signal surviving a lost preamble better than a strong one is what was measured; it was not
chased further. With 150 ms of tone ahead of the preamble every point up to 200 ms is as good as with nothing muted (the poor channel's one or two frames in 20 are the fading's own), and the loss comes back when the radio loses more than the tone and the 60 to 80 ms the preamble can spare:
from 250 ms on, first on a strong signal (0 of 20 at 20 dB, 12 at 10 dB). 150 ms was chosen for a VOX that needs up to 200 ms; it costs 150 ms of the channel's 3.8 s for every frame of a station on VOX, and nothing for any other keying. The lead-in is audio on purpose: silence does not trigger a VOX. The tone is below the 1219 to 1781 Hz that the mode
occupies, and ends before the preamble begins (the table's 0 ms rows are as good with the tone as without). The key is written only for VOX (`ini_text` in `neoaprs/mercury.py`); Mercury's ini reader asks for the keys it knows and ignores any other (`cfg_read` in `common/cfg_utils.c`), so a Mercury that does not know `tx_leadin_ms` would start and play frames as before, and there a VOX radio would have the table's left-hand columns. The patch changes the broadcast and ARQ data frames, which are what NeoAPRS sends, and not the ARQ keydown or the MFSK acknowledgement.

## The channel the measurements were made on

`tests/support/hfchannel.py` is the air between real Mercury instances on one computer: every station hears the sum of the others at a chosen signal-to-noise ratio, through a gain and a delay per link,
and since this change through a fading channel per link. It was checked against the two simulators Mercury's own figures rest on:

- **The signal-to-noise ratio** is counted as codec2's `ch` (`modem/freedv/ch.c` in Mercury's tree, the simulator behind the delivered-frames table of Mercury's its document MODES) counts it: the signal's
  own power against the noise in 3 kHz. `ch` measures the signal's power over its whole input; the channel's reference is the measured RMS of a DATAC3 frame, 7276 of 32768 (`REFERENCE_RMS`), which is
  within half a decibel of the level `ch`'s rule of thumb `SNR3k = -No - 14.82` stands for (about 7000). Before this change the reference was an assumption of a peak at half scale and a crest factor of
  10 dB (5181), so the channel's "30 dB" was 33 dB; the figures in the earlier notes are 3 dB optimistic.
- **The fading** is the Watterson channel of ITU-R F.1487 as Mercury's own simulator implements it (`common/watterson.c`): two paths of equal power, each multiplied by a complex Gaussian process with a
  Gaussian Doppler spectrum whose spread (twice the standard deviation) is the preset's, the second path delayed. The presets are CCIR 520-2's: good (0.5 ms, 0.1 Hz), moderate (1 ms, 0.5 Hz), poor (2 ms,
  1 Hz), flutter (0.5 ms, 10 Hz); Mercury has the same four as `ccir-good` to `ccir-flutter`. codec2's `--mpp` has the poor channel's parameters, with the spreading functions made by an Octave script whose
  spectrum may be narrower (its filter is designed on the magnitude, which no document resolves). The tests hold the tap process to unit power and to the Gaussian autocorrelation, the transformer that makes
  the analytic signal to within 0.1 dB from 500 to 3500 Hz, and a steady two-path channel to an exact echo.
- **The check against codec2's table:** DATAC3 on the poor channel at 0 dB delivered 19 of 24 beacons (79 percent) in the simulation's step and the frames of the decode measurement below, where
  codec2's table says 74 of 100 single frames. Mercury's own notes give DATAC3 on a flat channel 140 of 149 frames at -3.8 dB and 6 of 143 at -4.8 dB (its its document HARQ-FINDINGS), the cliff the decode
  measurement finds too.

## What `scripts/mercury-measure decode` measured

Frames delivered of 50 sent, one station to another, at each signal-to-noise ratio in 3 kHz (the reported SNR is the mean of Mercury's `SN` lines for the frames it decoded):

| channel | -6 dB | -4 dB | -2 dB | 0 dB | 2 dB | 3 dB | 4 dB | 6 dB | 8 dB | 9 dB | 10 dB | 12 dB | 15 dB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| flat (noise only) | 0 | 43 | 50 | 50 | 50 | | 50 | 50 | 50 | | 50 | | |
| poor (CCIR 520-2: 2 ms, 1 Hz) | | | | 39 | | 48 | | 50 | | 50 | | 50 | 50 |
| reported SNR, flat | | -3.3 | -2.2 | -0.7 | 1.1 | | 2.9 | 4.7 | 6.2 | | 7.7 | | |
| reported SNR, poor | | | | -0.6 | | 1.6 | | 3.6 | | 5.1 | | 6.2 | 6.8 |

The flat channel's cliff is between -4 and -6 dB, where Mercury's own notes put it; the poor channel loses a fifth of the frames at 0 dB (codec2: 74 of 100) and nothing from 6 dB up. The reported SNR
reads 1 to 2 dB under the true one from 0 to 10 dB and flattens above.

The weak link of `scripts/mercury-sim` is 27 dB below the others, 3 dB of SNR at the channel's 30 dB: inside the flat channel's margin, so that a lost frame there is a finding to read and not a
failure of the run.

## How to make the numbers again

```bash
scripts/mercury-measure frame
```

```bash
scripts/mercury-measure decode --snr -6,-4,-2,0,2,4 --fading poor
```

```bash
scripts/mercury-measure acks --messages 20 --fading poor --snr-one 6
```

```bash
scripts/mercury-measure vox --snr 10 --attack-ms 0,40,80,100,150,200 --leadin-ms 150
```

```bash
scripts/mercury-measure beacons
```

Each needs the Mercury of the checkout (`scripts/build-mercury --install`) but `beacons`, which is arithmetic; `--report FILE` writes the result as JSON, `--first-port N` lets two runs share the
machine, and a `decode` point of 50 frames takes about four and a half minutes, so a table is made by several runs at once with different ports. The simulation itself is `scripts/mercury-sim`
(`scripts/check --stage sim`, the CI job `sim`; `scripts/mercury-measure busy` makes the busy-threshold table above, about twenty minutes): `docs/development.md`, "The simulators".
