"""Settings with radios, for the tests that hold a Config: a station's radios are the rows of
`radio` and `radio_setting` (neoaprs/radiospec.py), and `Config.radios` holds them as stored.
"""
from dataclasses import replace
from typing import Any

from neoaprs.config import DEFAULTS, Config
from neoaprs.mercury import BROADCAST_PORT
from neoaprs.mercurydriver import ModemSettings, modem_settings, modem_words
from neoaprs.radiodriver import RunOverrides
from neoaprs.radiospec import FM_ID, HF_ID, RadioId, RadioSpec
from neoaprs.radiotype import Kind, stored_text
from neoaprs.radiotypes import BY_KEY, DEFAULT_TYPE
from neoaprs.tncdriver import TncSettings, line_settings

# The kind of a radio made by its id where no type says it: radio 1 the FM radio, radio 2 the HF
# radio, as the tests have them
KINDS: dict[RadioId, Kind] = {FM_ID: "fm", HF_ID: "hf"}
# And whether it is on: the FM radio on, the HF radio off
ON: dict[RadioId, bool] = {FM_ID: True, HF_ID: False}


def radio(id: RadioId, type: str = "", enabled: bool | None = None, **settings: Any) -> RadioSpec:
    """A radio of the id (its kind the type's, else KINDS'), at the place of its id, with these own
    settings."""
    kind = BY_KEY[type].kind if type else KINDS.get(id, "fm")
    return RadioSpec(id, kind, type or DEFAULT_TYPE[kind], "", ON.get(id, True) if enabled is None else enabled, id, settings={key: stored_text(value) for key, value in settings.items()})


def with_radio(config: Config, id: RadioId, type: str = "", enabled: bool | None = None, **settings: Any) -> Config:
    """The settings with the radio of the id changed (its type, its tickbox, its own settings put
    in), or made where it is not there; the others as they are."""
    spec = config.radio(id)
    if spec is None:
        made = radio(id, type, enabled, **settings)
    else:
        made = replace(spec, type=type or spec.type, enabled=spec.enabled if enabled is None else enabled, settings={**spec.settings, **{key: stored_text(value) for key, value in settings.items()}})
    return replace(config, radios=tuple(sorted((*(s for s in config.radios if s.id != id), made), key=lambda s: s.id)))


# The defaults: radio 1, an FM radio on, and radio 2, an HF radio off, each with every own setting
# its default (a new installation's database has none: Config.from_data(rows, radios=()))
TWO_RADIOS: Config = DEFAULTS


def _spec(config: Config, id: RadioId) -> tuple[RadioSpec, Config]:
    """The radio of the id and the settings with it (made of its kind's defaults where it is not
    there)."""
    config = config if config.radio(id) is not None else with_radio(config, id)
    spec = config.radio(id)
    assert spec is not None
    return spec, config


def fm_line(config: Config, port: str = "", pattern: str = "") -> TncSettings:
    """What radio 1's line is started with (tncdriver.line_settings), with the port and the pattern
    given for the run."""
    spec, config = _spec(config, FM_ID)
    return line_settings(spec, config, RunOverrides(port=port, pattern=pattern))


def hf_line(config: Config, port: str = "", modem_port: int = BROADCAST_PORT) -> ModemSettings:
    """What radio 2's line is started with (mercurydriver.modem_settings), with the Mercury given
    for the run and the broadcast port its modem chose."""
    spec, _ = _spec(config, HF_ID)
    return modem_settings(spec, RunOverrides(hf_port=port), modem_port)


def hf_said(config: Config, port: str) -> str:
    """Radio 2's words for the log (mercurydriver.modem_words), with the Mercury given for the run.
    """
    spec, _ = _spec(config, HF_ID)
    return modem_words(spec, RunOverrides(hf_port=port))
