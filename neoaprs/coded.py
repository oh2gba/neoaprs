"""A refusal with a code: the English sentence for a log and for the daemon's own words, and the stable `code` and `params` that a page (or a translation) goes by. `Reason` is the same for a why that is
passed on as a value before it becomes a refusal (why a radio takes no frame now, why nothing may be transmitted): a string, so that a log line keeps it as it was, that carries its code."""
from typing import Self

type Param = str | int | float


class Reason(str):
    """Why something is not done, as an English clause for the log, with the stable `code` and the `params` a page says it by (`Reason("the radio is silent", "radio.silent")`). It is equal to its text,
    so a comparison or a log line goes on as with a plain string; a refusal made of it (`CodedError.of`) carries the code. scripts/errorcodes.py finds its codes as it finds a refusal's."""
    code: str
    params: dict[str, Param]

    def __new__(cls, text: str, code: str = "other", **params: Param) -> Self:
        made = super().__new__(cls, text)
        made.code, made.params = code, params
        return made

    @classmethod
    def of(cls, why: object, text: str | None = None, **more: Param) -> "Reason":
        """The reason of a refusal or of another reason: its code and its values (with `more`), and its English, or `text` (a longer sentence for the log)."""
        code, params = code_of(why)
        return cls(str(why) if text is None else text, code, **{**params, **more})

    def but(self, **params: Param) -> "Reason":
        """The same reason with more values (the radio it is of): a refusal that says the radio passes it on."""
        return Reason(str(self), self.code, **{**self.params, **params})


def code_of(why: object) -> tuple[str, dict[str, Param]]:
    """The code and the values of a reason or a refusal (a Reason, a CodedError); `other` and none for anything else, a plain sentence."""
    code, params = getattr(why, "code", "other"), getattr(why, "params", None)
    return (code, dict(params) if isinstance(params, dict) else {}) if isinstance(code, str) else ("other", {})


class CodedError(ValueError):
    """A ValueError that says what it is as well as why. `code` is a stable dotted word (`setting.range`, `call.ssid`, `other` for a refusal that has none yet); `params` are the values the sentence
    is made of, by name, so that a sentence in another language can be made of them."""

    def __init__(self, text: str, code: str = "other", **params: Param) -> None:
        super().__init__(text)
        self.code = code
        self.params: dict[str, Param] = params

    @classmethod
    def of(cls, why: object, text: str | None = None, **more: Param) -> Self:
        """A refusal of this class made of a reason or of another refusal: its code and its values (with `more`), and its English, or `text` (a longer sentence for the log)."""
        code, params = code_of(why)
        return cls(str(why) if text is None else text, code, **{**params, **more})
