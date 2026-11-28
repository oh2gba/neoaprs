# Internet (APRS-IS)

**Settings → Internet (APRS-IS)** has two ticks, each on its own and both off until you tick them:

- **Show Internet stations** puts the stations that APRS-IS, the internet side of APRS, has within the radius of your map on the map, in the Stations tab and in the Packets tab, marked as heard over the internet ([the page](page.md#stations)).
- **Send what I hear** puts what every radio of yours hears on APRS-IS. Your station is then an iGate for its radios: a station near you that only reaches your radio is on the internet's maps, and a message heard on the radio for a service such as `EMAIL-2` reaches it this way.

Both need your call: until it is set, the ticks are there but cannot be ticked. Under them, while either is on, is the status row.

**Nothing from the internet is ever sent on the air**, whichever ticks are on. What the server sends goes to the map and the logs and nowhere else: a message for you that was sent from the internet is not kept or answered, no query from it is answered, no packet of APRS-IS is repeated by your radio, and a station known only from the internet cannot be messaged. This is how NeoAPRS is built, not a setting.

## Show Internet stations

Unticking it hides them again, as if it had never been on: no station known only from the internet, no packet from it, and a station heard both ways shows only what the radio heard (no Internet tag or time, the place the radio gave). The map's [replay](page.md#replay) does the same: it plays only what was on the air, whenever the internet's packets came. Nothing is deleted: tick it again and they are back at once.

- NeoAPRS logs in to APRS-IS with your call and asks for the stations within the **Radius** of the Map group of the Settings tab, round your position. The circle is asked for again when you change the radius and when your position has moved more than 10 km.
- With only this tick on, the login only reads: nothing of yours is sent to APRS-IS.

## Send what I hear

With it ticked, what every radio hears is put on APRS-IS, and your own position with it. A receive-only radio, such as a Yaesu FTM, is gated like any other, and so is a Mercury or LoRa radio. Without **Show Internet stations** NeoAPRS asks APRS-IS for no stations at all, and nothing that comes from it is shown or kept.

The login needs the APRS-IS passcode of your call, a number that belongs to the call without its SSID. NeoAPRS works it out from your call: there is nothing to type and nothing to request.

Which packets are left out:

A packet heard is not put on APRS-IS when:

- its path has `TCPIP` or `TCPXX`: it came from the internet already;
- its path has `NOGATE` or `RFONLY`: it asks to stay off the internet;
- it is a general query (the information field starts with `?`);
- it is a third-party packet (an iGate's) whose inner packet came from the internet. A third-party packet without that is put on APRS-IS as the packet inside, with the iGate's header taken off;
- its source is not a station (`N0CALL`, `WIDE2`, `TCPIP` and the like) or is your own call;
- it has a line break inside (APRS-IS has one packet to a line), or would make a line of more than 512 bytes;
- the same source, destination and text were put on APRS-IS in the last 30 seconds: a packet repeated by digipeaters is heard more than once and goes once;
- it was heard while the connection to APRS-IS was not up;
- it did not come from the air: a packet from the internet, or one made up by a Dummy radio, is never put on APRS-IS. While a Dummy radio is on, your own position is not put there either.

It has nothing to do with **RX only** (`station/transmit`): the radio does not transmit when it is gated, because nothing of the internet is ever sent on the air.

## The status row and the Internet mark

The status row is the one of the radio: **connected** (with the server and how many stations are within the radius, or, with only **Send what I hear**, how many packets were sent), **connecting**, or **waiting** with why it is not connected; behind its arrow are the server, the filter while the stations are shown, and what was sent while what you hear is sent.

With **Send what I hear** on, the arrow also opens a list of the packets it put on APRS-IS since NeoAPRS started (the newest 200, the newest at the bottom), each with its time and the radio that heard it, as it went to the server. The daemon sends them to the page only while that list is open. If the connection is lost it is opened again after 5, 10, 20 and then 30 seconds. A server that says nothing for three minutes counts as lost.

While the login is up the header has the **Internet** mark; its words when you point at it say which of the two it is for. It turns lime if the server does not take what your radios hear.

The log says at each change of the ticks what is on ("igate: on, gating what the radios hear, showing nothing of the internet"), then the login ("logged in as OH2GBA, verified, server T2FINLAND"). Each packet read from the internet and each packet gated is a line at the debug level (`neoaprs --debug`), and every hour there is a line with how many packets were read and, while it gates, how many were gated and why the others were not.

## The server

The setting `igate/server` is `rotate.aprs2.net:14580` unless you change it. That name picks a server of the volunteer network for each login, and 14580 is the port with a filter. It is not on the page, because the default suits nearly everyone; to use another server, `neoaprs db set igate/server host:port`.

## Advanced: a passcode set by hand

A passcode stored with `neoaprs db set igate/password NUMBER` (0 to 32767) is used in place of the one worked out from the call. A station that gated with a passcode set by hand before the two ticks came has **Send what I hear** ticked and goes on as before. The passcode is kept as a setting in the database on your computer, like the access key of the page, and is in no line of the log. `neoaprs db set igate/password ""` goes back to the one worked out from the call.

## Answering `?IGATE?`

While **Send what I hear** gates (logged in and verified: the status row says **connected**), NeoAPRS answers the general query `?IGATE?` that stations on the air send to find the iGates near them, as the specification asks. The answer is one packet of yours, by radio:

```
<IGATE,MSG_CNT=0,LOC_CNT=3,UPL_CNT=812
```

- `MSG_CNT` is the messages sent from the internet to the radio: always 0, because nothing of the internet is ever sent on the air;
- `LOC_CNT` is the "local" stations: those heard direct (by no digipeater) in the last hour on the radios that may carry a path, Packet and LoRa;
- `UPL_CNT` is the packets put on APRS-IS since NeoAPRS started, one of the counts Dire Wolf adds.

It goes after a random wait of 0 to 120 seconds by the path of the station that asked, and once one is taken another is not for 10 minutes, as for `?APRS?` ([Answers to queries](beacon.md#answers-to-queries)). With **Send what I hear** off, the login still connecting, or a server that did not take the login, it is no iGate and the query is not answered; nor under **RX only**, when nothing is sent at all.
