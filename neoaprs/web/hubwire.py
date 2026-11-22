"""Wire models of the state hub messages: `state`, `patch`, `subscribe` and `unsubscribe`.

Revisions count up per topic and restart at 0 with the daemon; a page that sees a gap subscribes again.
"""

from typing import Annotated, Any, Literal, Union

from pydantic import Field

from .wirebase import _Command, _Message, _Model

# Version of the messages; a page that does not know it reloads.
PROTOCOL = 1
# Topics in one command.
MAX_TOPICS = 16
Revision = Annotated[
    int, Field(ge=0, le=2**53, description="how many changes the topic has had since the daemon started")
]
TopicName = Annotated[str, Field(min_length=1, max_length=64)]
Key = Annotated[
    str,
    Field(max_length=256, description="the key of an item of a keyed topic: a station's call, a packet's id as text"),
]


# ---- the ops


class SetOp(_Model):
    """The item at `key` is `value` (the whole item, new or changed)."""

    op: Literal["set"]
    key: Key
    value: Any


class DelOp(_Model):
    """The item at `key` is gone."""

    op: Literal["del"]
    key: Key


class ReplaceOp(_Model):
    """The whole value of the topic is `value`."""

    op: Literal["replace"]
    value: Any


PatchOp = Annotated[Union[SetOp, DelOp, ReplaceOp], Field(discriminator="op")]


# ---- page to hub


class Subscribe(_Command):
    """Follow these topics (all are followed from the start): each is answered with `state`, then with `patch` as it changes. A topic that is followed already is sent whole again. A topic that is
    not there is refused with an `error` that names it; the others in the command are not affected."""

    cmd: Literal["subscribe"]
    topics: list[TopicName] = Field(max_length=MAX_TOPICS)


class Unsubscribe(_Command):
    """Stop following these topics. A topic that was not followed is ignored."""

    cmd: Literal["unsubscribe"]
    topics: list[TopicName] = Field(max_length=MAX_TOPICS)


# ---- hub to page


class StateMsg(_Message):
    """A topic as it is now: its revision and its whole `value`, which replaces what the page had. Patches for the changes made meanwhile follow."""

    type: Literal["state"]
    topic: TopicName
    rev: Revision
    value: Any


class PatchMsg(_Message):
    """What changed in a topic: apply the ops in order; the copy is then at `rev`. An op says what the item is, not what to add, so an op that is applied twice ends where it should. Changes are told
    on a tick of 100 ms (a radio's row in `radios` at most four times a second): what changed between two ticks is one patch for a topic, with at most one op for each key."""

    type: Literal["patch"]
    topic: TopicName
    rev: Revision
    ops: list[PatchOp]
