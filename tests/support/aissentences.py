"""Made-up AIS sentences for the tests: a message's fields put into bits, the bits into the six-bit payload, and the payload into NMEA sentences with their checksum."""


def _bits(fields: list[tuple[int, int]]) -> str:
    return "".join(format(value & ((1 << width) - 1), f"0{width}b") for value, width in fields)


def text(value: str, chars: int) -> list[tuple[int, int]]:
    """Text as AIS writes it: six bits a letter, '@' for padding."""
    padded = value.upper().ljust(chars, "@")[:chars]
    return [(ord(c) - 64 if ord(c) >= 64 else ord(c), 6) for c in padded]


def payload(fields: list[tuple[int, int]]) -> tuple[str, int]:
    bits = _bits(fields)
    fill = (-len(bits)) % 6
    bits += "0" * fill
    chars = []
    for at in range(0, len(bits), 6):
        code = int(bits[at:at + 6], 2)
        chars.append(chr(code + 48 if code < 40 else code + 56))
    return "".join(chars), fill


def checksum(body: str) -> str:
    total = 0
    for char in body:
        total ^= ord(char)
    return f"{total:02X}"


def sentence(data: str, fill: int = 0, count: int = 1, number: int = 1, seq: str = "", channel: str = "A", talker: str = "AIVDM") -> str:
    body = f"{talker},{count},{number},{seq},{channel},{data},{fill}"
    return f"!{body}*{checksum(body)}"


def sentences(fields: list[tuple[int, int]], per: int = 40, seq: str = "3", channel: str = "B") -> list[str]:
    """The message as one sentence, or as several when its payload is longer than `per` characters."""
    data, fill = payload(fields)
    if len(data) <= per:
        return [sentence(data, fill, channel=channel)]
    pieces = [data[at:at + per] for at in range(0, len(data), per)]
    return [sentence(piece, fill if n == len(pieces) else 0, len(pieces), n, seq, channel) for n, piece in enumerate(pieces, 1)]


def class_a(mmsi: int, lat: float, lon: float, sog: float = 0.0, cog: float = 0.0, heading: int = 511, kind: int = 1) -> list[tuple[int, int]]:
    return [(kind, 6), (0, 2), (mmsi, 30), (0, 4), (0, 8), (round(sog * 10), 10), (0, 1), (round(lon * 600000), 28), (round(lat * 600000), 27), (round(cog * 10), 12), (heading, 9), (60, 6), (0, 2), (0, 3), (0, 1), (0, 19)]


def class_b(mmsi: int, lat: float, lon: float, sog: float = 0.0, cog: float = 0.0, heading: int = 511, kind: int = 18) -> list[tuple[int, int]]:
    return [(kind, 6), (0, 2), (mmsi, 30), (0, 8), (round(sog * 10), 10), (0, 1), (round(lon * 600000), 28), (round(lat * 600000), 27), (round(cog * 10), 12), (heading, 9), (60, 6), (0, 2), (0, 8)]


def static_a(mmsi: int, name: str, ship_type: int, destination: str) -> list[tuple[int, int]]:
    return [(5, 6), (0, 2), (mmsi, 30), (0, 2), (9316983, 30), *text("3E2300", 7), *text(name, 20), (ship_type, 8), (0, 30), (1, 4), (0, 20), (68, 8), *text(destination, 20), (0, 1), (0, 1)]


def static_b(mmsi: int, part: int, name: str = "", ship_type: int = 0) -> list[tuple[int, int]]:
    head = [(24, 6), (0, 2), (mmsi, 30), (part, 2)]
    if part == 0:
        return [*head, *text(name, 20), (0, 8)]
    return [*head, (ship_type, 8), *text("SAAB", 7), *text("OH1X", 7), (0, 30), (0, 6)]
