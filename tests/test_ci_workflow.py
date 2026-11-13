"""The workflows that check a push (.github/workflows/ci.yml) and the packages by the clock (audit.yml), read as text: the Linux job calls scripts/check by stage and Windows runs the commands themselves, the suite keeps
the two files that need one process on one worker, the simulation job keeps its Mercury build between runs under a key made of what the build reads, and the weekly audit is a workflow of its own that publishes nothing.
What the steps do on GitHub is seen only there."""
import re
from pathlib import Path

from tests.conftest import ROOT

CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
AUDIT = (ROOT / ".github" / "workflows" / "audit.yml").read_text(encoding="utf-8")
CHECK = (ROOT / "scripts" / "check").read_text(encoding="utf-8")


def job(name: str, text: str = CI) -> str:
    found = re.search(rf"^  {name}:\n(.*?)(?=^  [\w-]+:\n|\Z)", text, re.S | re.M)
    assert found is not None, f"no job {name}"
    return found.group(1)


def steps(text: str) -> list[str]:
    """The steps of a job, each from its `- ` to the next."""
    return re.split(r"^      - ", text, flags=re.M)[1:]


def test_every_step_of_the_linux_job_is_a_stage_of_the_script_that_runs_before_a_push() -> None:
    linux = [step for step in steps(job("python")) if "if: runner.os == 'Linux'" in step and step.startswith("run: ")]
    stages = [re.match(r"run: scripts/check --stage (\S+)\n", step) for step in linux]
    assert [found.group(1) for found in stages if found] == ["lock", "ruff", "mypy", "architecture", "pytest"], "the stages, in the order of the script's own list"
    listed = re.search(r"^STAGES=\(([^)]*)\)", CHECK, re.M)
    assert listed is not None and all(name in listed.group(1).split() for name in ("lock", "ruff", "mypy", "architecture", "pytest"))
    assert "uv run ruff" not in "".join(linux) and "uv run pytest" not in "".join(linux) and "uv run mypy" not in "".join(linux), "no command of its own beside the stages"


def test_windows_runs_the_commands_and_the_suite_with_the_files_that_need_one_worker_grouped() -> None:
    windows = [step for step in steps(job("python")) if "if: runner.os == 'Windows'" in step]
    commands = [re.match(r"run: (.+)\n", step).group(1) for step in windows if step.startswith("run: ")]       # type: ignore[union-attr]
    assert commands == ["env -u UV_FROZEN uv lock --check", "uv run ruff check .", "uv run pytest -n auto --dist loadgroup"]
    assert "--dist loadgroup" in CHECK and "--dist worksteal" not in CHECK, "the stage pytest groups them too: worksteal ignores the groups"
    assert "--dist worksteal" not in (ROOT / "scripts" / "coverage").read_text(encoding="utf-8")


def test_the_two_files_that_need_one_worker_are_grouped_for_xdist() -> None:
    for name, group in (("test_package.py", "package"), ("test_desktop_qt.py", "desktop-qt")):
        assert f'pytest.mark.xdist_group("{group}")' in (ROOT / "tests" / name).read_text(encoding="utf-8"), f"{name} stays on one worker"


def test_the_page_job_runs_the_page_test_that_the_suite_of_the_linux_job_leaves_out() -> None:
    assert re.search(r"^      - run: scripts/check --stage page$", job("page"), re.M)
    assert 'PAGE_TESTS=(tests/test_page_build.py)' in CHECK and '"${PAGE_TESTS[@]/#/--ignore=}"' in CHECK


# ---- the simulation job's Mercury ----

def test_the_mercury_of_the_simulation_is_kept_under_a_key_of_what_its_build_reads_and_built_only_when_it_is_not_there() -> None:
    sim = job("sim")
    body = steps(sim)
    cache = next(step for step in body if "uses: actions/cache@" in step)
    build = next(step for step in body if "scripts/build-mercury --install" in step)
    assert body.index(cache) < body.index(build), "the cache is looked up before the build"
    assert "id: mercury" in cache and "if: steps.mercury.outputs.cache-hit != 'true'" in build
    assert "path: .venv/tools/mercury" in cache and '"tools" / "mercury"' in (ROOT / "scripts" / "build-mercury").read_text(encoding="utf-8"), "what --install makes in the venv"
    key = re.search(r"key: (.+)", cache)
    assert key is not None
    for part in ("runner.os", "runner.arch", "steps.image.outputs.name"):
        assert part in key.group(1)
    hashed = re.search(r"hashFiles\(([^)]*)\)", key.group(1))
    assert hashed is not None
    globs = re.findall(r"'([^']+)'", hashed.group(1))
    assert set(globs) == {"scripts/build-mercury", "neoaprs/mercury.py", "packaging/mercury/**"}, "the script, the pins it reads and the patches and the stub it applies"


def test_the_key_of_the_mercury_cache_names_every_file_of_packaging_the_build_reads() -> None:
    script = (ROOT / "scripts" / "build-mercury").read_text(encoding="utf-8")
    read = set(re.findall(r'ROOT / "packaging" / "(\w+)" / "[\w.]+"', script))
    assert read == {"mercury"}, f"the build reads files of {sorted(read)}: the key of the cache in ci.yml names them"
    assert re.search(r"ROOT / \"neoaprs\" / \"mercury\.py\"", script), "and the pins, which are neoaprs/mercury.py"
    assert all(Path(ROOT / "packaging" / "mercury" / name).is_file() for name in re.findall(r'"packaging" / "mercury" / "([\w.]+)"', script))


# ---- the weekly audit ----

def test_the_audit_is_a_weekly_workflow_of_its_own_that_runs_the_stage_and_publishes_nothing() -> None:
    assert re.search(r"^  schedule:\n    - cron: \"\d{1,2} \d{1,2} \* \* [0-6]\"", AUDIT, re.M), "once a week"
    assert "workflow_dispatch" in AUDIT and "scripts/check --stage audit" in AUDIT and "python3 scripts/security-tools osv-scanner" in AUDIT
    assert re.search(r"^permissions:\n  contents: read$", AUDIT, re.M) and "contents: write" not in AUDIT and "secrets." not in AUDIT
    assert [action.split("@")[0] for action in re.findall(r"uses: (\S+)", AUDIT)] == ["actions/checkout", "astral-sh/setup-uv"], "nothing else runs there (tests/test_release.py holds how an action is pinned)"
    assert "audit" in CHECK and "schedule:" not in CI, "a scheduled run of ci.yml would count as the green run of a commit that the release asks for"
