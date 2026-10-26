# The iGate

An iGate puts what a radio hears on APRS-IS, the internet side of APRS, so that stations far away and sites such as aprs.fi can see it. NeoAPRS has a **receive-only** iGate, and with it on the stations of the internet round you show on the map too. It is off until you switch it on.

## What it does

- It takes every packet your radio hears and, with a few exceptions (below), puts it on APRS-IS. The packet goes as it was heard, with the path as heard, the information field byte for byte, and `qAO,` and your call added at the end of the path. `qAO` is how a receive-only iGate says "I cannot put messages for this station back on the air".
- It puts your own position on APRS-IS, so that your iGate shows on maps: when it has logged in and every 30 minutes after, for a station that stays where it is (the same position as the beacon, sent as `TCPIP*`, the only path a packet of your own has on the internet). A moving station sends the beacons that go out on the radio, at most one a minute. The Beacon choice does not matter: with the beacon off the position still goes to APRS-IS.
- It shows the stations that APRS-IS has within 150 km of your position: on the map, in the Stations tab and in the Packets tab, marked as heard over the internet ([the page](page.md#stations)). The server is asked for that circle when the iGate logs in, and again when your position has moved more than 10 km.
- It shows in the Settings tab, in the **iGate** group, in one line: "Connected to T2FINLAND, 1234 packets gated, last 12 s ago".

## What it never does

**Nothing from the internet is ever sent on the air.** What the server sends goes to the map and the logs and nowhere else: a message for you that was sent from the internet is not kept or answered, no query from it is answered, no packet of APRS-IS is repeated by your radio, and a station known only from the internet cannot be messaged. This is how the iGate is built, not a setting.

## Switching it on

1. Set your call first (the Beacon tab). Until then the iGate group says **Set your call first**.
2. Tick **Gate to APRS-IS**. The **Passcode** field and the status line appear as soon as it is ticked.
3. **Request a passcode** (below), and type it into **Passcode**.

The status line says what it is waiting for, or that it is connected. Without a passcode nothing is gated, and the internet stations still show. If the server does not accept the passcode, the pill says **not verified**, nothing is gated, the stations of the internet still show, and the iGate does not log in again with it until you change a setting.

## The passcode

APRS-IS accepts packets only from a login with a passcode that belongs to the call. The passcode is a number made from your call (not its SSID), the same for every program. The APRS-IS rules leave it to each software author to give it to the users on request. NeoAPRS does not work it out. The link **Request a passcode** next to the field opens the request page of the NeoAPRS author in a new tab, with your call filled in; the passcode comes by e-mail. Type it into the field. The page shows it as dots.

The passcode `-1` only reads and cannot put anything on APRS-IS: it is not accepted here. A passcode is a number from 0 to 32767.

The passcode is kept as a setting (`igate/password`) in the database on your computer, like the access key of the page.

## The server

The setting `igate/server` is `rotate.aprs2.net:14580` unless you change it. That name picks a server of the volunteer network for each login, and 14580 is the port that iGates use. It is not on the page, because the default suits nearly everyone; to use another server, `neoaprs db set igate/server host:port`. The iGate logs in with your call, the passcode and the circle of 150 km round your position as the filter.

If the connection is lost it is opened again after 5, 10, 20 and then 30 seconds. A server that says nothing for three minutes counts as lost; the iGate itself sends a comment line when it has written nothing for two minutes.

## Which packets are left out

A packet heard is not put on APRS-IS when:

- its path has `TCPIP` or `TCPXX`: it came from the internet already;
- its path has `NOGATE` or `RFONLY`: it asks to stay off the internet;
- it is a general query (the information field starts with `?`);
- it is a third-party packet (an iGate's) whose inner packet came from the internet. A third-party packet without that is put on APRS-IS as the packet inside, with the iGate's header taken off;
- its source is not a station (`N0CALL`, `WIDE2`, `TCPIP` and the like) or is your own call;
- it has a line break inside (APRS-IS has one packet to a line), or would make a line of more than 512 bytes;
- the same source, destination and text were put on APRS-IS in the last 30 seconds: a packet repeated by digipeaters is heard more than once and goes once;
- the iGate was not logged in when it was heard;
- it did not come from the air: a packet from the internet, or one made up by the Dummy radio, is never put on APRS-IS. While the radio is the Dummy, your own position is not put there either.

## The counts

Since the program started, the page and the log tell how many packets were **gated**, and the pointer on the status line tells how many were not and why: *already via the internet*, *NOGATE or RFONLY*, *query*, *not a station*, *our own*, *line break*, *too long*, *duplicate*, *heard while offline*, *not from the air*.

The log has the login at the info level ("logged in as OH2GBA, verified, server T2FINLAND"), each packet gated and each packet read from the internet at the debug level (`neoaprs --debug`; those from the radio are at the info level), and every hour two lines: "igate: 812 packets gated in the last hour, 40 not gated: 31 TCPIP, 6 duplicate, 3 query" and "igate: 3512 packets read from APRS-IS in the last hour, 2 were no packet". The passcode is in no line of the log.

## Receive only

The word is the iGate's own: it does not take the internet to the radio. It has nothing to do with the daemon's setting `station/transmit` (the amber **Receive only** badge, [beacon.md](beacon.md#receive-only)): a station that never transmits can still run the iGate, because the iGate never transmits.
