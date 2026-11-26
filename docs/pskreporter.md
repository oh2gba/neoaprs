# PSK Reporter: what NeoAPRS sends and the rules it keeps

A Mercury radio with `radio/<id>/psk_report` ticked and a `radio/<id>/psk_dial` reports every station it hears directly to
[PSK Reporter](https://pskreporter.info). The datagrams are made in `neoaprs/pskreport.py` (pure code), the queue, the pace and the
socket are `neoaprs/services/pskreporter.py`. The protocol is the one of https://pskreporter.info/pskdev.html (read on 26 November
2026); its complete example datagram is `tests/fixtures/pskreporter/example-datagram.txt`, which `tests/test_pskreport.py` makes byte
for byte.

## What is reported

| field | what NeoAPRS puts in it | why |
|---|---|---|
| senderCallsign | the source call of the frame without its SSID | PSK Reporter counts calls, not stations of one call; LinBPQ's packet reports do the same |
| receiverCallsign | the station's call without its SSID | the same |
| senderLocator | the 6-character locator of the frame's position; else of the station's last position heard on a radio; else left out (a template without it) | "highly desirable" (pskdev.html, senderLocator); a position from the internet is not what the radio heard |
| receiverLocator | the station's position as a 6-character locator; without one nothing is sent | a receiver without a place means nothing on the map |
| frequency | the dial in Hz (`28.1800 MHz USB` is 28180000) | VarAC reports the dial, not the audio offset |
| sNR | Mercury's SNR of the frame, rounded and held to -128..127; left out when unknown | one signed byte |
| mode | `NEOAPRS` | the map's mode list fills itself from what is sent; at most 8 characters are seen there, and the name is ours alone so that our spots can be told |
| informationSource | 1, "automatically extracted" | "must be set to the value 1 ... in order for the record to be considered" |
| flowStartSeconds | when the frame was heard | |
| decodingSoftware | `NeoAPRS <version>` | shown as "Using:" on the map and on the statistics page |

Only a frame heard directly is a reception report: the radio is a Mercury radio (not the Dummy), the frame came on the air (not
from APRS-IS, not a third-party packet), no hop of its path is marked used, the source is an amateur call (`neoaprs/callsign.py`)
and not our own base call. A packet a pair passes on is sent, not heard, so it never counts.

## The templates

The receiver template (0x9992) and the two sender templates without an SNR (0x9993 without the locator, 0x9994 with it) are
pskdev.html's, byte for byte. Its templates with an SNR also carry iMD, which Mercury does not measure, so the two with an SNR are
our own, the page's without iMD (0x9995 without the locator, 0x9996 with it). Every datagram that carries descriptors carries all five.

## The pace

| rule | value | source |
|---|---|---|
| a datagram at most every | 5 minutes (`SEND_EVERY_SEC`) | "no more than one every five minutes (unless the packet becomes full)" |
| the first send after the first waiting report | 5 minutes plus 0 to 30 s at random (`JITTER_SEC`) | timed sends "must not be synchronized to the system clock" |
| a call on a band at most every | 5 minutes (`CALL_EVERY_SEC`); a later frame in that time is dropped, not put in the place of the first | each callsign "no more than once per five minute period" |
| the size of a datagram | at most 1200 bytes (`MAX_DATAGRAM`); more goes into the next datagram at once | chosen: below the path MTU of any network, so never fragmented; pskdev.html allows more "unless the packet becomes full" |
| the descriptors | in the first three datagrams of a session, then hourly | "send them in the first three datagrams sent on application startup, and then once per hour" |
| the session | one random id and one UDP socket (one source port) for the run of the daemon | the server keeps the descriptors by source address and port |
| the sequence number | the reports sent before the datagram | "the sequence number is the count of reports and not the count of packets" |
| the queue | 500 reports (`QUEUE_MAX`); when the network is down the oldest go, logged once | chosen |

A send that fails (no name, no network) leaves the reports waiting for the next round; the state is logged once until it changes.
Nothing is sent while nothing was heard. Reporting is no transmission, so it goes on while the station is RX only.

## Where the datagrams go

`report.pskreporter.info` port 4739 (`HOST`, `PORT`), or `NEOAPRS_PSKREPORTER=host:port`. With `NEOAPRS_UPDATE_CHECK=0`
(every test, the smoke runs, `scripts/demo-daemon`) and no `NEOAPRS_PSKREPORTER`, nothing is sent; `tests/conftest.py` takes the
variable away from every test, and a test that wants the datagrams gives a stand-in on 127.0.0.1. Under `NEOAPRS_NO_DEVICES=1` only
an address of this computer is sent to.

`scripts/pskreporter-probe` builds one datagram with `neoaprs/pskreport.py` and sends it to a host and port: PSK Reporter's test
listener (port 14739, whose analysis is at https://pskreporter.info/cgi-bin/psk-analysis.pl) shows how the server reads it.
