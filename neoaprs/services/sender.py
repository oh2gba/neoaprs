"""Our frames that go out by a schedule of their own (the objects and the bulletins: services/ownobjects.py, services/ownbulletins.py) through one place: `ready` says whether one may go now, `send` makes the
frame and hands it to its radio.

Nothing goes while the call is not set (the interlock, `ready("object")`: the first refusal is told in the log, as the interlock does) and nothing on a radio that is not usable: not connected, silent, not yet
confirmed or settling after KISS ON, or (the HF modem) transmitting or hearing a busy channel. What is due then is not skipped and not made up: it waits, the log says once per outage `... due and the radio is silent`,
and it goes out when the radio is back. The radio is the radio of the frame (services/radioset.py: the radios by id, `RadioPick`, each an `AirRadio`): `ready(kind)` says whether some enabled radio takes a frame now,
`ready(kind, radio)` whether that one does, and `send` refuses a frame for a radio that does not (the owner tries again at its next tick), so that an object on two radios goes on the one that is up while the other
is away, and an object on the HF radio alone does not wait for the FM radio. Every frame names its radio (an object's and a bulletin's are those of its set); a frame for which none is named (a test's) is
built for the first radio that can send, in the order of the boxes, and while there is none nothing goes (NO_RADIO). Our own frames go
out one at a time on each radio: after one, `spacing_sec` pass before the next on that radio (plan rule 3.1: the pause between our scheduled frames is per radio), so that a restart with many objects due at once,
or a radio that comes back, never sends a burst, and a frame due on one radio does not wait for the pause of another. An object on several radios goes on each in the first tick that radio's pause allows (so it may go on one a few seconds after
the other); its round ends when every connected radio has taken it (services/ownobjects.py). An object or a bulletin
goes on its radios as the set is in force (`radios_for`): a station with one radio that sends sends every one on it, and one whose radios are all off while several others are on goes on none (ticked
nowhere), until a tick of it is changed or one of its radios is on again. The frame is the one fit function's
(`radioset.fit`): from `station/call` to the tocall by the path given, else the radio's own path, none where the radio carries none, its comment cut to what the radio carries; one that cannot be made (a path of
more than 8 digipeaters, an information field that is too long) is a SendError."""
import logging
from collections.abc import Iterable
from datetime import datetime

from neoaprs import ax25
from neoaprs.clock import Clock, utcnow
from neoaprs.interlock import Interlock
from neoaprs.radiospec import in_force_set
from neoaprs.radiotype import RadioId
from neoaprs.services.common import ConfigSource, Radio, as_pick
from neoaprs.services.pace import SPACING_SEC
from neoaprs.services.radioset import NO_RADIO, AirRadio, RadioPick, first_sender, fit
from neoaprs.services.radioset import SendError as SendError          # (services/radioset.py's, where the one fit function raises it; here under its old name)
from neoaprs.source import Source

log = logging.getLogger("neoaprs.sender")


class Sender:
    def __init__(self, radios: RadioPick | Radio, config: ConfigSource, clock: Clock = utcnow, spacing_sec: float = SPACING_SEC) -> None:
        self._radios = radios                                   # the radios as given: app.py's registry, or an old shape of a test's (tests/support/rig.py) read as a RadioPick (`radios`)
        self._config = config
        self._interlock = Interlock(config)
        self.clock = clock
        self.spacing_sec = spacing_sec
        self.problem = ""                                       # why the latest try did not send (the interlock's or the radio's reason); empty when it could
        self._last: dict[RadioId, datetime] = {}                # by radio: when the latest frame of ours went out on it
        self._told = False

    @property
    def radios(self) -> RadioPick:
        """The station's radios (services/common.as_pick: the registry as it is, an old shape read as one)."""
        return as_pick(self._radios, self._config)

    def too_soon(self, radio: AirRadio) -> bool:
        """Whether the pause after our latest frame on the radio is not over."""
        last = self._last.get(radio.id)
        return last is not None and (self.clock() - last).total_seconds() < self.spacing_sec

    def ready(self, kind: str, radio: AirRadio | None = None) -> bool:
        """May a frame of this kind (a word for the log: "object", "bulletin") go out now, on `radio`, or, when none is named, on some enabled radio (the one a frame goes to is asked again by `send`)?
        Not while the pause after our latest frame is running on every radio asked about."""
        radios = [radio] if radio is not None else list(self.radios.senders())
        if radios and all(self.too_soon(r) for r in radios):
            return False
        if refusal := self._interlock.refused(kind):
            self.problem = refusal
            return False
        if not any(r.usable for r in radios):
            away = radios[0] if radios else None
            self.problem = away.why_unusable() if away is not None else NO_RADIO
            if not self._told and (away is None or away.state is not Source.State.CONNECTED):        # (a connected radio that is not usable is settling after KISS ON, or the modem is held: the frame waits for it, saying nothing)
                self._told = True
                log.warning("the %s is due and %s: it goes out when the radio is back", kind, self.problem)
            return False
        self._told = False
        self.problem = ""
        return True

    def radios_for(self, ids: Iterable[RadioId]) -> list[AirRadio]:
        """The radios of these ids (an object's or a bulletin's `radios`) as the set is in force (radiospec.in_force_set, as the beacon's: those that are enabled and can send, by position; one radio that
        can send: everything goes on it, whatever was chosen; none when none of them is, or none can send). An old shape of a test's, whose radios the settings do not name, is its one radio."""
        config = self._config()
        on = {radio.id: radio for radio in self.radios.senders()}
        found = [on[i] for i in in_force_set(ids, config.radios) if i in on]
        if not found and len(on) == 1 and not any(spec.id in on for spec in config.radios):
            return list(on.values())
        return found

    def frame(self, info: bytes, path: tuple[str, ...] | None, radio: AirRadio | None = None) -> ax25.Frame:
        """Our frame with this information field by this path (None: the radio's own path) for `radio` (when none is named, the first radio that can send), its comment cut to what the radio carries (said in
        the log). Raises SendError, also while there is no radio."""
        target = radio if radio is not None else first_sender(self.radios)
        if target is None:
            raise SendError(NO_RADIO)
        return fit(target, self._config(), info, path)

    def send(self, info: bytes, path: tuple[str, ...] | None, radio: AirRadio | None = None) -> bool:
        """Sends the frame on `radio` (when none is named, the first radio that can send); False when there is none, or it is not usable now (`problem` says why), its pause after our latest frame on it is
        running, or it would not take the frame (it is settling, or the write failed): it is tried again at the next tick. Raises SendError."""
        target = radio if radio is not None else first_sender(self.radios)
        if target is None or not target.usable:
            self.problem = NO_RADIO if target is None else target.why_unusable()
            return False
        if self.too_soon(target):
            return False
        frame = self.frame(info, path, target)
        if not target.send_frame(frame):
            self.problem = "the TNC did not take the frame (it is restarting into KISS mode, or the write failed)"
            return False
        self._last[target.id] = self.clock()
        return True
