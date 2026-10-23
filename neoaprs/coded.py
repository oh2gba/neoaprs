"""A refusal with a code: the English sentence for a log and for a page that has no sentence of its own for the code, and the stable `code` and `params` that a page (or a translation) goes by."""

type Param = str | int | float


class CodedError(ValueError):
    """A ValueError that says what it is as well as why. `code` is a stable dotted word (`setting.range`, `call.ssid`, `other` for a refusal that has none yet); `params` are the values the sentence
    is made of, by name, so that a sentence in another language can be made of them."""

    def __init__(self, text: str, code: str = "other", **params: Param) -> None:
        super().__init__(text)
        self.code = code
        self.params: dict[str, Param] = params
