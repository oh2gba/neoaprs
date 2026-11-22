"""The sound cards of the Mercury HF modem, as `mercury -z` lists them."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class SoundCard:
    id: str
    name: str
    playback: bool = False
    capture: bool = False
    default: bool = False
    numbered: str = ""


_DEVICE = re.compile(
    r"^device(?: #\d+)?: (?:name: '(?P<name>.*?)'\s+id: '(?P<id>.*?)'|(?P<name2>.*?)\s+id=(?P<id2>\S+))(?P<default>\s+\(system (?:default|route)\))?\s*$"
)


# Windows lists each card twice, as a recording ({0.0.1.) and a playing ({0.0.0.) device; opening
# one the wrong way fails. The two are one choice with the id "capture PAIR playback".
PAIR = "|"
WASAPI_PLAYBACK, WASAPI_CAPTURE = "{0.0.0.", "{0.0.1."
_ENDPOINT_NAME = re.compile(r"^(?P<kind>.+?) \((?P<card>.+)\)$")
_UNNUMBERED = re.compile(r"^\d+- ")


def endpoints(card: str) -> tuple[str, str]:
    """Return the (record, play) devices for a card setting; "" is the system default."""
    if PAIR in card:
        capture, _, playback = card.partition(PAIR)
        return capture, playback
    if card.startswith(WASAPI_CAPTURE):
        return card, ""
    if card.startswith(WASAPI_PLAYBACK):
        return "", card
    return card, card


def pair_directions(cards: Sequence[SoundCard]) -> list[SoundCard]:
    """Return the cards with the recording and playing device of one Windows card made one."""
    groups, named = _join_numbered(_by_card(cards))
    out: list[SoundCard] = []
    placed: set[int] = set()
    for c in cards:
        card = _card_of(c)
        group = groups.get(card, []) if card else []
        if not _whole(group):
            out.append(c)
        elif id(group) not in placed:
            placed.add(id(group))
            out += _pairs(group, named[card])
    return out


def _whole(group: Sequence[SoundCard]) -> bool:
    """Return whether the devices include a recording and a playing one."""
    return any(g.capture for g in group) and any(g.playback for g in group)


def _card_of(device: SoundCard) -> str:
    """Return the card of a one-direction Windows device ("Microphone (X)" gives "X"), else ""."""
    m = _ENDPOINT_NAME.match(device.name)
    return m.group("card") if m and device.playback != device.capture else ""


def _by_card(cards: Sequence[SoundCard]) -> dict[str, list[SoundCard]]:
    """Return the one-direction Windows devices by the card they belong to."""
    groups: dict[str, list[SoundCard]] = {}
    for c in cards:
        if card := _card_of(c):
            groups.setdefault(card, []).append(c)
    return groups


def unnumbered(card: str) -> str:
    """Return a card's name without the number Windows puts before a repeated name."""
    return _UNNUMBERED.sub("", card)


def _join_numbered(groups: dict[str, list[SoundCard]]) -> tuple[dict[str, list[SoundCard]], dict[str, str]]:
    """Return the groups, joining lone devices whose numbered names differ, and each pair's name."""
    lone = {card: group for card, group in groups.items() if not _whole(group)}
    by_name: dict[str, list[str]] = {}
    for card in lone:
        by_name.setdefault(unnumbered(card), []).append(card)
    joined, named = dict(groups), {card: card for card in groups}
    for name, cards_of in by_name.items():
        devices = [g for card in cards_of for g in lone[card]]
        if len(cards_of) > 1 and sum(g.capture for g in devices) == 1 and sum(g.playback for g in devices) == 1:
            for card in cards_of:
                joined[card], named[card] = devices, name
    return joined, named


def _pairs(group: Sequence[SoundCard], card: str) -> list[SoundCard]:
    """Return the pairs of one card's devices: one per recording and playing device."""
    captures, playbacks = [g for g in group if g.capture], [g for g in group if g.playback]
    alone = len(captures) == 1 and len(playbacks) == 1
    return [
        SoundCard(
            f"{rec.id}{PAIR}{play.id}",
            card if alone else f"{card} ({_kind(rec)}, {_kind(play)})",
            True,
            True,
            rec.default and play.default,
        )
        for rec in captures
        for play in playbacks
    ]


def _kind(card: SoundCard) -> str:
    m = _ENDPOINT_NAME.match(card.name)
    return m.group("kind") if m else card.name


def card_with(cards: Sequence[SoundCard], device: str) -> str:
    """Return the id of the listed pair containing `device`, or "" if none."""
    return next((c.id for c in cards if PAIR in c.id and device in c.id.split(PAIR)), "")


# ALSA card numbers change after a reboot or replug; the name (CARD=) is stable, so it is kept.
_ALSA_NUMBERED = re.compile(r"^(?P<plug>plughw|hw):(?P<card>\d+),(?P<dev>\d+)$")


def stable_alsa_id(ident: str, card_names: Mapping[int, str]) -> str:
    """Return `plughw:3,0` as `plughw:CARD=CODEC,DEV=0` if card 3's name is known."""
    m = _ALSA_NUMBERED.match(ident)
    name = card_names.get(int(m.group("card"))) if m else None
    return f"{m.group('plug')}:CARD={name},DEV={m.group('dev')}" if m and name else ident


def parse_sound_cards(text: str, card_names: Mapping[int, str] | None = None) -> list[SoundCard]:
    """Return the sound cards listed in `mercury -z` output; a card in both sections is one."""
    cards: dict[str, SoundCard] = {}
    section = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.endswith("devices:"):
            section = stripped.split()[0]
            continue
        m = _DEVICE.match(stripped)
        if m is None or not section:
            continue
        listed = m.group("id") or m.group("id2") or ""
        ident = stable_alsa_id(listed, card_names or {})
        name = (m.group("name") or m.group("name2") or ident).strip()
        before = cards.get(ident, SoundCard(ident, name))
        default = m.group("default") is not None or "(system route)" in name or "(system default)" in name
        cards[ident] = SoundCard(
            ident,
            before.name or name,
            before.playback or section == "playback",
            before.capture or section == "capture",
            before.default or default,
            listed if listed != ident else "",
        )
    return pair_directions(list(cards.values()))
