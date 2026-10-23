"""Development boards and debug probes, known by their USB ids: the search for the radio never opens them. Their USB console resets the chip, or drops it into its boot loader, when a program opens or closes the port (the
kernel and pyserial toggle DTR and RTS), so opening one of them to see whether a radio answers resets whatever runs on it. None of these is a TNC or a radio's USB port; a board that is one is chosen by its name (`serial/port`), which is
never filtered. The generic USB-serial bridges (FTDI 0403, Silicon Labs 10c4, WCH 1a86, Prolific 067b) and the TNCs' own ids (ST's own serial port 0483:5740, which the Mobilinkd TNC4 uses) are not here."""

# (vendor id, product ids or None for every product of the vendor, what it is)
BOARDS: tuple[tuple[int, frozenset[int] | None, str], ...] = (
    (0x303A, None, "an ESP32 development board"),                    # Espressif: the USB Serial/JTAG console 303a:1001 and the native USB of the S2, S3 and C3
    (0x2341, None, "an Arduino board"),
    (0x2A03, None, "an Arduino board"),
    (0x2E8A, None, "a Raspberry Pi Pico board"),                     # RP2040 and RP2350, the Debug Probe too
    (0x239A, None, "an Adafruit board"),
    (0x16C0, frozenset({0x0483}), "a Teensy board"),                 # (16c0 is shared by other makers: only the Teensy's serial)
    (0x1366, None, "a SEGGER J-Link debug probe"),
    (0x0483, frozenset({0x3744, 0x3748, 0x374B, 0x374D, 0x374E, 0x374F, 0x3752, 0x3753}), "an ST-Link debug probe"),      # (0483:5740, the serial port of an STM32 firmware such as the Mobilinkd TNCs', is not one)
)


def board_kind(vid: int | None, pid: int | None) -> str:
    """What a USB device with these ids is when it is a board the search leaves alone ("an ESP32 development board"), else an empty text."""
    if vid is None or pid is None:
        return ""
    for board_vid, pids, kind in BOARDS:
        if vid == board_vid and (pids is None or pid in pids):
            return kind
    return ""


def describe(vid: int, pid: int) -> str:
    return f"{board_kind(vid, pid)} (USB {vid:04x}:{pid:04x})"
