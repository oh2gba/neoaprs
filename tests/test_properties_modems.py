"""Properties of the readers of what a modem program or a rig server says: Mercury's control lines, its log
lines and the keying setting, Direwolf's lines, rigctld's answers and a TCP port setting. What is written
reads back; any line, real ones damaged above all, never raises; a number read is finite and in its range.
"""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from neoaprs import direwolf, mercury, rigctld
from neoaprs.coded import CodedError
from neoaprs.tncprofile import tcp_host, tcp_url
from tests.support.mutation import mutated_bytes, mutated_text

CONTROL_LINES = ["PTT ON", "PTT OFF", "BUSY ON", "BUSY OFF", "SN -2.5", "SN 12", "BUFFER 4096", "IAMALIVE"]
MERCURY_LINES = [
    "2026-11-28 05:47:54.123 [+0.066s] [ERR] [serial-ptt] Cannot open COM10 (Windows error 5)",
    "22:16:22.912 [+0.003s] [ERR] [audio-play] error in audio->open(): 1: snd_pcm_hw_params_set_access: (-22) Invalid argument",
    "2026-11-13 22:16:22.912 [+0.003s] [ERR] [audio-cap] error in audio->open(): -1: No such device",
    "[ERR] [serial-ptt] Cannot open /dev/ttyUSB0: Device or resource busy",
    mercury.RADIO_INIT_FAILED,
    mercury.CAPTURE_FULL,
]
DIREWOLF_LINES = [
    "Ready to accept KISS TCP client application 0 on port 8002 (radio channel 0) ...",
    "Some other application is probably already using port 8002.",
    "OH2XYZ audio level = 48(12/9)   [NONE]   ___|||___",
    "Digipeater WIDE2 (probably N3LEE-4) audio level = 28(10/6)   [NONE]   __|||||||",
    "RXLEVEL 0 = 57",
    "PTT 0 = 1",
    "DCD 0 = 0",
    "Available audio input devices for receive (*=selected):",
    " *  1: Microphone (USB Audio CODEC)   (channel 0)",
    "    0: Microphone (Realtek(R) Audio)",
    "Audio input level is too high.  Reduce so most stations are around 50.",
]
_LINES = st.one_of(
    st.text(max_size=80), st.sampled_from(CONTROL_LINES + MERCURY_LINES + DIREWOLF_LINES).flatmap(mutated_text)
)


@given(st.sampled_from(["PTT", "BUSY"]), st.booleans(), st.floats(allow_nan=False, allow_infinity=False))
def test_a_control_line_reads_back(kind: str, on: bool, snr: float) -> None:
    """PTT and BUSY lines give their state, SN and BUFFER lines their number."""
    assert mercury.parse_control_line(f"{kind} {'ON' if on else 'OFF'}") == mercury.ControlEvent(
        kind.lower(), on=on, text=f"{kind} {'ON' if on else 'OFF'}"
    )
    assert mercury.parse_control_line(f"SN {snr!r}").value == snr


@given(_LINES)
def test_any_control_line_is_an_event_with_a_finite_number(line: str) -> None:
    """Any line gives an event of a known kind whose number, when it has one, is finite."""
    event = mercury.parse_control_line(line)
    assert event.kind in ("ptt", "busy", "snr", "alive", "buffer", "other")
    assert event.value is None or math.isfinite(event.value)


@pytest.mark.parametrize("line", ["SN nan", "SN inf", "BUFFER -inf", "SN NaN"])
def test_a_number_that_is_not_finite_is_another_line(line: str) -> None:
    """A control line whose number is NaN or infinite is no reading."""
    assert mercury.parse_control_line(line).kind == "other"


@given(st.lists(st.one_of(st.sampled_from(CONTROL_LINES), st.text(max_size=20)), max_size=6), st.integers(0, 100))
def test_the_control_stream_gives_back_its_lines_however_it_is_cut(lines: list[str], cut: int) -> None:
    """Lines read in two pieces are the lines written, stripped, without the empty ones; a partial line stays."""
    data = "\r\n".join(lines).encode("ascii", "replace") + b"\r"
    buffer, found = bytearray(), []
    for piece in (data[:cut], data[cut:]):
        buffer.extend(piece)
        found += mercury.split_control_lines(buffer)
    expected = [
        part.strip()
        for part in data.decode("ascii").replace("\r\n", "\r").replace("\n", "\r").split("\r")
        if part.strip()
    ]
    assert found == expected and not buffer


@given(st.one_of(st.binary(max_size=80), mutated_bytes(b"PTT ON\r\nSN -2.5\r\nIAMALIVE\r\n")))
def test_any_bytes_of_the_control_port_never_raise(data: bytes) -> None:
    """Any bytes give lines without a line end, and what is left holds none."""
    buffer = bytearray(data)
    for line in mercury.split_control_lines(buffer):
        assert "\r" not in line and "\n" not in line and line
    assert b"\r" not in buffer and b"\n" not in buffer


@given(_LINES)
def test_any_mercury_log_line_never_raises(line: str) -> None:
    """Any log line, a real one damaged above all, gives a known keying failure, or none."""
    assert mercury.keying_failure(line) in ("", "keying", "keying_in_use", "keying_missing")
    mercury.audio_open_error(line)
    mercury.capture_full(line)
    assert len(mercury.unstamped(line)) <= len(line)


def test_a_windows_error_number_of_thousands_of_digits_is_a_failure_of_the_keying() -> None:
    """An error number too long for int() is no ValueError."""
    assert mercury.keying_failure(f"[ERR] [serial-ptt] Cannot open COM1 (Windows error {'9' * 5000})") in ("", "keying")


@given(st.text(max_size=40))
def test_the_stamp_comes_off_and_the_rest_stays(rest: str) -> None:
    """unstamped of a stamped line gives the line as Mercury wrote it after the stamp."""
    assert mercury.unstamped(f"2026-11-24 16:44:47.187 [+1034.694s] {rest}") == rest


_DEVICE = st.text(alphabet=st.characters(min_codepoint=33, max_codepoint=0x2FF), min_size=1, max_size=40).filter(
    str.isprintable
)


@given(st.sampled_from(mercury.PTT_KINDS), _DEVICE)
def test_a_keying_reads_back(kind: str, device: str) -> None:
    """keying_of of a keying's text gives the keying."""
    keying = mercury.Keying(kind, device if kind in mercury.PTT_WITH_DEVICE else "")
    assert mercury.keying_of(keying.text) == keying


@given(
    st.one_of(
        st.text(max_size=40), st.sampled_from(["vox", "cm108", "rts:/dev/ttyUSB0", "dtr:COM3"]).flatmap(mutated_text)
    )
)
def test_any_keying_setting_is_a_keying_or_a_coded_error(text: str) -> None:
    """Any text gives a keying of one word or the CodedError setting.not_keying."""
    try:
        keying = mercury.keying_of(text)
    except CodedError as e:
        assert e.code == "setting.not_keying"
        return
    assert keying.kind in mercury.PTT_KINDS and not any(c.isspace() for c in keying.device)


@given(_LINES)
def test_any_direwolf_line_never_raises_and_its_numbers_are_in_range(line: str) -> None:
    """Any line, a real one damaged above all, gives a port of 0 to 65535, levels of 0 or more, or nothing."""
    port = direwolf.ready_port(line)
    assert port is None or 0 <= port <= 65535
    for level in (direwolf.level_of(line), direwolf.level_now_of(line)):
        assert level is None or level >= 0
    for check in (
        direwolf.kiss_from_client,
        direwolf.kiss_dump,
        direwolf.bind_failed,
        direwolf.audio_open_error,
        direwolf.keying_open_error,
        direwolf.wrong_device,
        direwolf.several_cm108,
        direwolf.ptt_of,
        direwolf.dcd_of,
        direwolf.is_error,
    ):
        check(line)


@given(st.lists(_LINES, max_size=8))
def test_any_device_list_never_raises(lines: list[str]) -> None:
    """Lines fed to the WinMM device lists keep a number for each starred device."""
    lists = direwolf.DeviceLists()
    for line in [DIREWOLF_LINES[7], *lines]:
        lists.feed(line)
    lists.wrong((0, 1))


@pytest.mark.parametrize(
    "line",
    [
        "Ready to accept KISS TCP client application 0 on port " + "9" * 5000,
        "Ready to accept KISS TCP client application 0 on port 99999 ...",
        "RXLEVEL 0 = " + "9" * 5000,
        "OH2XYZ audio level = " + "9" * 5000 + "(12/9)",
    ],
)
def test_a_number_beyond_its_range_in_a_direwolf_line_is_no_number(line: str) -> None:
    """A port above 65535 or a number too long for int() is none, not a ValueError."""
    assert direwolf.ready_port(line) is None
    assert direwolf.level_of(line) is None
    assert direwolf.level_now_of(line) is None


def test_a_device_of_thousands_of_digits_is_passed_over() -> None:
    lists = direwolf.DeviceLists()
    lists.feed(DIREWOLF_LINES[7])
    lists.feed(f" *  {'1' * 5000}: Microphone")
    assert lists.selected is None


@given(st.integers(1, 10**12))
def test_a_frequency_of_rigctld_reads_back(hz: int) -> None:
    """A frequency in hertz as rigctld writes it gives the same number."""
    assert rigctld._hz(rigctld._line(f"{hz}\n".encode())) == hz


@given(st.one_of(st.binary(max_size=40), mutated_bytes(b"7054100\n"), mutated_bytes(b"RPRT -11\n")))
def test_any_answer_of_rigctld_is_a_frequency_above_0_or_a_rig_error(raw: bytes) -> None:
    """Any bytes give a frequency above 0 Hz, or a RigError."""
    try:
        assert rigctld._hz(rigctld._line(raw)) > 0
    except rigctld.RigError:
        pass


@pytest.mark.parametrize("line", ["inf", "1e400", "-inf", "nan"])
def test_a_frequency_that_is_not_finite_is_a_rig_error(line: str) -> None:
    """rigctld's infinite or NaN frequency is a RigError, not an OverflowError."""
    with pytest.raises(rigctld.RigError):
        rigctld._hz(line)


_HOST = st.one_of(
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789.-", min_size=1, max_size=30),
    st.lists(st.text(alphabet="0123456789abcdef", max_size=4), min_size=3, max_size=8).map(":".join),
)


@given(_HOST, st.integers(1, 65535))
def test_a_tcp_port_setting_gives_back_its_host(host: str, port: int) -> None:
    """tcp_host of tcp_url is the host, an IPv6 address without its brackets."""
    assert tcp_host(tcp_url(host, port)) == host
