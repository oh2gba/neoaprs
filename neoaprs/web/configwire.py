"""The settings on the wire: the topic `config` and the command that changes them. Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import _Command, _Model


class HttpsState(_Model):
    """The secure connection (`web/https`) as the daemon has it."""
    on: bool = Field(description="the page is served over https right now (`web/https` and `web/network` are on, and it started)")
    port: int = Field(description="the https port; 0 while it is not served")
    fingerprint: str = Field(description="SHA-256 fingerprint of NeoAPRS's certificate authority, `AB:CD:...`, for a person to compare with what the device shows when the certificate is installed; empty while it is not served")
    problem: str = Field(description="why the secure connection could not start or go on, when it was asked for; empty otherwise")


class ConfigValues(_Model):
    """The settings: each key of the settings table (`station/call`, `serial/baud`, ...) with its value as text, the way the daemon writes it, and the defaults beside them. The value of the topic
    `config`, told again after every save, though nothing differs."""
    values: dict[str, str] = Field(description="the settings in force, key to text; every key is there (the keys of `CONFIG_KEYS`: the station's, and the flat keys of radios 1 and 2 of before)")
    defaults: dict[str, str] = Field(description="the same keys with their defaults, for a form's reset")
    radio_values: dict[str, str] = Field(description="the radios' own settings in force, `radio/<id>/<key>` to text, every field of its kind for each radio that is not removed (the fields of `RADIO_TYPES`), and the station's settings "
                                                     "of the radios (`station/main_radio`, the main radio's id, empty for the first enabled): what `set_config` takes beside `values`; kept apart from `values` so that the form of before "
                                                     "shows none of them")
    radio_defaults: dict[str, str] = Field(description="the same keys with their defaults (the field's of the radio's kind)")
    urls: list[str] = Field(description="where another device opens the page while `web/network` is on (this computer's address on the network and its name there, with the port); empty while it is off (with `https` on, the https addresses)")
    https: HttpsState = Field(description="the secure connection: whether it is served, its port, the fingerprint of the authority's certificate (which `GET /neoaprs-ca.crt` downloads), and why not when it could not start")


class SetConfig(_Command):
    """Changes settings. Every key and value is checked before anything is stored: the first that is wrong is answered with an `error` that names the key, and nothing changes. A key that is
    left out keeps its value. The answer is the `config` topic told again. `web/port` and `web/allowed_hosts` are read at the daemon's start, `web/network` (and with it the access key `web/key`) and `web/https` count at once, `serial/*`, `tcp/*` and `tnc/profile` restart the
    TNC, `station/*` move our own station on the map. A radio's own setting is `radio/<id>/<key>` (a key of `radio_values`): it is checked by the field of its kind, stored with the rest in one write and restarts that radio
    alone where its driver says so; a radio that is none or removed is refused with `radio.unknown`, a key its kind has not with `radio.no_setting` (its `name`), `station/main_radio` changed to name no radio with
    `radio.unknown`, a device another radio holds or is set to, or the GPS receiver holds, with `radio.resource_held` (`resource`, `holder`), each with the key. A key of the form of before whose radio (1 or 2) is
    removed is refused with `radio.unknown` when it would change what it shows (sent back as shown, it is let through). A page of another device is refused with `setting.local_only` for `messages/alert_command`, `update/url`, `map/source` and `web/allowed_hosts`."""
    cmd: Literal["set_config"]
    values: dict[str, str] = Field(max_length=64, description="key to the new text of the value; the text is checked and written the way the daemon writes it (`oh2gba` becomes `OH2GBA`)")
