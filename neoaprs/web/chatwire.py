"""Wire models of the chat of the HF tests tab: the topics `chat` and `chat_lines`, the command to say a
line and the message that tells of new lines, and the rows they are built from."""

from typing import Any, Literal

from pydantic import Field, field_validator

from neoaprs.chat import MAX_LINES, MAX_TEXT, Line, clean_text
from neoaprs.clock import iso

from .wirebase import Iso, _Command, _Message, _Model


class ChatState(_Model):
    """Where the chat stands. The value of the topic `chat`, told whole as it changes."""

    state: Literal["ok", "offline", "off", "closed"] = Field(
        description="`ok`: the chat was read (or has not been tried yet), and a line may be said. `offline`: the project's server could not be read; `chat_lines` are the last ones known. `off`: the check is off "
        "(`NEOAPRS_UPDATE_CHECK=0`): nothing is read or said, `chat_lines` is empty. `closed`: the chat takes no lines now (closed by the project, or for this call); the lines are still shown"
    )


class ChatLineRow(_Model):
    """A line of the chat, checked again by the daemon: one line of text of at most 200 characters, without control or invisible characters, never empty. The page shows it as text, never as markup."""

    id: int = Field(ge=1, description="the server's id of the line, which grows by one with each line said")
    at: Iso = Field(description="when the server took it, by the server's clock")
    call: str = Field(description="the call that said it, upper case without an SSID of 0 (`OH2GBA`, `OH2GBA-7`)")
    text: str = Field(min_length=1, max_length=MAX_TEXT, description="what was said")
    ours: bool = Field(description="this installation said it, or it is under our call: it never notifies")

    @classmethod
    def of(cls, line: Line, ours: bool) -> dict[str, Any]:
        return {"id": line.id, "at": iso(line.at), "call": line.call, "text": line.text, "ours": ours}


class ChatSay(_Command):
    """Says a line in the chat of the HF tests tab: the daemon posts it to the project's server with our call (the setting `station/call`, as the board has it) and this installation's token, over the Internet and never by radio. Cleaned as the server cleans it (white space
    becomes single spaces, control and invisible characters go, at most 200 characters). Answered by the topic `chat_lines`, which then has it with `ours` true. An `error` when no call is set (the interlock's reason; RX only does not matter), too many lines were said from here
    in the last minute (`chat.rate`), the chat takes no lines now (`chat.closed`; the topic `chat` then says `closed`), or the project's server could not be reached or would not take it (`chat.unreachable`)."""

    cmd: Literal["chat_say"]
    text: str = Field(max_length=MAX_TEXT * 4, description="the line; not empty once cleaned")

    @field_validator("text")
    @classmethod
    def _said(cls, text: str) -> str:
        if not clean_text(text):
            raise ValueError("an empty line")
        return text


class ChatFreshMsg(_Message):
    """Lines of others came into the chat that were not seen before (newer than the newest this installation had seen, a restart too): told to every page that is open, once for the lines of one reading, and only while `messages/chat_alert` is on. The page alerts as for a message to us (the sound, the notification, the browser tab, as its own choice says)."""

    type: Literal["chat_fresh"]
    count: int = Field(ge=1, le=MAX_LINES, description="how many lines came")
    id: int = Field(ge=1, description="the newest of them")
    call: str = Field(description="who said the newest")
    text: str = Field(max_length=MAX_TEXT, description="what the newest says")

    @classmethod
    def of(cls, lines: list[Line]) -> dict[str, Any]:
        last = lines[-1]
        return {"type": "chat_fresh", "count": len(lines), "id": last.id, "call": last.call, "text": last.text}
