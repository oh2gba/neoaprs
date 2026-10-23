"""What the desktop app keeps in the data folder when the folder is not what it should be (neoaprs/desktop/appstate.py): a size that cannot be written is not worth a crash, and the app's own log is a file of its own
with the level asked for. The size that is remembered and the default are in tests/test_desktop_logic.py."""
import logging
from pathlib import Path

import pytest

from neoaprs.desktop import appstate


def test_a_folder_that_cannot_be_written_does_not_stop_the_app_from_closing(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, "neoaprs.desktop")
    appstate.save_size(tmp_path / "gone" / "deeper", 1000, 700)       # (the folder is not there: the write is refused)
    assert not (tmp_path / "gone").exists()
    assert any("could not be saved" in r.getMessage() for r in caplog.records)


@pytest.fixture
def root_logger() -> object:
    """The root logger as it was: the handlers and the level the test adds are taken away."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield root
    for handler in list(root.handlers):
        if handler not in handlers:
            root.removeHandler(handler)
            handler.close()
    root.setLevel(level)


@pytest.mark.parametrize("debug, level", [(False, logging.INFO), (True, logging.DEBUG)])
def test_the_app_logs_to_a_file_of_its_own_at_the_level_asked_for(tmp_path: Path, root_logger: logging.Logger, debug: bool, level: int) -> None:
    appstate.setup_logging(tmp_path, debug)
    assert root_logger.level == level
    logging.getLogger("neoaprs.desktop").info("the window is open")
    logging.getLogger("neoaprs.desktop").debug("a detail")
    for handler in root_logger.handlers:
        handler.flush()
    text = (tmp_path / appstate.LOG_NAME).read_text(encoding="utf-8")
    assert "INFO  the window is open" in text and (("DEBUG  a detail" in text) == debug)
