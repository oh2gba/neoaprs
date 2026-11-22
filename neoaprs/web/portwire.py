"""Wire models for listing serial ports and finding the radio's port."""

from typing import Literal

from pydantic import Field

from .wirebase import _Command, _Message, _Model


class PortRow(_Model):
    """A serial port the system lists, or a Bluetooth device paired with it (Linux; on Windows a paired Bluetooth serial port is a COM port of the system's list). Nothing was opened or connected to find it."""

    device: str = Field(
        description="the name to give as `serial/port`: `COM3`, `/dev/ttyUSB0`, `bt://AA:BB:CC:DD:EE:FF` for a paired Bluetooth device"
    )
    description: str = Field(
        description="what the system calls it, such as `USB Serial Port (COM3)`; `n/a` where it does not say"
    )
    hwid: str = Field(
        description="the hardware id the system gives, such as `USB VID:PID=0403:6001 SER=A1`; `n/a` where it does not say"
    )
    vid: int | None = Field(description="the USB vendor id of an adapter; null for a port that is not USB")
    pid: int | None = Field(description="the USB product id of an adapter; null for a port that is not USB")
    held_by: int | None = Field(
        description="the radio of the station that holds the port now (its id), 0 for the GPS receiver; null while none of ours does. A port another radio holds is not proposed, and the page greys it with the holder's name"
    )
    usb_group: str | None = Field(
        default=None,
        description="which USB device the port sits on together with the others of one radio (an opaque token: equal for a sound card and the serial ports on one radio's own USB hub, or on one USB device; neoaprs/usbtie.py); null where it is not known (Windows, macOS, a port that is not USB, a Bluetooth device). The page orders the keying lines by it and never shows it",
    )


class SoundCardRow(_Model):
    """A sound card as the Mercury HF modem lists it (`mercury -z`), for the Sound card choice of the Mercury radio type."""

    id: str = Field(
        description="the name to give as `mercury/sound_card`: `plughw:CARD=CODEC,DEV=0` on Linux (by the card's name, which a reboot does not change); on Windows the card's recording device and its playing device, joined by `|` (one of them alone for a device with no partner)"
    )
    name: str = Field(description="what the system calls it, such as `USB Audio CODEC`")
    numbered: str = Field(
        default="",
        description="the same card by its number (`plughw:3,0`), as a setting made before named it; empty where the id is not by name",
    )
    default: bool = Field(description="whether it is the system's default device, which the empty setting means")
    pick: bool = Field(
        description="whether it is the card the daemon proposes for the radio (the one it would choose itself, else the system's default, else the first that records and plays): the page preselects it and stores it as `mercury/sound_card` while that is empty; at most one row has it"
    )
    held_by: int | None = Field(
        description="the radio of the station whose modem holds the card now (its id); null while none does. A card another radio holds is never the `pick`"
    )
    usb_group: str | None = Field(
        default=None,
        description="which USB device the card sits on together with the serial ports of one radio: the `usb_group` of those ports (an opaque token); null where it is not known (Windows, macOS, a card that is not USB)",
    )


class ListPorts(_Command):
    """Asks for the serial ports of the machine the daemon runs on, and the Bluetooth devices paired with it. Answered with `ports` to the page that asked. A KISS TCP port (`socket://127.0.0.1:8001`, Direwolf) is not a
    port of the machine: it is typed. With `radio`, also the sound cards its modem lists while that radio's type has a modem on a sound card (Mercury, Sound card), and the proposals leave out what the other radios and
    the GPS receiver hold; each row says who holds it (`held_by`). An `error` for a `radio` that is none (`radio.unknown`)."""

    cmd: Literal["list_ports"]
    radio: int | None = Field(
        default=None,
        ge=1,
        description="the radio the list is for (its id): the sound cards and the proposals are its own; left out: the ports alone, with no sound card and no proposal",
    )


class PortsMsg(_Message):
    """The answer to `list_ports`."""

    type: Literal["ports"]
    ports: list[PortRow] = Field(
        description="the ports, in natural order (`COM2` before `COM10`), then the paired Bluetooth devices"
    )
    search: bool = Field(
        description="whether the daemon looks for the radio among the ports by itself (Linux, the ports that match `serial/pattern`); where it is false (Windows, macOS) the radio is the port in `serial/port`, so the operator picks it from this list"
    )
    find: bool = Field(description="whether Find my radio (`find_radio`) can be asked for: on Linux, Windows and macOS")
    sound_cards: list[SoundCardRow] = Field(
        description="the sound cards the radio's modem lists, for a `radio` named whose type has a modem on a sound card (Mercury, Sound card) while the program is installed; empty otherwise"
    )
    keying: str = Field(
        description="the keying the daemon proposes with the card it proposes (`vox`, `cm108`, `rts:PORT` or `dtr:PORT`): the page preselects it and stores it as the radio's `keying` while that is empty; empty when no sound card is listed"
    )
    radio: int | None = Field(
        description="the radio the list was asked for (`radio` of `list_ports`: the sound cards and the proposals are its own); null for a list that named none. The ports are the machine's, the same whoever asked"
    )


class FindRadio(_Command):
    """Find my radio: tries the serial ports and the paired Bluetooth devices that the search for the radio looks at (not a KISS TCP address), one after the other and each at the usual speeds, until a TNC answers in KISS or can be
    put into KISS the way a TNC profile does. The radio's own line is closed while it runs and opened again after it. It writes nothing but a carriage return and, to a TNC that answers with text, the steps of the TNC profiles that
    put it into KISS; nothing is sent to the air. Told to the page that asked with `radio_search` messages (`trying` before each try, then `found` or `cancelled`); the page puts the answer in the settings. An `error` when a search is running
    (`radio.busy`), when there is no port to try (`radio.no_ports`), when none answered (`radio.not_found`), for a `radio` that is none (`radio.unknown`) and for one of a type that has no serial line (`radio.no_line`). Only that radio's line is
    let go (radio 1's when `radio` is left out), the ports another radio or the GPS receiver holds are passed over, and the messages name it."""

    cmd: Literal["find_radio"]
    radio: int | None = Field(
        default=None,
        ge=1,
        description="the radio the search is for (its id); left out: radio 1, the FM radio of before",
    )


class FindRadioCancel(_Command):
    """Ends the search of `find_radio`; the page that asked is told `cancelled`. An `error` (`radio.not_running`) when none is running. One search runs at a time, so `radio` changes nothing: it is taken so that the page names the radio
    in every command of its box."""

    cmd: Literal["find_radio_cancel"]
    radio: int | None = Field(
        default=None, ge=1, description="the radio whose search is ended; left out: the one running"
    )


class RadioSearchMsg(_Message):
    """How `find_radio` goes, to the page that asked."""

    type: Literal["radio_search"]
    state: Literal["trying", "found", "cancelled"] = Field(
        description="`trying`: about to try `port` at `baud`; `found`: a TNC answered at `port` at `baud` and `profile` fits it, and the search is over; `cancelled`: `find_radio_cancel` ended it"
    )
    port: str = Field(description="the port being tried or found; empty for `cancelled`")
    baud: int | None = Field(
        description="the speed; null for a port that has none (a Bluetooth device) and for `cancelled`"
    )
    profile: str = Field(description="for `found`, the key of the TNC profile (`tnc/profile`); empty otherwise")
    number: int = Field(ge=0, description="the try that is under way, from 1; 0 for `found` and `cancelled`")
    total: int = Field(ge=0, description="how many tries there are if nothing answers; 0 for `found` and `cancelled`")
    radio: int | None = Field(
        description="the radio the search is for (its id); null for a search that named none (radio 1)"
    )
    radio_type: str = Field(
        description="for `found`, the radio type that fits the TNC (a `key` of `RADIO_TYPES`, the same as `profile` for every FM type: 1.11's `type`, which the message's own tag takes); empty otherwise"
    )
