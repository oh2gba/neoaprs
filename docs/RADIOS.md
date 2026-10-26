# Radios and TNCs

How to connect your radio or TNC to NeoAPRS, on Linux or Windows. In the page, **Settings** tab, **TNC** group, choose the **Radio type** and, for a serial one, the **Port** and **Speed**; for KISS over TCP, the **TCP host** and **TCP port**. On Linux an empty serial port means NeoAPRS searches the USB serial ports; on Windows pick the COM port from the list. **Find my radio**, in the Settings tab and in the setup guide, tries the ports for you (Linux, Windows, macOS). With no radio at all, the type *Dummy* makes up traffic to try NeoAPRS with.

## Which radio or TNC do you have?

| Radio / TNC | Works? | Radio type | Connects by |
|---|---|---|---|
| Kenwood TH-D7 | yes | Kenwood TH-D7 / TM-D700 / TS-2000, TNC-2 | PC cable PG-4W, serial 9600 |
| Kenwood TM-D700 | yes | same | PC port (DE-9), serial 9600 |
| Kenwood TM-D710, TH-D72 | yes with notes | Kenwood TM-D710 / TH-D72 | COM socket (D710) or USB (D72), 9600 |
| Kenwood TH-D74, TH-D75 | yes | KISS TNC (Mobilinkd, NinoTNC, TNC-Pi, TH-D74/D75…) | USB-C or Bluetooth (classic); KISS switched on at the radio. Bluetooth LE only through a B.B. Link adapter |
| Kenwood TS-2000 | yes with notes (unverified) | Kenwood TH-D7 / TM-D700 / TS-2000, TNC-2 | COM port, shared with CAT |
| Kenwood TM-D750E | unknown | – | announced, nothing known |
| Mobilinkd TNC3, TNC4 | yes | KISS TNC | USB, Bluetooth (classic) or Bluetooth LE (`ble://`, needs the extra `ble`; LE untested by us) |
| NinoTNC | yes | KISS TNC | USB, 57600 |
| TNC-X, TNC-Pi, other TNC already in KISS | yes | KISS TNC | serial or USB; TNC-Pi baud unverified (19200 reported) |
| MFJ-1270B/1274/1278, TAPR TNC-2 clones | yes with notes | Kenwood TH-D7 / TM-D700 / TS-2000, TNC-2 | RS-232; depends on the firmware |
| Kantronics KPC-3+ | yes | Kantronics KPC-3+ | RS-232 |
| Direwolf or soundmodem with a sound card: Digirig, SignaLink, a radio's data port, a USB sound dongle | yes | KISS over TCP (Direwolf, soundmodem) | Direwolf or the soundmodem serves KISS on a TCP port |
| BTech UV-PRO, Vero VR-N76, Radioddity GA-5WB (one radio under three names) | untested, reports say it works | KISS TNC | Bluetooth (classic), users' reports only; the BLE KISS specification also lists the radio for Bluetooth LE (`ble://`), untested |
| PicoAPRS V4 (DB1NTO) | untested, follows the manual | KISS TNC | Bluetooth (classic), USB-C or TCP; Bluetooth LE (`ble://`) is listed by the BLE KISS specification, untested |
| LoRa APRS iGate and Tracker (CA2RXU firmware) | untested, follows the firmware's source | KISS over TCP (iGate) or KISS TNC over Bluetooth LE (Tracker) | the iGate serves KISS on TCP port 8001; the Tracker has Bluetooth LE with KISS ([LoRa APRS](#lora-aprs-ca2rxu-firmware)) |
| Yaesu FTM-*, FT1D/2D/3D/5D | no | – | no KISS TNC for a PC. They send received APRS to the PC, never transmit from it. Use a sound-card interface and Direwolf instead |
| Icom (D-STAR radios, IC-9700, IC-705) | no | – | D-PRS is not APRS packets. A sound card and Direwolf work as for any radio |
| Icom ID-5200A | unverified | – | has a KISS TNC (USB, Bluetooth); entry and speed not known, needs a tester |

Tried on the air: the Kenwood TH-D7. The other entries follow the radios' manuals and users' reports; "unverified" marks a detail nobody has confirmed.

NeoAPRS sends and receives over RF only. Receiving from the internet needs no TNC: use any APRS-IS client.

## Kenwood TH-D7 and TM-D700

1. Connect the PC port to the computer: the PG-4W cable on the TH-D7, a serial cable on the TM-D700 (a USB-serial adapter does).
2. Radio type: *Kenwood TH-D7 / TM-D700 / TS-2000, TNC-2*. Port: your adapter. Speed: 9600.
3. Switch the radio on with the TNC in packet mode (the display shows PACKET). Nothing else: NeoAPRS sends `KISS ON` and `RESTART` itself, waits 3 s, and later checks that the radio is still there.

- TM-D700: leave the COM speed at 9600 (menu 1-9-5). A Bluetooth module without handshake lines needs RTS and CTS joined. A serial module that is paired with the computer is a Bluetooth port like the others ("Bluetooth" below; the module's own speed is set on the module).
- TH-D7: a forum report says the TNC is unstable in KISS at 9600 bps on air and fine at 1200. Unverified.

## Kenwood TM-D710 and TH-D72

1. **TM-D710:** use the COM mini-DIN socket on the rear of the control panel, not the PC port on the main unit. Set menu 929 (COM port speed) to 9600. Menu 920 is the speed of the PC port and has no effect here.
   **TH-D72:** connect USB; on Windows install the Kenwood driver first. Press [TNC] until the display shows PACKET12.
2. Radio type: *Kenwood TM-D710 / TH-D72*. Speed: 9600.
3. NeoAPRS sends `TC 1`, `TN 2,0` (packet on band A), `HBAUD 1200`, `KISS ON`, `RESTART`, with pauses. This is the sequence of the Debian tool tmd710_tncsetup, which lists both radios as working. Kenwood documents none of it, and what `TC` means is described differently in different sources, so NeoAPRS copies it unchanged. The first entry takes about 8 s.

- In KISS the port carries KISS only: NeoAPRS cannot tune the radio, and the radio's own APRS is off.
- Outpost reports a rare D710 fault: the bytes `TC 0` plus carriage return inside KISS data throw the radio out of TNC mode. Unverified here.
- The menu numbers are from the TM-D710GA/GE manual. The TM-D710 without G was not read.

## Kenwood TH-D74 and TH-D75

KISS only, no command mode. NeoAPRS cannot enter KISS or ask the radio anything, so it sends nothing and a silent line is normal.

1. Menu 983: choose **USB** or **Bluetooth** for KISS (one at a time).
2. USB: menu 980 to *COM + AF/IF Output* (not Mass Storage). Connect USB-C. **Windows:** install the Kenwood virtual COM driver *before* the first plugging in. **Linux:** the port is a ttyACM device, under `/dev/serial/by-id` named like `usb-JVCKENWOOD_TH-D75-if00` (D75; the D74's name is unverified). The baud setting is ignored.
   Bluetooth: pair it once with the system as in "Bluetooth" below (radio side: menu 930 on, 932 search; D74: menu 931 on, 934 pairing mode).
3. Radio type: *KISS TNC (Mobilinkd, NinoTNC, TNC-Pi, TH-D74/D75…)*. Port: the serial port, the COM port, or on Linux the paired radio in the list (`bt://AA:BB:CC:DD:EE:FF`; NeoAPRS finds its serial channel, which is usually 2, itself).
   The radio's own Bluetooth is classic only. The B.B. Link adapter (an ESP32 that joins the radio's classic Bluetooth serial to Bluetooth LE, made for iPhones) speaks the BLE KISS service, so it can be reached as `ble://`; untested by us.
4. On the radio press **[F]** then **[LIST]** until the display shows KISS (D75; D74: **[F]** then **[TNC]**). Menu 505 data speed 1200 or 9600, menu 506 data band A or B, menu 508 TX delay (D75).

- While KISS is on, the radio takes no PC commands and sends no GPS or APRS output.
- Several COM ports can appear after pairing; only one works.
- Several D75 radios on one PC all report the same USB serial number: use `/dev/serial/by-path`.

## Mobilinkd TNC3 and TNC4

1. **USB:** connect it. Linux: a ttyACM device; Windows: a COM port. Blue LED: three short blips = USB.
2. **Bluetooth:** pair it ("Bluetooth" below); if a passkey is asked for, it is `123456`. Double blip = connected. One connection at a time: close the phone app.
   Linux: pick the paired TNC in **Port** (`bt://AA:BB:CC:DD:EE:FF`; its channel is usually 1). Windows: the *Outgoing* COM port.
3. Radio type: *KISS TNC…*. Speed: any, the default is fine.

The TNC4 guide describes Bluetooth serial as working, but one project calls the TNC4 BLE-only. If it does not show up among the paired devices as a serial device, or the `bt://` connection fails, use its Bluetooth LE mode (`ble://AA:BB:CC:DD:EE:FF`, see "Bluetooth LE" below) or USB. The TNC3 and TNC4 are the devices the BLE KISS service was made for: NeoAPRS uses the same service as the aprs.fi app does. The TNC3 and TNC4 have one address for both kinds of Bluetooth; use either, one at a time. **Status of LE: untested by us** (no hardware; it follows the Mobilinkd source and the specification).

## BTech UV-PRO, Vero VR-N76, Radioddity GA-5WB

One radio sold under these names (the GA-5WB too). It has a KISS TNC that is reached over Bluetooth. **Status: untested by us.** Users report it working over classic Bluetooth serial (SPP) with APRSdroid and with Linux software through an RFCOMM port; the radio also has Bluetooth LE. The specification of KISS over Bluetooth LE (see "Bluetooth LE" below) lists it among the devices that implement it, while a RadioMail developer wrote in 2024 that it then did classic Bluetooth only, so what your radio's firmware offers is settled by trying: if `bt://` fails, try `ble://AA:BB:CC:DD:EE:FF`. Please report what you find.

1. **KISS on:** Menu, General Settings, *KISS TNC*: switch it on and save (the UV-PRO's menu; the VR-N76's names may differ slightly).
2. **Pair:** on the radio Menu, *Pairing*, OK (it stays discoverable about two minutes); then pair it with the computer as in "Bluetooth" below. The device is named `UV-PRO` or `VR-N76`. If a code is asked for, try `0000` or `1234`.
3. **Disconnect the radio's own app** (the phone app) first. A Bluetooth serial link serves one program at a time; the vendors do not say so, it is the rule for the others.
4. **NeoAPRS:** Radio type *KISS TNC (Mobilinkd, NinoTNC, TNC-Pi, TH-D74/D75…)*, **Port**: the radio, `bt://AA:BB:CC:DD:EE:FF`. Reports give RFCOMM channel 1 (a user who bound it by hand says another number did not work); NeoAPRS asks the radio which channel its serial port is on and tries 1 to 3 after it, and the log (`neoaprs.log`) says which channel connected. If it is not the right one, write it: `bt://AA:BB:CC:DD:EE:FF/1` with *Other...*.
5. The radio shows a small telephone icon beside the power level when the link is up. A silent line is normal until it hears a packet.
6. Bluetooth LE: address the radio as `ble://AA:BB:CC:DD:EE:FF` (its address is in `bluetoothctl devices` or a scan, "Bluetooth LE" below). Nothing here has been tried with this radio's LE.

- On Linux a desktop that connects the radio as a headset (audio) can get in the way: one report fixes it with `Disable=Headset` in the `[General]` section of `/etc/bluetooth/input.conf`, then restarting Bluetooth. Unverified here.
- One report says that Direwolf received through the radio's KISS but did not transmit; another saw APRS messages arrive with a `(NOT AX.25)` mark. Whether NeoAPRS is affected is not known.
- The TX delay and similar KISS parameters are not documented by the vendors; NeoAPRS does not set them.

## PicoAPRS V4

DB1NTO's pocket APRS device (VHF, 0.5 or 1 W, GPS, a KISS TNC). **Status: untested by us;** this follows the manual of the V4 (November 2023, and later firmware). It offers its KISS TNC over USB-C, TCP, **Bluetooth Classic** and **Bluetooth LE**, as four choices in its menu; NeoAPRS uses the classic one (or USB-C, or KISS over TCP, or LE as `ble://`, which is untested). The manual does not give the RFCOMM channel.

1. **Mode:** device mode *TNC*, then choose *Bluetooth* (not *Bluetooth LE*). Bluetooth works only in TNC mode and switches on with it.
2. **Pair:** the PicoAPRS is visible for 4 minutes after TNC mode is switched on and then switches Bluetooth off to save power; the Bluetooth icon in its main menu switches it on again. Pair it with the computer as in "Bluetooth" below, in that time: it is named `PicoAPRS`, both sides show a PIN, and the **right-hand button (Confirm)** on the device confirms it.
3. **NeoAPRS:** Radio type *KISS TNC (Mobilinkd, NinoTNC, TNC-Pi, TH-D74/D75…)*, **Port**: `bt://AA:BB:CC:DD:EE:FF` as listed under its name. The channel is looked up on the device; if that fails, 1 to 3 are tried, and the log says which one connected (name it with `/1` if need be).
4. The Bluetooth LE mode needs no pairing and does not appear among the paired devices; it is reached as `ble://AA:BB:CC:DD:EE:FF` ("Bluetooth LE" below; the specification of KISS over LE lists the PicoAPRS V4, the manual does not say which service it uses). The USB-C port (a virtual COM port, 115200, ignored by the device) is the other way.

## NinoTNC

1. Connect USB. Set the mode on its DIP switches (or by KISS command; see the NinoTNC wiki).
2. Radio type: *KISS TNC…*. **Speed: 57600.**
3. On Linux add the udev rules from the wiki, and see "Permissions on Linux".

## LoRa APRS (CA2RXU firmware)

The firmware of CA2RXU (Ricardo Guzman) for ESP32 LoRa boards (TTGO T-Beam, LoRa32, Heltec and others) comes in two programs: the **LoRa APRS iGate** (`richonguzman/LoRa_APRS_iGate`; iGate, digipeater, and a KISS TNC for the network) and the **LoRa APRS Tracker** (`richonguzman/LoRa_APRS_Tracker`; a tracker with a display, and a KISS TNC for a phone). **Status: untested by us;** this follows the sources of both on GitHub. LoRa APRS is not the 1200 baud AFSK of the other radios here: the frames are the same APRS text, sent by LoRa on 433.775 MHz (Europe) and heard only by LoRa APRS stations; the KISS side of the boards carries ordinary AX.25 frames.

**The iGate: KISS over TCP.** Its web configuration page has a *TNC* group; switch on *Enable TNC server (Port 8001)* and keep *Protocol* at KISS (the default; TNC2 is the other choice and NeoAPRS does not speak it). In the file `igate_conf.json` they are `tnc.enableServer` and `tnc.kissProtocol`. The server needs the board on a network (WiFi or Ethernet) and the eco mode of the digipeater off. The firmware serves up to four clients at once on TCP port **8001** (fixed in the source, not a setting) and announces itself with mDNS as `igate-<callsign>.local` and the DNS-SD service `_kiss-tnc._tcp`. What the board hears on LoRa is sent to the clients, and a frame a client sends is transmitted on LoRa when the board's LoRa transmission is on (and, with *Enable APRS Bridge*, also uploaded to APRS-IS). *Accept own frames* decides whether a frame from the board's own callsign is taken.

1. NeoAPRS: Radio type *KISS over TCP (Direwolf, soundmodem)*, TCP host: the board's address (the router's list, or `igate-<callsign>.local` where the system resolves mDNS), TCP port `8001`. Or as a port: `socket://<ip>:8001`.
2. The port is not protected: keep it inside your LAN, and only one program should send to it.
3. The board is a digipeater or iGate of its own: its callsign, beacons and path are set on its page, not by NeoAPRS.

**The Tracker: Bluetooth LE.** The Tracker has no TCP server. Its Bluetooth LE serves KISS to phones (the aprs.fi iOS app, APRSdroid with the NA7Q modification). On its configuration page (the file `tracker_conf.json`, group `bluetooth`) switch Bluetooth on (`active`), choose BLE (`useBLE`; the boards with only BLE have it fixed) and **KISS** (`useKISS`, true is KISS, false is TNC2 text). The device name is `deviceName` (default `LoRaTracker`). In KISS mode it advertises the BLE KISS service of "Bluetooth LE" above, and NeoAPRS reaches it as `ble://AA:BB:CC:DD:EE:FF` with the extra `ble`; in TNC2 mode it offers the Nordic UART Service with text lines, which NeoAPRS cannot use. A Tracker also has a classic Bluetooth mode on boards that have it (the changelog of the firmware says so); the port is then `bt://`, with the same KISS choice, untested here. The Tracker sends what it hears to the phone in pieces of up to 512 bytes, a frame may arrive in several, and KISS makes no difference to that.

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
4. NeoAPRS: Radio type *KISS over TCP (Direwolf, soundmodem)*, TCP host `127.0.0.1`, TCP port `8001`.
5. Direwolf on another machine (a Pi): enter its address as the TCP host. Port 8001 is open to the whole network: keep it inside your LAN.

- **Never choose the Digirig's serial port as a serial TNC.** Opening it keys the transmitter through RTS. Choose KISS over TCP.
- Channels, TX delay and the like are Direwolf's: see its User Guide.

## UZ7HO soundmodem (Windows)

1. In the soundmodem settings choose the sound card and the PTT as for any modem, and switch on its KISS server.
2. NeoAPRS: *KISS over TCP*, TCP host `127.0.0.1`, TCP port as in the soundmodem's setting. Reports say 8100 (unverified; the AGW port is 8000, do not use it). If NeoAPRS does not connect, check that the KISS port is on and the AGW port is not the same number.
3. QtSoundModem works the same way.

## Kantronics KPC-3+

1. Connect RS-232 (the KPC-3XE has USB).
2. Radio type: *Kantronics KPC-3+*, speed: the speed of the terminal port.
3. NeoAPRS sends `INTFACE KISS` and `RESET`. The TNC stays in KISS across power cycles. A user reports that the host baud seemed to change after the RESET; if the TNC goes silent, set the baud again. Unverified.

KISS exit is `C0 FF C0`, or a hard reset.

## Bluetooth

NeoAPRS uses two kinds of Bluetooth. **Classic Bluetooth serial** (the Serial Port Profile, SPP/RFCOMM, `bt://`, Linux) is for the Kenwood TH-D74/D75, the Mobilinkd TNC3, a TM-D700 with a Bluetooth serial module. **Bluetooth LE** (`ble://`, "Bluetooth LE" at the end of this section) is for the devices that carry KISS over it: the Mobilinkd TNC3/TNC4, the LoRa APRS Tracker and the others the specification lists.

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

2. In NeoAPRS, **Settings** tab, **TNC** group, **Port**: choose the radio, listed by its name as `bt://AA:BB:CC:DD:EE:FF` (Refresh if it is new). The setup guide's radio step lists it too.

The list is the system's own (BlueZ, which KDE's Bluedevil and the other desktops use), so a radio paired in any of them appears. NeoAPRS opens the Bluetooth link itself: no `rfcomm bind`, no root, no dialout group. The serial channel is looked up on the radio when the port is opened (the TH-D74/D75 use 2, Mobilinkd 1); if the radio lists none, or refuses the one it lists, channels 1 to 3 are tried in turn and the log says which connected. To name it, write it after the address, `bt://AA:BB:CC:DD:EE:FF/2`, with *Other...* in the list. The link is made when NeoAPRS opens the port and drops when the radio sleeps or goes out of range; NeoAPRS opens it again. The list holds the paired devices that have a serial port (a device the system has not yet looked into is listed too). It is read from BlueZ's records and no device is connected to for it. The search for the radio does not look at Bluetooth devices: a `bt://` port is used only when it is chosen. A radio keeps one connection at a time: close the phone app or the other program first. If the open fails with "Connection refused", the channel is wrong (name it); "Host is down" or "no answer" means the radio is off or out of range or its Bluetooth is off.

The older way still works as a fallback, when a program of the system has to share the link or your Python has no Bluetooth sockets: `sudo rfcomm bind /dev/rfcomm0 AA:BB:CC:DD:EE:FF 2` (the last number is the channel; `sdptool browse AA:BB:CC:DD:EE:FF` lists them), then the port is `/dev/rfcomm0`. `rfcomm` is deprecated in BlueZ but still works.

**Windows**

1. Settings, Bluetooth & devices, add the radio or TNC and pair it.
2. More Bluetooth settings, *COM Ports* tab: Windows lists two ports; use the **Outgoing** one. Choose it as the **Port** in NeoAPRS.
3. An older PC may ask for the PIN `0000`.

`bt://` ports are for Linux. **macOS:** pair the radio in System Settings, Bluetooth; the serial port is the `/dev/cu.*` one named after it.

### Bluetooth LE

A Bluetooth LE device offers a *GATT service*, and a KISS TNC has one with two *characteristics*: NeoAPRS writes KISS bytes to one and is notified of KISS bytes on the other, as a serial line. The service the radios and TNCs of this guide use is the **BLE KISS service** of the aprs.fi apps and the Mobilinkd TNC3 and TNC4: service `00000001-ba2a-46c9-ae49-01b0961f68bb`, the TNC takes writes on `00000002-...` and notifies on `00000003-...` (the specification of KISS over BLE, hessu/aprs-specs, lists the Mobilinkd TNC3 and TNC4, the PicoAPRS V4, the RPC Electronics ESP32-APRS tracker, the CA2RXU LoRa APRS Tracker, the B.B. Link adapter for the Kenwood TH-D74/D75, the UV-PRO/VR-N76/GA-5WB and a do-it-yourself ESP32 adapter). NeoAPRS also knows the **Nordic UART Service** (`6e400001-b5a3-f393-e0a9-e50e24dcca9e`, write `6e400002-...`, notify `6e400003-...`), which homebrew BLE-to-serial TNCs use; no device of this guide does for KISS (the LoRa APRS Tracker's Nordic UART Service carries TNC2 text lines, not KISS, and NeoAPRS cannot use it).

1. **Install the extra.** The BLE library (bleak) is not part of the base install: `pip install 'neoaprs[ble]'`, or `uv tool install 'neoaprs[ble]'` for an install made with uv. Without it a `ble://` port does not open and says so. The deb, the AppImage and the Windows installer do not have it.
2. **Linux** needs BlueZ running (`bluetoothd`, `systemctl status bluetooth`) and a Bluetooth adapter that does LE. NeoAPRS talks to BlueZ over the system's D-Bus as any user: BlueZ's own D-Bus policy lets every user do that, so no root and no `bluetooth` group (an old distribution's policy may differ; then add the user to the `bluetooth` group). **Windows 10/11** and **macOS** use the system's own Bluetooth LE, and macOS asks once whether the program may use Bluetooth.
3. **Switch the device on, put it in LE mode and close the phone app.** A BLE device is connected to one program at a time and stops advertising meanwhile; a device that is connected to a phone cannot be found.
4. **Find its address.** Linux: `bluetoothctl`, `scan le`, and note the address of the device by its name (the Mobilinkd TNC3 advertises itself as `TNC3`; the LoRa APRS Tracker as `LoRaTracker` unless renamed). **macOS** does not give the address: the system gives the device an identifier like `6E6C9C1A-0E5D-4A3B-9D6C-0123456789AB`, which is the address of the port there. A device that asks for a PIN is paired once with the system first (`pair AA:BB:CC:DD:EE:FF` in `bluetoothctl`; the Mobilinkd's is `123456`).
5. **In NeoAPRS**, **Settings** tab, **TNC** group: Radio type *KISS TNC…*, **Port**, *Other...*, and type `ble://AA:BB:CC:DD:EE:FF`. Or for one run: `neoaprs --port ble://AA:BB:CC:DD:EE:FF`. A Bluetooth LE device is not listed in the Port choice (finding one takes a scan of several seconds), and the search for the radio does not look for them.

The port is opened by finding the device by its address (up to 10 s), connecting, looking at its services and using the first of the Mobilinkd/aprs.fi service and the Nordic UART Service that it has; the log (`neoaprs.log`) says which: `connected, using the BLE KISS service ... (none was named)`. To use one only, or another service, write it after the address: `ble://AA:BB:CC:DD:EE:FF/nus`, `ble://AA:BB:CC:DD:EE:FF/mobilinkd`, or the UUID of a GATT service (`ble://AA:BB:CC:DD:EE:FF/ffe0`, as an HM-10 module has: the characteristic that can be written and the one that notifies are then found by what they can do). Bytes are written without a response where the characteristic allows it, in pieces of what the link takes (20 bytes at least). A device that goes out of range, is switched off or is taken by a phone is a line that dropped, and NeoAPRS opens it again after 5, 10, 20, 30 seconds. Failures say what bleak said, or "the device does not answer (is it switched on, in range and not connected to a phone?)".

Not every radio's Bluetooth LE is KISS. The BTech UV-PRO family also has a Bluetooth LE protocol of the vendor for the radio's own app and for settings; NeoAPRS speaks none of it, only KISS (a UV-PRO needs its KISS TNC switched on). **Status: untested by us.** There was no Bluetooth LE hardware at hand, so the port is tested with a fake device that behaves as the specification says (the profile search, notifications, writes in pieces, a lost link), and the services above are read from the sources listed below.

## A GPS receiver

A moving station ([the Beacon tab](manual/beacon.md#mobile-operation)) takes its position from a GPS. It is not a radio and is not connected the way a radio is.

1. **gpsd.** On Linux the GPS service gpsd reads a USB or serial receiver and serves its fixes on TCP port 2947. In the Beacon tab choose **Position**, **A GPS via gpsd**; the **gpsd address** is `127.0.0.1:2947` for a gpsd on this computer, or the address of the one on another computer.
2. **A receiver on a serial port.** Any receiver that sends NMEA sentences (a u-blox USB stick, a GPS puck) can be read directly: **Position**, **A GPS on a serial port**, then the **GPS port** from the list (Refresh after plugging it in, *Other...* for a typed path or `socket://host:port` of a receiver behind a TCP serial server) and the **GPS speed**: 4800 is the speed of NMEA itself, and many USB receivers speak 9600. A wrong speed shows as no fix.
3. **Keep it apart from the radio.** One device cannot be both: the GPS has a port of its own. With the radio on `/dev/ttyUSB0` the GPS may be `/dev/ttyUSB1`; naming the radio's port in the Settings tab keeps the search for the radio from listening to the GPS ([Not working?](#not-working), item 5).

The beacon status at the top of the Beacon tab says whether the receiver is connected and has a fix. With no fix nothing is sent, and never the position you gave for a fixed station.

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
5. **Port search finds the wrong device:** name the port in the Settings tab, TNC group, or keep the search away from that device: `neoaprs db set serial/skip /dev/ttyUSB2`.
6. **A port is not searched:** the search leaves out development boards, because opening their USB console resets the chip (an ESP32 on a USB Serial/JTAG port restarts at every open): Espressif (303a), Arduino (2341, 2a03), Raspberry Pi Pico (2e8a), Adafruit (239a), Teensy (16c0:0483), SEGGER J-Link (1366) and ST-Link (0483:3744, 3748, 374b, 374d, 374e, 374f, 3752, 3753). The log says `skipping /dev/ttyACM0: an ESP32 development board (USB 303a:1001)`, and `neoaprs doctor` marks the port. USB-serial cables and the TNCs' own ports (FTDI, Silicon Labs, WCH, Prolific, the Mobilinkd's ST 0483:5740, Kenwood radios) are searched. A TNC built on one of these boards works when you choose its port by name (**Port** in the Settings tab, or `--port`): a named port is never left out.
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
- [Specification of KISS over BLE (hessu/aprs-specs, BLE-KISS-API.md)](https://github.com/hessu/aprs-specs/blob/master/BLE-KISS-API.md), [KISS over TCP with DNS-SD](https://github.com/hessu/aprs-specs/blob/master/TCP-KISS-DNS-SD.md)
- Mobilinkd's BLE service in its own code: [iosTncConfig, UUIDKey.swift](https://github.com/mobilinkd/iosTncConfig/blob/master/Mobilinkd%20TNC%20Config/UUIDKey.swift), [BLEConfig, BluetoothService.kt](https://github.com/mobilinkd/BLEConfig/blob/master/app/src/main/java/com/mobilinkd/bleconfig/BluetoothService.kt), [tnc3-firmware](https://github.com/mobilinkd/tnc3-firmware)
- [B.B. Link, the BLE adapter for the Kenwood TH-D74/D75](https://github.com/islandmagic/bb-link), [kiss-ble-uart-tnc](https://github.com/tomasgeci/kiss-ble-uart-tnc)
- [LoRa APRS iGate (CA2RXU): tnc_utils.cpp, configuration.cpp, data_embed/index.html](https://github.com/richonguzman/LoRa_APRS_iGate), [LoRa APRS Tracker (CA2RXU): ble_utils.cpp, kiss_utils.cpp, configuration.cpp](https://github.com/richonguzman/LoRa_APRS_Tracker)
- [benlink, a library for the vendor's own Bluetooth protocol of the UV-PRO family](https://pypi.org/project/benlink/)
- [bleak, the Bluetooth LE library](https://github.com/hbldh/bleak), [BlueZ D-Bus policy](https://github.com/bluez/bluez/blob/master/src/bluetooth.conf)
- [Mobilinkd TNC4 guide](https://mobilinkd.s3.amazonaws.com/TNC4/MobilinkdTNC4.pdf), [TNC3 guide](https://mobilinkd.s3.amazonaws.com/TNC3/MobilinkdTNC3.pdf)
- [NinoTNC wiki](https://wiki.oarc.uk/packet:ninotnc)
- [Direwolf](https://github.com/wb2osz/direwolf), [Direwolf User Guide](https://packet-radio.net/wp-content/uploads/2018/10/Direwolf-User-Guide.pdf)
- [Soundmodem ports (Digirig forum)](https://forum.digirig.net/t/soundmodem-and-pinpoint-aprs-with-digirig-will-not-tx-aprs-packets/2340), [QtSoundModem](https://wiki.oarc.uk/packet:qtsoundmodem)
- [G7JJF TNC init strings](https://g7jjf.com/tncsetup.htm), [Kantronics KPC-3+ KISS](https://manualzz.com/doc/o/22vn6v/kantronics-kpc%E2%80%933-plus-user-manual-kiss-mode)
- [Icom ID-5200A](https://www.icomjapan.com/lineup/products/ID-5200A/), [D-PRS](https://www.aprs-is.net/dprs.aspx)
- [Yaesu receive-only gateway (ygate)](https://github.com/craigerl/ygate)
