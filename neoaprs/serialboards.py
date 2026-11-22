"""Development boards and debug probes, known by their USB ids: the search never opens them.

Opening one resets it; a board that is a radio is chosen by its name (`serial/port`) instead.
"""

# (vendor id, product ids or None for every product of the vendor, what it is)
BOARDS: tuple[tuple[int, frozenset[int] | None, str], ...] = (
    # Espressif: USB Serial/JTAG console 303a:1001 and the native USB of S2, S3, C3
    (0x303A, None, "an ESP32 development board"),
    (0x2341, None, "an Arduino board"),
    (0x2A03, None, "an Arduino board"),
    (0x2E8A, None, "a Raspberry Pi Pico board"),  # RP2040 and RP2350, the Debug Probe too
    (0x239A, None, "an Adafruit board"),
    (0x16C0, frozenset({0x0483}), "a Teensy board"),  # 16c0 is shared by other makers: only the Teensy's serial
    (0x1366, None, "a SEGGER J-Link debug probe"),
    # 0483:5740, the serial port of an STM32 firmware such as the Mobilinkd TNCs, is not one.
    (0x0483, frozenset({0x3744, 0x3748, 0x374B, 0x374D, 0x374E, 0x374F, 0x3752, 0x3753}), "an ST-Link debug probe"),
)


def board_kind(vid: int | None, pid: int | None) -> str:
    """Return what a USB device with these ids is if it is a board the search leaves alone."""
    if vid is None or pid is None:
        return ""
    for board_vid, pids, kind in BOARDS:
        if vid == board_vid and (pids is None or pid in pids):
            return kind
    return ""


def describe(vid: int, pid: int) -> str:
    return f"{board_kind(vid, pid)} (USB {vid:04x}:{pid:04x})"
