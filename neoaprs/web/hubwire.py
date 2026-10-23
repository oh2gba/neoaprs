"""The messages of the state hub (neoaprs/web/hub.py), as pydantic models: how a page follows the daemon's state.

  hello        the first message of a connection (neoaprs/web/hostwire.py); the page follows every topic from the start
  state        a topic as it is: its revision and its whole value (when the page opens, when it asks with `subscribe`, and when it was too slow to be sent patches)
  patch        what changed in a topic: ops `set key value`, `del key` and `replace value`, and the revision they lead to
  subscribe    (re)start following topics: each is answered with its `state`
  unsubscribe  stop following topics

They are in the unions of neoaprs/web/protocol.py (`Command`, `Message`), so PROTOCOL.md and the page's types come from them.

Revisions count up in each topic and start again at 0 when the daemon starts; a patch has the revision after it, and a page that sees a gap asks again with `subscribe`.
"""
from typing import Annotated, Any, Literal, Union

from pydantic import Field

from .wirebase import _Command, _Message, _Model

PROTOCOL = 1                          # the version of the messages: a page that does not know it reloads
MAX_TOPICS = 16                       # in one command
Revision = Annotated[int, Field(ge=0, le=2**53, description="how many changes the topic has had since the daemon started")]
TopicName = Annotated[str, Field(min_length=1, max_length=64)]
Key = Annotated[str, Field(max_length=256, description="the key of an item of a keyed topic: a station's call, a packet's id as text")]


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
    on a tick of 100 ms (the topic `tnc` at most four times a second): what changed between two ticks is one patch for a topic, with at most one op for each key."""
    type: Literal["patch"]
    topic: TopicName
    rev: Revision
    ops: list[PatchOp]
