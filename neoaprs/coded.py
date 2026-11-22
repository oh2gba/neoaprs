"""Refusals that carry a stable code.

The English sentence is for the log; the page translates by `code` and `params`. `Reason` is a
string that carries a code before it becomes a refusal.
"""

from typing import Self

type Param = str | int | float


class Reason(str):
    """An English clause for the log with a stable `code` and `params`; equal to its text.

    Example: `Reason("the radio is silent", "radio.silent")`."""

    code: str
    params: dict[str, Param]

    def __new__(cls, text: str, code: str = "other", **params: Param) -> Self:
        made = super().__new__(cls, text)
        made.code, made.params = code, params
        return made

    @classmethod
    def of(cls, why: object, text: str | None = None, **more: Param) -> "Reason":
        """Return a reason with the code and params of `why` plus `more`; `text` overrides."""
        code, params = code_of(why)
        return cls(str(why) if text is None else text, code, **{**params, **more})

    def but(self, **params: Param) -> "Reason":
        """Return the same reason with more params."""
        return Reason(str(self), self.code, **{**self.params, **params})


def code_of(why: object) -> tuple[str, dict[str, Param]]:
    """Return the code and params of a Reason or CodedError; `other` and none for anything else."""
    code, params = getattr(why, "code", "other"), getattr(why, "params", None)
    return (code, dict(params) if isinstance(params, dict) else {}) if isinstance(code, str) else ("other", {})


class CodedError(ValueError):
    """A ValueError with a stable dotted `code` (`setting.range`, `call.ssid`, or `other`).

    `params` are the named values of the sentence, so that another language can rebuild it.
    """

    def __init__(self, text: str, code: str = "other", **params: Param) -> None:
        super().__init__(text)
        self.code = code
        self.params: dict[str, Param] = params

    @classmethod
    def of(cls, why: object, text: str | None = None, **more: Param) -> Self:
        """Return an error with the code and params of `why` plus `more`; `text` overrides."""
        code, params = code_of(why)
        return cls(str(why) if text is None else text, code, **{**params, **more})
