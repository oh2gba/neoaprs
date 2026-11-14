"""The usage report of the project's server (server/usage-report.sh) on made-up logs, with `--local` so that nothing is fetched: the requests with id 0 (a run from the source tree, a test machine) are left out of every count and said in a line
of their own; the ignore list (a plain file of ids, comments after #, blank lines, from `--ignore FILE` or `usage-ignore` beside the secrets file) leaves out its numbers for every month and says how many requests and numbers; the old lines
without an id (`-` or no fourth column) are still the requests without an id; what the present version.php writes for an id of 0 (`-`) is one of those, and what the one with the fix writes (`0`) is a developers' run."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.support.ptyline import posix_only

pytestmark = posix_only

ROOT = Path(__file__).resolve().parent.parent
A, B, C = "0123456789abcdef0123456789abcdef", "fedcba9876543210fedcba9876543210", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
OCTOBER = [f"2026-10-01T10:00Z\t0.19.0\tlinux\t{A}", f"2026-10-02T10:00Z\t0.19.0\tlinux\t{B}", "2026-10-02T11:00Z\t0.19.0\twindows\t0", "2026-10-03T11:00Z\t0.19.0\twindows\t-", "2026-10-03T12:00Z\t0.18.0\twindows"]
NOVEMBER = [f"2026-11-01T10:00Z\t0.20.0\tlinux\t{A}", f"2026-11-02T10:00Z\t0.20.0\tlinux\t{C}", "2026-11-02T11:00Z\t0.20.0\twindows\t0", f"2026-11-03T11:00Z\t0.20.0\tlinux\t{C}"]


@pytest.fixture
def server(tmp_path: Path) -> Path:
    """A copy of the script in a `server/` folder of its own, with logs of two months."""
    folder = tmp_path / "work" / "server"
    (folder / "logs").mkdir(parents=True)
    shutil.copy(ROOT / "server" / "usage-report.sh", folder / "usage-report.sh")
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / ".secrets").write_text("# a stand-in: --local reads nothing from it\n", encoding="utf-8")
    (folder / "logs" / "starts-2026-10.log").write_text("\n".join(OCTOBER) + "\n", encoding="utf-8")
    (folder / "logs" / "starts-2026-11.log").write_text("\n".join(NOVEMBER) + "\n", encoding="utf-8")
    return folder


def report(server: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {"PATH": os.environ["PATH"], "SECRETS_FILE": str(server.parent.parent / "secrets" / ".secrets")}
    return subprocess.run(["bash", str(server / "usage-report.sh"), "--local", *args], capture_output=True, text=True, env=env, timeout=60, check=False)


def months(out: list[str]) -> list[str]:
    """The rows of the installations per month."""
    start = out.index("Installations (distinct ids) per month:") + 1
    return out[start:out.index("", start)]


def lines(result: subprocess.CompletedProcess[str]) -> list[str]:
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


def test_id_0_is_neither_an_installation_nor_a_request_without_an_id_and_is_said_in_a_line_of_its_own(server: Path) -> None:
    out = lines(report(server))
    assert "7 starts in total" in out, "the nine requests less the two of id 0"
    assert months(out) == ["  2026-10  2", "  2026-11  2"]
    assert "2 of 7 requests came without an id (older versions)" in out, "the old lines, '-' and no fourth column"
    assert out[-2:] == ["2 requests came from developers' runs (id 0)", "(no ignore list at " + str(server.parent.parent / "secrets" / "usage-ignore") + ")"]
    assert "Installations in 2026-11, per platform:" in out and "  windows          0" not in out and not any(line.startswith("  windows") and "2026-11" in line for line in out)


def test_the_ignore_list_leaves_its_numbers_out_of_every_month_and_says_how_many(server: Path) -> None:
    ignore = server.parent / "ignore"
    ignore.write_text(f"# my machines\n\n{A}   # the laptop\r\n   \n{B}\n# {C}\n", encoding="utf-8")
    out = lines(report(server, "--ignore", str(ignore)))
    assert months(out) == ["  2026-11  1"], "A and B are in no month, C is left"
    assert out[-2:] == ["2 requests came from developers' runs (id 0)", "3 requests came from 2 numbers of the ignore list"], "A twice (one in each month) and B once"
    assert "2 of 4 requests came without an id (older versions)" in out


def test_the_default_list_is_usage_ignore_beside_the_secrets_file_and_a_missing_one_given_by_name_is_an_error(server: Path) -> None:
    (server.parent.parent / "secrets" / "usage-ignore").write_text(f"{C}\n", encoding="utf-8")
    assert lines(report(server))[-1] == "2 requests came from 1 number of the ignore list"
    gone = report(server, "--ignore", str(server.parent / "nowhere"))
    assert gone.returncode == 1 and "no ignore list at" in gone.stderr and gone.stdout == ""


def test_a_list_of_nothing_but_comments_leaves_out_nothing(server: Path) -> None:
    empty = server.parent / "empty"
    empty.write_text("# nobody yet\n\n", encoding="utf-8")
    assert lines(report(server, "--ignore", str(empty)))[-1] == "0 requests came from 0 numbers of the ignore list"


def test_the_number_of_a_month_that_is_in_the_list_in_the_one_month_is_out_in_the_next_too(server: Path) -> None:
    ignore = server.parent / "ignore"
    ignore.write_text(f"{A}\n", encoding="utf-8")
    out = lines(report(server, "--ignore", str(ignore)))
    assert months(out) == ["  2026-10  1", "  2026-11  1"], "B in October, C in November"


def test_the_logs_of_the_present_version_page_write_a_dash_for_id_0_and_that_is_a_request_without_an_id(server: Path) -> None:
    (server / "logs" / "starts-2026-11.log").write_text(f"2026-11-02T11:00Z\t0.20.0\twindows\t-\n2026-11-02T12:00Z\t0.20.0\tlinux\t{C}\n", encoding="utf-8")
    out = lines(report(server))
    assert "3 of 6 requests came without an id (older versions)" in out and out[-2] == "1 requests came from developers' runs (id 0)"


def test_an_option_that_does_not_exist_is_refused_and_help_is_the_header(server: Path) -> None:
    refused = report(server, "--bogus")
    assert refused.returncode == 2 and refused.stdout == "" and "usage:" in refused.stderr
    helped = subprocess.run(["bash", str(server / "usage-report.sh"), "--help"], capture_output=True, text=True, timeout=60, check=False)
    assert "usage-ignore" in helped.stdout and "neoaprs db get update/install_id" in helped.stdout


def test_a_list_saved_by_a_windows_editor_with_a_byte_order_mark_and_upper_case_still_leaves_its_first_number_out(server: Path) -> None:
    ignore = server.parent / "ignore"
    ignore.write_bytes(b"\xef\xbb\xbf" + A.upper().encode() + b"\r\n" + B.encode() + b"\r\n")
    out = lines(report(server, "--ignore", str(ignore)))
    assert months(out) == ["  2026-11  1"] and out[-1] == "3 requests came from 2 numbers of the ignore list"


def test_no_logs_at_all_is_said_and_nothing_is_reported(server: Path) -> None:
    for log in (server / "logs").iterdir():
        log.unlink()
    result = report(server)
    assert result.returncode == 1 and result.stdout == "" and "no start logs in" in result.stderr
