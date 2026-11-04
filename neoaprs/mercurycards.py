"""The sound cards of the Mercury HF modem: what `mercury -z` lists, read into cards, with the two devices of a Windows card made one (its recording and its playing device, each with an id of its own),
and the devices a card setting gives Mercury to record from and to play to."""
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class SoundCard:
    """A sound card as `mercury -z` lists it: the id to give Mercury and the name the system gives it."""
    id: str
    name: str
    playback: bool = False
    capture: bool = False
    default: bool = False
    numbered: str = ""                    # the id by the card's number (`plughw:3,0`), where `id` is by its name: a setting made before names it so


_DEVICE = re.compile(r"^device(?: #\d+)?: (?:name: '(?P<name>.*?)'\s+id: '(?P<id>.*?)'|(?P<name2>.*?)\s+id=(?P<id2>\S+))(?P<default>\s+\(system (?:default|route)\))?\s*$")


# Windows lists every sound card twice, as a device that records ("Microphone (USB Audio CODEC)", an id that begins {0.0.1.) and one that plays ("Speakers (USB Audio CODEC)", {0.0.0.), each with its own id, and a
# device opened the wrong way fails (AUDCLNT_E_WRONG_ENDPOINT_TYPE: OH2GAX's IC-7300, 3 Nov 2026, whichever of the two he chose). The two of one card are one choice here, named after the card, with an id that holds
# both (capture, PAIR, playback): Mercury records from the one and plays to the other. A device alone of its kind is given for its own direction only, the system's default device doing the other.
PAIR = "|"
WASAPI_PLAYBACK, WASAPI_CAPTURE = "{0.0.0.", "{0.0.1."
_ENDPOINT_NAME = re.compile(r"^(?P<kind>.+?) \((?P<card>.+)\)$")
_UNNUMBERED = re.compile(r"^\d+- ")              # the number Windows puts before a device name it has seen before ("2- USB Audio CODEC")


def endpoints(card: str) -> tuple[str, str]:
    """The device Mercury records from and the one it plays to for a sound card setting, "" for the system's default device: both halves of a pair, the one direction of a Windows device of one direction, and
    the same card both ways everywhere else (ALSA's plughw:1,0 records and plays)."""
    if PAIR in card:
        capture, _, playback = card.partition(PAIR)
        return capture, playback
    if card.startswith(WASAPI_CAPTURE):
        return card, ""
    if card.startswith(WASAPI_PLAYBACK):
        return "", card
    return card, card


def pair_directions(cards: Sequence[SoundCard]) -> list[SoundCard]:
    """The cards with the recording and the playing device of one card made one (Windows: see PAIR), in the place of the first of them; a card with a recording and a playing device each is named after the card,
    one with several has one pair for each, named with the devices' own names. Windows numbers a device whose name another of its kind had before ("Speakers (2- USB Audio CODEC)"), each kind on its own, so the two
    devices of one radio may carry different numbers: a recording and a playing device that are left with no partner are one card when they are the only two of that name without the number. Cards that record
    and play already, and devices with no partner, are as they were."""
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
    """Whether the devices are a recording and a playing one at least."""
    return any(g.capture for g in group) and any(g.playback for g in group)


def _card_of(device: SoundCard) -> str:
    """The card a Windows device of one direction belongs to ("USB Audio CODEC" of "Microphone (USB Audio CODEC)"); "" for anything else."""
    m = _ENDPOINT_NAME.match(device.name)
    return m.group("card") if m and device.playback != device.capture else ""


def _by_card(cards: Sequence[SoundCard]) -> dict[str, list[SoundCard]]:
    """The Windows devices of one direction, by the card they belong to."""
    groups: dict[str, list[SoundCard]] = {}
    for c in cards:
        if card := _card_of(c):
            groups.setdefault(card, []).append(c)
    return groups


def _join_numbered(groups: dict[str, list[SoundCard]]) -> tuple[dict[str, list[SoundCard]], dict[str, str]]:
    """The groups with the lone devices of one name without its number joined, where they are one recording and one playing device ("Speakers (2- USB Audio CODEC)" and "Microphone (USB Audio CODEC)"), and the name
    each group's pair is given: the card's, or for the joined ones the name without the number."""
    lone = {card: group for card, group in groups.items() if not _whole(group)}
    unnumbered: dict[str, list[str]] = {}
    for card in lone:
        unnumbered.setdefault(_UNNUMBERED.sub("", card), []).append(card)
    joined, named = dict(groups), {card: card for card in groups}
    for name, cards_of in unnumbered.items():
        devices = [g for card in cards_of for g in lone[card]]
        if len(cards_of) > 1 and sum(g.capture for g in devices) == 1 and sum(g.playback for g in devices) == 1:
            for card in cards_of:
                joined[card], named[card] = devices, name
    return joined, named


def _pairs(group: Sequence[SoundCard], card: str) -> list[SoundCard]:
    """The pairs of one card's devices: one named after the card for one of each, else one for each way, named with the devices' own names."""
    captures, playbacks = [g for g in group if g.capture], [g for g in group if g.playback]
    alone = len(captures) == 1 and len(playbacks) == 1
    return [SoundCard(f"{rec.id}{PAIR}{play.id}", card if alone else f"{card} ({_kind(rec)}, {_kind(play)})", True, True, rec.default and play.default) for rec in captures for play in playbacks]


def _kind(card: SoundCard) -> str:
    m = _ENDPOINT_NAME.match(card.name)
    return m.group("kind") if m else card.name


def card_with(cards: Sequence[SoundCard], device: str) -> str:
    """The id of the listed card one of whose two devices is `device` (a setting made before the two were one, which names only one of them), "" when none is."""
    return next((c.id for c in cards if PAIR in c.id and device in c.id.split(PAIR)), "")


# Linux numbers its sound cards in the order they are found, so `plughw:0,0` is another card after a reboot or a replug (John's station, 4 Nov 2026: the FTdx101D's codec, card 0 on 2 Nov, was card 3,
# and the setting gave Mercury the FTX-1's). ALSA also knows each card by a name of its own (/proc/asound/cardN/id: CODEC, Device), which a device string takes as CARD=: that is the id kept.
_ALSA_NUMBERED = re.compile(r"^(?P<plug>plughw|hw):(?P<card>\d+),(?P<dev>\d+)$")


def stable_alsa_id(ident: str, card_names: Mapping[int, str]) -> str:
    """`plughw:3,0` as `plughw:CARD=CODEC,DEV=0` when the name of card 3 is known; anything else as it is."""
    m = _ALSA_NUMBERED.match(ident)
    name = card_names.get(int(m.group("card"))) if m else None
    return f"{m.group('plug')}:CARD={name},DEV={m.group('dev')}" if m and name else ident


def parse_sound_cards(text: str, card_names: Mapping[int, str] | None = None) -> list[SoundCard]:
    """The sound cards of `mercury -z` (Mercury 1.9.21: "playback devices:" and "capture devices:" each followed by `device: name: 'USB Audio CODEC'  id: 'plughw:1,0'  (system default)` lines, or `device #1: Default (system route)
    id=default` where the backend lists none). A card that is in both lists is one card, which is what a radio's sound card is."""
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
        cards[ident] = SoundCard(ident, before.name or name, before.playback or section == "playback", before.capture or section == "capture", before.default or default, listed if listed != ident else "")
    return pair_directions(list(cards.values()))
