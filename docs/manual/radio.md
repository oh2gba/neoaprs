# The radios

Plug in your radio, tell NeoAPRS what it is, and the map fills with the stations it hears. A station may have one radio or several: a handheld's TNC for the local FM network, an SSB radio with the Mercury modem for stations a thousand kilometres away, a LoRa board on the roof. Every station any of them hears is on the same map and in the same station book, and each message goes out on the radio that reaches its station.

This chapter says what a radio is in NeoAPRS, how to add one, and what to choose for each kind of radio. How to wire each radio and TNC is in [`docs/RADIOS.md`](../RADIOS.md).

## A radio in NeoAPRS

A radio is one box in **Settings → Radio**: the radio with its TNC or modem, the way NeoAPRS reaches it, and what it may do on the air.

- **Its kind** is Packet, Mercury or LoRa: how its signal is made, which says who can hear it. A packet radio is heard by every classic APRS station, on VHF and UHF or on HF, a Mercury radio only by stations that run the Mercury modem on the same frequency, a LoRa radio only by LoRa APRS stations. The kind also says what the radio may carry: a path of digipeaters, the fill-in digipeater, SmartBeaconing, a beacon at short intervals. It is fixed when the radio is added.
- **Its type** is the line of the list that matches the device, such as *KISS TNC* under Packet or *Sound card* under Mercury. It says what you have in hand: a radio or a TNC by its model, a sound card, a tracker or an iGate. Where it stands alone, in the box's **Radio type** and in the log, its kind comes first: *Packet, KISS TNC*, *Mercury, sound card*. It can be changed within the kind. A radio keeps the values of a type it leaves.
- **Its name** is a short word the page calls it by everywhere: on its tags, in Route, in the Send on ticks. A radio with no name of its own is called by its kind: "Packet", "Mercury", "LoRa", and "Packet 2" for the second of a kind.

With one radio, only the tags of how a packet or a station came name it ("Packet", or the name you gave it): Settings → Radio has its one box and **Add radio** under it. With several radios on, every tag, message, object and Monitor says which radio it belongs to.

## The Radio group

The Radio group of the Settings tab has, from the top:

- one box for each radio, in the order they were added;
- **Add radio**, last.

The box of a radio that is on has its **Enable** tickbox, its status line and, behind the arrow of the status line, its **Radio type**, the fields of that type and what the type can do (Find my radio, Tune, the Spectrum, the Terminal). The box of a radio that is off is its Enable alone (with its Name and Remove, below). A box folds by the arrow in front of its name, and the page remembers in this browser which ones you folded. A box opens by itself while its radio is on and not connected, when the daemon refuses one of its settings, and when the page leads you to it.

The box is called after its kind ("Packet radio", "Mercury radio", "LoRa radio", and "Packet radio 2" for the second of a kind). With several boxes, a radio you gave a name is called by it. The setup guide's Radio step shows the same boxes ([start.md](start.md#the-setup-guide)).

### Adding a radio

**Add radio** is a choice of the type and an **Add** button beside it. The list has every type there is, in four groups: **Packet (classic APRS)**, **Mercury (DATAC3)**, **LoRa**, and **Without a radio**, the [Dummy radios](#the-dummy-radios) for trying NeoAPRS out. In a group, what most stations have comes first and the types that only receive come last. Choosing a type adds nothing; **Add** adds the radio, and the page opens its box, brings it into view and puts the keyboard on its Enable. Fill in what its type asks for (a port, a sound card, an address) and watch its status line.

A new radio is on. To change a radio's kind, add a radio of the other kind and remove the old one.

### Name, enable, remove

- **Enable** switches the radio on and off. Its settings are kept while it is off. A station keeps one radio on: the Enable of the only radio that is on is greyed, with the hover text "The station's only radio that is on".
- **Name** and **Remove** are in every box once the station has more than one. The name is at most 8 characters, such as `20 m` or `Mobile`, and is saved when you leave the field or press Enter. Its placeholder is what the radio is called without one. A name another radio has, or the name of a kind ("Packet", "LoRa 2"), is refused under the field.
- **Remove** asks twice: it reads **Really remove?** after the first press. It is off for the only radio that is on. A removed radio's packets and messages keep its name, and its box is gone.

### What goes on which radio

All radios are equal: each thing the station sends of its own has its own radios.

- Each has its own **Send on**, a tick for each radio that can send, beside the thing it sends:
  - the beacon, under the Beacon choice of the My station tab ([beacon.md](beacon.md#the-beacon-on-several-radios));
  - the status report, under the Status choice of the same tab;
  - Ask around, under Ask in the Nearby tab; Local info, under Ask in its box of the Objects tab;
  - each object, in its form in the Objects tab ([objects.md](objects.md)); each bulletin, in the Post box of the Bulletins tab ([bulletins.md](bulletins.md)).
- Email goes on one radio, chosen beside Check email in the Email tab ([email.md](email.md#which-radio)).
- With one radio that can send on, everything goes on it, whatever is ticked, and no tick is shown.
- With several, each thing goes on the radios ticked for it that are on, and on none while none of them is.
- A radio you add or switch on stops nothing: what went on the radios that were on goes on there, and a new radio starts with its beacon alone. A new object or bulletin starts with the radios of the one you saved last.
- A message to a call no radio heard, and a text to `CQ`, `ALL` or `QST`, go on the radio that can send whose box is highest in this group ([messages.md](messages.md#the-radio-of-a-message)).

## What each radio does, and what the station does once

Each radio has its own:

- **beacon tick.** While several radios are on, **Send on** in the Beacon group of the My station tab has a tick for each of them ([beacon.md](beacon.md#the-beacon-on-several-radios)). The beacon goes out on every radio that is ticked.
- **beacon interval in force.** The station has one interval; a radio that has a floor raises it to that floor. A fixed station's beacon on a Mercury or a LoRa radio goes every 30 minutes at the most often; a moving station's on a LoRa radio follows SmartBeaconing, as on a packet radio on VHF. A packet radio on VHF or UHF keeps the interval you chose; one on HF is held to 30 minutes as a Mercury radio is. Every timed send has a random pause: up to 30 seconds on a packet radio on VHF or UHF, up to 5 minutes on HF, Mercury and LoRa ([beacon.md](beacon.md#the-random-pause)).
- **path.** A radio that may carry a path has its own **Path** row in the My station tab, under Advanced. A Mercury radio sends its frames direct, with no path; only a message or an ack to a station that was heard through a gateway goes with the gateway's call ([how](beacon.md#passing-a-packet-between-two-radios)), and what is RF only goes with `RFONLY` ([RF only](messages.md#rf-only)).
- **digipeater tick.** The Digipeater group of the Settings tab has an **Enable** for each packet radio on VHF or UHF that is on. A packet radio on HF, a Mercury or a LoRa radio repeats nothing as a fill-in; a packet reaches one from another radio only through a [pair](beacon.md#passing-a-packet-between-two-radios). Each pair has its own box in the group.
- **status line, statistics and Terminal**, and what it heard of each station: when, by which route, and the path that reaches it.

The station has once: the call, the position and the symbol, the comment, the beacon interval, the GPS and SmartBeaconing, the status text and its interval, **RX only**, Internet (APRS-IS) (whose Send what I hear gates what every radio hears) and the alerts.

A message goes on one radio: the one you choose in Route, else the radio that heard the station lately ([messages.md](messages.md#the-radio-of-a-message)). An ack or an answer goes back on the radio the message came in on.

A radio that only receives (a Yaesu FTM, the LoRa iGate on USB) is left out wherever the page offers a choice of radio. Beside one other radio there is no **Send on** and no radio to choose in Route. A message heard only on it is acked on the radio a message to that station would take; a query heard only on it is not answered.

## The types

A new installation has no radio. Each radio is added with its type: in **Add radio** under the boxes (in the setup guide's Radio step too), or with `neoaprs db radios add TYPE`. Its kind follows from the type.

### A TNC on a serial port

**For:** a radio with a KISS TNC inside (Kenwood TH-D74, TH-D75, the Mobilinkd TNC3 and TNC4, a NinoTNC, a TNC-Pi), or a TNC on a serial cable or over Bluetooth.

**Choose:** the type of the TNC, under Packet:

- *KISS TNC* for a TNC that is in KISS when it is switched on;
- *Kenwood TM-D710 / TH-D72*, *Kenwood TH-D7, TM-D700, TNC-2* (the TS-2000 too) or *Kantronics KPC-3+* for a TNC that NeoAPRS puts into KISS itself ([The TNC type](#the-tnc-type)).

Then **Port** and, only when the TNC's manual says so, **Speed** (a NinoTNC needs 57600). On Linux the Port may stay *find automatically*. On Windows and macOS pick the port from the list, or press **Find my radio** ([below](#find-my-radio)).

**On HF**: tick it when the TNC is on an HF radio (classic APRS at 300 baud). The radio is then held as a Mercury radio is: the beacon every 30 minutes at the most often, a random pause of up to 5 minutes before what goes by the clock, a pause before each retry of a message, no fill-in digipeater and no SmartBeaconing. Every type above has it, and so has *Direwolf* below.

**When it works:** the status line says *connected* and "Last packet 2 min ago". A TNC in KISS says nothing until it hears a packet, so on a quiet channel the first packet may take a while.

### Your own Direwolf or soundmodem

**For:** a program you run yourself that speaks KISS on the network: Direwolf, UZ7HO SoundModem or QtSoundModem, a serial server such as `ser2net`.

**Choose:** *Direwolf* under Packet (for a sound modem too), then **Address** (the computer it runs on, `127.0.0.1` for this one) and **Port**: Direwolf listens on 8001, the sound modems on 8100 (their KISS port, not their AGW port).

**When it works:** the status line says *connected* as soon as the program answers. NeoAPRS writes nothing but KISS frames to it, and opens the line again whenever it drops.

### Sound card

**For:** a radio on a sound-card interface (a Digirig, an AIOC, a SignaLink, a USB sound card, the radio's own USB audio) with no TNC of its own: an FM radio for the APRS network on VHF or UHF, or an SSB radio for classic APRS on HF. On Windows and Linux NeoAPRS carries Direwolf and starts it for the radio: nothing else to install. The sound card is not a TNC: opening its serial port as one would key the transmitter.

**Choose:** under Packet, *Sound card, 1200 (VHF/UHF)* for an FM radio, or *Sound card, 300 (HF)* for an SSB radio on HF, whose usual dial is 10.1476 MHz USB. Its box has:

- **Sound card**, the interface's card, proposed for you. When no card could be the radio's, the radio waits for one rather than play to the computer's speakers. One sound card is one radio's: a card a Mercury radio holds is refused, and the other way round.
- On Linux with PipeWire or PulseAudio the sound is two choices, **Sound from the radio** and **Sound to the radio**. Each lists the sound cards and the desktop's own sound devices by the names its sound settings show, devices you made yourself too. A device of more than two channels is also offered one channel at a time (*Rubix44, channel 1*): choose the radio's, and nothing else on the device is mixed in. When a chosen device is gone the radio waits, as for a card that is not there, and never plays to the loudspeakers.
- **Keying**, proposed from what is plugged in: the CM108 pin of an AIOC, RTS of the interface's own serial port (a Digirig), else VOX. On Linux the lines of the serial ports that sit on one USB hub with the sound card come first in its list. At the end of the list are *flrig* and *rigctld*, for a radio keyed by its own commands ([below](#keying-through-flrig-or-rigctld)). **Test** beside it keys the radio for a second.
- **Tune**, ten seconds of Direwolf's two tones, for the audio level or finding the radio's sound card, and **Transmit level**: where the sound card has a playback level of its own, a slider for it, from 0 to 100 %; else Direwolf's own level, from -20 to 0 dB with **-** and **+**. A radio whose Direwolf level you moved off 0 dB keeps its **-** and **+** until it is back at 0 dB and you open the box again; then the slider is there. Until the radio has run once since NeoAPRS started, the row shows neither.
- **Receive level**, the level of the audio that arrives now, on a bar with its good range in green: a packet should reach the green, and with the radio off the bar is empty. While you look at it the bar follows the audio ten times a second, so you see at once what choosing another sound card, moving a plug or turning the radio's volume does. Where the sound card has a capture level of its own, its slider stands before the bar: move it and watch the bar.

The two sliders are the sound card's own levels, the ones the desktop's sound settings move too (on Linux and Windows; a card without such a control has no slider). Each slider starts where the card is. Once you move one, NeoAPRS keeps the value and puts it back on the card each time the radio starts, so a replug or the desktop does not leave the radio faint. A radio set to a sound card another radio is using leaves that card's levels alone.

A slider changes nothing else: Direwolf is not restarted. The card's own switches, a mute or an automatic gain, stay as they are; with the automatic gain on, the receive slider does less. Several presses of **-** and **+** in a row make the radio stop listening once, when you stop pressing.

Each transmission is the same for every keying: from the moment the radio is keyed, 300 ms of flags (the steady sound before the packet, in which the radio comes up to power), the packet, then 200 ms of flags before the radio is let go. Through flrig or rigctld the flags last 400 ms, since the command to the radio comes first.

**On HF** (*Sound card, 300 (HF)*) Direwolf runs its 300 baud modem, the tones 1600 and 1800 Hz with seven decoders 30 Hz apart, so that a station up to about 100 Hz off the dial is still decoded; the status line says *AFSK300*. A packet takes seconds on the channel there, so the radio is held as a Mercury radio is: the beacon every 30 minutes at the most often, a random pause of up to 5 minutes before what goes by the clock, a pause before each retry of a message, no fill-in digipeater and no SmartBeaconing.

**When it works:** the status line says *connected*, and a packet Direwolf decodes is on the map a moment later.

On a Mac there are no *Sound card* types under Packet: run Direwolf yourself ([`docs/RADIOS.md`](../RADIOS.md#your-own-direwolf) has its few lines of setup) and add a radio of the type *Direwolf* with **Port** 8001. The same holds for a Direwolf of your own on any computer.

### The Mercury modem

**For:** a radio with a sound card or an interface (a Digirig, a SignaLink, the radio's own USB audio), to reach stations that run the same modem: most often an SSB radio on shortwave. The Mercury modem comes inside NeoAPRS, which starts and stops it. It works through any radio's audio, on any band: an SSB radio on 6 m or on 2 m, an FM radio too.

**Choose:** *Sound card* under Mercury (DATAC3). **Sound card** and **Keying** are chosen for you; check that they are the radio's. Tune the radio to a dial of **Suggested frequencies**. Only stations on the same modem and the same frequency hear each other.

**When it works:** the status line says *Listening*, then the signal-to-noise ratio of each frame heard: "DATAC3 · Listening · SNR 3 dB · Last packet 2 min ago". The details are below ([The Mercury radio's box](#the-mercury-radios-box)).

### Your own Mercury

**For:** a Mercury you start yourself, such as Rhizomatica's Mercury for Windows, which keys the radio and has the sound card itself.

**Choose:** *Your own program* under Mercury (DATAC3), then **Address** (the computer it runs on, `127.0.0.1` for this one) and **Port**, its KISS port: 8100 unless you started it on another. Its control port must be the one 200 above, 8300 for 8100, as Mercury has them unless told otherwise. The box has no sound card, keying, tune or level: those are your Mercury's.

NeoAPRS starts no Mercury of its own for this radio. It is a Mercury radio in every other way: the slow pace of the beacon, the frame of 123 bytes, no frame while your Mercury transmits or hears another station, PSK Reporter. Your Mercury must run DATAC3, the mode of every station NeoAPRS talks to; NeoAPRS does not ask its version.

**When it works:** the status line says *Listening* as soon as your Mercury answers on its control port, and *Not connected* while it does not.

### A LoRa APRS board

**For:** an ESP32 board with a LoRa chip (a LilyGO LoRa32 or T-Beam, a Heltec WiFi LoRa 32) running the CA2RXU iGate or Tracker, DL9SAU's tracker or esp32_loraprs. A LoRa radio hears only LoRa APRS stations, on 433.775 MHz in Europe.

**Choose** one of three types, of the kind LoRa:

| type | for | what to fill in |
|---|---|---|
| *Tracker or iGate on Wi-Fi* | the CA2RXU iGate on WiFi, its TNC server set to KISS | **Address**: the board's address, which you type (nothing is opened until then); **Port** 8001 |
| *Tracker or iGate, USB or Bluetooth* | the CA2RXU Tracker's TNC image, the CA2RXU iGate's TNC on USB, DL9SAU's tracker, esp32_loraprs | **Port**: the serial port, or a `bt://` or `ble://` address |
| *LoRa APRS iGate on USB (RX only)* | the CA2RXU iGate on USB as it comes, its TNC off | **Port**. This radio only receives: nothing is ever sent on it, and it is left out of every choice of radio ([above](#what-each-radio-does-and-what-the-station-does-once)) |

- **Set the board to KISS.** A board left in TNC2 text is heard and sends nothing; its status says "the board sends text lines: set it to KISS". A CA2RXU Tracker on classic Bluetooth is turned to KISS by NeoAPRS itself.
- **On the CA2RXU iGate:** *LoRa Tx* on, or what you send goes nowhere; a callsign of its own, or *Accept own frames*; the *APRS bridge* off.
- **The frequency and the LoRa settings** (433.775 MHz, SF12, 125 kHz in Europe) are set on the board, not here.
- **What goes out:** our frames go by WIDE1-1 when the radio has no path of its own; a fixed station's beacon at most every 30 minutes, each timed send with a random pause of up to five minutes. A frame over 250 bytes, 252 bytes of text or 256 bytes of KISS (its escapes counted) has its comment shortened, or is not sent. NeoAPRS repeats nothing on LoRa as a fill-in (a packet from another radio reaches it only through a [pair](beacon.md#passing-a-packet-between-two-radios)): the network's iGates do. A board on USB is never searched for: choose its port.

**When it works:** the status line says *connected*, and packets come with their signal where the board gives it: the CA2RXU iGate on the network, DL9SAU's tracker, esp32_loraprs and the iGate on USB; the CA2RXU Tracker gives none. [`docs/RADIOS.md`](../RADIOS.md) has each firmware's settings.

### A Yaesu FTM, or a TNC that has no KISS

**For:** a Yaesu FTM-100, FTM-400 or FTM-500 on the data cable that comes with it (the FTM-300 has not been tried), or a TAPR TNC-2 (or clone), a Kantronics or an AEA PK-232 left in its own monitor mode. They print what they hear as text, and they cannot be sent through.

**Choose:** *Yaesu FTM, receive only* under Packet (for a TNC in monitor mode too), then **Port** and **Speed** (9600 for an FTM). On the FTM set Setup → DATA → COM PORT SETTING to OUTPUT PACKET at 9600. What to set on each TNC is in [`docs/RADIOS.md`](../RADIOS.md).

**When it works:** what the radio hears is on the map, and with Send what I hear on the station gates what it hears to APRS-IS. NeoAPRS writes nothing to the line, not even a carriage return. The radio is never a message's, the beacon's, an object's or a bulletin's: it has no Path row in the My station tab and no Enable in the Digipeater group, and it is left out of every choice of radio ([above](#what-each-radio-does-and-what-the-station-does-once)). While it is the only radio on, nothing is sent and the switch at the top right of the page reads **RX only**.

### The Dummy radios

A Dummy is a radio that is not there: NeoAPRS makes up the traffic itself, around your position (around Helsinki until you have set one), on any system, with no port and nothing on the air. There is one for each kind.

Every call is made up on the prefix Q (`Q1ABC`, `Q3TKU`), which the ITU gives to no country, so none of them is anybody's. What you send to a Dummy is swallowed. Its status line says so in a muted pill, its stations have the tag **Dummy**, and the header's radio mark is dashed while every radio is a Dummy.

#### The Dummy packet radio

*Dummy packet radio* is the packet Dummy.

- A few stations that stay (a house, a club, a cottage), three cars and a walker on routes round the position, a weather station that reports every 5 minutes, two digipeaters that repeat the others, two objects, a bulletin now and then and a status. Something is on the air within half a minute, then a few packets a minute.
- **The stations that take messages answer.** A message to one of them is acked after a moment and answered with "Hello from the dummy radio".
- **The club station Q1CLB answers local info**, with its categories 70 cm repeater and Food ([objects.md](objects.md#asking-for-local-info)).
- A digipeater is heard repeating a beacon of yours now and then, as if it had been on the air.
- The status line says **Dummy radio: made-up traffic, nothing goes on the air**.

#### The Dummy Mercury radio

*Dummy Mercury radio* is the Mercury Dummy: APRS over HF with no radio and no other station on the air.

- Six fixed stations hundreds of kilometres away (Turku, Kuopio, Oulu, Stockholm, Hamburg, Warsaw), each beaconing every half hour to an hour, every frame direct. The first beacons come within two minutes, so the map fills while you watch.
- **Q3TKU in Turku answers a message**: an ack about eight seconds later and "Hello from the dummy Mercury radio" after it. The others take messages and stay quiet, as most do.
- **You hear what the modem sounds like.** On Linux your own frames are played through the computer's speakers as the modem's real audio; nothing is keyed. On Windows the Dummy Mercury radio runs without the sound.
- The status line says **Dummy Mercury radio: made-up distant stations, your frames on the speakers, nothing goes on the air**.

#### The Dummy LoRa radio

*Dummy LoRa radio* is the LoRa Dummy: a few made-up LoRa APRS stations round your station, among them an iGate that repeats your beacon. Your frames go by WIDE1-1, as on a real LoRa radio. Switch it off and its made-up stations are forgotten.

## The port

A radio on a serial line has one choice, **Port**, behind the arrow of its status line: its own setting `radio/<id>/port` (`neoaprs db set radio/1/port ...` for radio 1).

| port | what it is |
|---|---|
| a serial port | `/dev/ttyUSB0`, `/dev/brainbox_3`, `COM3` or a macOS `/dev/cu.*` port |
| `socket://host:port` | KISS over TCP (`tcp://host:port` is accepted too), such as a bridge made with `ser2net`. It works with every TNC type |
| `bt://AA:BB:CC:DD:EE:FF` | Linux and Windows: a Bluetooth radio or TNC paired with the computer, listed by its name. `bt://AA:BB:CC:DD:EE:FF/2` names the RFCOMM channel. No COM port, no `rfcomm bind` and no root |
| `ble://AA:BB:CC:DD:EE:FF` | a Bluetooth LE KISS TNC (the Mobilinkd TNC4 in LE mode, the LoRa APRS tracker, the PicoAPRS V4 in its LE mode and the like). `ble://AA:BB:CC:DD:EE:FF/nus` names the profile (`mobilinkd` or `nus`) or a GATT service by its UUID. The downloads have Bluetooth LE; an install with pip or uv needs its extra: `pip install 'neoaprs[ble]'` or `uv tool install 'neoaprs[ble]'`. On macOS the address is the UUID the system gives the device |

The Port choice offers *find automatically* on Linux (*not set* on Windows and macOS, and for a LoRa board), the ports the system lists, the paired Bluetooth devices that have a serial port (by name, on Linux and Windows), and *Other...* for a path or a `socket://` or `ble://` address typed (a Bluetooth LE device is not listed: it is typed). **Refresh** asks again. Beside an automatic port it says `found: PORT` when NeoAPRS has found the radio before. A port another radio of the station is set to is refused, with that radio's name.

- **A port on the network** (`socket://`, or a type that takes an Address and a Port) has no speed and is never searched for. Nothing is sent to it that is not a KISS frame, so there is no keep-alive check. A connection that closes is a line that dropped, and it is opened again after the back-off.
- **A Bluetooth port** has no speed and is never searched for or opened to list it. A link that drops (the radio is switched off or out of range) is opened again like any other. On macOS the paired device's `/dev/cu.*` port is the way ([`docs/RADIOS.md`](../RADIOS.md#bluetooth)).
- **Bluetooth on Windows:** pair the device in Windows first (Settings, Bluetooth & devices). It then appears in the Port list by its name, *Bluetooth: NAME*, and NeoAPRS connects to it directly; the two COM ports Windows made for it are not offered beside it. A radio already set to one of those COM ports keeps working; the one that reaches no device, the computer's incoming port, says to choose another. What the status line says when the device cannot be reached:
  - *Another program has the port: close it*: another program (a terminal, APRSIS32, a rig program) has the COM port open.
  - *The device does not answer: switched off, asleep or out of range*: switch it on, wake it or bring it nearer; NeoAPRS keeps trying.
  - *The device is not paired with this computer*: pair it in Windows again.
  - *The device refused the connection*: its serial port is busy (a phone app has it) or it offers none on that channel; close the phone app.
  - *The port could not be opened*: anything else; the log has Windows' own words and number.
- **A Bluetooth LE port** is not paired the way a classic device is: NeoAPRS looks for the device by its address when the port is opened and uses the KISS service it finds. A device that another program or a phone is connected to cannot be reached: LE allows one connection at a time.
- **A virtual COM port on Windows** (com0com, hub4com, VSPE: a rig shared between programs) is listed by its name alone. NeoAPRS never picks one by itself, for keying or in Find my radio: it may be another program's; choose it and it is opened like any other port.
- **A serial port** has a speed in baud, 8N1. Empty means the type's own, which is 9600 for every serial type. The NinoTNC needs 57600; the Mobilinkd and the TH-D74/D75 ignore it.
- **The control lines** DTR and RTS are set low as soon as the port is open, because a sound-card interface keys the transmitter on RTS.

## Finding the radio

With no port given, on Linux NeoAPRS listens to all the ports that match the setting `serial/pattern` at the same time, for as long as it takes, for the one that sends KISS frames. The default pattern is `/dev/serial/by-id/*`, `/dev/ttyUSB*` and `/dev/ttyACM*`. One radio searches at a time; a second radio with no port waits, and its status says so.

- A TNC in KISS mode sends nothing until it hears a packet, so on a quiet band the search takes a long time.
- With a TNC type that can be asked (Kenwood, Kantronics), a carriage return is sent to every port after 10 seconds of silence. A TNC in command mode answers it and is then switched to KISS. With any other type the ports are only listened to.
- A port another program or another radio holds is skipped. So is a development board, known by its USB ids (ESP32, Arduino, Raspberry Pi Pico and similar boards), whose console resets the chip when the port is opened. The log says which ports were left out and why. A port named in a radio's Port or in `--port` is never left out.
- The port it found is remembered and tried first next time. NeoAPRS opens a port once at a time: a radio's own retry, the search and Find my radio wait for each other, and listing the ports opens none. A port that cannot be opened is followed by the search, and a line that drops is opened again after 5, 10, 20, 30 seconds.
- `serial/skip` lists ports the search never opens (a rotator's adapter, or the GPS receiver of a moving station), separated by commas. A pattern of your own, such as `/dev/brainbox_*`, is set with `neoaprs db set serial/pattern "..."`. Neither is on the page.

On Windows and macOS NeoAPRS listens to no port it was not told of, because it could write into a GPS or into a rig interface that keys a transmitter. The radio is the port you chose, the one remembered, or the one **Find my radio** finds when you press it. A COM port that another program has open is reported as in use by another program.

## Find my radio

**Find my radio** is in the box of a radio on a serial line, behind the arrow of its status line, in the Settings tab and in the setup guide's Radio step alike. It finds the port, the speed and the type of TNC by itself and puts them in that radio's settings like any other change (the toast offers **Undo**). It works on Linux, Windows and macOS. Nothing happens unless you press it.

- **Linux:** it tries the ports of the search above, one after the other (the by-id name first), then the paired Bluetooth devices. The ports of development boards, those `serial/skip` names and those another program or radio holds are left out.
- **Windows:** it tries the COM ports the system lists, USB adapters first, then the paired Bluetooth devices by name, last because connecting to one can take seconds. A COM port another program has open is passed over, with "in use by another program" in the log.
- **macOS:** it tries the `/dev/cu.*` devices in the same way.
- Each serial port is opened at 9600, 57600, 19200, 38400, 115200, 4800 and 1200 baud in turn, listened to for a second, sent one carriage return and listened to for 1.5 seconds more, so a port nobody answers on costs about 18 seconds.
- It stops at the first that answers. A TNC that sends a KISS frame is the type *KISS TNC*. A TNC that answers the carriage return with text is in command mode, and the Kenwood and Kantronics types are tried on it in turn. Nothing is sent to the air.
- The toast says which port at which speed it is trying, with **Cancel**; with several radios on it names the radio. One search runs at a time, and the other boxes' buttons are off meanwhile. The radio's own line is closed while it runs and opened again after it.

## The radio status

Each box of a radio that is on has one line, the radio status, with an arrow in front of it that opens the rest of the box.

- The state is a coloured word: connected, waiting, silent, and so on.
- One plain line follows: "Last packet 2 min ago", "Searching for the radio…" with the ports it listens to behind **Ports**, "Not connected" with the reason, or for a silent radio since when it said nothing. The packet and byte counts are its hover text.
- A port that takes no data (a write to it waits more than 2 seconds) shows the radio as waiting, with "The port takes no data", until something goes through or comes from the radio. Frames are still handed to it meanwhile.
- **Reconnect**, small, at the end of the line, opens the line again.
- **Terminal**, behind the arrow and closed until you open it, shows the latest 100 lines of what the TNC saw and did, in your browser's time.
- When the radio's digipeater is on and has repeated something, the status says "digipeated N".

## The Mercury radio's box

The box of a Mercury radio has, behind the arrow of its status line, no port, speed or host:

- **Sound card** is the radio's, chosen among the cards the modem finds (hold the pointer over one for its id); **Refresh** reads the list again. On Linux with PipeWire or PulseAudio it is two choices, the sound from and to the radio, as in the Sound card radio's box. NeoAPRS proposes the one USB sound card that records and plays, else the system's default device, and stores it when none is set. A sound card another radio holds is refused.
- **Keying** is how the radio is switched to transmit: *The radio keys itself (VOX)*, *CM108 sound chip*, RTS or DTR of a serial port, on Linux those of the ports on one USB hub with the sound card first, or *flrig* or *rigctld* ([below](#keying-through-flrig-or-rigctld)). NeoAPRS proposes RTS of the one USB serial port of an interface when the sound card is a USB one, else VOX.
- **Test**, beside Keying, keys the radio for a second; the status line says *Keyed*. With VOX it sends the tuning tone for that second.
- **Tune** keys the radio and sends a steady tone for ten seconds, for an antenna tuner, the audio level or finding the radio's sound card; a second press, on *Stop*, ends it. No frame of yours goes out under the tone. Refused while a frame is on the air or the channel is busy.
- **Transmit level** is how strong the modem's audio is to the radio, from -20 to 20 dB. Press **-** or **+** while Tune runs and watch the radio's ALC: it should hardly move. **Peak** turns orange at 0 dBFS, where the sound card clips. Where the sound card has a playback level of its own the row is its slider instead, from 0 to 100 %, as in the Sound card radio's box; a level you moved off 0 dB keeps its **-** and **+** until it is back at 0 dB and you open the box again, and until the radio has run once since NeoAPRS started the row shows neither.
- **Spectrum**, folded under Transmit level, is the radio's audio from 300 to 2700 Hz as a waterfall, with the call and SNR of each station heard where its frame ended and a mark at the edge for your own transmissions. Under it, **Receive level** is a bar with its good range in green, with the slider of the sound card's own capture level before it where the card has one. **Monitor** in the map's menu shows the same larger ([the monitor card](page.md#the-monitor-card)). Both are full at once, the card as far back as it is tall (up to ten minutes).
- **Suggested frequencies** has a button, **Show**, that opens the dials the group agrees on, a line for each band (*40 m 7.0541 MHz USB*), read from the project page. They are not read from your radio and are not a setting.
- **PSK Reporter**, a box of its own at the end, has its **Enable** and the **Frequency** ([below](#psk-reporter)).
- Test and Tune are off while the station is RX only and while the modem is not running.

The status line says what you can act on: the mode, *Listening*, *Transmitting…*, *Channel busy, waiting* while another station's signal is on the channel, *Tuning…* or *Keyed*, the SNR of the latest frame and the last packet. When the modem cannot open the sound card, it says *Sound card could not be opened: choose another*, and the modem is tried again after a while with the card chosen then.

When Mercury hears nothing because its receive side has stalled (it records sound it does not take), NeoAPRS starts it again, never while it transmits and at most every 10 minutes; after three restarts in an hour the line says *Mercury hears nothing, even after restarts: switch the radio off and on again*.

A radio whose Mercury is not running sends nothing and is not shown connected: what was due waits, as for any radio that is not connected. Three more lines tell what is in the way:

- *Keying port in use by another program*: the serial port the radio is keyed by is open in another program, often a Mercury, a rig program or a CAT program you started. Close it; NeoAPRS tries again by itself every half minute while the radio is on.
- *Keying port not found*: that serial port is not there (unplugged, or another number since). Plug the interface in or choose the port again in **Keying**.
- *Another program is already using the modem's ports*: a program listens on the network where NeoAPRS starts its Mercury, most likely a Mercury you started yourself (the one NeoAPRS starts listens on this computer only, so a second NeoAPRS is no such program). NeoAPRS does not start a second one beside it, nor send a frame to it. Close that program, or choose [*Your own program*](#your-own-mercury) as the radio's type to work through it.

- A Mercury radio sends its frames direct: no digipeater repeats them, so no path is sent, except that a message or an ack to a station heard through a gateway goes with the gateway's call ([how](beacon.md#passing-a-packet-between-two-radios)), and what is RF only (Ask around, Local info, a station marked RF only) goes with `RFONLY`, after that call where there is one. Where a path is chosen beside a Mercury radio (Route, Ask around, Local info, an object), it is greyed, its value kept.
- The beacon of a Mercury radio goes every 30 minutes at the most often, each timed send with a random pause of up to five minutes, and is a timed one: SmartBeaconing is for the radios that allow it, and a moving station's Mercury beacon says where it is now.
- A beacon's comment is cut to the modem's frame (123 bytes) when it would not fit; the longest message always fits.
- On macOS the system asks once whether NeoAPRS may use the microphone, which is what a sound input is to it. Allow it, or the radio hears nothing.

### PSK Reporter

Tick **Enable** in the box **PSK Reporter** at the end of the Mercury radio's box and choose the **Frequency** the radio is tuned to: one of the suggested dials, or *Other* and the number in MHz (always USB). From then on every station the radio hears shows on the map of [pskreporter.info](https://pskreporter.info/pskmap) as heard by you, under the mode *NEOAPRS*, with "Using: NeoAPRS <version>".

- Only a station heard directly is reported: not one that came through a digipeater, a gateway or the internet, and never your own call.
- The station is placed where its packet says, or where your radio heard it last; your own place is your station's position. Without a position of your own nothing is reported.
- A station is reported once every five minutes at most on a band, and the reports go out together every five minutes or so.
- It works while the station is RX only, and without either tick of Internet (APRS-IS).
- Untick it, or leave the frequency empty, and nothing is reported.

## Keying through flrig or rigctld

Some stations share the radio's CAT port among several programs: flrig holds the radio, and the others switch it to transmit by a command through flrig, not by a line of a serial port. NeoAPRS can do the same, for a Sound card radio of either kind, Packet or Mercury.

- Choose **Keying** *flrig* for flrig's own control, or *rigctld* for Hamlib's rigctld, which needs no flrig: start it yourself on the radio's CAT port, a real one or a virtual one, for example `rigctld -m MODEL -r COM8`, where MODEL is the number of your radio in the list that `rigctl -l` prints.
- **Address**, under Keying, is where the program listens. Left empty it is this computer on the program's own port; type another `host:port` for a program elsewhere or on another port.
- You run flrig or rigctld yourself, before or after NeoAPRS: NeoAPRS does not start it. NeoAPRS keys nothing else and opens no serial port for the keying, so it takes no port away from your other programs.
- **Test** keys the radio for a second through the program: the radio should go to transmit and come back.

A Mercury frame is about 4.1 s on the air this way instead of 3.8 s: the modem waits a little longer before its audio, so that the radio is transmitting when the frame begins.

The radio is never left keyed by NeoAPRS: the radio is let go at the end of each transmission, when the radio or NeoAPRS stops, when the modem stops, and after the longest a transmission can take, whatever the modem says. Two lines tell what is in the way:

- *The rig program does not answer: frames wait*: flrig or rigctld is not running, is at another address, has no radio connected, or did not confirm that it let the radio go. Nothing is sent meanwhile; NeoAPRS keeps asking and goes on by itself once it answers. Check the radio's transmit indicator if the line stays.
- *The radio stayed keyed too long and was let go*: a transmission outlasted its time and NeoAPRS let the radio go. It goes away after the next transmission that ends by itself.

`neoaprs doctor` says for each such radio whether its program answers.

## The TNC type

The type of a packet radio (its key in brackets, as `neoaprs db radios` shows it) says what, if anything, is written to the TNC to put it in KISS, whether the TNC is asked if it is there, and how it is reached. You choose it when you add the radio: in the setup guide, in the Settings tab (Radio), or with `neoaprs db radios add TYPE`. A device that needs nothing is sent nothing.

| type | for | to enter KISS (the wait after each step) | to leave | asked if it is there |
|---|---|---|---|---|
| *KISS TNC* (`kiss`) | Mobilinkd TNC3 and TNC4, NinoTNC (speed 57600), TNC-Pi, TNC-X, the Kenwood TH-D74 and TH-D75 with KISS switched on at the radio (`[F]` then `[LIST]` on the D75), any TNC that is in KISS when it is switched on | nothing | nothing | no |
| *Kenwood TM-D710 / TH-D72* (`kenwood-d710`) | Kenwood TM-D710A/E/G/GA/GE, TH-D72A/E | `TC 1` (1 s), `TN 2,0` (3 s), `HBAUD 1200` (1 s), `KISS ON` (1 s), `RESTART` (1 s), each ended by a carriage return | `C0 FF C0` | yes, and the check enters again with the whole sequence |
| *Kenwood TH-D7, TM-D700, TNC-2* (`kenwood-tnc2`) | Kenwood TH-D7, TM-D700, TS-2000; TAPR TNC-2 and the MFJ-1270B/1274/1278 and PacComm clones | `\rKISS ON\rRESTART\r` (3 s) | `C0 FF C0` | yes |
| *Kantronics KPC-3+* (`kantronics`) | Kantronics KPC-3+, KPC-3, KAM | `\rINTFACE KISS\rRESET\r` (3 s) | `C0 FF C0` | yes |
| *Direwolf* (`kiss-tcp`) | Direwolf (8001), UZ7HO SoundModem and QtSoundModem (8100) | nothing | nothing | no |
| *Yaesu FTM, receive only* (`tnc-text`) | a Yaesu FTM-100, -300, -400 or -500 with its data port on Output PACKET, a TAPR TNC-2, Kantronics or PK-232 left in its own monitor mode | nothing, ever | nothing | no |

- **RX only** (*Yaesu FTM, receive only*): nothing at all is written to the line, not even a carriage return, and no frame is sent on the radio: it is never a message's, the beacon's, an object's or a bulletin's. The text the device prints of each packet it hears is read in every form a TNC-2, a Kantronics, a PK-232 and a Yaesu print, and a line of 7 bits with parity is recognised by itself. While it is the only radio on, nothing is sent and the switch reads RX only. What to set at the device once is in [`docs/RADIOS.md`](../RADIOS.md#yaesu-ftm-receive-only).
- **A TNC that is not asked** (*KISS TNC*, *Direwolf*): nothing is written to it but KISS frames. There is no keep-alive check and no silent state. The open line is all NeoAPRS can know of the radio.
- A TNC in command mode that sends text is told in the radio status; it is not answered. The Kenwood TH-D74 and TH-D75 have no command mode and cannot be asked: put them in KISS at the radio.
- **The wait after the last step** is the settle time. What the TNC says meanwhile is thrown away and no frame is sent.
- The Kenwood TNC-2 sequence is the one the Kenwood TNC-2 takes, the TM-D710 one that of the tmd710_tncsetup project (Debian), copied as it is and not tried on a radio. The Kantronics entry is from the KPC-3+ manual; a reset has been reported to change the host speed on some units.
- The list of types is not a promise that a device works. The strings are from the manufacturers' manuals and from users' reports, and [`docs/RADIOS.md`](../RADIOS.md) marks which is which.

## Is the radio there?

A radio that is switched off leaves its USB adapter and port in place. A radio that is power-cycled comes back with its TNC in command mode. A TNC in KISS mode says nothing until it hears a packet. So a quiet line proves nothing, and for a type that can be asked NeoAPRS asks.

- **Keep-alive.** After 10 minutes with nothing at all on the line (and a random minute or two more), NeoAPRS takes the TNC out of KISS, sends a carriage return and puts it back in KISS. A TH-D7 that is on answers within about a second. The check runs only after a quiet spell, never while packets flow.
- **A line just opened** has not shown that the radio is there. Until a byte arrives the radio is connected but not usable: the beacon, status, messages, acks and answers to queries wait.
- **A silent radio.** If nothing comes within 2 seconds of the check, the radio is *silent*, and the header says so. Nothing is sent on it: the beacon that is due waits, and messages wait without using up an attempt.
- **Coming back.** While silent, NeoAPRS probes every 30 seconds, and every fifth probe also closes the port and opens it again. The first byte that arrives ends the silence: KISS is entered again, and a beacon that fell due in the night goes out then.
- **A port that goes away and comes back** (the USB adapter pulled out and plugged in again) is tried again every 5 to 30 seconds. Where NeoAPRS does not look for the radio by itself (Windows, macOS), an adapter that comes back as another COM port is found by its serial number, or as the only adapter of its kind. If two look alike, choose the port in its box.
- These checks exist only for the types that can be asked. *KISS TNC* and *Direwolf* are usable as soon as the line is open.

The log says `the radio is silent: nothing heard since 18:43 UTC, no answer to a check; probing every 30 s` once when the silence begins, and `the radio answers again after 17 min; entering KISS` when it ends.
