"""The HF radio's Allow button, the half of the modem part (mercurymodem.py, whose `Mercury` inherits this) that makes the Windows Firewall keep the network from Mercury when it does not: asked again for the
state of the Firewall, the rule made as an administrator (mercuryrule.py), asked again, and the owner told whether Mercury may be started (the controller starts the HF radio the usual way then). A class of its own
for its size alone: it reads and sets the modem's state and finds its program, which the modem part provides."""
import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

from . import mercuryfirewall, mercuryrule
from .mercuryhelper import Command, candidate_ports, is_shipped
from .signal import Signal

log = logging.getLogger("neoaprs.mercury")


class Allowing:
    allowing = False                                   # the rule is being made: the prompt of Windows may be open (the page's button waits)
    state: str
    reason: str
    changed: Signal[[]]
    _finder: Callable[[], Command | None]

    def _set(self, state: str, problem: str, reason: str = "", lets_in: str = "") -> None:
        raise NotImplementedError

    def _failed(self, problem: str, reason: str) -> None:
        raise NotImplementedError

    async def _shielded(self, program: Command) -> bool:
        """Whether a start may go on: the network is kept from `program` by the Windows Firewall (always, off Windows, and for a program that is not the one NeoAPRS ships). If not, the state says why and the start is left;
        a Firewall that could not be asked is tried again after the back-off, one that is off or lets Mercury in is not (the operator acts)."""
        if not is_shipped(program):
            return True
        shield = await asyncio.to_thread(mercuryfirewall.check, Path(program[0]), candidate_ports())
        if shield.reason == "not_started":
            self._failed(shield.problem, shield.reason)
        elif shield.problem:
            self._set("waiting", shield.problem, shield.reason, shield.lets_in)
        return not shield.problem

    async def allow_firewall(self) -> bool:
        """Makes the Firewall keep the network from Mercury, for the Allow button that the page shows while the modem waits for the Firewall; True when it does now, and the owner starts the HF radio again. A declined prompt
        or a run that cannot be made leaves the state as it was, with a line in the log."""
        program = self._finder()
        if self.allowing or self.state != "waiting" or self.reason != "firewall" or program is None or not is_shipped(program):
            log.info("Mercury firewall rule: not asked for in state %s (%s)", self.state, self.reason or "no reason")
            return False
        self.allowing = True
        self.changed.emit()
        try:
            return await self._allow(Path(program[0]))
        finally:
            self.allowing = False
            self.changed.emit()

    async def _allow(self, program: Path) -> bool:
        ports = candidate_ports()
        now = await asyncio.to_thread(mercuryfirewall.check, program, ports)
        if not now.problem:
            log.info("Mercury firewall rule: the network is kept from Mercury already")
            return True
        if now.reason != "firewall":
            self._set("waiting", now.problem, now.reason, now.lets_in)
            return False
        if await mercuryrule.make_rule(program, now.rule) == "not_run":
            return False
        after = await asyncio.to_thread(mercuryfirewall.check, program, ports)
        if after.problem:
            self._set("waiting", after.problem, after.reason, after.lets_in)
        return not after.problem
