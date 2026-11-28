"""What the page is shown of the stations and packets, by the two ticks that leave some out.

Show Internet stations (`igate/enabled`) leaves out what came from APRS-IS; Show Internet packets
heard by radio (`igate/show_gated`) what an iGate put on the air from the internet (`rf-gated`),
except a message or ack to our own call. Nothing is deleted: the book and the log keep it all.
"""

from dataclasses import dataclass

from .config import Config
from .message import addressed_to
from .packet import IS, RF_GATED, Message, Packet
from .station import Station


@dataclass(frozen=True)
class Shown:
    internet: bool = True
    gated: bool = True
    own: str = ""  # our call, whose messages and acks are shown whatever the ticks

    @classmethod
    def of(cls, config: Config) -> "Shown":
        return cls(config.igate_enabled, config.igate_show_gated, config.station_call)

    def station(self, station: Station) -> Station | None:
        """Return the station as the page is shown it; None if nothing of it is shown."""
        view = station if self.internet else station.radio_view()
        return view if view is None or self.gated else view.without_gated()

    def packet(self, packet: Packet) -> bool:
        if packet.via == IS:
            return self.internet
        return self.gated or packet.via != RF_GATED or to_us(packet, self.own)


def to_us(packet: Packet, own: str) -> bool:
    """Return whether the packet is a message or ack addressed to our call."""
    return isinstance(packet.decoded, Message) and addressed_to(packet.decoded.addressee, own)
