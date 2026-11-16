"""The settings on the wire: the topic `config` and the command that changes them. Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import _Command, _Model


class HttpsState(_Model):
    """The secure connection (`web/https`) as the daemon has it."""
    on: bool = Field(description="the page is served over https right now (`web/https` and `web/network` are on, and it started)")
    port: int = Field(description="the https port; 0 while it is not served")
    fingerprint: str = Field(description="SHA-256 fingerprint of NeoAPRS's certificate authority, `AB:CD:...`, for a person to compare with what the device shows when the certificate is installed; empty while it is not served")
    reason: Literal["", "no_library", "clock", "certificates", "no_port"] = Field(description="why the secure connection could not start or go on, when it was asked for, as a code the page says in its words (the log has the details): "
                                                                                   "`no_library` this installation cannot make it; `clock` the clock of this computer is not set; `certificates` the certificates could not be made, read or loaded; "
                                                                                   "`no_port` no port after the page's own was free for it; empty otherwise")


class ConfigValues(_Model):
    """The settings: each key of the station's settings (`station/call`, `beacon/interval_min`, ...) with its value as text, the way the daemon writes it, and the defaults beside them. The value of the topic
    `config`, told again after every save, though nothing differs."""
    values: dict[str, str] = Field(description="the settings in force, key to text; every key is there (the keys of `CONFIG_KEYS`: the station's settings, and `serial/last_port`, the port radio 1's search found last, which the page shows and does not set)")
    defaults: dict[str, str] = Field(description="the same keys with their defaults, for a form's reset")
    radio_values: dict[str, str] = Field(description="the radios' own settings in force, `radio/<id>/<key>` to text, every field of its kind for each radio that is not removed (the fields of `RADIO_TYPES`), and the station's settings "
                                                     "of the radios (`email/radio`, the id of the radio chosen for email, empty for none chosen: the radio in force is `status.email_radio`): what `set_config` takes beside `values`; kept apart from `values`, "
                                                     "whose form shows none of them")
    radio_defaults: dict[str, str] = Field(description="the same keys with their defaults (the field's of the radio's kind)")
    urls: list[str] = Field(description="where another device opens the page while `web/network` is on (this computer's address on the network and its name there, with the port); empty while it is off (with `https` on, the https addresses)")
    https: HttpsState = Field(description="the secure connection: whether it is served, its port, the fingerprint of the authority's certificate (which `GET /neoaprs-ca.crt` downloads), and why not when it could not start")


class SetConfig(_Command):
    """Changes settings. Every key and value is checked before anything is stored: the first that is wrong is answered with an `error` that names the key, and nothing changes. A key that is
    left out keeps its value. The answer is the `config` topic told again. `web/port` and `web/allowed_hosts` are read at the daemon's start, `web/network` (and with it the access key `web/key`) and `web/https` count at once, `station/*` move our own station on the
    map. A radio's own setting is `radio/<id>/<key>` (a key of `radio_values`): it is checked by the field of its kind, stored with the rest in one write and restarts that radio
    alone where its driver says so; a radio that is none or removed is refused with `radio.unknown` (a removed one with its `name` and `removed` 1), a key its kind has not with `radio.no_setting` (its `name` and id,
    `radio`), `email/radio` changed to name no radio with `radio.unknown`, a device another radio holds or is set to, or the GPS receiver holds, with `radio.resource_held` (`resource`, `holder`, and the holder's
    id `held_by`, 0 for the GPS receiver), and the last radio that is on switched off with `radio.last_enabled` (the radio's id, `radio`), each with the key. A key of a radio's setting that does not name the
    radio (`serial/port`, `hf/enabled`) is refused with `setting.unknown`: the radio's own key is `radio/<id>/<key>`, its type and Enable are `radio_change`'s. A page of another device is refused with `setting.local_only` for `messages/alert_command`, `update/url`, `map/source` and `web/allowed_hosts`."""
    cmd: Literal["set_config"]
    values: dict[str, str] = Field(max_length=64, description="key to the new text of the value; the text is checked and written the way the daemon writes it (`oh2gba` becomes `OH2GBA`)")
