"""The rules of a kind of radio, as a value the services read: what a frame may carry and what the beacon does depend on the radio, not on the service, and no service asks which radio it has. There is one
kind for the local FM radio (the KISS TNC of today) and one for the HF modem (Mercury); a third kind (a LoRa board) is one more value here, with its own rules, and nothing else.

Why each number is what it is:

- FM: the paths and the fill-in digipeater of the VHF network, SmartBeaconing for a moving station, the beacon from 20 minutes (the net cycle of a 2-hop path), AX.25's own frame limit.
- HF (Mercury): no path ever (every station on the mode hears every frame direct, there are no digipeaters, and a path costs bytes of a frame that carries 123); no digipeater (a repeat would only fill a channel
  every station already hears); no SmartBeaconing (a moving station sends its timed beacon with the current fix: on HF a report every few tens of seconds in a turn would take the channel for everyone); the one
  beacon interval of the station (`beacon/interval_min`) with a floor of 30 minutes while this radio is on (John's rule: not very often, a frame of 3.8 s on a shared channel); a random pause of up to BEACON_JITTER_SEC after each interval, because fixed stations have stable clocks
  and those that started their hour at the same moment would key up together on one channel every hour from then on (the start of the daemon is a random phase already; the pause keeps two stations on the same
  interval apart afterwards). The size was measured by `scripts/mercury-measure beacons` (docs/mercury.md): on the 30-minute interval with a frame of 3.8 s, stations that started within one minute of each other
  lose 14 percent of their beacons without the pause when there are two of them and 43 percent when there are five; with the pause of 300 s they lose 0.8 and 2.7 percent, within a point of what stations with random
  phases lose by chance (0.4 and 1.6 percent: the floor), while a pause of 120 s leaves them at 1.3 and 5.0 percent. A beacon lost by chance is made up by the next one; tests/test_mercury.py samples the pause.
  Frames up to the 123 bytes the mode carries."""
from dataclasses import dataclass

FM_BEACON_MIN_MIN = 20
HF_BEACON_MIN_MIN = 30                 # the floor of beacon/interval_min while the HF radio is on (the FM radio's alone: FM_BEACON_MIN_MIN)
HF_BEACON_JITTER_SEC = 300             # measured: the smallest pause that puts stations started together within a point of the random-phase floor (the docstring above; docs/mercury.md)
HF_MAX_FRAME = 123


@dataclass(frozen=True)
class RadioRules:
    kind: str                      # "fm" or "hf": the slot of the radio, which a station is remembered by
    paths: bool                    # whether a frame of ours carries digipeaters; False: every frame goes direct, whatever the settings say
    digipeat: bool                 # whether the fill-in digipeater may repeat what this radio hears
    smart_beacon: bool             # whether a moving station's SmartBeaconing (and the GPS) applies; False: the timed beacon of a fixed station only
    beacon_min_min: int            # the shortest beacon interval the radio takes (the one setting beacon/interval_min is raised to it while the radio is on)
    beacon_jitter_sec: int         # the longest random pause added to each timed beacon; 0: none
    max_frame: int | None          # the longest AX.25 frame the radio carries whole; None: AX.25's limit alone


FM = RadioRules("fm", True, True, True, FM_BEACON_MIN_MIN, 0, None)
HF = RadioRules("hf", False, False, False, HF_BEACON_MIN_MIN, HF_BEACON_JITTER_SEC, HF_MAX_FRAME)
