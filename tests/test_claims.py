"""Tests for the resource table (neoaprs/claims.py): one holder per resource, refused second claims,
a serial device as one resource, releasing by kind or entirely, and one signal per change."""
from neoaprs.claims import Claim, Claims


def test_a_resource_has_one_holder_and_a_second_claim_is_refused_with_the_holders() -> None:
    claims = Claims()
    changes: list[int] = []
    claims.changed.connect(lambda: changes.append(len(claims.all())))
    port = Claim("serial", "/dev/ttyUSB0", 1)
    assert claims.hold(port) is None and claims.holder_of("serial", "/dev/ttyUSB0") == 1
    assert claims.hold(Claim("serial", "/dev/ttyUSB0", 3)) == port, "the other holder's claim"
    assert claims.hold(Claim("serial", "/dev/ttyUSB0", 1)) is None, "held already by the same radio: nothing to refuse"
    assert claims.hold(Claim("sound_card", "/dev/ttyUSB0", 3)) is None, "the same text of another kind is another resource"
    assert claims.hold(Claim("gps", "/dev/ttyACM0", None)) is None and claims.hold(Claim("gps", "/dev/ttyACM0", 2)) == Claim("gps", "/dev/ttyACM0", None), "the station holds the GPS receiver"
    assert changes == [1, 2, 3], "one signal for each claim that was taken, none for a refusal or a repeat"
    assert claims.all() == (port, Claim("sound_card", "/dev/ttyUSB0", 3), Claim("gps", "/dev/ttyACM0", None))


def test_what_the_others_hold_is_left_out_and_a_holder_lets_go_of_a_kind_or_everything() -> None:
    claims = Claims()
    for claim in (Claim("serial", "/dev/ttyUSB0", 1), Claim("serial", "/dev/ttyUSB1", 2), Claim("sound_card", "plughw:1,0", 2), Claim("keying", "/dev/ttyUSB1", 2), Claim("modem_ports", "8100", 2), Claim("gps", "/dev/ttyACM0", None)):
        claims.hold(claim)
    assert claims.held_by_others(1, "serial") == {"/dev/ttyUSB1", "/dev/ttyACM0"} and claims.held_by_others(3, "serial") == {"/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0"}, "the GPS receiver's port too"
    assert claims.held_by_others(None, "gps") == {"/dev/ttyUSB0", "/dev/ttyUSB1"} and claims.held_by_others(1, "gps") == {"/dev/ttyUSB1", "/dev/ttyACM0"}
    assert claims.held_by_others(1, "sound_card") == {"plughw:1,0"} and claims.held_by_others(1, "modem_ports") == {"8100"}
    changes: list[str] = []
    claims.changed.connect(lambda: changes.append("changed"))
    claims.release(2, "serial")
    assert claims.holder_of("serial", "/dev/ttyUSB1") == 2, "its keying line still holds the device"
    assert claims.holder_of("sound_card", "plughw:1,0") == 2
    claims.release(2)
    assert [c.holder for c in claims.all()] == [1, None]
    claims.release(5)
    claims.release(1, "keying")
    assert changes == ["changed", "changed"], "a release that lets go of nothing says nothing"
    assert claims.hold(Claim("serial", "/dev/ttyUSB1", 3)) is None, "free again"


def test_a_serial_device_is_one_resource_whether_it_is_a_radios_port_a_keying_line_or_the_gps_receiver() -> None:
    claims = Claims()
    gps = Claim("gps", "/dev/ttyACM0", None)
    assert claims.hold(gps) is None
    assert claims.hold(Claim("serial", "/dev/ttyACM0", 1)) == gps and claims.hold(Claim("keying", "/dev/ttyACM0", 2)) == gps, "the GPS receiver's port is no radio's"
    port = Claim("serial", "/dev/ttyUSB1", 1)
    assert claims.hold(port) is None
    assert claims.hold(Claim("keying", "/dev/ttyUSB1", 2)) == port and claims.hold(Claim("gps", "/dev/ttyUSB1", None)) == port, "a radio's port is no keying line of another's, nor the GPS receiver"
    assert claims.holder_of("keying", "/dev/ttyUSB1") == 1 and claims.holder_of("gps", "/dev/ttyACM0") is None
    assert claims.hold(Claim("keying", "/dev/ttyUSB1", 1)) is None and claims.all() == (gps, port, Claim("keying", "/dev/ttyUSB1", 1)), "one radio may use its device two ways"
    assert claims.hold(Claim("sound_card", "/dev/ttyUSB1", 2)) is None, "a sound card is not a serial device"
