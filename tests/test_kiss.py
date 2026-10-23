"""KISS framing (neoaprs/kiss.py): every rule of the decoder and the encoder on explicit byte strings."""
import pytest

from neoaprs.kiss import FEND, FESC, MAX_FRAME, TFEND, TFESC, KissDecoder, KissFrame, encode


def test_the_constants_are_those_of_the_kiss_protocol() -> None:
    assert (FEND, FESC, TFEND, TFESC) == (0xC0, 0xDB, 0xDC, 0xDD)


# ---- encode

def test_encode_wraps_the_payload_in_fends_with_the_command_byte_first() -> None:
    assert encode(b"abc") == b"\xc0\x00abc\xc0"


def test_encode_puts_the_port_in_the_high_nibble_and_the_command_in_the_low_one() -> None:
    assert encode(b"\x01", port=2, command=1) == b"\xc0\x21\x01\xc0"
    assert encode(b"", port=15, command=15) == b"\xc0\xff\xc0"


def test_encode_escapes_fend_and_fesc_in_the_payload() -> None:
    assert encode(b"a\xc0b\xdbc") == b"\xc0\x00a\xdb\xdcb\xdb\xddc\xc0"


def test_encode_escapes_a_command_byte_that_is_a_fend_or_a_fesc_too() -> None:
    # port 12 command 0 is 0xC0, port 13 command 11 is 0xDB: legal values that must not end or break the frame
    assert encode(b"x", port=12) == b"\xc0\xdb\xdcx\xc0"
    assert encode(b"x", port=13, command=11) == b"\xc0\xdb\xddx\xc0"


@pytest.mark.parametrize("port,command", [(-1, 0), (16, 0), (0, -1), (0, 16)])
def test_encode_refuses_a_port_or_command_that_does_not_fit_four_bits(port: int, command: int) -> None:
    with pytest.raises(ValueError):
        encode(b"x", port=port, command=command)


# ---- decode

def test_a_frame_in_one_piece() -> None:
    decoder = KissDecoder()
    assert decoder.feed(b"\xc0\x00abc\xc0") == [KissFrame(port=0, command=0, payload=b"abc")]
    assert decoder.dropped == 0


def test_the_command_byte_is_split_into_port_and_command() -> None:
    assert KissDecoder().feed(b"\xc0\x52xyz\xc0") == [KissFrame(port=5, command=2, payload=b"xyz")]


def test_the_escapes_are_undone() -> None:
    assert KissDecoder().feed(b"\xc0\x00a\xdb\xdcb\xdb\xddc\xc0")[0].payload == b"a\xc0b\xdbc"


def test_a_frame_that_arrives_in_pieces_is_kept_between_calls() -> None:
    decoder = KissDecoder()
    assert decoder.feed(b"\xc0\x00ab") == []
    assert decoder.feed(b"\xdb") == []
    assert decoder.feed(b"\xdcc") == []
    assert decoder.feed(b"\xc0") == [KissFrame(0, 0, b"ab\xc0c")]


def test_a_frame_split_byte_by_byte() -> None:
    decoder = KissDecoder()
    frames = [f for byte in b"\xc0\x00a\xdb\xddb\xc0" for f in decoder.feed(bytes([byte]))]
    assert frames == [KissFrame(0, 0, b"a\xdbb")]


def test_two_frames_in_one_call_and_one_fend_may_close_one_and_open_the_next() -> None:
    assert KissDecoder().feed(b"\xc0\x00one\xc0\x00two\xc0") == [KissFrame(0, 0, b"one"), KissFrame(0, 0, b"two")]


def test_empty_frames_are_ignored() -> None:
    decoder = KissDecoder()
    assert decoder.feed(b"\xc0\xc0\xc0\xc0\x00a\xc0\xc0\xc0") == [KissFrame(0, 0, b"a")]
    assert decoder.dropped == 0


def test_a_frame_with_only_a_command_byte_is_a_frame_with_an_empty_payload() -> None:
    assert KissDecoder().feed(b"\xc0\x00\xc0") == [KissFrame(0, 0, b"")]


def test_a_stream_that_starts_in_the_middle_of_a_frame_resynchronises_at_the_next_fend() -> None:
    decoder = KissDecoder()
    assert decoder.feed(b"tail of a frame\xc0\x00good\xc0") == [KissFrame(0, 0, b"good")]
    assert decoder.dropped == 0


def test_nothing_comes_out_before_the_first_fend() -> None:
    decoder = KissDecoder()
    assert decoder.feed(b"\x00no fend yet") == []
    assert decoder.feed(b"\xc0\x00ok\xc0") == [KissFrame(0, 0, b"ok")]


def test_an_escape_that_is_neither_tfend_nor_tfesc_drops_the_frame_and_counts_it() -> None:
    decoder = KissDecoder()
    assert decoder.feed(b"\xc0\x00ab\xdb\x41cd\xc0") == []
    assert decoder.dropped == 1
    assert decoder.feed(b"\xc0\x00next\xc0") == [KissFrame(0, 0, b"next")]
    assert decoder.dropped == 1


def test_a_bad_escape_costs_the_rest_of_its_frame_but_not_the_following_one() -> None:
    decoder = KissDecoder()
    assert decoder.feed(b"\xc0\x00a\xdb\x00zzz\xc0\x00b\xc0") == [KissFrame(0, 0, b"b")]
    assert decoder.dropped == 1


def test_an_escape_cut_off_by_the_closing_fend_drops_the_frame() -> None:
    decoder = KissDecoder()
    assert decoder.feed(b"\xc0\x00ab\xdb\xc0\x00ok\xc0") == [KissFrame(0, 0, b"ok")]
    assert decoder.dropped == 1


def test_an_escape_pair_split_between_two_calls_is_still_one_escape() -> None:
    decoder = KissDecoder()
    assert decoder.feed(b"\xc0\x00a\xdb") == []
    assert decoder.feed(b"\xddb\xc0") == [KissFrame(0, 0, b"a\xdbb")]
    assert decoder.dropped == 0


def test_a_frame_of_exactly_max_frame_bytes_passes_and_one_more_is_dropped() -> None:
    decoder = KissDecoder()
    exactly = b"\x00" + b"x" * (MAX_FRAME - 1)
    assert decoder.feed(b"\xc0" + exactly + b"\xc0") == [KissFrame(0, 0, b"x" * (MAX_FRAME - 1))]
    assert decoder.feed(b"\xc0" + exactly + b"x\xc0") == []
    assert decoder.dropped == 1


def test_a_long_frame_is_counted_once_however_long_it_goes_on_and_the_next_frame_is_fine() -> None:
    decoder = KissDecoder()
    assert decoder.feed(b"\xc0\x00" + b"y" * 5000) == []
    assert decoder.feed(b"y" * 5000 + b"\xc0\xc0\x00after\xc0") == [KissFrame(0, 0, b"after")]
    assert decoder.dropped == 1


def test_the_limit_counts_unescaped_bytes_and_can_be_set() -> None:
    decoder = KissDecoder(max_frame=4)
    assert decoder.feed(b"\xc0\x00\xdb\xdc\xdb\xdd\xdb\xdc\xc0") == [KissFrame(0, 0, b"\xc0\xdb\xc0")]
    assert decoder.feed(b"\xc0\x00abcd\xc0") == []
    assert decoder.dropped == 1


def test_the_default_limit_is_1024() -> None:
    assert MAX_FRAME == 1024
    assert KissDecoder().max_frame == 1024


def test_what_the_encoder_makes_the_decoder_reads_back() -> None:
    payload = bytes(range(256)) * 2
    assert KissDecoder().feed(encode(payload, port=3, command=1)) == [KissFrame(3, 1, payload)]
