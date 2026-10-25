# Beacon, status and digipeater

The Beacon tab holds what your station says on the air: the **Station** group (call, location, symbol), the **Beacon** group, a closed **Antenna** heading, a closed **Advanced** heading with the path choice, and the **Status** group. A setting applies as you change it ([start.md](start.md#how-settings-apply)).

A first transmission on the air is not tried by NeoAPRS's tests, which never open the radio. Check it live with **Beacon now**, then look for your call on aprs.fi or on another station's screen, before you leave a timer on.

## Receive only

The first row of the Station group is **Transmit**, with the choices **On** and **Receive only** (the setting `station/transmit`, `true` by default). It is for the days you want the radio to listen and nothing more. While it is **Receive only** nothing at all is transmitted, whoever asks and whatever is due: no beacon, status, message, ack, answer to a query, object, bulletin or digipeated packet.

The page shows an amber **Receive only** badge beside the title in its header, on every screen size; a click on it opens this tab. The setting is kept in the database, so it holds after a restart of the daemon.

* **Beacon now**, **Send status now**, a message, an email, an object or a bulletin you send meanwhile is refused at once with the toast "Receive only: nothing is sent" (`neoaprs db set` and the wire give the code `transmit.off`).
* A message that was already being sent waits: no attempt is used up and it does not fail, and the waits that were running are moved on by the time transmitting was off. It goes on when you switch back to **On**. A message you receive is kept, but its ack is not sent and not kept for later; the station that sent it will try again.
* Timers do not catch up. A beacon or a status that came due meanwhile goes out once, at the first moment after you switch to **On**, and the next one an interval after that; objects and bulletins that are due follow one at a time, with the usual pause between frames, so there is never a burst.

## The beacon

Set the beacon to Off, or to every 30 minutes, every 60 minutes or every 3 hours. The setting `beacon/interval_min` takes 0 (off) or 20 to 1440: 20 minutes is the net cycle of the APRS specification for a path of two hops, and 30 is routine operation. A stored value that the page does not offer, such as 20 or 45, is shown as one more choice until you pick another, and one below 20 is raised to 20 (the log says so). The default is off, so an upgrade never starts to transmit. The setup guide gives a new station a beacon every 30 minutes.

The first beacon goes out 30 seconds after the daemon starts, so that the radio and the TNC settle first. After that one goes out every interval, counted from the latest beacon, however it was sent.

- **A restart does not send another.** The time of each beacon is kept. A daemon that starts less than an interval after the last beacon sends its first one an interval after that one, not 30 seconds after the start.
- **A beacon that falls due while the radio is away is not skipped.** If the TNC is not connected or the radio is silent (switched off at night), the beacon stays due. The log says once `the beacon is due and the radio is silent: it goes out when the radio is back`. The first second the radio is usable again one beacon goes out, however many intervals went by, and the next is an interval after it.
- **A frame the TNC refuses** (it is settling after entering KISS, or the write failed) is tried again 5 seconds later, six refusals in all. Then that interval is skipped and the next is the first interval boundary after now.
- **Beacon now** and a changed interval count from the kept time. Saving a new interval takes effect at once, and 0 stops the timer.

The beacon is a packet from your call to the tocall `APZNEO`, by the digipeaters of `beacon/path`. Its information field starts with `=` (a station that takes messages), then your position rounded to the hundredth of a minute, your symbol and your comment. With the defaults (a house, the recommended path of a fixed station) it is:

```
OH2GBA>APZNEO,WIDE2-1:=6010.20N/02456.40E-NeoAPRS
```

A station that stays sends the plain uncompressed form, which every receiver reads; a moving station sends a compressed position ([Mobile operation](#mobile-operation)). `APZNEO` is in the experimental range of destination calls. Every frame NeoAPRS sends carries it: the beacon, status, messages and their acks, answers to queries, objects and bulletins.

The **path** (Advanced) is one choice:

- **Recommended**, the default, which goes by your station's type. The type is the **symbol** of your station; there is no setting for it. The choice names the path of the symbol you have, and follows it when you change the symbol.
  - A moving or carried station is **Recommended (WIDE1-1,WIDE2-1)**: a small digipeater nearby picks the packet up first and a wide-area one carries it on. Its symbol is a car, truck, van, bus, jeep, motorcycle, bicycle, jogger, wheelchair, boat, ship, canoe, yacht, aircraft, helicopter, glider, balloon, snowmobile, horse, farm vehicle, recreational vehicle, ambulance, fire truck or police car, with any overlay.
  - Any other symbol is a fixed station, which reaches a wide-area digipeater directly and needs no fill-in hop: **Recommended (WIDE2-1)**.
- **Direct only (no digipeaters)**, for a station that everyone you talk to hears directly.
- **Custom...**, which shows a field for up to 8 calls separated by commas, each a call with an optional SSID: `WIDE2-2`, say. A path that is neither of the first two shows as Custom, `WIDE1-1,WIDE2-1` typed in included, and stays as it is when you change the symbol.

Recommended and Direct only apply at once; the custom calls apply on Enter or when the field is left. An empty custom field is the recommended path again.

In the database the setting `beacon/path` is the calls, `DIRECT` for direct only, and empty means the recommended path of the symbol: **an empty path is never "no digipeaters"**, that is always said with the word `DIRECT`. (Older versions took an empty path to mean none; a database that has one is changed once to `DIRECT` by the update, so that nothing starts to digipeat. Older versions also stored `WIDE1-1,WIDE2-1` as the default of every save, so the update changes that stored value to empty, and your path then follows your symbol; any other path you have is kept.)

The same path is what status reports, objects without a path of their own, bulletins and the answers to queries use, and what a message goes by for its last two attempts (below, in [messages](messages.md#how-the-path-of-a-message-is-chosen)).

The **comment** is printable ASCII without `|` and `~`, at most 43 characters, and 36 when the PHG extension is sent. A save that breaks this is refused with the reason, and a beacon whose comment is too long is not sent.

Your own row on the map is your settings (position, symbol and comment), or the GPS fix for a moving station, never what a packet says. A packet with your own call that you hear back (the TNC may echo what it sends, a digipeater repeats it) only updates the time you were last heard.

## Power, height and gain (PHG)

With a power set (`beacon/power_w`, 0 to 9999 watts) the beacon carries the PHG extension right after the symbol. The Beacon tab asks for the antenna's height above the average terrain around it (HAAT, not above sea level; 0 to 9999 m), gain (0 to 9 dBi) and direction (`omni` or N, NE, E, SE, S, SW, W, NW) only once there is a power. With no power set no PHG is sent.

PHG is written `PHGphgd`:

- `p` is the square root of the power in watts;
- `h` is the base-2 logarithm of the antenna height above average terrain in tens of feet;
- `g` is the gain in dBi;
- `d` is the direction: 0 omni, 1 NE, 2 E, 3 SE, 4 S, 5 SW, 6 W, 7 NW, 8 N.

`p` and `h` are rounded and held to 0 to 9. For 2 W, 3 m, 2 dBi and omni it is `PHG1020`. For 25 W, 6 m, 3 dBi and east it is `PHG5132`, the specification's example.

The **Preview** under the Beacon tab, closed until you open it, shows the packet the settings make and, for a status that is a text of your own, the status report.

## Beacon now

The Beacon group starts with a row "Last beacon: 2 min ago" (the full time on hover) and the primary button **Beacon now**. It asks twice ("Really send?"). It is off while the TNC is not connected, and while a change of the settings is being saved, so what is sent is what is in force. The next beacon of the timer is then an interval later.

A beacon you send is in the Packets tab as a packet with direction `out`.

## Mobile operation

For a car, a bicycle or a boat the beacon can follow a GPS receiver. With **Mobile** on, the position, course, speed and altitude come from the GPS, and the beacon goes when SmartBeaconing says: often when you move fast or turn a corner, rarely when you stand still.

What to set (the Mobile group of the Beacon tab):

1. **GPS source**: `gpsd` reads a gpsd daemon (on this computer or another one on the network; its address is `gps/host`, `127.0.0.1:2947` by default), `serial` reads the NMEA sentences of a GPS receiver on a serial port (`gps/device`, such as `/dev/ttyUSB1`, at `gps/baud`: 4800 is NMEA's own speed, and many USB receivers speak 9600). Keep the GPS apart from the radio's port. A save of `gpsd` without an address, or `serial` without a port, is refused.
2. **Mobile** on (`beacon/mobile`).
3. A symbol of a moving station (a car, say), which also makes the recommended path `WIDE1-1,WIDE2-1`.

The GPS is read as soon as a source is chosen, Mobile or not, so you can see the fix before the beacon follows it.

**What the Beacon tab shows.** The Mobile group starts with the state of the GPS, in the look of the radio's: a coloured word (off, connecting, no fix, fix or stale) and one line in plain words:

- **Off**, while no source is set.
- **Connecting to gpsd at 127.0.0.1:2947**, or **Opening /dev/ttyUSB1 at 4800 baud** for a receiver on a port. When it cannot, the reason stands under the line, such as Connection refused.
- **No fix yet**, with the reason the receiver gives.
- **Fix: 60.4295 N 24.1452 E, 48 km/h, course 215°, 103 m, 9 satellites, 2 s ago.** What the receiver does not tell (the speed of one that stands still, say) is left out.
- **Fix lost 3 min ago (stale)**, once the latest fix is more than 2 minutes old. Nothing is sent on it.

Under the state come the GPS source, the address of the gpsd (for `gpsd`) or the port and speed of the receiver (for `serial`), and the Mobile switch. Behind the heading **SmartBeaconing**, which is there while Mobile is on, are the seven numbers; a value outside its range is refused under its field, and so is a fast speed that is not above the slow one or a fast time that is not below the slow one. With Mobile on:

- Under the row "Last beacon" a line says when SmartBeaconing sends next, and why the last beacon went: **SmartBeaconing: next by time in 42 s, last sent 12 s ago (turn)**. The reason is first fix, time, turn or Beacon now; a turn goes sooner than the time shown. With no fix the line says **No beacon: no GPS fix**. Beacon now stays as it is, and is refused with the reason while there is no fix.
- The Location row of the Station group is called **Home position** and says that the GPS position is what is sent, never this one. Its fields stay: it is where your station is whenever it is not moving, and before the first fix.
- The interval of the fixed beacon is not shown, because a mobile beacon does not use it.

**What is sent.** A packet from your call to `APZNEO` by your path, like the fixed beacon, but with a compressed position, which is shorter and carries the course and speed:

```
OH2GBA-9>APZNEO,WIDE1-1,WIDE2-1:=//w5#TW?M>eM[/A=000103NeoAPRS mobile
```

After the position comes the altitude in feet (`/A=000103`) and then your comment. A compressed position and its comment may be 40 characters in all, so a long comment is cut at the end to fit (a station with an altitude has 31 characters of its own). There is no PHG: a compressed position cannot carry it, and it is for a station that stays where it is. A GPS that gives no speed or course sends the position alone.

**When it is sent (SmartBeaconing).** The method is HamHUD's SmartBeaconing, as Dire Wolf and APRSdroid have it:

- The first fix after the daemon starts is sent at once.
- A station that stands still (at or below the slow speed) sends every slow time, 30 minutes by default. One that goes fast (at or above the fast speed) sends every fast time, 1 minute by default. Between the two the time falls with the speed: at 50 km/h it is 2 minutes.
- A turn is sent at once: when the course differs from the course of the last beacon by more than the turn angle plus the slope divided by the speed in miles per hour, and the turn time has passed since the last beacon. The faster you go, the smaller a turn counts. A station that is not above the slow speed sends no turns.
- **Beacon now** sends the position as it is, and the times count from it.

The numbers are settings, with Dire Wolf's values in kilometres per hour:

| setting | default | what it is |
|---|---|---|
| `smart/fast_kmh` | 100 | the speed from which the fast time applies (10 to 300) |
| `smart/fast_sec` | 60 | the fast time, seconds (10 to 600) |
| `smart/slow_kmh` | 8 | the speed up to which you stand still (1 to 50) |
| `smart/slow_sec` | 1800 | the slow time, seconds (60 to 3600) |
| `smart/turn_min_deg` | 30 | the least change of course that is a turn (5 to 90) |
| `smart/turn_min_sec` | 15 | the least time since the last beacon for a turn (5 to 120) |
| `smart/turn_slope` | 255 | degrees times miles per hour that are added to the turn angle, divided by the speed (0 to 1000) |

The fast speed must be above the slow one, and the fast time below the slow one; a save that breaks this is refused with the reason. The 20-minute floor of the fixed beacon does not apply to a mobile station, and `beacon/interval_min` is not used while Mobile is on. Keep the fast time long on a busy channel: a beacon a minute from every car makes a busy channel busier.

**No fix, no beacon.** With no fresh GPS fix nothing is sent: not at the start, while the receiver is looking for satellites, not when gpsd or the port is away, and not once the latest fix is more than 2 minutes old. Your home position is never sent in its place, because a station that seems to jump home is worse than a silent one. Beacon now is refused with the reason, and a query for your position (`?APRSP`) is not answered. The page says why in the state of the GPS. A fix lost for less than 2 minutes (a tunnel) is still the latest one, and the beacon goes on by the clock.

**On the map.** While Mobile is on, your own station follows the GPS fix, with its course, speed and altitude, moving every few seconds once you have gone 10 metres, and the distance and bearing of the other stations follow. If the GPS is lost your station stays where it was last seen. With Mobile off it is the location of the settings, as before. A query for your position (`?APRSP`) is answered with the position as it is now.

**Follow me.** While Mobile is on and the GPS has a fix, a **Follow me** button at the top right of the map keeps the map centred on you, at a close zoom at least. Dragging the map lets go, and so does the loss of the fix or switching Mobile off; press the button again to take hold.

To try it without a vehicle, the [development guide](../development.md#trying-mobile-operation-without-a-vehicle) describes a replay of a drive.

## The location

The Location is a row of the Station group under the call, like the call itself: the word Location bold in the label column and, in the input column, a **Choose on map** button (full width on a phone). The next click on the map becomes your position, applied at once as latitude and longitude together. The button says Cancel while the map waits.

One line under the button says where you are ("60.42945 N, 24.14524 E · KP20le", with the Maidenhead locator after the dot; "Not set" while there is none).

Under that line the latitude and longitude fields are behind a small **Enter coordinates** heading. It is open while there is no position or one of the fields is wrong, else until you open it. What you type applies together, when you leave the pair and both are right. North and east are positive, south and west negative.

With no position there is no beacon, no station of your own on the map, and the map opens on the world.

## The symbol

The symbol is a picture and its name with **Change**, which opens a picker with every symbol of both tables, the usual ones first, searchable by name (`house`, `car`, `digi`, `wx`). Your own symbol is the setting pair `station/symbol_table` and `station/symbol_code`. The default is a house.

A symbol made to carry a letter or a digit (a digipeater, a car, a gateway) has a small field "Letter or digit on it", which sets the overlay.

## The status

A status report is a text line that tells what you are doing. It goes out as one packet from your call to the tocall, by the beacon's path: `>`, the day, hour and minute in UTC and a `z`, then the text.

**Where it comes from** is the choice **Status**, the setting `status/source`:

| choice | what it sends |
|---|---|
| **off** | nothing |
| **a text of my own** | the text of `station/status`: printable ASCII without `\|` and `~`, at most 55 characters (the time takes the rest of the specification's 62) |
| **the frequency from my radio (rigctld)** | the frequency and mode of a radio that a [Hamlib rigctld](https://hamlib.github.io/) can read, made into text by a template |

The tab shows only the fields the choice needs. For a text: **Text** and **Every**. For the radio: **Rigctld**, **Text** (the template) and **Every**. Left empty, the setting follows the others: the radio while `status/rigctld` is set, else the text while there is one, else off. Choosing the radio without a rigctld address is refused with the reason.

**From the radio.** NeoAPRS connects to `host:port` of the rigctld (Hamlib's default is `127.0.0.1:4532`) every 30 seconds, asks the frequency and the mode, and fills in the template. The default template is `QRV {freq} {mode}`. `{freq}` is megahertz with three decimals (`14.074 MHz`), `{mode}` is the mode as rigctld names it (`USB`, `LSB`, `CW`, `FM`). No other field in braces, and at most 55 characters with the widest values (`1296.000 MHz`, `PKTUSB`). With `14074000` Hz and `USB` the frame at 12:00 UTC on the 21st is:

```
OH2GBA>APZNEO,WIDE2-1:>211200zQRV 14.074 MHz USB
```

**The rule.** A status goes out when the interval (`status/interval_min`, a choice of 30 min, 60 min or 2 hours, at least 15) has passed since the last one, and what it says has changed since that one: the frequency to the kilohertz, or the mode, for a radio; the text for a static status. So:

- nothing goes inside the interval however the dial moves;
- nothing goes when it is the same, so a long quiet band does not repeat itself every half hour;
- the first status goes out at the first poll after the start;
- a restart does not send it again: the time and text of the last status are kept, so a daemon started inside the interval sends nothing, and one started after it sends a status only when the frequency and mode (or the text) differ from the kept text.

**The radio off.** If rigctld answers with an error (a radio that is switched off), refuses the connection or does not answer within 5 seconds, the radio is off or rigctld is away. Nothing is sent. The log says so once when it begins (`rigctld at 127.0.0.1:4532: connection refused: no status while it is away`) and once when the radio answers again.

**Send status now** is a button at the top of the Status group, beside the status line, there only while the status is not off. It asks twice, acts on the saved settings and sends the status at once, inside the interval and although nothing changed. The interval counts from it. It is refused when the call is not set, when the TNC is not connected, when the text is over 55 characters, when the status is off or the text empty, and with the radio as the source when rigctld is away; it says why.

The status line at the top of the group shows the status last sent and, with the radio as the source, whether rigctld answers. The last text sent is also the answer to the query `?APRSS`.

## Answers to queries

A message to your call whose text is one of these queries is answered by NeoAPRS. The text is read without regard to case or blanks. The answers are packets of their own, not messages: none is kept as a message, retried or waited for. They go by the path of the station that asked (its own path, else the beacon's; for a packet an iGate wrapped, the sender inside).

| query | the answer |
|---|---|
| `?APRSP` | your position packet, the beacon's own frame (a moving station's with the position as it is now, and nothing while it has no GPS fix) |
| `?APRSS` | your status report as it was last sent, with the time of the answer; nothing while none has been sent |
| `?APRSD` | a message to the asker with the calls heard direct in the last hour, the one heard last first: `Directs= OH2RCH-2 OH2PU-9`, or `Directs= none`. At most 67 bytes; if the calls do not fit it is two messages, each starting `Directs=`, and what does not fit in two is left out |
| `?APRST`, `?PING?` | a message to the asker with the header of the query as you heard it, with the digipeaters it went by and their stars, as the specification's example writes it: `OH2RDG>APZNEO,WIDE1*,OH2RCH-2*,WIDE2-1:`. The last digipeaters go when it would be over 67 bytes |
| `?APRSH N0QBF` | a message to the asker that tells in which of the last 8 hours that station was heard, as the specification's example has it: `N0QBF HEARD: 1 3 2 . . 4 5 6`. The numbers are the packets heard from it, the last 60 minutes first, then the 60 before them, and so on; a dot is an hour with none. A station you never heard is answered `N0QBF NOT HEARD`. The call may follow the query with or without a blank. The specification also has the answer carry the station's position as an object; NeoAPRS leaves that out, because an object named like a station is the one thing it never makes |
| `?APRSO` | your live objects and items, each once as it is now, at most 5, 10 seconds apart; also those you keep to send only when asked ([Objects](objects.md#objects-sent-only-when-asked)) |
| `?APRSM` | your messages to the asker that are not acked (being sent, failed or unconfirmed), each once more, the latest 5, 10 seconds apart. They stay as they were: an ack that comes settles them |

The general query `?APRS?` is a packet and not the text of a message (a message with that text is not answered, whoever it is for). It is answered with your position packet and then your status report, after a random wait of 0 to 120 seconds. Once one is taken, another is not taken for 10 minutes.

It may carry the specification's target footprint, `?APRS?V34.02,-117.15,0200`: latitude and longitude in degrees (the `V` stands for a space and may be left out; a west or south value has its minus) and the radius in miles. Then you answer only when your position is inside the circle, and a footprint that does not read is not answered.

The general queries `?WX?` (asking the weather stations for a weather report) and `?IGATE?` (asking the iGates for their capabilities) are recognised and never answered: NeoAPRS has no weather report of its own to send and is no iGate, and a station that has nothing relevant need not answer. The log notes them at the debug level and the packet is an ordinary packet in the packet log.

A message to the addressee `QRU` is not a query to you; if you keep objects for it, NeoAPRS answers it as a QRU server ([Objects](objects.md#objects-sent-only-when-asked)).

- The answers are not retried and not sent while the TNC is not connected (the log says so). They have no message id.
- The same query from the same station within 30 seconds (copies of one transmission by different digipeaters, an impatient asker) is answered once.
- A query that cannot be answered, because the settings make no frame, is told in the log.
- Try the queries live with a station that can ask, such as `?APRSP` from another radio or from the message form of aprs.fi.

## The fill-in digipeater

The digipeater is off unless `digi/enabled` is `true` (Settings tab, group Digipeater, with an (i)). It is a fill-in digipeater for a spot with poor coverage, where nearby stations cannot reach a digipeater of their own. There is nothing else to set.

When it is on, NeoAPRS sends a packet it heard on the radio again, once, when the first digipeater of the packet's path that is not yet marked as used is:

- `WIDE1-1`. Your call, marked as used, takes its place: `OH2XYZ>APRS,WIDE1-1,WIDE2-1` goes out as `OH2XYZ>APRS,OH2GBA*,WIDE2-1`.
- your own call with your SSID (a station routing through you on purpose). That hop is marked as used where it stands.

Nothing else is repeated:

- not a path whose first unused hop is anything else (`WIDE2-1`, `WIDE2-2` and the like are for the digipeaters on a high site);
- not a packet from your own call, or one that already shows your call as used;
- not a duplicate: the same source, destination (its SSID does not count) and information field heard or sent in the last 30 seconds, whatever the path;
- not a packet whose path has `TCPIP` or `TCPXX` (it came from the internet). `NOGATE` and `RFONLY` ask iGates only and are repeated. A third-party packet (`}`, which an iGate sends to put a message from the internet on the air) is repeated like any other: only its own path counts.

The frame is the one that was heard, byte for byte, with only the path changed. It goes through the same checks as every transmission: nothing at all while no call is set or the radio is not usable. A fill-in is of use only at once, so it does not wait for the 10 seconds between your scheduled frames. At most 4 digipeated frames go out in any 10 seconds, and the rest are dropped.

A KISS TNC still waits for a free channel by its own rules, a random delay set by its PERSIST and SLOTTIME, before it sends what NeoAPRS hands it. So the repeat comes a moment after the original, not at once as from a digipeater built into a TNC.

Each one is a line in the log (`digipeated OH2XYZ>APRS: the path WIDE1-1,WIDE2-1 is sent as OH2GBA*,WIDE2-1`) and is in the Packets tab as a packet with direction `out`. The radio status of the Settings tab says "digipeated N" once N is more than 0.
