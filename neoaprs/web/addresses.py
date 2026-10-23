"""The address of this computer that another device on the network can open the page at."""
import socket

PROBE = "192.0.2.1"            # a documentation address: a UDP "connect" sends nothing, it only asks the system which address it would send from


def lan_addresses() -> list[str]:
    """The IPv4 address the system would use to reach the network (an IPv6 one changes by itself, and a phone is given the IPv4 one by the router); none without a route, and never the loopback."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            if sock.connect_ex((PROBE, 9)) != 0:
                return []                               # no route
            address = str(sock.getsockname()[0])
    except OSError:
        return []
    return [] if address.startswith(("127.", "0.")) else [address]
