"""The settings on the wire: the topic `config` and the command that changes them. Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import _Command, _Model


class ConfigValues(_Model):
    """The settings: each key of the settings table (`station/call`, `serial/baud`, ...) with its value as text, the way the daemon writes it, and the defaults beside them. The value of the topic
    `config`, told again after every save, though nothing differs."""
    values: dict[str, str] = Field(description="the settings in force, key to text; every key is there")
    defaults: dict[str, str] = Field(description="the same keys with their defaults, for a form's reset")
    urls: list[str] = Field(description="where another device opens the page while `web/network` is on (this computer's address on the network and its name there, with the port); empty while it is off")


class SetConfig(_Command):
    """Changes settings. Every key and value is checked before anything is stored: the first that is wrong is answered with an `error` that names the key, and nothing changes. A key that is
    left out keeps its value. The answer is the `config` topic told again. `web/port` and `web/allowed_hosts` are read at the daemon's start, `web/network` (and with it the access key `web/key`) counts at once, `serial/*`, `tcp/*` and `tnc/profile` restart the
    TNC, `station/*` move our own station on the map. `tnc/check_sec` counts at once, with no restart."""
    cmd: Literal["set_config"]
    values: dict[str, str] = Field(max_length=64, description="key to the new text of the value; the text is checked and written the way the daemon writes it (`oh2gba` becomes `OH2GBA`)")
