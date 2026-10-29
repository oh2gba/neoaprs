"""IP addresses: reading one from the text a request or a setting has, and the address of this computer that another device on the network can open the page at."""
import ipaddress
import socket

PROBE = "192.0.2.1"            # a documentation address: a UDP "connect" sends nothing, it only asks the system which address it would send from


def as_address(text: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """The IP address `text` is, or None when it is a name. A zone (`fe80::1%eth0`) is left off, and an IPv4 address that arrives on an IPv6 socket (`::ffff:127.0.0.1`) is the IPv4 address."""
    try:
        address = ipaddress.ip_address(text.split("%", 1)[0])
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def is_loopback(text: str) -> bool:
    """Is `text` an address of this computer itself (any of 127.0.0.0/8, ::1, and the IPv4 one in its IPv6 form)?"""
    address = as_address(text)
    return address is not None and address.is_loopback


def lan_addresses() -> list[str]:
    """The IPv4 address the system would use to reach the network (an IPv6 one changes by itself, and a phone is given the IPv4 one by the router); none without a route, and never the loopback."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            if sock.connect_ex((PROBE, 9)) != 0:
                return []                               # no route
            address = str(sock.getsockname()[0])
    except OSError:
        return []
    return [] if is_loopback(address) or address.startswith("0.") else [address]
