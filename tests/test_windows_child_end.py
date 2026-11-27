"""Windows only: the real calls of neoaprs/winchild.py. A program started hidden, as Mercury is, takes
the Ctrl-C of a daemon without a console and ends by itself; a program in the daemon's job ends when
the job's last handle closes, as when the daemon dies.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from neoaprs import winchild

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="the calls are Windows' own")

ROOT = Path(__file__).resolve().parents[1]
WAIT_SEC = 120.0
DETACHED_PROCESS = 0x00000008


def test_a_hidden_program_is_asked_to_end_by_a_daemon_without_a_console(tmp_path: Path) -> None:
    out = tmp_path / "asked.json"
    subprocess.run(
        [sys.executable, "-m", "tests.support.winask", str(out)],
        cwd=ROOT,
        creationflags=DETACHED_PROCESS,
        timeout=WAIT_SEC,
        check=True,
    )
    told = json.loads(out.read_text())
    # every way is tried and written down whatever happens: the file says which call stopped it
    print(json.dumps(told, indent=1))
    ctrl_c = told["ctrl_c"]
    assert (ctrl_c["sent"], ctrl_c["code"], ctrl_c["child"]) == (True, 0, "SIGINT"), (
        f"the program ends by its own Ctrl-C handler, as Mercury does, not killed: {json.dumps(told)}"
    )


def test_a_program_in_the_daemons_job_ends_when_the_job_is_closed() -> None:
    k = winchild.kernel32()
    job = winchild.new_job(k)
    assert job is not None
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    try:
        process = k.OpenProcess(winchild.PROCESS_TERMINATE | winchild.PROCESS_SET_QUOTA, False, child.pid)
        assert process and k.AssignProcessToJobObject(job, process)
        k.CloseHandle(process)
        assert child.poll() is None
        k.CloseHandle(job)
        assert child.wait(WAIT_SEC) is not None, "the job's kill on close ended it"
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


def test_the_daemons_own_children_are_put_into_its_job() -> None:
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    try:
        assert winchild.tie_to_daemon(child.pid)
    finally:
        child.kill()
        child.wait()
