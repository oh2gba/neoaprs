"""The list of heard packets a LoRa board's web page answers (neoaprs/loralist.py `parse`), on its own: what is wrong of an answer is told in words that hold no control character of the board's."""
import pytest

from neoaprs.loralist import ListError, parse


def test_a_status_line_with_control_characters_is_told_without_them() -> None:
    with pytest.raises(ListError) as refused:
        parse(b"HTTP/1.1 500 \x1b[31mBroken\x07\x00\r\n\r\n")
    assert str(refused.value) == "the answer is 500 ?[31mBroken??"


def test_an_answer_that_is_not_http_is_told_so() -> None:
    with pytest.raises(ListError, match="the answer is not HTTP"):
        parse(b"\r\n\r\n")
