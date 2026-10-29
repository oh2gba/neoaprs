# Internet stations

**Settings → Internet stations → Enable** shows the stations that APRS-IS, the internet side of APRS, has within the radius of your map. They are on the map, in the Stations tab and in the Packets tab, marked as heard over the internet ([the page](page.md#stations)). Nothing is sent. It is off until you switch it on.

Switching it off hides them again, as if it had never been on: no station known only from the internet, no packet from it, and a station heard both ways shows only what the radio heard (no Internet tag or time, the place the radio gave). The map's [replay](page.md#replay) does the same: it plays only what was on the air, whenever the internet's packets came. Nothing is deleted: switch it on and they are back at once.

## What it does

- It logs in to APRS-IS with your call, read only, and asks for the stations within the **Radius** of the Map group of the Settings tab, round your position. The circle is asked for again when you change the radius and when your position has moved more than 10 km.
- The status row under the tickbox is the one of the radio: **connected** (with the server and how many stations are within the radius), **connecting**, or **waiting** with why it is not connected; behind its arrow are the server and the filter. The tickbox needs your call: until it is set the group says **Set your call first**.
- If the connection is lost it is opened again after 5, 10, 20 and then 30 seconds. A server that says nothing for three minutes counts as lost.

**Nothing from the internet is ever sent on the air.** What the server sends goes to the map and the logs and nowhere else: a message for you that was sent from the internet is not kept or answered, no query from it is answered, no packet of APRS-IS is repeated by your radio, and a station known only from the internet cannot be messaged. This is how NeoAPRS is built, not a setting.

The log has the login at the info level ("logged in as OH2GBA, server T2FINLAND"), each packet read from the internet at the debug level (`neoaprs --debug`), and every hour a line with how many packets were read.

## The server

The setting `igate/server` is `rotate.aprs2.net:14580` unless you change it. That name picks a server of the volunteer network for each login, and 14580 is the port with a filter. It is not on the page, because the default suits nearly everyone; to use another server, `neoaprs db set igate/server host:port`.

## Advanced: putting what the radio hears on APRS-IS

NeoAPRS can also act as an iGate for your radio. This is not on the page. With a passcode that belongs to your call (a number from 0 to 32767; `neoaprs db set igate/password NUMBER`) and the switch on, what the radio hears is put on APRS-IS, and your own position with it. The rules are the specification's:

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
- it did not come from the air: a packet from the internet, or one made up by the Dummy radio, is never put on APRS-IS. While the radio is the Dummy, your own position is not put there either.

The passcode is kept as a setting in the database on your computer, like the access key of the page. The log then has each packet gated at the debug level and every hour a line with the counts. It has nothing to do with `station/transmit` (the **RX only** pill): the radio does not transmit when it is gated, because nothing of the internet is ever sent on the air.
