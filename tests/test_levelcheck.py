"""The gate's level stage (scripts/levelcheck.py): which pins it collects, and each outcome against
stand-in registries on the loopback: level, behind and young, behind and old, allowed (and an
allowance that has ended), a registry that does not answer, no network, and pre-release, yanked
and deprecated versions left out."""

import gzip
import http.server
import json
import re
import socket
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from neoaprs.mercury import VERSION as MERCURY_VERSION

from tests.support.httpthread import serve
from tests.test_scripts import load_script

levelcheck = load_script("levelcheck.py")
ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 28, 12, 0, tzinfo=UTC)


def ago(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat().replace("+00:00", "Z")


class Registry(http.server.BaseHTTPRequestHandler):
    """Answers each path of `routes` with its JSON (gzipped when asked), anything else 404."""

    routes: dict[str, object] = {}
    asked: list[str] = []

    def do_GET(self) -> None:  # noqa: N802 (the name the library calls)
        Registry.asked.append(self.path)
        body = Registry.routes.get(self.path)
        if isinstance(body, int):
            self.send_response(body)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if body is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if isinstance(body, bytes):  # cut short or damaged, said to be gzip
            self.send_response(200)
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        data = json.dumps(body).encode()
        self.send_response(200)
        if "gzip" in self.headers.get("Accept-Encoding", ""):
            data = gzip.compress(data)
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args: object) -> None:
        pass


@pytest.fixture
def registries() -> Iterator[Any]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Registry)
    serve(server)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    Registry.routes, Registry.asked = {}, []
    yield levelcheck.Registries(pypi=base, npm=base, github=base, nodejs=base, token="", timeout=5)
    server.shutdown()
    server.server_close()


def pypi(name: str, **releases: tuple[float, bool]) -> None:
    """A PyPI project: each version with its age in days and whether it is yanked."""
    files = {v.replace("_", "."): [{"upload_time_iso_8601": ago(d), "yanked": y}] for v, (d, y) in releases.items()}
    Registry.routes[f"/pypi/{name}/json"] = {"releases": files}


def pin(kind: str, name: str, version: str) -> Any:
    return levelcheck.Pin(kind, name, version, ("pyproject.toml",))


def verdict(registries: Any, p: Any, allow: dict[tuple[str, str], Any] | None = None) -> Any:
    return levelcheck.ask(p, registries, allow or {}, NOW)


def test_a_pin_at_the_newest_release_is_level(registries: Any) -> None:
    pypi("tornado", **{"6_6_0": (90, False), "6_6_1": (30, False)})
    assert verdict(registries, pin("pypi", "tornado", "6.6.1")).word == "level"


def test_a_release_out_for_less_than_two_weeks_is_listed_and_passes(registries: Any) -> None:
    pypi("certifi", **{"2026_10_23": (36, False), "2026_11_20": (8, False)})
    said: list[str] = []
    code = levelcheck.run([pin("pypi", "certifi", "2026.10.23")], {}, registries, NOW, lambda: True, said.append)
    assert code == 0 and said[1].split()[:5] == ["young", "pypi:certifi", "2026.10.23", "2026.11.20", "8d"]


def test_behind_for_longer_than_two_weeks_fails_counted_from_the_first_release_after_ours(registries: Any) -> None:
    pypi("pydantic", **{"2_14_0": (60, False), "2_14_1": (20, False), "2_14_4": (0.1, False)})
    found = verdict(registries, pin("pypi", "pydantic", "2.14.0"))
    assert (found.word, found.fails, found.newest, found.newest_days, found.behind_days) == (
        "behind",
        True,
        "2.14.4",
        0,
        20,
    )
    said: list[str] = []
    code = levelcheck.run([pin("pypi", "pydantic", "2.14.0")], {}, registries, NOW, lambda: True, said.append)
    assert code == 1 and said[1].startswith("FAIL") and said[-1].endswith("1 failed")


def test_pre_releases_and_yanked_versions_do_not_count(registries: Any) -> None:
    pypi("pytest", **{"9_2_0": (40, False), "9_3_0rc1": (30, False), "9_3_0": (20, True), "10_0_0_dev1": (20, False)})
    assert verdict(registries, pin("pypi", "pytest", "9.2.0")).word == "level"
    Registry.routes["/vite"] = {
        "versions": {"8.4.0": {}, "9.0.0-beta.1": {}, "8.5.0": {"deprecated": "broken"}},
        "time": {"8.4.0": ago(30), "9.0.0-beta.1": ago(29), "8.5.0": ago(28)},
    }
    assert verdict(registries, pin("npm", "vite", "8.4.0")).word == "level"
    Registry.routes["/repos/a/b/releases/latest"] = {"tag_name": "continuous", "published_at": ago(1)}
    Registry.routes["/repos/a/b/releases?per_page=30"] = [
        {"tag_name": "continuous", "published_at": ago(1)},
        {"tag_name": "v2.0.0", "published_at": ago(30), "prerelease": True},
        {"tag_name": "v1.9.0", "published_at": ago(30), "draft": True},
        {"tag_name": "v1.8.1", "published_at": ago(300)},
    ]
    assert verdict(registries, pin("github", "a/b", "1.8.1")).word == "level"


def test_npm_and_github_releases_are_dated_and_compared(registries: Any) -> None:
    Registry.routes["/@types%2Fnode"] = {
        "versions": {"22.20.5": {}, "26.6.11": {}},
        "time": {"22.20.5": ago(600), "26.6.11": ago(1)},
    }
    found = verdict(registries, pin("npm", "@types/node", "22.20.5"))
    assert (found.word, found.newest, found.newest_days, found.behind_days) == ("young", "26.6.11", 1, 1)
    Registry.routes["/repos/zizmorcore/zizmor/releases/latest"] = {"tag_name": "v1.33.1", "published_at": ago(20)}
    Registry.routes["/repos/zizmorcore/zizmor/releases?per_page=30"] = [
        {"tag_name": "v1.33.1", "published_at": ago(20)},
        {"tag_name": "v1.32.0", "published_at": ago(40)},
    ]
    found = verdict(registries, pin("github", "zizmorcore/zizmor", "v1.32.0"))
    assert (found.word, found.newest, found.behind_days) == ("behind", "1.33.1", 20)


def node_index(**releases: float) -> None:
    """The release index of nodejs.org: each version with its age in days; a pre-release of a later line too."""
    Registry.routes["/dist/index.json"] = [
        {"version": "v27.0.0-alpha.0.2.0", "date": ago(3)[:10]},
        {"version": "v26.7.0", "date": ago(2)[:10]},
        *({"version": "v" + v.replace("_", "."), "date": ago(d)[:10]} for v, d in releases.items()),
    ]


def test_node_is_compared_with_the_newest_release_of_its_own_line(registries: Any) -> None:
    node_index(**{"22_23_5": 40, "22_22_0": 80})
    found = verdict(registries, pin("node", "node", "22.23.5"))
    assert found.word == "level", "a later line (26) is a choice, not a fall behind"
    registries._cache.clear()
    node_index(**{"22_23_5": 40, "22_24_0": 5, "22_22_0": 80})
    found = verdict(registries, pin("node", "node", "22.23.5"))
    assert (found.word, found.fails, found.newest, found.behind_days) == ("young", False, "22.24.0", 5)
    registries._cache.clear()
    node_index(**{"22_23_5": 40, "22_24_0": 20})
    found = verdict(registries, pin("node", "node", "22.23.5"))
    assert (found.word, found.fails, found.newest, found.behind_days) == ("behind", True, "22.24.0", 20)


def test_inno_setup_tags_are_read_as_versions(registries: Any) -> None:
    assert levelcheck.tag_version("is-6_7_1") == "6.7.1" and levelcheck.tag_version("v1.2") == "1.2"
    Registry.routes["/repos/jrsoftware/issrc/releases/latest"] = {"tag_name": "is-6_7_1", "published_at": ago(60)}
    assert verdict(registries, pin("github", "jrsoftware/issrc", "6.7.1")).word == "level"
    newer = [{"tag_name": "is-7_1_1", "published_at": ago(30)}, {"tag_name": "is-6_7_1", "published_at": ago(300)}]
    registries._cache.clear()
    Registry.routes["/repos/jrsoftware/issrc/releases/latest"] = newer[0]
    Registry.routes["/repos/jrsoftware/issrc/releases?per_page=30"] = newer
    found = verdict(registries, pin("github", "jrsoftware/issrc", "6.7.1"))
    assert (found.word, found.fails, found.newest, found.behind_days) == ("behind", True, "7.1.1", 30)
    registries._cache.clear()
    Registry.routes["/repos/jrsoftware/issrc/releases/latest"] = newer[0] | {"published_at": ago(3)}
    Registry.routes["/repos/jrsoftware/issrc/releases?per_page=30"] = [newer[0] | {"published_at": ago(3)}, newer[1]]
    assert verdict(registries, pin("github", "jrsoftware/issrc", "6.7.1")).word == "young"


def test_a_github_pin_that_is_the_latest_release_asks_once(registries: Any) -> None:
    Registry.routes["/repos/wb2osz/direwolf/releases/latest"] = {"tag_name": "1.8.1", "published_at": ago(380)}
    assert verdict(registries, pin("github", "wb2osz/direwolf", "1.8.1")).word == "level"
    assert Registry.asked == ["/repos/wb2osz/direwolf/releases/latest"]


def test_a_list_of_releases_that_times_out_leaves_the_latest_alone(registries: Any) -> None:
    Registry.routes["/repos/a/python/releases/latest"] = {"tag_name": "20261124", "published_at": ago(4)}
    Registry.routes["/repos/a/python/releases?per_page=30"] = 504
    found = verdict(registries, pin("github", "a/python", "20261021"))
    assert (found.word, found.newest, found.behind_days) == ("young", "20261124", 4)


def test_an_allowed_version_and_every_later_one_pass_until_its_date_and_the_rest_still_counts(registries: Any) -> None:
    Registry.routes["/typescript"] = {
        "versions": {"5.6.3": {}, "5.9.3": {}, "7.0.2": {}, "8.0.1": {}},
        "time": {"5.6.3": ago(700), "5.9.3": ago(100), "7.0.2": ago(140), "8.0.1": ago(30)},
    }
    allow = {("npm", "typescript"): levelcheck.Allowance("7", date(2026, 12, 31), "vue-tsc does not run on it")}
    found = verdict(registries, pin("npm", "typescript", "5.9.3"), allow)
    assert (found.word, found.fails, found.newest) == ("allowed", False, "8.0.1"), "a later major is held too"
    assert found.note == "allowed until 2026-12-31: vue-tsc does not run on it"
    found = verdict(registries, pin("npm", "typescript", "5.6.3"), allow)
    assert (found.word, found.newest, found.behind_days) == ("behind", "5.9.3", 100)
    ended = {("npm", "typescript"): levelcheck.Allowance("7", date(2026, 11, 27), "vue-tsc does not run on it")}
    found = verdict(registries, pin("npm", "typescript", "5.9.3"), ended)
    assert (found.word, found.fails, found.note) == ("behind", True, "the allowance for 7 ended on 2026-11-27")


def test_a_registry_that_does_not_answer_is_reported_and_passes(registries: Any) -> None:
    Registry.routes["/pypi/ruff/json"] = 503
    said: list[str] = []
    pins = [pin("pypi", "ruff", "0.17.6"), pin("pypi", "absent", "1.0")]
    assert levelcheck.run(pins, {}, registries, NOW, lambda: True, said.append) == 0
    assert [line.split()[:2] for line in said[1:3]] == [["not", "asked"], ["not", "asked"]]
    assert "answered 503" in said[1] and "answered 404" in said[2]
    with socket.socket() as spare:
        spare.bind(("127.0.0.1", 0))
        port = spare.getsockname()[1]
    closed = levelcheck.Registries(pypi=f"http://127.0.0.1:{port}", token="", timeout=2)
    assert verdict(closed, pin("pypi", "ruff", "0.17.6")).note.startswith("the registry did not answer")


def test_only_being_behind_fails_never_an_answer_it_cannot_read_or_a_release_without_a_date(registries: Any) -> None:
    Registry.routes["/pypi/odd/json"] = ["not", "a", "project"]
    Registry.routes["/pypi/limited/json"] = 429
    Registry.routes["/repos/a/b/releases/latest"] = 403
    Registry.routes["/undated"] = {"versions": {"1.0.0": {}, "1.1.0": {}}, "time": {"1.0.0": ago(400)}}
    pins = [
        pin("pypi", "odd", "1.0"),
        pin("pypi", "limited", "1.0"),
        pin("github", "a/b", "1.0"),
        pin("npm", "undated", "1.0.0"),
    ]
    said: list[str] = []
    assert levelcheck.run(pins, {}, registries, NOW, lambda: True, said.append) == 0
    rows = {next(word for word in line.split() if ":" in word): line for line in said[1:-1]}
    assert "not one this reads" in rows["pypi:odd"] and "answered 429" in rows["pypi:limited"]
    assert "answered 403" in rows["github:a/b"] and rows["npm:undated"].endswith("the registry gave no date")


def test_an_answer_that_is_cut_short_or_damaged_is_reported_and_passes(registries: Any) -> None:
    packed = gzip.compress(json.dumps({"releases": {"1.1": []}}).encode())
    Registry.routes["/pypi/cut/json"] = packed[:-8]
    Registry.routes["/pypi/damaged/json"] = b"\x1f\x8b\x08\x00" + b"not a gzip stream at all"
    for name in ("cut", "damaged"):
        found = verdict(registries, pin("pypi", name, "1.0"))
        assert (found.word, found.fails) == ("not asked", False), name
        assert found.note.startswith("the registry did not answer"), found.note


def test_with_no_network_it_says_so_and_passes() -> None:
    said: list[str] = []

    def no_lookup(_host: str) -> object:
        raise OSError("no network")

    pins = [pin("pypi", "tornado", "6.6.1")]
    assert levelcheck.run(pins, {}, None, NOW, lambda: levelcheck.online(no_lookup), said.append) == 0
    assert said == ["levelcheck: no network (pypi.org cannot be looked up): 1 pins not asked"]


def test_it_collects_every_exact_pin_of_the_tree(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling==1.33.0"]\n[project]\ndependencies = ["tornado==6.6.1"]\n'
        "[project.optional-dependencies]\napp = [\"Pillow==13.0.0; sys_platform == 'win32'\"]\n"
        '[dependency-groups]\ndev = ["ruff==0.17.6", "loose>=1"]\n'
    )
    (tmp_path / "ui").mkdir()
    (tmp_path / "ui" / "package.json").write_text(
        '{"dependencies": {"vue": "3.5.46"}, "devDependencies": {"vite": "8.4.0"}}'
    )
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "security-tools").write_text(
        '"https://github.com/zizmorcore/zizmor/releases/download/v1.33.1/zizmor-x86_64.tar.gz",\n'
    )
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    workflow = '      - uses: astral-sh/setup-uv@abc123 # v10.4.0\n        with:\n          version: "0.13.10"\n'
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(workflow * 2)
    (tmp_path / "neoaprs").mkdir()
    (tmp_path / "neoaprs" / "mercury.py").write_text('VERSION = "1.9.26"\nPREVIOUS_VERSION = "1.9.25"\n')
    (tmp_path / "packaging" / "ci").mkdir(parents=True)
    (tmp_path / "packaging" / "ci" / "Dockerfile").write_text("ARG UV_VERSION=0.13.10\nARG NODE_VERSION=22.23.5\n")
    (tmp_path / ".github" / "workflows" / "release.yml").write_text(
        "if (-not $iscc) { choco install innosetup --version=6.7.1 -y --no-progress }\n"
    )
    (tmp_path / "scripts" / "build-gi").write_text(
        'PYGOBJECT_URL = "https://files.pythonhosted.org/packages/a7/5d/f29/pygobject-3.50.2.tar.gz"\n'
        'MESON_URL = "https://files.pythonhosted.org/packages/d2/f3/9d5/meson-1.6.1-py3-none-any.whl"\n'
    )
    found = {(p.kind, p.name, p.version): p.where for p in levelcheck.collect(tmp_path)}
    assert found == {
        ("pypi", "hatchling", "1.33.0"): ("pyproject.toml",),
        ("pypi", "tornado", "6.6.1"): ("pyproject.toml",),
        ("pypi", "Pillow", "13.0.0"): ("pyproject.toml",),
        ("pypi", "ruff", "0.17.6"): ("pyproject.toml",),
        ("npm", "vue", "3.5.46"): ("ui/package.json",),
        ("npm", "vite", "8.4.0"): ("ui/package.json",),
        ("github", "zizmorcore/zizmor", "v1.33.1"): ("scripts/security-tools",),
        ("github", "astral-sh/uv", "0.13.10"): (".github/workflows/ci.yml", "packaging/ci/Dockerfile"),
        ("node", "node", "22.23.5"): ("packaging/ci/Dockerfile",),
        ("github", "jrsoftware/issrc", "6.7.1"): (".github/workflows/release.yml",),
        ("pypi", "pygobject", "3.50.2"): ("scripts/build-gi",),
        ("pypi", "meson", "1.6.1"): ("scripts/build-gi",),
        ("github", "Rhizomatica/mercury", "1.9.26"): ("neoaprs/mercury.py",),
    }


def test_the_trees_pins_include_every_kind_and_one_uv() -> None:
    pins = levelcheck.collect()
    names = {(p.kind, p.name) for p in pins}
    assert {
        ("pypi", "pydantic"),
        ("npm", "vue"),
        ("github", "Rhizomatica/mercury"),
        ("github", "wb2osz/direwolf"),
    } <= names
    assert {("github", "gitleaks/gitleaks"), ("github", "google/osv-scanner")} <= names
    assert len([p for p in pins if p.name == "astral-sh/uv"]) == 1, "every place pins the same uv"
    assert {
        ("node", "node"),
        ("github", "jrsoftware/issrc"),
        ("pypi", "pygobject"),
        ("pypi", "meson"),
    } <= names, "Node of the container, Inno Setup and the GTK build's two are followed too"
    mercury = [p.version for p in pins if p.name == "Rhizomatica/mercury"]
    assert mercury == [MERCURY_VERSION], "the previous Mercury is built beside ours for the tests, not a pin to chase"
    cpython = [p for p in pins if p.name == "astral-sh/python-build-standalone"]
    assert len(cpython) == 1 and set(cpython[0].where) == {
        "scripts/build-appimage",
        "scripts/build-deb",
        "scripts/build-macos-app",
    }, "the AppImage, the packages and the macOS app have the same CPython"


def test_the_allow_file_gives_each_entry_its_version_date_and_reason(tmp_path: Path) -> None:
    path = tmp_path / "allowed.txt"
    path.write_text("# comment\n\nnpm:typescript 7 2026-12-31 vue-tsc 3 does not run on it\n")
    assert levelcheck.allowed(path) == {
        ("npm", "typescript"): levelcheck.Allowance("7", date(2026, 12, 31), "vue-tsc 3 does not run on it")
    }
    path.write_text("npm:typescript 7 soon\n")
    with pytest.raises(SystemExit):
        levelcheck.allowed(path)
    for allowance in levelcheck.allowed().values():
        assert allowance.reason and allowance.until


def test_versions_are_ordered_by_their_numbers() -> None:
    order = ["0.9", "0.11.26", "0.13.10", "1.9.25", "v1.9.26", "1.10", "4!1.0", "20261021", "20261124"]
    keys = [levelcheck.version_key(v) for v in order]
    assert keys == sorted(keys[:7]) + keys[7:] and keys[7] < keys[8]
    assert levelcheck.version_key("1.0.post1") > levelcheck.version_key("1.0")
    assert not any(levelcheck.stable(v) for v in ("1.0rc1", "2.0.0-beta.1", "1.0.dev3", "continuous"))


def test_every_exact_pin_of_the_tree_is_followed_or_listed_as_not_followed() -> None:
    """A file of scripts/, packaging/, server/ or .github/ that holds a digest or a commit is the
    place of a followed pin or one the list names with its reason (and the list's text is still in its file)."""
    followed = {where for pin in levelcheck.collect() for where in pin.where}
    listed = {where for _what, where, _needle, _because in levelcheck.NOT_FOLLOWED}
    for what, where, needle, because in levelcheck.NOT_FOLLOWED:
        assert needle in (ROOT / where).read_text(encoding="utf-8"), f"{what}: {where} no longer has {needle!r}"
        assert because
    pinned = re.compile(r"\b[0-9a-f]{64}\b|@[0-9a-f]{40}\b")
    owned = {
        "scripts/build-mercury",
        "scripts/build-direwolf",
        "packaging/deb/copyright",
    }  # the modems' source digests (their VERSION is followed)
    owned.add("scripts/security-baseline.json")  # the hashes of findings, not of tools
    for folder in ("scripts", "packaging", "server", ".github"):
        for path in sorted((ROOT / folder).rglob("*")):
            name = path.relative_to(ROOT).as_posix()
            if not path.is_file() or "__pycache__" in name or name.startswith("scripts/__") or path.suffix == ".pyc":
                continue
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            if pinned.search("\n".join(line for line in lines if "uses: " not in line)):  # the actions are Dependabot's
                assert name in followed | listed | owned, (
                    f"{name} pins a digest the stage level neither follows nor lists"
                )
