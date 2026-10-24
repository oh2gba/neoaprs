# Beacon, status and digipeater

The Beacon tab holds what your station says on the air: the **Station** group (call, location, symbol), the **Beacon** group, a closed **Antenna** heading, a closed **Advanced** heading with the path choice, and the **Status** group. A setting applies as you change it ([start.md](start.md#how-settings-apply)).

A first transmission on the air is not tried by NeoAPRS's tests, which never open the radio. Check it live with **Beacon now**, then look for your call on aprs.fi or on another station's screen, before you leave a timer on.

## The beacon

Set the beacon to Off, or to every 15, 30 or 60 minutes. The setting `beacon/interval_min` takes 0 (off) or 15 to 1440. A stored value that the page does not offer, such as 20 or 120, is shown as one more choice until you pick another. The default is off, so an upgrade never starts to transmit.

The first beacon goes out 30 seconds after the daemon starts, so that the radio and the TNC settle first. After that one goes out every interval, counted from the latest beacon, however it was sent.

- **A restart does not send another.** The time of each beacon is kept. A daemon that starts less than an interval after the last beacon sends its first one an interval after that one, not 30 seconds after the start.
- **A beacon that falls due while the radio is away is not skipped.** If the TNC is not connected or the radio is silent (switched off at night), the beacon stays due. The log says once `the beacon is due and the radio is silent: it goes out when the radio is back`. The first second the radio is usable again one beacon goes out, however many intervals went by, and the next is an interval after it.
- **A frame the TNC refuses** (it is settling after entering KISS, or the write failed) is tried again 5 seconds later, six refusals in all. Then that interval is skipped and the next is the first interval boundary after now.
- **Beacon now** and a changed interval count from the kept time. Saving a new interval takes effect at once, and 0 stops the timer.

The beacon is a packet from your call to the tocall `APZNEO`, by the digipeaters of `beacon/path`. Its information field starts with `=` (a station that takes messages), then your position rounded to the hundredth of a minute, your symbol and your comment. With the defaults it is:

```
OH2GBA>APZNEO,WIDE1-1,WIDE2-1:=6010.20N/02456.40E-NeoAPRS
```

The position is always the plain uncompressed form, which every receiver reads. `APZNEO` is in the experimental range of destination calls. Every frame NeoAPRS sends carries it: the beacon, status, messages and their acks, answers to queries, objects and bulletins.

The **path** (Advanced) is one choice:

- **Recommended (WIDE1-1,WIDE2-1)**, the default and right for most stations: a small digipeater nearby picks the packet up first and a wide-area one carries it on.
- **Direct only (no digipeaters)**, for a station that everyone you talk to hears directly.
- **Custom...**, which shows a field for up to 8 calls separated by commas, each a call with an optional SSID: `WIDE2-2`, or `WIDE2-1` for a fixed station that the wide-area digipeaters hear directly, such as one on a hill. A path that is neither of the first two shows as Custom.

Recommended and Direct only apply at once; the custom calls apply on Enter or when the field is left. An empty custom field is the recommended path again. In the database the setting `beacon/path` is the calls, `DIRECT` for direct only, and empty means the recommended path: **an empty path is never "no digipeaters"**, that is always said with the word `DIRECT`. (Older versions took an empty path to mean none; a database that has one is changed once to `DIRECT` by the update, so that nothing starts to digipeat.)

The same path is what status reports, objects without a path of their own, bulletins and the answers to queries use, and what a message goes by for its last two attempts (below, in [messages](messages.md#how-the-path-of-a-message-is-chosen)).

The **comment** is printable ASCII without `|` and `~`, at most 43 characters, and 36 when the PHG extension is sent. A save that breaks this is refused with the reason, and a beacon whose comment is too long is not sent.

Your own row on the map is always your settings (position, symbol and comment), never what a packet says. A packet with your own call that you hear back (the TNC may echo what it sends, a digipeater repeats it) only updates the time you were last heard.

## Power, height and gain (PHG)

With a power set (`beacon/power_w`, 0 to 9999 watts) the beacon carries the PHG extension right after the symbol. The Beacon tab asks for the antenna's height (0 to 9999 m), gain (0 to 9 dB) and direction (`omni` or N, NE, E, SE, S, SW, W, NW) only once there is a power. With no power set no PHG is sent.

PHG is written `PHGphgd`:

- `p` is the square root of the power in watts;
- `h` is the base-2 logarithm of the antenna height in tens of feet;
- `g` is the gain in dB;
- `d` is the direction: 0 omni, 1 NE, 2 E, 3 SE, 4 S, 5 SW, 6 W, 7 NW, 8 N.

`p` and `h` are rounded and held to 0 to 9. For 2 W, 3 m, 2 dB and omni it is `PHG1020`. For 25 W, 6 m, 3 dB and east it is `PHG5132`, the specification's example.

The **Preview** under the Beacon tab, closed until you open it, shows the packet the settings make and, for a status that is a text of your own, the status report.

## Beacon now

The Beacon group starts with a row "Last beacon: 2 min ago" (the full time on hover) and the primary button **Beacon now**. It asks twice ("Really send?"). It is off while the TNC is not connected, and while a change of the settings is being saved, so what is sent is what is in force. The next beacon of the timer is then an interval later.

A beacon you send is in the Packets tab as a packet with direction `out`.

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
OH2GBA>APZNEO,WIDE1-1,WIDE2-1:>211200zQRV 14.074 MHz USB
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
| `?APRSP` | your position packet, the beacon's own frame |
| `?APRSS` | your status report as it was last sent, with the time of the answer; nothing while none has been sent |
| `?APRSD` | a message to the asker with the calls heard direct in the last hour, the one heard last first: `Directs= OH2RCH-2 OH2PU-9`, or `Directs= none`. At most 67 bytes; if the calls do not fit it is two messages, each starting `Directs=`, and what does not fit in two is left out |
| `?APRST`, `?PING?` | a message to the asker with the header of the query as you heard it, with the digipeaters it went by and their stars: `Path= OH2RDG>APZNEO,WIDE1*,OH2RCH-2*,WIDE2-1`. The last digipeaters go when it would be over 67 bytes |

The general query `?APRS?` is a packet and not the text of a message (a message with that text is not answered, whoever it is for). It is answered with your position packet and then your status report, after a random wait of 0 to 120 seconds. Once one is taken, another is not taken for 10 minutes.

It may carry the specification's target footprint, `?APRS?V34.02,-117.15,0200`: latitude and longitude in degrees (the `V` stands for a space and may be left out; a west or south value has its minus) and the radius in miles. Then you answer only when your position is inside the circle, and a footprint that does not read is not answered.

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
- not a duplicate: the same source, destination and information field heard or sent in the last 30 seconds, whatever the path;
- not a packet from the internet: a third-party packet (`}`) or a path with `TCPIP` or `TCPXX`. `NOGATE` and `RFONLY` ask iGates only and are repeated.

The frame is the one that was heard, with only the path changed. It goes through the same checks as every transmission: nothing at all while no call is set or the radio is not usable. A fill-in is of use only at once, so it does not wait for the 10 seconds between your scheduled frames. At most 4 digipeated frames go out in any 10 seconds, and the rest are dropped.

Each one is a line in the log (`digipeated OH2XYZ>APRS: the path WIDE1-1,WIDE2-1 is sent as OH2GBA*,WIDE2-1`) and is in the Packets tab as a packet with direction `out`. The radio status of the Settings tab says "digipeated N" once N is more than 0.
