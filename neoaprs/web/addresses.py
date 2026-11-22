"""IP address parsing and the LAN address of this computer."""
import ipaddress
import socket

# A documentation address: a UDP "connect" sends nothing, it only selects the source address.
PROBE = "192.0.2.1"


def as_address(text: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Return the IP address in `text`, or None for a name.

    Drops an IPv6 zone and unmaps `::ffff:a.b.c.d`.
    """
    try:
        address = ipaddress.ip_address(text.split("%", 1)[0])
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def is_loopback(text: str) -> bool:
    """Return True if `text` is a loopback address (127.0.0.0/8, ::1 or its IPv4-mapped form)."""
    address = as_address(text)
    return address is not None and address.is_loopback


def lan_addresses() -> list[str]:
    """Return the IPv4 address used to reach the network; empty without a route, never loopback.

    IPv6 addresses are skipped because they change on their own.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            if sock.connect_ex((PROBE, 9)) != 0:
                return []
            address = str(sock.getsockname()[0])
    except OSError:
        return []
    return [] if is_loopback(address) or address.startswith("0.") else [address]
