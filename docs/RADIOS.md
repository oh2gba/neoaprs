# Radios and TNCs

How to connect your radio or TNC to NeoAPRS, on Linux or Windows. In the page, **Settings** tab, choose the *TNC* and, for a serial one, the *Port* and *Baud*; for KISS over TCP, the *Host* and *Port*. On Linux an empty serial port means NeoAPRS searches the USB serial ports; on Windows pick the COM port from the list.

## Which radio or TNC do you have?

| Radio / TNC | Works? | TNC setting | Connects by |
|---|---|---|---|
| Kenwood TH-D7 | yes | Kenwood TH-D7 / TM-D700 / TS-2000, TNC-2 | PC cable PG-4W, serial 9600 |
| Kenwood TM-D700 | yes | same | PC port (DE-9), serial 9600 |
| Kenwood TM-D710, TH-D72 | yes with notes | Kenwood TM-D710 / TH-D72 | COM socket (D710) or USB (D72), 9600 |
| Kenwood TH-D74, TH-D75 | yes | KISS TNC (Mobilinkd, NinoTNC, TNC-Pi, TH-D74/D75…) | USB-C or Bluetooth; KISS switched on at the radio |
| Kenwood TS-2000 | yes with notes (unverified) | Kenwood TH-D7 / TM-D700 / TS-2000, TNC-2 | COM port, shared with CAT |
| Kenwood TM-D750E | unknown | – | announced, nothing known |
| Mobilinkd TNC3, TNC4 | yes | KISS TNC | USB or Bluetooth (the TNC3 is classic Bluetooth; for the TNC4 see its entry) |
| NinoTNC | yes | KISS TNC | USB, 57600 |
| TNC-X, TNC-Pi, other TNC already in KISS | yes | KISS TNC | serial or USB; TNC-Pi baud unverified (19200 reported) |
| MFJ-1270B/1274/1278, TAPR TNC-2 clones | yes with notes | Kenwood TH-D7 / TM-D700 / TS-2000, TNC-2 | RS-232; depends on the firmware |
| Kantronics KPC-3+ | yes | Kantronics KPC-3+ | RS-232 |
| Direwolf or soundmodem with a sound card: Digirig, SignaLink, a radio's data port, a USB sound dongle | yes | KISS over TCP (Direwolf, soundmodem) | Direwolf or the soundmodem serves KISS on a TCP port |
| BTech UV-PRO, Vero VR-N76, Radioddity GA-5WB (one radio under three names) | untested, reports say it works | KISS TNC | Bluetooth (classic); users' reports only. Its Bluetooth LE is not supported by NeoAPRS |
| PicoAPRS V4 (DB1NTO) | untested, follows the manual | KISS TNC | Bluetooth (classic), USB-C or TCP. Its Bluetooth LE mode is not supported by NeoAPRS |
| Yaesu FTM-*, FT1D/2D/3D/5D | no | – | no KISS TNC for a PC. They send received APRS to the PC, never transmit from it. Use a sound-card interface and Direwolf instead |
| Icom (D-STAR radios, IC-9700, IC-705) | no | – | D-PRS is not APRS packets. A sound card and Direwolf work as for any radio |
| Icom ID-5200A | unverified | – | has a KISS TNC (USB, Bluetooth); entry and speed not known, needs a tester |

Tried on the air: the Kenwood TH-D7. The other entries follow the radios' manuals and users' reports; "unverified" marks a detail nobody has confirmed.

NeoAPRS sends and receives over RF only. Receiving from the internet needs no TNC: use any APRS-IS client.

## Kenwood TH-D7 and TM-D700

1. Connect the PC port to the computer: the PG-4W cable on the TH-D7, a serial cable on the TM-D700 (a USB-serial adapter does).
2. TNC setting: *Kenwood TH-D7 / TM-D700 / TS-2000, TNC-2*. Port: your adapter. Baud: 9600.
3. Switch the radio on with the TNC in packet mode (the display shows PACKET). Nothing else: NeoAPRS sends `KISS ON` and `RESTART` itself, waits 3 s, and later checks that the radio is still there.

- TM-D700: leave the COM speed at 9600 (menu 1-9-5). A Bluetooth module without handshake lines needs RTS and CTS joined. A serial module that is paired with the computer is a Bluetooth port like the others ("Bluetooth" below; the module's own speed is set on the module).
- TH-D7: a forum report says the TNC is unstable in KISS at 9600 bps on air and fine at 1200. Unverified.

## Kenwood TM-D710 and TH-D72

1. **TM-D710:** use the COM mini-DIN socket on the rear of the control panel, not the PC port on the main unit. Set menu 929 (COM port speed) to 9600. Menu 920 is the speed of the PC port and has no effect here.
   **TH-D72:** connect USB; on Windows install the Kenwood driver first. Press [TNC] until the display shows PACKET12.
2. TNC setting: *Kenwood TM-D710 / TH-D72*. Baud: 9600.
3. NeoAPRS sends `TC 1`, `TN 2,0` (packet on band A), `HBAUD 1200`, `KISS ON`, `RESTART`, with pauses. This is the sequence of the Debian tool tmd710_tncsetup, which lists both radios as working. Kenwood documents none of it, and what `TC` means is described differently in different sources, so NeoAPRS copies it unchanged. The first entry takes about 8 s.

- In KISS the port carries KISS only: NeoAPRS cannot tune the radio, and the radio's own APRS is off.
- Outpost reports a rare D710 fault: the bytes `TC 0` plus carriage return inside KISS data throw the radio out of TNC mode. Unverified here.
- The menu numbers are from the TM-D710GA/GE manual. The TM-D710 without G was not read.

## Kenwood TH-D74 and TH-D75

KISS only, no command mode. NeoAPRS cannot enter KISS or ask the radio anything, so it sends nothing and a silent line is normal.

1. Menu 983: choose **USB** or **Bluetooth** for KISS (one at a time).
2. USB: menu 980 to *COM + AF/IF Output* (not Mass Storage). Connect USB-C. **Windows:** install the Kenwood virtual COM driver *before* the first plugging in. **Linux:** the port is a ttyACM device, under `/dev/serial/by-id` named like `usb-JVCKENWOOD_TH-D75-if00` (D75; the D74's name is unverified). The baud setting is ignored.
   Bluetooth: pair it once with the system as in "Bluetooth" below (radio side: menu 930 on, 932 search; D74: menu 931 on, 934 pairing mode).
3. TNC setting: *KISS TNC (Mobilinkd, NinoTNC, TNC-Pi, TH-D74/D75…)*. Port: the serial port, the COM port, or on Linux the paired radio in the list (`bt://AA:BB:CC:DD:EE:FF`; NeoAPRS finds its serial channel, which is usually 2, itself).
4. On the radio press **[F]** then **[LIST]** until the display shows KISS (D75; D74: **[F]** then **[TNC]**). Menu 505 data speed 1200 or 9600, menu 506 data band A or B, menu 508 TX delay (D75).

- While KISS is on, the radio takes no PC commands and sends no GPS or APRS output.
- Several COM ports can appear after pairing; only one works.
- Several D75 radios on one PC all report the same USB serial number: use `/dev/serial/by-path`.

## Mobilinkd TNC3 and TNC4

1. **USB:** connect it. Linux: a ttyACM device; Windows: a COM port. Blue LED: three short blips = USB.
2. **Bluetooth:** pair it ("Bluetooth" below); if a passkey is asked for, it is `123456`. Double blip = connected. One connection at a time: close the phone app.
   Linux: pick the paired TNC in *Port* (`bt://AA:BB:CC:DD:EE:FF`; its channel is usually 1). Windows: the *Outgoing* COM port.
3. TNC setting: *KISS TNC…*. Baud: any, the default is fine.

The TNC4 guide describes Bluetooth serial as working, but one project calls the TNC4 BLE-only. If it does not show up among the paired devices, or the connection fails, use USB: Bluetooth LE is not supported by NeoAPRS.

## BTech UV-PRO, Vero VR-N76, Radioddity GA-5WB

One radio sold under these names (the GA-5WB too). It has a KISS TNC that is reached over Bluetooth. **Status: untested by us.** Users report it working over classic Bluetooth serial (SPP) with APRSdroid and with Linux software through an RFCOMM port; the radio also has Bluetooth LE, which NeoAPRS does not support, and one project lists it as LE-only for KISS, so what your radio's firmware offers is settled by trying. Please report what you find.

1. **KISS on:** Menu, General Settings, *KISS TNC*: switch it on and save (the UV-PRO's menu; the VR-N76's names may differ slightly).
2. **Pair:** on the radio Menu, *Pairing*, OK (it stays discoverable about two minutes); then pair it with the computer as in "Bluetooth" below. The device is named `UV-PRO` or `VR-N76`. If a code is asked for, try `0000` or `1234`.
3. **Disconnect the radio's own app** (the phone app) first. A Bluetooth serial link serves one program at a time; the vendors do not say so, it is the rule for the others.
4. **NeoAPRS:** TNC setting *KISS TNC (Mobilinkd, NinoTNC, TNC-Pi, TH-D74/D75…)*, *Port*: the radio, `bt://AA:BB:CC:DD:EE:FF`. Reports give RFCOMM channel 1 (a user who bound it by hand says another number did not work); NeoAPRS asks the radio which channel its serial port is on and tries 1 to 3 after it, and the log (`neoaprs.log`) says which channel connected. If it is not the right one, write it: `bt://AA:BB:CC:DD:EE:FF/1` with *Other...*.
5. The radio shows a small telephone icon beside the power level when the link is up. A silent line is normal until it hears a packet.

- On Linux a desktop that connects the radio as a headset (audio) can get in the way: one report fixes it with `Disable=Headset` in the `[General]` section of `/etc/bluetooth/input.conf`, then restarting Bluetooth. Unverified here.
- One report says that Direwolf received through the radio's KISS but did not transmit; another saw APRS messages arrive with a `(NOT AX.25)` mark. Whether NeoAPRS is affected is not known.
- The TX delay and similar KISS parameters are not documented by the vendors; NeoAPRS does not set them.

## PicoAPRS V4

DB1NTO's pocket APRS device (VHF, 0.5 or 1 W, GPS, a KISS TNC). **Status: untested by us;** this follows the manual of the V4 (November 2023, and later firmware). It offers its KISS TNC over USB-C, TCP, **Bluetooth Classic** and **Bluetooth LE**, as four choices in its menu; NeoAPRS uses the classic one (or USB-C, or KISS over TCP). The manual does not give the RFCOMM channel.

1. **Mode:** device mode *TNC*, then choose *Bluetooth* (not *Bluetooth LE*). Bluetooth works only in TNC mode and switches on with it.
2. **Pair:** the PicoAPRS is visible for 4 minutes after TNC mode is switched on and then switches Bluetooth off to save power; the Bluetooth icon in its main menu switches it on again. Pair it with the computer as in "Bluetooth" below, in that time: it is named `PicoAPRS`, both sides show a PIN, and the **right-hand button (Confirm)** on the device confirms it.
3. **NeoAPRS:** TNC setting *KISS TNC (Mobilinkd, NinoTNC, TNC-Pi, TH-D74/D75…)*, *Port*: `bt://AA:BB:CC:DD:EE:FF` as listed under its name. The channel is looked up on the device; if that fails, 1 to 3 are tried, and the log says which one connected (name it with `/1` if need be).
4. The Bluetooth LE mode needs no pairing and does not appear among the paired devices; NeoAPRS cannot use it. The USB-C port (a virtual COM port, 115200, ignored by the device) is the alternative.

## NinoTNC

1. Connect USB. Set the mode on its DIP switches (or by KISS command; see the NinoTNC wiki).
2. TNC setting: *KISS TNC…*. **Baud: 57600.**
3. On Linux add the udev rules from the wiki, and see "Permissions on Linux".

## Direwolf (sound card)

For a sound-card interface (Digirig, SignaLink, a USB dongle, a radio's USB audio) with Direwolf.

1. Install. Linux: `sudo apt install direwolf`. Windows: download the release from github.com/wb2osz/direwolf and unpack it.
2. Write a file, direwolf.conf:

```
# Linux: card number from "arecord -l".  Windows: the device list is printed at the start; try ADEVICE USB
ADEVICE plughw:1,0
CHANNEL 0
MYCALL N0CALL
MODEM 1200
# PTT: pick one
PTT /dev/ttyUSB0 RTS      # Digirig Mobile; Windows: PTT COM5 RTS
#PTT CM108                # Digirig Lite, CM108 dongles (GPIO 3)
KISSPORT 8001
```

3. Start it: `direwolf -c direwolf.conf` (Windows: `direwolf.exe -c direwolf.conf`). It prints "Ready to accept KISS client application on port 8001".
4. NeoAPRS: TNC setting *KISS over TCP (Direwolf, soundmodem)*, host `127.0.0.1`, port `8001`.
5. Direwolf on another machine (a Pi): enter its address as the host. Port 8001 is open to the whole network: keep it inside your LAN.

- **Never choose the Digirig's serial port as a serial TNC.** Opening it keys the transmitter through RTS. Choose KISS over TCP.
- Channels, TX delay and the like are Direwolf's: see its User Guide.

## UZ7HO soundmodem (Windows)

1. In the soundmodem settings choose the sound card and the PTT as for any modem, and switch on its KISS server.
2. NeoAPRS: *KISS over TCP*, host `127.0.0.1`, port as in the soundmodem's setting. Reports say 8100 (unverified; the AGW port is 8000, do not use it). If NeoAPRS does not connect, check that the KISS port is on and the AGW port is not the same number.
3. QtSoundModem works the same way.

## Kantronics KPC-3+

1. Connect RS-232 (the KPC-3XE has USB).
2. TNC setting: *Kantronics KPC-3+*, baud: the speed of the terminal port.
3. NeoAPRS sends `INTFACE KISS` and `RESET`. The TNC stays in KISS across power cycles. A user reports that the host baud seemed to change after the RESET; if the TNC goes silent, set the baud again. Unverified.

KISS exit is `C0 FF C0`, or a hard reset.

## Bluetooth

NeoAPRS uses classic Bluetooth serial (the Serial Port Profile, SPP/RFCOMM): the Kenwood TH-D74/D75, the Mobilinkd TNC3, a TM-D700 with a Bluetooth serial module. **Bluetooth LE** (the Mobilinkd TNC4 in its LE mode, the BTech UV-PRO, the Vero VR-N76) is not supported.

**Linux**

1. Pair the radio once with the system. **KDE Plasma:** System Settings, Bluetooth (or the Bluetooth icon in the tray), *Add New Device*, choose the radio, *Pair*; GNOME: Settings, Bluetooth. Or in a terminal, with the radio in pairing mode:

   ```
   bluetoothctl
     power on
     agent on
     scan on                      # note the radio's address
     pair AA:BB:CC:DD:EE:FF       # TH-D75: confirm on the radio within 30 s
     trust AA:BB:CC:DD:EE:FF
     quit
   ```

2. In NeoAPRS, *Settings*, *TNC*, *Port*: choose the radio, listed by its name as `bt://AA:BB:CC:DD:EE:FF` (Refresh if it is new). The setup guide's radio step lists it too.

The list is the system's own (BlueZ, which KDE's Bluedevil and the other desktops use), so a radio paired in any of them appears. NeoAPRS opens the Bluetooth link itself: no `rfcomm bind`, no root, no dialout group. The serial channel is looked up on the radio when the port is opened (the TH-D74/D75 use 2, Mobilinkd 1); if the radio lists none, or refuses the one it lists, channels 1 to 3 are tried in turn and the log says which connected. To name it, write it after the address, `bt://AA:BB:CC:DD:EE:FF/2`, with *Other...* in the list. The link is made when NeoAPRS opens the port and drops when the radio sleeps or goes out of range; NeoAPRS opens it again. The list holds the paired devices that have a serial port (a device the system has not yet looked into is listed too). It is read from BlueZ's records and no device is connected to for it. The search for the radio does not look at Bluetooth devices: a `bt://` port is used only when it is chosen. A radio keeps one connection at a time: close the phone app or the other program first. If the open fails with "Connection refused", the channel is wrong (name it); "Host is down" or "no answer" means the radio is off or out of range or its Bluetooth is off.

The older way still works as a fallback, when a program of the system has to share the link or your Python has no Bluetooth sockets: `sudo rfcomm bind /dev/rfcomm0 AA:BB:CC:DD:EE:FF 2` (the last number is the channel; `sdptool browse AA:BB:CC:DD:EE:FF` lists them), then the port is `/dev/rfcomm0`. `rfcomm` is deprecated in BlueZ but still works.

**Windows**

1. Settings, Bluetooth & devices, add the radio or TNC and pair it.
2. More Bluetooth settings, *COM Ports* tab: Windows lists two ports; use the **Outgoing** one. Choose it as the *Port* in NeoAPRS.
3. An older PC may ask for the PIN `0000`.

`bt://` ports are for Linux. **macOS:** pair the radio in System Settings, Bluetooth; the serial port is the `/dev/cu.*` one named after it.

## Permissions on Linux

- **dialout:** `sudo usermod -aG dialout $USER`, then log out and in. (Arch: group `uucp`.) Without it the port opens with "permission denied".
- **brltty** takes some USB serial chips (CP210x, FTDI) as a braille display, and the port vanishes a moment after plugging in. Remove it: `sudo apt remove brltty`, or `sudo systemctl mask brltty-udev.service`.
- **ModemManager** probes new serial ports with AT commands, which a TNC answers badly, and holds the port. Either `sudo systemctl disable --now ModemManager`, or tell it to leave your device alone with a udev rule (idVendor and idProduct from `lsusb`):

```
# /etc/udev/rules.d/99-tnc.rules
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", ENV{ID_MM_DEVICE_IGNORE}="1"
```

Then `sudo udevadm control --reload` and plug the device in again.

## Not working?

1. **Settings tab, TNC group:** the state at the top. *connecting* or *waiting*: the port cannot be opened (wrong port, permissions, another program holds it). *connected* with no packets: normal for a KISS TNC until it hears something. *silent*: the line is open but the radio says nothing; check the cable, the baud and that the radio is on.
2. **Log:** `neoaprs.log` in the data folder; start with `--debug` for more. It names the port, the entry sequence sent and what came back.
3. **Wrong baud or port:** garbage or nothing. The TH-D75 and Mobilinkd ignore the baud on USB and Bluetooth; the NinoTNC needs 57600; Kenwood serial 9600.
4. **TH-D74/D75, Mobilinkd, NinoTNC:** NeoAPRS cannot check that they are there. KISS must be on at the radio, and a radio that was switched off must have KISS switched on again.
5. **Port search finds the wrong device:** name the port in Settings, TNC, or keep the search away from that device: `neoaprs db set serial/skip /dev/ttyUSB2`.
6. **A port is not searched:** the search leaves out development boards, because opening their USB console resets the chip (an ESP32 on a USB Serial/JTAG port restarts at every open): Espressif (303a), Arduino (2341, 2a03), Raspberry Pi Pico (2e8a), Adafruit (239a), Teensy (16c0:0483), SEGGER J-Link (1366) and ST-Link (0483:3744, 3748, 374b, 374d, 374e, 374f, 3752, 3753). The log says `skipping /dev/ttyACM0: an ESP32 development board (USB 303a:1001)`, and `neoaprs doctor` marks the port. USB-serial cables and the TNCs' own ports (FTDI, Silicon Labs, WCH, Prolific, the Mobilinkd's ST 0483:5740, Kenwood radios) are searched. A TNC built on one of these boards works when you choose its port by name (*Port* in the Settings, or `--port`): a named port is never left out.
7. **Nothing transmitted:** the call must be set (not `N0CALL`); see the manual.

## Sources

- [PicoAPRS V4 manual (WiMo)](https://www.wimo.com/media/akeneo_connector/media_files/P/i/PicoAPRS_V4_User_Manual_May2024_9d06.pdf)
- [VR-N76 (UV-PRO) KISS-TNC under Linux (hamradiotech.de)](https://www.hamradiotech.de/posts/2025-09-11-VR-N76-KISS-TNC/), [btkiss](https://github.com/8ff/btkiss), [VR-N76 with APRSdroid (hamradio.my)](https://hamradio.my/setting-up-bluetooth-kiss-tnc-on-verotelecom-vgc-vr-n76-with-aprsdroid/)
- [Kenwood TH-D75 manual, chapters 12, 15, 18](https://kasc.kenwood.com/files/prod/3692/5/THD75E_User_manuals_English.pdf)
- [Kenwood TM-D710GA/GE manual](https://kasc.kenwood.com/files/prod/2681/5/TM-D710GE_GA_Instruction_Manual_CD-ROM_V1.01.pdf)
- [Kenwood TM-D700 APRS/packet manual](https://www.repeater-builder.com/kenwood/pdfs/tm-d700a-aprs-packet-manual.pdf)
- [tmd710_tncsetup](https://github.com/fmarier/tmd710_tncsetup)
- [TH-D74 on Linux (habets.se)](https://blog.habets.se/2020/06/Amateur-packet-radio-walkthrough.html), [K1CHN](https://www.k1chn.com/posts/winlink-on-the-th-d74-with-raspberry-pi/)
- [kiss-tnc-bridge](https://github.com/kotfu/kiss-tnc-bridge)
- [Mobilinkd TNC4 guide](https://mobilinkd.s3.amazonaws.com/TNC4/MobilinkdTNC4.pdf), [TNC3 guide](https://mobilinkd.s3.amazonaws.com/TNC3/MobilinkdTNC3.pdf)
- [NinoTNC wiki](https://wiki.oarc.uk/packet:ninotnc)
- [Direwolf](https://github.com/wb2osz/direwolf), [Direwolf User Guide](https://packet-radio.net/wp-content/uploads/2018/10/Direwolf-User-Guide.pdf)
- [Soundmodem ports (Digirig forum)](https://forum.digirig.net/t/soundmodem-and-pinpoint-aprs-with-digirig-will-not-tx-aprs-packets/2340), [QtSoundModem](https://wiki.oarc.uk/packet:qtsoundmodem)
- [G7JJF TNC init strings](https://g7jjf.com/tncsetup.htm), [Kantronics KPC-3+ KISS](https://manualzz.com/doc/o/22vn6v/kantronics-kpc%E2%80%933-plus-user-manual-kiss-mode)
- [Icom ID-5200A](https://www.icomjapan.com/lineup/products/ID-5200A/), [D-PRS](https://www.aprs-is.net/dprs.aspx)
- [Yaesu receive-only gateway (ygate)](https://github.com/craigerl/ygate)
