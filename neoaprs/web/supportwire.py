"""What the page tells the daemon about itself, for the support bundle: the command that reports an error of the page's own. A model like the rest of the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import Iso, _Command


class PageError(_Command):
    """An error that happened in the page itself (the browser's script, not a refusal of the daemon): the daemon writes it to its log as a warning, `page error (vue) on page BUILD: MESSAGE | FIRST LINE OF THE STACK`, and keeps the latest 100 for
    the support bundle. At most 20 of a connection are logged in a minute; the rest are counted in one line. No answer: a page that cannot report must not fail twice."""
    cmd: Literal["page_error"]
    message: str = Field(max_length=2000, description="what the error says")
    stack: str = Field(max_length=8000, description="where it happened, as the browser gives it; empty for none")
    source: Literal["vue", "window", "promise"] = Field(description="who caught it: `vue` (the component framework's error handler), `window` (an uncaught error of the window), `promise` (a promise nobody caught)")
    at: Iso = Field(description="when it happened, by the page's clock")
    build: str = Field(max_length=64, description="the build of the page that reported it (the `page` of `hello`)")
