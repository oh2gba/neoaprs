# Roadmap

What is planned.

- An Email tab that explains itself: plain actions ("send an email", "read my mail") instead of the gateway's commands (`<shortcut> L`, `<shortcut> R`, `get`, which work only for shortcuts registered with the gateway first); a clear state for a mail whose gateway ack never came back (the acks of EMAIL-2 reach the radio only through an iGate, so a mail that went through can look failed); the gateway's answers shown as answers
- A lighter station card: the message settings of a station (Path and its suggestion, RF only, Attempts) only in the header of its conversation, not on the card; the card keeps what is known of the station, its "Off map after", and the Message and Forget buttons; a row with nothing to say is left out (no Course, Speed or Altitude for a house, no Status when none was heard)
- A hover card on the map: pointing at a station shows the important things at once, without a click (call, last heard, status, comment, distance and bearing, the temperature of a weather station, whether it is heard direct); a click still opens the full card, and a phone, with no hover, keeps the tap
- The route on the map: a click on a station draws how its packets reach us, from the station through each digipeater (that has a position) to our own, its latest route and its best one
- Bluetooth LE KISS
- A receive-only text-monitor profile
- A `.deb` for the Raspberry Pi
- Signing the Windows installer
- A registered tocall
