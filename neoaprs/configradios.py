"""The radios of the settings, until they are stored as radios (package D1a): today's flat keys read as radio 1, the FM radio (tnc/profile, fm/enabled, serial/*, tcp/*, beacon/path, digi/enabled), and radio 2,
the HF radio (hf/profile, hf/enabled, mercury/*), each a `RadioSpec` with its own settings as text (`radios_from_flat`). `RadioViews` gives `Config` the radios and what is read of them under the names the
round writes against; nothing here changes what a setting means. The rows of a radio's own state (its beacon's last send, the port its search found) are `radio_state_key`'s. No I/O."""
import re
from functools import cached_property
from typing import Protocol, cast

from .radiospec import FM_ID, HF_ID, RadioError, RadioId, RadioSpec, enabled, live, main_radio
from .radiotype import stored_text
from .radiotypes import kind_field


class FlatRadios(Protocol):
    """The flat settings the two radios of today are made of (Config's fields)."""
    @property
    def tnc_profile(self) -> str: ...
    @property
    def fm_enabled(self) -> bool: ...
    @property
    def serial_port(self) -> str: ...
    @property
    def serial_baud(self) -> int | None: ...
    @property
    def tcp_host(self) -> str: ...
    @property
    def tcp_port(self) -> int: ...
    @property
    def beacon_path(self) -> str: ...
    @property
    def digi_enabled(self) -> bool: ...
    @property
    def hf_profile(self) -> str: ...
    @property
    def hf_enabled(self) -> bool: ...
    @property
    def mercury_sound_card(self) -> str: ...
    @property
    def mercury_keying(self) -> str: ...
    @property
    def mercury_tx_gain_db(self) -> int: ...


def radios_from_flat(config: FlatRadios) -> tuple[RadioSpec, ...]:
    """Radio 1 (fm: tnc/profile, fm/enabled, the port, the speed and the TCP server from serial/* and tcp/*, the path from beacon/path, the digipeater from digi/enabled) and radio 2 (hf: hf/profile, hf/enabled,
    the sound card, the keying and the gain from mercury/*), the beacon on both: what `Config.radios` is until the radios are stored (D1a)."""
    fm = {"port": config.serial_port, "baud": stored_text(config.serial_baud), "tcp_host": config.tcp_host, "tcp_port": stored_text(config.tcp_port),
          "beacon": "true", "path": config.beacon_path, "digipeat": stored_text(config.digi_enabled)}
    hf = {"sound_card": config.mercury_sound_card, "keying": config.mercury_keying, "tx_gain_db": stored_text(config.mercury_tx_gain_db), "beacon": "true"}
    return (RadioSpec(FM_ID, "fm", config.tnc_profile, "", config.fm_enabled, 1, settings=fm), RadioSpec(HF_ID, "hf", config.hf_profile, "", config.hf_enabled, 2, settings=hf))


def radio_state_key(radio: RadioId, name: str) -> str:
    """The row of the settings table that keeps a radio's own state (services/memory.py): `radio/<id>/beacon_last_sent_at`, `radio/<id>/last_port`."""
    return f"radio/{radio}/{name}"


_RADIO_KEY = re.compile(r"radio/([1-9][0-9]*)/([^/]+)")


def radio_key_of(text: str) -> tuple[RadioId, str] | None:
    """The radio and its own key that a key `radio/<id>/<key>` names (radio_state_key's rows, and the wire's and the command line's keys of a radio's setting); None for a key that is no radio's."""
    found = _RADIO_KEY.fullmatch(text)
    return (int(found[1]), found[2]) if found else None


class RadioViews:
    """The radios of the settings, as `Config` gives them (its base): views of the flat keys until D1a stores them."""

    @cached_property
    def radios(self) -> tuple[RadioSpec, ...]:
        """Every radio, removed ones too, by id."""
        return radios_from_flat(cast(FlatRadios, self))

    @property
    def main_choice(self) -> RadioId | None:
        """The radio the operator chose as the main one (station/main_radio, from wave 4 on); None: the first enabled."""
        return None

    def radio(self, id: RadioId) -> RadioSpec | None:
        return next((s for s in self.radios if s.id == id), None)

    @property
    def live_radios(self) -> list[RadioSpec]:
        return live(self.radios)

    @property
    def enabled_radios(self) -> list[RadioSpec]:
        return enabled(self.radios)

    @property
    def main_radio(self) -> RadioId | None:
        """The main radio (radiospec.main_radio): today the FM radio while it is on, else the HF one, else none."""
        return main_radio(self.radios, self.main_choice)

    @staticmethod
    def check_radio(spec: RadioSpec, key: str, text: str) -> str:
        """The text of a radio's setting as it is stored; RadioError naming `radio/<id>/<key>` when the key is no setting of its kind or the text is not a value of it."""
        found = kind_field(spec.kind, key)
        if found is None:
            raise RadioError(f"radio/{spec.id}/{key}: a radio of the kind {spec.kind} has no such setting")
        try:
            return stored_text(found.parse(text))
        except ValueError as e:
            raise RadioError(f"radio/{spec.id}/{key}: {e}") from None
