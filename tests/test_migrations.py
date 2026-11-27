"""The migrations of the one database (neoaprs/migrations.py): a new file gets every table, an
applied migration is frozen, the copy before a migration, the history, a refused file is left as it
was, a failed one changes nothing.
"""

import hashlib
import inspect
import logging
import sqlite3
import sys
import types
from collections.abc import Callable
from pathlib import Path

import pytest

from neoaprs import migrations as migrations_module
from neoaprs.dberror import StoreError
from neoaprs.migrations import COPY_MARGIN_BYTES, MIB, MIGRATIONS, SCHEMA_VERSION, _require_room, source_hash
from neoaprs.migrationlog import MIGRATION_LOG
from neoaprs.stopfile import MIGRATING_NAME
from neoaprs.store import DB_NAME
from tests.support.clock import FixedClock
from tests.support.migrated import opened, try_open
from tests.support.migrated32 import SAID

# The checksum of the source of each migration. If this test fails somebody edited a migration that
# may have run on databases already: add a new migration instead. Only a migration that has never
# run on a kept database may have its entry changed.
GOLDEN = {
    1: "9ab3c608724b21575f4555fcfcd5c2aaa60ad5b56ee5de68e583797f5667ae2b",
    2: "73f6f40f87d65ea9fa81468c8bfc645c0aa4a46fb726b441f59850ae640aeb96",
    3: "7ba3029f6d89094fdf6b0d7258ccd9938971ffb261aea61dbf8c237b9c1d78ae",
    4: "44b656e05ac34912905196b410e053d21512683d56abb061ecd44201507485dc",
    5: "8e709486fbd27abf47b6a6220d7f6a3e1fe74bad6062595b7e56b952229b3cf3",
    6: "233db7ea1e0174e3319a56d1ad0fd2726607c2d4ee75f4fee26f5d0d3f11dd7c",
    7: "d4c0d405d595625396761f528e27acf2a69b06a7c9274ac6e0678aeafabab571",
    8: "f58b8cee1811d5b9d44dc0be2a192fdd0459d6fd174413f85537050d2f35f91e",
    9: "db26a840d6f030cd0151244578ac4ae41f0c8039aafc86817db97bcd495019c5",
    10: "49491e5f8c7ce3d06a0e144edbd9be674ad88b2b900056c52069893b9c8cab79",
    11: "12651b007129877130709482c05e95d382a0c368259c635b5ac3063d99d51807",
    12: "9d55228537b4b9219f29fd44b2d66afefbc4d25fabf62f6b0956f0062a7ba1ee",
    13: "2e9d3b8254a0297832fb65fcec930f8978c609d32d8fadce7b00c33f0addbcf4",
    14: "c52ef26994e7030d3e7c8ef0ec35cba10d8f9697a868a7a5fd347a9c11227096",
    15: "167a3357cbfc0d585908a266b5127e520c3e3882fe4c812d7779302b077fc218",
    16: "f88d56c469236663789815ac1d10b3e9d627ada73d45a7d2caa34a37f446e432",
    17: "f185428df99cb4efc0c5fdc939c47e528470c13b1ec0ad4e056f78b859d6cd8d",
    18: "4dec7cf8917269d4bc17dc8ceacdafb0bdc7074a845924f90acaf4cd7dca62af",
    19: "dfee77b1bac4440a1facf802efdb0778cf85c518d99cd73ce8d7051063b04666",
    20: "c2124299ed4db2ef7601427b3fc747c87683d1ed4c284b4f1fb7a0073e77477b",
    21: "547f0d897cd84f524b7ab1ab5aa50e82f08ae8c890dd27fa22029f85a5aacf45",
    22: "47a08fb6c435b0cf69a02c64ba1e9d8f8c13b021dbd94eb73287f0420509fc4a",
    23: "3e5b9f2fac293b51462f788a000d855724c49d8fd0cf795fd6c12cc81339cc25",
    24: "a15e3652b7e2c8c638df1703e1a4d6ea0b431ba396d410650b036d05b4b26ff8",
    25: "309ed52fbae10d5aad20a0c06fd91629c366d5c5e559fcf4f47551ede56ebccf",
    26: "ee71509ab70d712c2116200b77a975b564e9bfc4d3fba2b0951be1f9acb909bd",
    27: "af1005c12d078514e326d2bcf322e7f8ac44d477eadafd5ac31401ce7d8d15b9",
    28: "c082b660c1ea145adcdabd04185bead6bbdee8b3d0e549f73ead569af675a96f",
    29: "f37bc1c40d4ff8f20c3bdb5d35e5f4c5b08fcb6b37e477d82df0c6a479a362a5",
    30: "2ac08e702b03cbfb8de02677458e74eb0c1d6f0404700f8f91bf9d3132d3e0d4",
    31: "3f4253eb76b65cc049509915a7db44623c5a8da1b7401c6af1cbcd0e95d1d1b1",
    32: "54b58792fd02b37750969d56f157b6f9e76513aeb3ff63084c7dd3eef6f58e3a",
    33: "ea139c3b7b28ccdd4d46367fa98a11a96c658f8adbbfad7eba26113415131a64",
    34: "ae4ad4d217638373cd5bb3195798d202a801afb6243e50254537f07e8aef2784",
    35: "dc4f36a4f56d86dc8bf1299f416ea82bd07198a9a5adfeb505bd4e8ebc39e1a3",
    36: "c6333392c7370fe153b42e6c5de476082f16391e6a914a4f4bc7f1947ff28628",
    37: "40969465acac7d7f520251996c2090206f4fbd4e354f8e452703d9ea5cc5d405",
}


# What a step calls or reads that is written outside it, in the module beside it: the helper
# functions and the constants (a text, a number, a tuple), by the step that uses them and the hash
# of what they are. Editing one changes what a step does on a database it has not run on yet, so
# they are frozen as the steps are.
GOLDEN_USED = {
    "_v21": {"_third_party_sender": "5a15e75b3fbb473e8ec940c464521dd68b7ec34c49d633a6441a4cdf1c5e54c2"},
    "_v22": {
        "_OLD_LINUX_ALERT": "5fb693746274abb1ee0e8149fdf0264c1cb906f6e8bbeed6189d4fe0bfa377f9",
        "_OLD_WINDOWS_ALERT": "0b4b01fbd7a1f34a5703db45884f161b882ff4af0b90514424be568c339123ea",
    },
    "_v29": {
        "_allowed_host": "cdac1e89d80032fe364499a32247597d9895e94bef5752ce1f71b688f366f082",
        "_HOST_LABEL": "c221b1e4a74e5e08ce521e3de652ebb797c93c5678e39d26cc567f9ffc18b0d8",
    },
    "_v31": {
        "_CHOICES": "8dff05af4898688bb573d41c40e6ea66cb01fec877ebf9d1103e4e60ad8afbd6",
        "_FALSE": "26d5af627562f4f506311ff6b1f373ce1d4406cfbd264b33a38ed9fc8f613802",
        "_FM_MOVES": "51c809510ed2916bd937bbbd481e61c2ced3975132253b646c4544fa0d1cce96",
        "_FM_TYPES": "7541c474b50bbecda547e23a7ca29d8783194a22d030e54ba2cce545bfe803b9",
        "_GONE": "899f89869d238a2e74ed59d38c738a293da367551f893b12830f5e082b1f1e88",
        "_HF_MOVES": "4e04d8edf6de4538b82213828691ce0b0e0ae70998b818ed2eb4b57d2d43c49c",
        "_HF_ROWS": "193801f61fca27cd9ded94bac5f1f7cded93f930f3684f22435e7d4d606fde11",
        "_HF_TYPES": "40d1c888a8e29895c78e13046d4715f7e5be0b622c14709ebc8cf84203988679",
        "_KEPT": "81d155c5e50be9f6ef91ea3241da710fabe991e4377a1412919ed7ec71371fa5",
        "_STATE": "d15998254a92fef6d3ac0265df36572c51567de7b573570f61cfda7028f39757",
        "_TRUE": "2903545dd56c033b3f0962fa48660f7136a4656b920d5ff309b7f5cb810ebbb4",
        "_choices31": "38cc46833e0239c9051396bffba6e612f3c01025a619295951ae68c2bd33ae36",
        "_hf_named31": "7afe8ecbd8e34526876dbb7fe17155d89f89153aef209920bc7f6cd043b0654d",
        "_move31": "b827728202d34d1f4e2a9d3b7d00babdf9281af5d41205a51992a6dc28e4bff5",
        "_on31": "e0f91aa73006f8063e626492ea643502ae23ed4c90839a929649cec7006c0d67",
        "_tables31": "412412734227c3e63e9563ceb7156e04fc4edb8a621b83fca07ffc540dffd835",
        "_type31": "2d14e908b6235225e003fda1b4b077b0f021e53c4ca9f541d13315aa5b563fea",
    },
    "_v35": {
        "_LIMIT35": "983bd614bb5afece5ab3b6023f71147cd7b6bc2314f9d27af7422541c6558389",
        "_RADIUS35": "891363c76b41fd1909afa4ce70598297665b99da9b7beccd238733115bc8e2f2",
    },
    "_v36": {
        "_ANNOUNCEMENT36": "8722616204217eddb39e7df969e0698aed8e599ba62ed2de1ce49b03ade0fede",
        "_BULLETIN36": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    },
    "_v37": {
        "_GATE37": "357c5fff0460ca34743f703e6e181c262b8162fdf24c95b25e808977ab573239",
        "_PASSWORD37": "a5616e5c99582b60bd9e6205d12482e33229dc6e850e65390ba334b28cfb4cf7",
        "_SHOW37": "24d3a79b82793dbc14c58e9a65ee4a2dfccb37879c44d49d6071e225be6ca0b2",
        "_TRUE37": "2903545dd56c033b3f0962fa48660f7136a4656b920d5ff309b7f5cb810ebbb4",
    },
    "_v34": {
        "_CHOSEN_BY_ROW34": "22046b5183e59ddac3bffe3f625e4e05860f1a059cd2edf36a02bc4c483e86c5",
        "_FALSE34": "26d5af627562f4f506311ff6b1f373ce1d4406cfbd264b33a38ed9fc8f613802",
        "_MAIL34": "a732f2d02df484e7dff8236549704b4c310a3412330fde2b91fdf2d95f863347",
        "_MAIL_KINDS34": "d630e4d4b2390abfdcb95fd4fd832da83a23fc19371817878839db55dca0e7b2",
        "_MAIN34": "ceed6e129f4fddbaa13eaeb6c076ed7c7427d08f1b9eb4f670601ed137702a19",
        "_NEW_ONES34": "dd2e06bf832208ebee3bef79a0898719d332a30a7cd7d5119bb5e5bd611b3c56",
        "_SENDS34": "a52db0716fe5ab9e8c06dcb588bbdc846d51ad37a62146d6ed92eb2d4518ac06",
        "_TRUE34": "2903545dd56c033b3f0962fa48660f7136a4656b920d5ff309b7f5cb810ebbb4",
        "_beacon34": "af52b594715283c3cd8815e5917a19620a32e276ed813f51f2eb0964d92a4536",
        "_checked34": "324ffdde35ae4e282d5172e0e5cbe87a9a694d2626a382e20dcebcdd1edd3a68",
        "_chosen34": "c97e414f5b49644ae0af47319b0dd3aae2e300e187404e17ceb33182cee51d4e",
        "_mail34": "4250a11de8f7fe3143d46325409775744a66243a63bb5a4f497248d39ed962e0",
        "_nowhere34": "937b03e071b97b8410c1b9b51db39752774de570fb5efba7e32076492ee2349a",
        "_objects34": "1c6fe4eb30c98d484c757503d0df922505f15d9860fd273cd6cc2a8eec21e263",
        "_order34": "cf01ed617bb54ded7c94e2145cd0d50ee4c02f4fbe1846a7e87c991a7b42a9eb",
        "_put34": "934292e5132b5851d41d5bc89e45a5a6cf0d1c5c6160041eae6f15ca9637261d",
        "_radios34": "bcec235a5a77e99efe4429b40aa13276bd4c133a0769e774d6866b8845b9e291",
        "_row34": "b7ca47ccd93d1320f6570221a134a6e079433755e25df491e3db2e14bb0caf55",
        "_send_on34": "ec73801bcc87125a353b81a23be9e55a7a32f444a892a70783439790facfb612",
        "_state34": "253da4b8487452d064ed8e7fa2bd8988b56b173037c58d308913ea940d422eac",
        "_ticked34": "1bb78afa833160251703082ea641f9e8313c55bc5081c8f663719a3689657fb0",
    },
}


def used_by(step: Callable[..., object]) -> dict[str, str]:
    """The hash of each module-level function (and of the functions those call) and constant that
    `step` names, by name."""
    module = sys.modules[step.__module__]
    found: dict[str, str] = {}

    def names_in(code: types.CodeType) -> set[str]:
        return set(code.co_names) | {n for c in code.co_consts if isinstance(c, types.CodeType) for n in names_in(c)}

    def visit(code: types.CodeType) -> None:
        for name in sorted(names_in(code) - found.keys()):
            value = vars(module).get(name)
            if isinstance(value, types.FunctionType) and value.__module__ == module.__name__:
                found[name] = hashlib.sha256(inspect.getsource(value).encode("utf-8")).hexdigest()
                visit(value.__code__)
            elif isinstance(value, (str, bytes, int, tuple, frozenset)) and not name.startswith("__"):
                found[name] = hashlib.sha256(repr(value).encode("utf-8")).hexdigest()

    visit(step.__code__)
    return found


def test_what_an_applied_migration_uses_beside_itself_is_frozen_too() -> None:
    used = {step.__name__: used_by(step) for step in MIGRATIONS}
    assert {name: sorted(found) for name, found in used.items() if found} == {
        name: sorted(found) for name, found in GOLDEN_USED.items()
    }
    assert {name: found for name, found in used.items() if found} == GOLDEN_USED


NEXT = SCHEMA_VERSION + 1  # the version of a file after the migration the tests make up


def raw(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path, isolation_level=None)


def test_an_applied_migration_is_frozen() -> None:
    assert {i + 1: source_hash(m) for i, m in enumerate(MIGRATIONS)} == GOLDEN
    assert SCHEMA_VERSION == len(MIGRATIONS) == len(GOLDEN)


def test_a_new_file_gets_the_settings_and_the_history_at_the_current_version(tmp_path: Path) -> None:
    s = opened(tmp_path / DB_NAME)
    assert (
        s.version() == SCHEMA_VERSION
        and {"settings", "schema_history", "packet", "station", "message", "bulletin"} <= s.tables()
    )
    assert s.db.execute(
        "SELECT name, type, \"notnull\" FROM pragma_table_info('settings') ORDER BY cid"
    ).fetchall() == [("key", "TEXT", 1), ("value", "TEXT", 1), ("rev", "INTEGER", 1)]
    s.close()


def test_the_settings_table_is_strict_and_refuses_what_the_program_cannot_produce(tmp_path: Path) -> None:
    s = opened(tmp_path / DB_NAME)
    db = s.db
    db.execute("INSERT INTO settings (key, value) VALUES ('station/call', 'OH2GBA')")
    assert db.execute("SELECT value, rev FROM settings").fetchall() == [("OH2GBA", 1)]
    for statement, name in [
        ("INSERT INTO settings (key, value) VALUES ('', 'x')", "settings_key_present"),
        ("INSERT INTO settings (key, value, rev) VALUES ('a', 'x', 0)", "settings_rev_positive"),
        ("INSERT INTO settings (key, value) VALUES ('b', NULL)", "NOT NULL"),
        ("INSERT INTO settings (key, value, rev) VALUES ('c', 'x', 'many')", "cannot store"),
        ("INSERT INTO settings (key, value) VALUES ('station/call', 'again')", "UNIQUE"),
    ]:
        with pytest.raises(sqlite3.IntegrityError, match=name):
            db.execute(statement)
    s.close()


def test_a_second_open_migrates_nothing_and_keeps_the_rows(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / DB_NAME
    s = opened(path)
    s.db.execute("INSERT INTO settings (key, value) VALUES ('station/call', 'OH2GBA')")
    s.close()
    caplog.set_level(logging.INFO, MIGRATION_LOG)
    s = opened(path)
    assert s.db.execute("SELECT key, value FROM settings").fetchall() == [("station/call", "OH2GBA")]
    assert [r[0] for r in s.history()] == list(range(1, SCHEMA_VERSION + 1))
    assert not [r for r in caplog.records if "a copy of it is in" in r.getMessage()]
    assert not (tmp_path / "backup").exists(), "a file that is at its version is not copied"
    s.close()


def test_a_file_of_a_newer_neoaprs_is_refused_and_left_alone(tmp_path: Path) -> None:
    path = tmp_path / DB_NAME
    db = raw(path)
    db.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 2}")
    db.execute("CREATE TABLE theirs (x)")
    db.close()
    before = path.read_bytes()
    ok, why = try_open(path)
    assert not ok and "newer NeoAPRS" in why and str(SCHEMA_VERSION + 2) in why
    assert path.read_bytes() == before and not (tmp_path / "backup").exists()


def test_a_file_that_is_not_a_database_is_refused_with_a_reason(tmp_path: Path) -> None:
    path = tmp_path / DB_NAME
    path.write_bytes(b"this is not a database, it is a sentence of some length" * 20)
    ok, why = try_open(path)
    assert not ok and why


def test_a_folder_that_does_not_exist_is_refused_with_a_reason(tmp_path: Path) -> None:
    ok, why = try_open(tmp_path / "nowhere" / DB_NAME)
    assert not ok and why


def test_a_database_in_memory_is_made_and_migrated() -> None:
    s = opened(":memory:")
    assert s.version() == SCHEMA_VERSION and "settings" in s.tables()
    s.close()


def v_next(db: sqlite3.Connection) -> None:
    """A later migration, made up for these tests: a table for the beacons."""
    db.execute("CREATE TABLE beacon (id INTEGER PRIMARY KEY, raw BLOB NOT NULL) STRICT")


def broken(db: sqlite3.Connection) -> None:
    """A later migration that fails half way."""
    db.execute("CREATE TABLE half (x INTEGER)")
    raise sqlite3.OperationalError("the disk is full")


def mended(db: sqlite3.Connection) -> None:
    """The migration that `broken` failed at, as the next release has it."""
    db.execute("CREATE TABLE half (x INTEGER)")


def with_steps(monkeypatch: pytest.MonkeyPatch, *steps: object) -> None:
    all_steps = [*MIGRATIONS, *steps]
    monkeypatch.setattr(migrations_module, "MIGRATIONS", all_steps)
    monkeypatch.setattr(migrations_module, "SCHEMA_VERSION", len(all_steps))


def test_a_later_migration_runs_once_on_the_data_that_is_there_after_a_copy_of_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / DB_NAME
    clock = FixedClock()
    s = opened(path, clock)
    s.db.execute("INSERT INTO settings (key, value) VALUES ('station/call', 'OH2GBA')")
    s.close()
    with_steps(monkeypatch, v_next)
    s = opened(path, clock)
    assert s.version() == NEXT and "beacon" in s.tables()
    assert s.db.execute("SELECT value FROM settings").fetchall() == [("OH2GBA",)]
    assert [r[0] for r in s.history()] == [*range(1, NEXT + 1)] and s.history()[NEXT - 1][1] == "v_next"
    s.close()
    copies = sorted((tmp_path / "backup").glob("premigrate-*.sqlite"))
    assert [c.name for c in copies] == [f"premigrate-v{SCHEMA_VERSION}-to-v{NEXT}-20261021-120000.sqlite"]
    copy = raw(copies[0])
    assert copy.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION and copy.execute(
        "SELECT value FROM settings"
    ).fetchall() == [("OH2GBA",)]
    copy.close()
    assert opened(path, clock).version() == NEXT  # and again: nothing to run
    assert len(list((tmp_path / "backup").glob("premigrate-*.sqlite"))) == 1


def test_a_copy_in_the_same_second_as_one_that_is_there_gets_a_number_and_the_older_one_goes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / DB_NAME
    clock = FixedClock()
    opened(path, clock).close()
    (tmp_path / "backup").mkdir()
    first = f"premigrate-v{SCHEMA_VERSION}-to-v{NEXT}-20261021-120000"
    (tmp_path / "backup" / f"{first}.sqlite").write_bytes(b"an earlier copy")
    with_steps(monkeypatch, v_next)
    opened(path, clock).close()
    assert sorted(p.name for p in (tmp_path / "backup").iterdir()) == [f"{first}-2.sqlite"], (
        "the new copy is whole and the earlier one is gone"
    )


def test_only_the_latest_premigration_copy_is_kept_and_a_copy_somebody_made_stays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / DB_NAME
    clock = FixedClock()
    opened(path, clock).close()
    folder = tmp_path / "backup"
    folder.mkdir()
    for name in (
        "premigrate-v3-to-v4-20260101-000000.sqlite",
        "premigrate-v24-to-v25-20260601-000000.sqlite",
        "mine.sqlite",
        "premigrate-notes.txt",
    ):
        (folder / name).write_bytes(b"x")
    with_steps(monkeypatch, v_next)
    opened(path, clock).close()
    assert sorted(p.name for p in folder.iterdir()) == [
        "mine.sqlite",
        "premigrate-notes.txt",
        f"premigrate-v{SCHEMA_VERSION}-to-v{NEXT}-20261021-120000.sqlite",
    ]


@pytest.mark.expects_errors
def test_a_copy_that_cannot_be_made_leaves_the_earlier_one_and_a_disk_without_room_stops_the_migration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / DB_NAME
    opened(path).close()
    folder = tmp_path / "backup"
    folder.mkdir()
    earlier = folder / "premigrate-v3-to-v4-20260101-000000.sqlite"
    earlier.write_bytes(b"the only copy there is")
    with_steps(monkeypatch, v_next)
    size = path.stat().st_size
    monkeypatch.setattr("neoaprs.migrations.shutil.disk_usage", lambda _: types.SimpleNamespace(free=size))
    ok, why = try_open(path, FixedClock())
    assert (
        not ok
        and "has 0 MB free" in why
        and "needs 8 MB" in why
        and "free at least 8 MB" in why
        and "nothing was changed" in why
    ), why
    assert earlier.read_bytes() == b"the only copy there is" and [p.name for p in folder.iterdir()] == [earlier.name]
    db = raw(path)
    assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION, "and the file is as it was"
    db.close()
    monkeypatch.setattr("neoaprs.migrations.shutil.disk_usage", lambda _: types.SimpleNamespace(free=10**12))
    ok, why = try_open(path, FixedClock())
    assert ok, why
    assert [p.name for p in folder.iterdir()] == [f"premigrate-v{SCHEMA_VERSION}-to-v{NEXT}-20261021-120000.sqlite"]


def test_a_file_that_migration_32_has_yet_to_rewrite_needs_its_size_twice_beside_the_margin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Migration 32 writes the packet table again where it lies, and until it is committed the
    write-ahead log holds the table once more (0.92 of a gigabyte's file, scripts/migration-size):
    below version 32 the disk needs the file's size for the copy and once more for that log; from 32
    on the copy alone."""
    db = sqlite3.connect(tmp_path / DB_NAME)
    db.execute("CREATE TABLE packet (raw BLOB)")
    db.executemany("INSERT INTO packet (raw) VALUES (?)", [(bytes(4000),)] * 100)
    db.commit()
    size = int(db.execute("PRAGMA page_count").fetchone()[0]) * int(db.execute("PRAGMA page_size").fetchone()[0])
    room = {"free": 2 * size + COPY_MARGIN_BYTES - 1}
    monkeypatch.setattr("neoaprs.migrations.shutil.disk_usage", lambda _: types.SimpleNamespace(free=room["free"]))
    with pytest.raises(
        StoreError,
        match="the migration needs .* MB there for the copy of the database it makes first and for the database's log",
    ):
        _require_room(db, tmp_path, 30)
    _require_room(db, tmp_path, 32)
    _require_room(db, tmp_path, 33)
    with pytest.raises(StoreError, match="MB free"):
        _require_room(db, tmp_path, 31)
    room["free"] += 1
    _require_room(db, tmp_path, 31)
    room["free"] = size + COPY_MARGIN_BYTES - 1
    with pytest.raises(StoreError, match="MB free"):
        _require_room(db, tmp_path, 33)
    db.close()


@pytest.mark.expects_errors
def test_a_migration_that_fails_changes_nothing_and_the_file_is_refused_with_the_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / DB_NAME
    opened(path).close()
    folder = tmp_path / "backup"
    folder.mkdir()
    (folder / "premigrate-v22-to-v23-20260101-000000.sqlite").write_bytes(
        b"the copy at the old version, made by the migration before"
    )
    with_steps(monkeypatch, v_next, broken)
    ok, why = try_open(path)
    assert not ok and "the disk is full" in why
    names = sorted(p.name for p in folder.iterdir())
    assert (
        names[0] == "premigrate-v22-to-v23-20260101-000000.sqlite"
        and len(names) == 2
        and names[1].startswith(f"premigrate-v{SCHEMA_VERSION}-to-v{NEXT + 1}-")
    ), (
        "a migration that did not get through removes no copy: the one at the old version is the way back, and this run's copy is of the file as it was at the start"
    )
    db = raw(path)
    assert db.execute("PRAGMA user_version").fetchone()[0] == NEXT, (
        "every step is a transaction of its own: the first is in, the failing step is rolled back and the file stays at the version it had"
    )
    names = {r[0] for r in db.execute("SELECT name FROM sqlite_master")}
    assert "beacon" in names and "half" not in names
    db.close()


@pytest.mark.expects_errors
def test_the_copy_at_the_old_version_outlives_the_start_that_ends_a_migration_cut_short(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A migration cut short leaves the file at a middle version, which no release opens: the start
    that gets through stands on the copy taken at the old version, makes none of the middle version,
    says so, and keeps that one copy; the migration before's goes."""
    path = tmp_path / DB_NAME
    s = opened(path)
    s.db.execute("INSERT INTO settings (key, value) VALUES ('station/call', 'OH2GBA')")
    s.close()
    folder = tmp_path / "backup"
    folder.mkdir()
    (folder / "premigrate-v22-to-v23-20260101-000000.sqlite").write_bytes(b"the copy of the migration before")
    clock = FixedClock()
    with_steps(monkeypatch, v_next, broken)
    ok, why = try_open(path, clock)
    assert not ok and "the disk is full" in why
    first = folder / f"premigrate-v{SCHEMA_VERSION}-to-v{NEXT + 1}-20261021-120000.sqlite"
    assert first.is_file()
    with_steps(monkeypatch, v_next, mended)
    clock.advance(60)
    caplog.set_level(logging.INFO, MIGRATION_LOG)
    ok, why = try_open(path, clock)
    assert ok, why
    assert any(
        r.getMessage().endswith(f"{first}, taken by a start that did not get through; no other is made")
        for r in caplog.records
    )
    assert sorted(p.name for p in folder.iterdir()) == [first.name], (
        "the copy at the old version is the one kept: none of the middle version was made, and the migration before's goes"
    )
    copy = raw(first)
    assert copy.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION and copy.execute(
        "SELECT value FROM settings"
    ).fetchall() == [("OH2GBA",)], "and it holds the file as the program before left it"
    assert copy.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'beacon'").fetchone() == (0,)
    copy.close()


def made_copy(source: Path, dest: Path) -> None:
    """A copy of the database at `source` as the migrations make one (dbfile.copy_database)."""
    from neoaprs.dbfile import copy_database

    db = raw(source)
    try:
        copy_database(db, dest)
    finally:
        db.close()


def test_a_copy_is_whole_by_its_header_and_a_half_written_or_changed_one_is_not(tmp_path: Path) -> None:
    from neoaprs.backupfolder import whole

    path = tmp_path / DB_NAME
    s = opened(path)
    s.db.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", [(f"k/{i}", "x" * 500) for i in range(200)])
    s.close()
    folder = tmp_path / "backup"
    good = folder / f"premigrate-v{SCHEMA_VERSION}-to-v{NEXT}-20261021-120000.sqlite"
    made_copy(path, good)
    assert whole(good, SCHEMA_VERSION)
    assert not whole(good, SCHEMA_VERSION - 1), "a copy of another version than its name says is not the copy it names"
    data = good.read_bytes()
    cut = folder / "cut.sqlite"
    cut.write_bytes(data[: len(data) // 2])
    assert not whole(cut, SCHEMA_VERSION), (
        "a file cut short (a copy somebody copied half of, a disk that lost its end) is not whole"
    )
    odd = folder / "odd.sqlite"
    odd.write_bytes(data + b"\x00" * 10)
    assert not whole(odd, SCHEMA_VERSION)
    (folder / "junk.sqlite").write_bytes(b"x")
    assert not whole(folder / "junk.sqlite", SCHEMA_VERSION) and not whole(folder / "absent.sqlite", SCHEMA_VERSION)
    journal = good.with_name(good.name + "-journal")
    journal.write_bytes(b"")
    assert not whole(good, SCHEMA_VERSION), "a copy with a journal of its own beside it is being changed"
    journal.unlink()
    assert whole(good, SCHEMA_VERSION)


def test_a_start_that_finds_the_file_as_a_whole_copy_holds_it_makes_no_second_one_and_a_changed_file_gets_a_new_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The first step fails twice (nothing of the migration is in): the second start finds the file
    at the version it was copied at, unchanged, and makes no copy (a machine killed again and again
    does not fill its disk with copies); the file is then changed at that version (the NeoAPRS
    before ran on it again), and the next start copies it anew and keeps only that copy once it gets
    through."""
    path = tmp_path / DB_NAME
    s = opened(path)
    s.db.execute("INSERT INTO settings (key, value) VALUES ('station/call', 'OH2GBA')")
    s.close()
    folder = tmp_path / "backup"
    clock = FixedClock()
    with_steps(monkeypatch, broken)
    assert not try_open(path, clock)[0]
    [first] = sorted(folder.iterdir())
    caplog.set_level(logging.INFO, MIGRATION_LOG)
    clock.advance(60)
    assert not try_open(path, clock)[0]
    assert sorted(folder.iterdir()) == [first], "no second copy of the same file"
    said = [r.getMessage() for r in caplog.records if "the copy of it from before this migration" in r.getMessage()]
    assert len(said) == 1 and said[0].endswith("and the file has not changed since it was taken; no other is made"), (
        "(true also of the copy put back by `neoaprs db restore`, where no start was cut short)"
    )
    db = raw(path)
    db.execute("UPDATE settings SET value = 'OH2GBA-7' WHERE key = 'station/call'")
    db.close()
    clock.advance(60)
    assert not try_open(path, clock)[0]
    copies = sorted(folder.iterdir())
    assert len(copies) == 2 and copies[0] == first, "the file is not what the copy holds any more: a new copy"
    with_steps(monkeypatch, mended)
    clock.advance(60)
    ok, why = try_open(path, clock)
    assert ok, why
    assert sorted(folder.iterdir()) == [copies[1]], (
        "the newer copy is the file as the program before left it; the stale one goes"
    )
    copy = raw(copies[1])
    assert copy.execute("SELECT value FROM settings").fetchall() == [("OH2GBA-7",)]
    copy.close()


def test_a_copy_that_is_not_whole_a_temporary_one_and_one_made_by_hand_are_never_stood_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Beside a file of the version for this migration: a copy under its name cut short, the whole
    temporary file of a copy that was never renamed, a copy made by hand of the same file; the start
    makes a copy of its own, and the end of the migration removes the copy that was not whole and
    leaves the hand's and the temporary one, which another migration that runs may be writing (the
    sweep takes it once it is old)."""
    path = tmp_path / DB_NAME
    s = opened(path)
    s.db.execute("INSERT INTO settings (key, value) VALUES ('station/call', 'OH2GBA')")
    s.close()
    folder = tmp_path / "backup"
    stem = f"premigrate-v{SCHEMA_VERSION}-to-v{NEXT}"
    whole_one = folder / "by-hand.sqlite"
    made_copy(path, whole_one)
    half = folder / f"{stem}-20261020-120000.sqlite"
    half.write_bytes(whole_one.read_bytes()[:4096])
    unnamed = folder / f"{stem}-20261020-130000.sqlite.tmp"
    unnamed.write_bytes(whole_one.read_bytes())
    # Another migration runs: the temporary file may be its copy being written
    (tmp_path / MIGRATING_NAME).write_text("migrating\n", encoding="ascii")
    with_steps(monkeypatch, v_next)
    ok, why = try_open(path, FixedClock())
    assert ok, why
    assert sorted(p.name for p in folder.iterdir()) == [
        "by-hand.sqlite",
        f"{stem}-20261020-130000.sqlite.tmp",
        f"{stem}-20261021-120000.sqlite",
    ]


def test_a_migration_that_stands_on_a_copy_needs_room_for_the_log_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = sqlite3.connect(tmp_path / DB_NAME)
    db.execute("CREATE TABLE packet (raw BLOB)")
    db.executemany("INSERT INTO packet (raw) VALUES (?)", [(bytes(4000),)] * 100)
    db.commit()
    size = int(db.execute("PRAGMA page_count").fetchone()[0]) * int(db.execute("PRAGMA page_size").fetchone()[0])
    room = {"free": size + COPY_MARGIN_BYTES}
    monkeypatch.setattr("neoaprs.migrations.shutil.disk_usage", lambda _: types.SimpleNamespace(free=room["free"]))
    _require_room(db, tmp_path, 31, copy=False)
    room["free"] -= 1
    with pytest.raises(
        StoreError, match="needs .* MB there for the database's log while it runs; .*taken before this migration stays"
    ):
        _require_room(db, tmp_path, 31, copy=False)
    room["free"] = COPY_MARGIN_BYTES
    _require_room(db, tmp_path, 32, copy=False)
    with pytest.raises(StoreError, match="for the copy of the database it makes first"):
        _require_room(db, tmp_path, 32)
    db.close()


def test_the_copy_the_program_before_opens_is_the_one_the_latest_migration_stands_on(tmp_path: Path) -> None:
    from neoaprs.backupfolder import before_copy

    path = tmp_path / DB_NAME
    opened(path).close()
    folder = tmp_path / "backup"
    assert before_copy(folder) is None
    for name in (
        "premigrate-v29-to-v30-20261001-120000.sqlite",
        f"premigrate-v{SCHEMA_VERSION}-to-v{NEXT}-20261101-120000.sqlite",
        f"premigrate-v{SCHEMA_VERSION}-to-v{NEXT}-20261102-120000.sqlite",
        "mine.sqlite",
    ):
        made_copy(path, folder / name)
    db = raw(folder / "premigrate-v29-to-v30-20261001-120000.sqlite")
    db.execute("PRAGMA user_version = 29")
    db.close()
    (folder / f"premigrate-v{NEXT}-to-v{NEXT + 1}-20261103-120000.sqlite").write_bytes(b"not whole")
    found = before_copy(folder)
    assert found is not None and found.path.name == f"premigrate-v{SCHEMA_VERSION}-to-v{NEXT}-20261102-120000.sqlite"


def premigration_names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir() if p.name.startswith("premigrate-"))


def held(copy: Path) -> tuple[int, list[tuple[str, ...]], list[str]]:
    """A copy, read only: its version, its settings, the tables of the made-up steps in it."""
    db = sqlite3.connect(f"{copy.as_uri()}?mode=ro", uri=True)
    try:
        return (
            int(db.execute("PRAGMA user_version").fetchone()[0]),
            db.execute("SELECT value FROM settings ORDER BY key").fetchall(),
            [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE name IN ('beacon', 'half')")],
        )
    finally:
        db.close()


def a_station(path: Path, clock: FixedClock | None = None) -> None:
    s = opened(path, clock or FixedClock())
    s.db.execute("INSERT INTO settings (key, value) VALUES ('station/call', 'OH2GBA')")
    s.close()


@pytest.mark.parametrize("when", ["while the copy is written", "between the reading of the version and the copy"])
def test_another_neoaprs_that_migrates_the_file_meanwhile_leaves_one_whole_copy_of_the_old_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, when: str
) -> None:
    """`neoaprs db set`, a second daemon or the app migrate the file themselves (the daemon may be
    running): one runs the whole migration while the other is copying the file (page by page, as on
    a slow card: sqlite3's backup starts again when another connection writes the file) or has read
    its version and is about to copy it. The other's copy is the file at the version its name says,
    or it makes none; at the end backup/ holds one copy, whole, of the old version with the settings
    as they were."""
    from neoaprs import dbfile

    path = tmp_path / DB_NAME
    a_station(path)
    with_steps(monkeypatch, v_next)
    real_room = migrations_module._require_room
    state = {"inner": False, "done": False}

    def the_other_migrates() -> None:
        if not state["done"] and not state["inner"]:
            state["done"] = state["inner"] = True
            try:
                ok, why = try_open(path)
                assert ok, why
            finally:
                state["inner"] = False

    if when == "while the copy is written":

        def slow_copy(src: sqlite3.Connection, dest: Path) -> None:
            if state["inner"]:
                dbfile.copy_database(src, dest)
                return
            tmp = dest.with_name(dest.name + ".tmp")
            out = sqlite3.connect(tmp)
            try:
                src.backup(out, pages=1, progress=lambda *_: the_other_migrates())
                out.execute("PRAGMA journal_mode=DELETE")
            finally:
                out.close()
            tmp.replace(dest)

        monkeypatch.setattr(migrations_module, "_copy_database", slow_copy)
    else:

        def room(db: sqlite3.Connection, folder: Path, version: int = SCHEMA_VERSION, *, copy: bool = True) -> None:
            real_room(db, folder, version, copy=copy)
            the_other_migrates()

        monkeypatch.setattr(migrations_module, "_require_room", room)
    ok, why = try_open(path)
    assert ok, why
    assert state["done"], "the other ran"
    [kept] = premigration_names(tmp_path / "backup")
    assert kept.startswith(f"premigrate-v{SCHEMA_VERSION}-to-v{NEXT}-") and held(tmp_path / "backup" / kept) == (
        SCHEMA_VERSION,
        [("OH2GBA",)],
        [],
    )


@pytest.mark.expects_errors
def test_a_clock_that_went_back_after_the_copy_does_not_make_the_start_after_a_cut_copy_the_middle_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Raspberry Pi without a clock of its own: the copy is named by the time before a power cut,
    the step after it is written an hour earlier (the clock restored at the boot), and the next step
    fails. That the file came from the copy is read from both histories, not from the clock: the
    start that gets through makes no copy of the middle version and keeps the one of the old
    version."""
    path = tmp_path / DB_NAME
    a_station(path)
    folder = tmp_path / "backup"
    folder.mkdir()
    (folder / "premigrate-v22-to-v23-20260101-000000.sqlite").write_bytes(b"the copy of the migration before")
    clock = FixedClock()
    real_copy = migrations_module._copy_database

    def copy_then_the_clock_goes_back(src: sqlite3.Connection, dest: Path) -> None:
        real_copy(src, dest)
        clock.advance(-3600)

    monkeypatch.setattr(migrations_module, "_copy_database", copy_then_the_clock_goes_back)
    with_steps(monkeypatch, v_next, broken)
    ok, why = try_open(path, clock)
    assert not ok and "the disk is full" in why
    first = f"premigrate-v{SCHEMA_VERSION}-to-v{NEXT + 1}-20261021-120000.sqlite"
    assert first in premigration_names(folder)
    with_steps(monkeypatch, v_next, mended)
    clock.advance(60)
    ok, why = try_open(path, clock)
    assert ok, why
    assert premigration_names(folder) == [first], (
        "no copy of the middle version; the one of the old version is kept, the migration before's goes"
    )
    assert held(folder / first) == (SCHEMA_VERSION, [("OH2GBA",)], [])


@pytest.mark.expects_errors
def test_a_copy_taken_after_the_clock_went_back_is_named_after_the_one_before_and_is_the_one_stood_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first step fails (the file stays at its version, copied); the NeoAPRS before writes to
    it; the clock goes back an hour; the next start copies the changed file, gets one step further
    and is cut short. A copy of the same migration is named after the ones there are, so the start
    that gets through stands on the copy taken last, which holds what the NeoAPRS before wrote."""
    from neoaprs.backupfolder import taken_copies

    path = tmp_path / DB_NAME
    a_station(path)
    folder = tmp_path / "backup"
    clock = FixedClock()
    gate = {"fail": True}

    def first_step(db: sqlite3.Connection) -> None:
        db.execute("CREATE TABLE beacon (id INTEGER PRIMARY KEY)")
        if gate["fail"]:
            raise sqlite3.OperationalError("the disk is full")

    with_steps(monkeypatch, first_step, broken)
    assert not try_open(path, clock)[0]
    [one] = premigration_names(folder)
    db = raw(path)
    db.execute("UPDATE settings SET value = 'OH2GBA-7' WHERE key = 'station/call'")
    db.close()
    clock.advance(-3600)
    gate["fail"] = False
    assert not try_open(path, clock)[0]
    assert len(premigration_names(folder)) == 2 and taken_copies(folder)[0].path.name != one, (
        "the copy taken last is the newest by its name, whatever the clock said"
    )
    with_steps(monkeypatch, first_step, mended)
    clock.advance(60)
    ok, why = try_open(path, clock)
    assert ok, why
    [kept] = premigration_names(folder)
    assert kept != one and held(folder / kept) == (SCHEMA_VERSION, [("OH2GBA-7",)], [])


@pytest.mark.expects_errors
def test_a_copy_the_file_did_not_come_from_is_not_stood_on_and_not_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The file is at a middle version and backup/ holds a whole copy of the old version for the
    same migration, but of another file (another station's database, one the operator moved in): its
    history is not the file's. The start makes its own copy of the middle version, and the end of
    the migration leaves the other one, which the file may be thought to have come from."""
    path = tmp_path / DB_NAME
    a_station(path)
    other = tmp_path / "other" / DB_NAME
    other.parent.mkdir()
    a_station(other, FixedClock(FixedClock().now.replace(year=2025)))
    with_steps(monkeypatch, v_next, broken)
    assert not try_open(path)[0]
    folder = tmp_path / "backup"
    [own] = premigration_names(folder)
    (folder / own).unlink()
    made_copy(other, folder / own)
    with_steps(monkeypatch, v_next, mended)
    ok, why = try_open(path)
    assert ok, why
    names = premigration_names(folder)
    assert (
        own in names and len(names) == 2 and any(n.startswith(f"premigrate-v{NEXT}-to-v{NEXT + 1}-") for n in names)
    ), names


def test_the_end_of_a_migration_removes_no_copy_when_its_own_is_not_whole_and_never_an_older_one_the_file_may_have_come_from(
    tmp_path: Path,
) -> None:
    from neoaprs.backupfolder import drop_older_copies

    path = tmp_path / DB_NAME
    opened(path).close()
    folder = tmp_path / "backup"

    def at(name: str, version: int) -> str:
        made_copy(path, folder / name)
        db = raw(folder / name)
        db.execute(f"PRAGMA user_version = {version}")
        db.close()
        return name

    earlier = at("premigrate-v29-to-v30-20261001-120000.sqlite", 29)
    older = at("premigrate-v30-to-v35-20261101-120000.sqlite", 30)
    kept = at("premigrate-v31-to-v35-20261102-120000.sqlite", 31)
    middle = at("premigrate-v32-to-v35-20261103-120000.sqlite", 32)
    cut = "premigrate-v30-to-v35-20261031-120000.sqlite"
    (folder / cut).write_bytes(b"not whole")
    made_copy(path, folder / "mine.sqlite")
    assert sorted(drop_older_copies(folder, kept)) == sorted([earlier, middle, cut])
    assert sorted(p.name for p in folder.iterdir()) == sorted(["mine.sqlite", older, kept]), (
        "a whole copy of an older version, taken by a migration that went past the kept one's version, stays: the file may have come from it"
    )
    middle = at(middle, 32)
    at(kept, 33)
    assert drop_older_copies(folder, kept) == [], (
        "a copy that is not the file at the version its name says is no reason to remove the others"
    )
    assert (folder / middle).is_file()


@pytest.mark.expects_errors
def test_a_disk_short_of_room_because_of_what_a_killed_copy_left_waits_until_that_is_dead_and_migrates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A kill while the copy was written leaves its temporary file, up to the size of the database,
    and the restart comes seconds later (a reboot): the sweep keeps a file that young. On a disk
    with room for the migration but not for that file too, the start would be refused, and the unit
    does not start a refused daemon again. It waits until the file has been still long enough to be
    dead, removes it and migrates; a temporary file that changes meanwhile (another process writes
    its copy) stays and the refusal stands."""
    import os
    from neoaprs.backupfolder import LITTER_AGE_SEC

    path = tmp_path / DB_NAME
    a_station(path)
    folder = tmp_path / "backup"
    folder.mkdir()
    db = raw(path)
    need = (
        int(db.execute("PRAGMA page_count").fetchone()[0]) * int(db.execute("PRAGMA page_size").fetchone()[0])
        + COPY_MARGIN_BYTES
    )
    db.close()

    def used() -> int:
        return sum(f.stat().st_size for f in tmp_path.rglob("*") if f.is_file())

    cap = used() + need + 2 * MIB
    monkeypatch.setattr("neoaprs.migrations.shutil.disk_usage", lambda _: types.SimpleNamespace(free=cap - used()))
    litter = folder / f"premigrate-v{SCHEMA_VERSION}-to-v{NEXT}-20261021-115959.sqlite.tmp"
    litter.write_bytes(bytes(4 * MIB))
    waits: list[float] = []

    def written_meanwhile(seconds: float) -> None:
        waits.append(seconds)
        with open(litter, "ab") as f:
            f.write(b"more")

    monkeypatch.setattr(migrations_module, "_sleep", written_meanwhile)
    with_steps(monkeypatch, v_next)
    note = tmp_path / MIGRATING_NAME
    # The note of the start a kill ended seconds ago is fresh: the temporary file may be somebody's
    note.write_text("migrating\n", encoding="ascii")
    ok, why = try_open(path)
    assert not ok and "MB free" in why and litter.exists() and len(waits) == 1, why
    os.truncate(litter, 4 * MIB)
    note.write_text("migrating\n", encoding="ascii")
    monkeypatch.setattr(migrations_module, "_sleep", waits.append)
    ok, why = try_open(path)
    assert ok, why
    assert 0 < waits[1] <= LITTER_AGE_SEC + 1 and not litter.exists()
    [kept] = premigration_names(folder)
    assert held(folder / kept) == (SCHEMA_VERSION, [("OH2GBA",)], [])


def test_a_start_while_no_other_migration_runs_removes_what_a_killed_copy_left_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every migration keeps its note fresh from before its copy to its end: with no fresh note, the
    temporary file of a copy in backup/ is of a start a kill ended, however young, and the start
    that migrates removes it before it copies, without waiting (a station killed again and again in
    its copy does not gather them)."""
    path = tmp_path / DB_NAME
    a_station(path)
    folder = tmp_path / "backup"
    folder.mkdir()
    left = [
        folder / f"premigrate-v{SCHEMA_VERSION}-to-v{NEXT}-20261021-115959.sqlite.tmp",
        folder / f"premigrate-v{SCHEMA_VERSION}-to-v{NEXT}-20261021-115959.sqlite.tmp-journal",
    ]
    for f in left:
        f.write_bytes(b"what a kill left")
    waits: list[float] = []
    monkeypatch.setattr(migrations_module, "_sleep", waits.append)
    with_steps(monkeypatch, v_next)
    ok, why = try_open(path)
    assert ok, why
    assert not any(f.exists() for f in left) and waits == [] and len(premigration_names(folder)) == 1


@pytest.mark.expects_errors
def test_a_migration_that_cannot_be_copied_first_is_not_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / DB_NAME
    opened(path).close()
    (tmp_path / "backup").write_text("a file where the folder should be")
    with_steps(monkeypatch, v_next)
    ok, why = try_open(path)
    assert not ok and "nothing was changed" in why
    db = raw(path)
    assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    db.close()


def test_history_records_when_and_what_and_flags_a_migration_that_was_edited_since(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / DB_NAME
    clock = FixedClock()
    s = opened(path, clock)
    rows = s.history()
    assert [(r[0], r[1], r[2], r[3], r[4]) for r in rows] == [
        (1, "_v1", GOLDEN[1], clock.now, ""),
        (2, "_v2", GOLDEN[2], clock.now, ""),
        (3, "_v3", GOLDEN[3], clock.now, ""),
        (4, "_v4", GOLDEN[4], clock.now, ""),
        (5, "_v5", GOLDEN[5], clock.now, ""),
        (6, "_v6", GOLDEN[6], clock.now, ""),
        (7, "_v7", GOLDEN[7], clock.now, ""),
        (8, "_v8", GOLDEN[8], clock.now, ""),
        (9, "_v9", GOLDEN[9], clock.now, ""),
        (10, "_v10", GOLDEN[10], clock.now, ""),
        (11, "_v11", GOLDEN[11], clock.now, ""),
        (12, "_v12", GOLDEN[12], clock.now, ""),
        (13, "_v13", GOLDEN[13], clock.now, ""),
        (14, "_v14", GOLDEN[14], clock.now, ""),
        (15, "_v15", GOLDEN[15], clock.now, ""),
        (16, "_v16", GOLDEN[16], clock.now, ""),
        (17, "_v17", GOLDEN[17], clock.now, ""),
        (18, "_v18", GOLDEN[18], clock.now, ""),
        (19, "_v19", GOLDEN[19], clock.now, ""),
        (20, "_v20", GOLDEN[20], clock.now, ""),
        (21, "_v21", GOLDEN[21], clock.now, ""),
        (22, "_v22", GOLDEN[22], clock.now, ""),
        (23, "_v23", GOLDEN[23], clock.now, ""),
        (24, "_v24", GOLDEN[24], clock.now, ""),
        (25, "_v25", GOLDEN[25], clock.now, ""),
        (26, "_v26", GOLDEN[26], clock.now, ""),
        (27, "_v27", GOLDEN[27], clock.now, ""),
        (28, "_v28", GOLDEN[28], clock.now, ""),
        (29, "_v29", GOLDEN[29], clock.now, ""),
        (30, "_v30", GOLDEN[30], clock.now, ""),
        (31, "_v31", GOLDEN[31], clock.now, ""),
        (32, "_v32", GOLDEN[32], clock.now, ""),
        (33, "_v33", GOLDEN[33], clock.now, ""),
        (34, "_v34", GOLDEN[34], clock.now, ""),
        (35, "_v35", GOLDEN[35], clock.now, ""),
        (36, "_v36", GOLDEN[36], clock.now, ""),
        (37, "_v37", GOLDEN[37], clock.now, ""),
    ]
    s.close()
    caplog.set_level(logging.WARNING, MIGRATION_LOG)
    opened(path).close()
    assert not [r for r in caplog.records if "source has changed" in r.getMessage()]
    tampered = raw(path)
    tampered.execute("UPDATE schema_history SET sha256 = 'f' || substr(sha256, 2) WHERE version = 1")
    tampered.close()
    opened(path).close()
    assert any("migration 1 (_v1)" in r.getMessage() and "source has changed" in r.getMessage() for r in caplog.records)


def test_a_history_row_of_a_step_this_program_does_not_know_is_told(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / DB_NAME
    opened(path).close()
    db = raw(path)
    db.execute("INSERT INTO schema_history (version, name, sha256, applied) VALUES (?, ?, 'x', 0)", (NEXT, f"_v{NEXT}"))
    db.close()
    caplog.set_level(logging.WARNING, MIGRATION_LOG)
    opened(path).close()
    assert any(f"a step {NEXT} that this NeoAPRS does not know" in r.getMessage() for r in caplog.records)


def test_the_litter_of_a_copy_that_a_kill_ended_is_swept_at_the_open(tmp_path: Path) -> None:
    import os

    path = tmp_path / DB_NAME
    clock = FixedClock()
    folder = tmp_path / "backup"
    folder.mkdir()
    old, fresh = folder / "premigrate-x.sqlite.tmp", folder / "other.sqlite.tmp"
    old.write_bytes(b"x")
    fresh.write_bytes(b"x")
    stamp = clock().timestamp()
    os.utime(old, (stamp - 3600, stamp - 3600))
    os.utime(fresh, (stamp - 10, stamp - 10))
    opened(path, clock).close()
    assert not old.exists() and fresh.exists(), (
        "a temporary file older than five minutes goes; one that may be being written stays"
    )


# ---- migration 2: the packets and the stations


def version_one(path: Path, clock: FixedClock) -> None:
    """A database at schema version 1: the settings table with rows, the history with its one step,
    user_version 1."""
    db = raw(path)
    migrations_module._v1(db)
    db.execute("PRAGMA user_version = 1")
    db.execute(
        "INSERT INTO schema_history (version, name, sha256, applied) VALUES (1, '_v1', ?, ?)",
        (GOLDEN[1], int(clock().timestamp())),
    )
    for key, value in [
        ("station/call", "OH2GBA"),
        ("station/lat", "60.17"),
        ("serial/port", "/dev/brainbox_3"),
        ("web/port", "7303"),
    ]:
        db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))
    db.execute("UPDATE settings SET rev = 4 WHERE key = 'station/lat'")
    db.close()


def shape(db: sqlite3.Connection) -> list[tuple[str, str, str | None]]:
    return [
        (str(t), str(n), q) for t, n, q in db.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name")
    ]


def test_a_database_of_version_one_gets_the_packet_and_station_tables_and_keeps_its_settings(tmp_path: Path) -> None:
    clock = FixedClock()
    old = tmp_path / "old" / DB_NAME
    old.parent.mkdir()
    version_one(old, clock)
    migrated = opened(old, clock)
    fresh = opened(tmp_path / DB_NAME, clock)
    assert migrated.version() == fresh.version() == SCHEMA_VERSION >= 2
    assert shape(migrated.db) == shape(fresh.db), (
        "a migrated database has exactly the tables, indexes and checks of a new one"
    )
    assert migrated.db.execute("SELECT key, value, rev FROM settings ORDER BY key").fetchall() == [
        ("station/call", "OH2GBA", 1),
        ("station/lat", "60.17", 4),
        ("web/port", "7303", 1),
    ]
    assert migrated.db.execute("SELECT radio_id, key, value, rev FROM radio_setting").fetchall() == [
        (1, "port", "/dev/brainbox_3", 1)
    ], "the port is the FM radio's own setting since migration 31, with its value and revision"
    assert [(r[0], r[1]) for r in migrated.history()] == [
        (1, "_v1"),
        (2, "_v2"),
        (3, "_v3"),
        (4, "_v4"),
        (5, "_v5"),
        (6, "_v6"),
        (7, "_v7"),
        (8, "_v8"),
        (9, "_v9"),
        (10, "_v10"),
        (11, "_v11"),
        (12, "_v12"),
        (13, "_v13"),
        (14, "_v14"),
        (15, "_v15"),
        (16, "_v16"),
        (17, "_v17"),
        (18, "_v18"),
        (19, "_v19"),
        (20, "_v20"),
        (21, "_v21"),
        (22, "_v22"),
        (23, "_v23"),
        (24, "_v24"),
        (25, "_v25"),
        (26, "_v26"),
        (27, "_v27"),
        (28, "_v28"),
        (29, "_v29"),
        (30, "_v30"),
        (31, "_v31"),
        (32, "_v32"),
        (33, "_v33"),
        (34, "_v34"),
        (35, "_v35"),
        (36, "_v36"),
        (37, "_v37"),
    ] and [r[2] for r in migrated.history()] == [GOLDEN[n] for n in range(1, 38)]
    assert (
        migrated.db.execute("SELECT COUNT(*) FROM packet").fetchone()[0] == 0
        and migrated.db.execute("SELECT COUNT(*) FROM station").fetchone()[0] == 0
    )
    names = {n for _, n, _ in shape(migrated.db)}
    assert {"packet_heard_at", "packet_source"} <= names
    for s in (migrated, fresh):
        s.close()
    copies = sorted((old.parent / "backup").glob("premigrate-v1-to-v*.sqlite"))
    assert len(copies) == 1, "the file that held settings was copied before the step"
    copy = raw(copies[0])
    assert copy.execute("PRAGMA user_version").fetchone()[0] == 1 and "packet" not in {
        r[0] for r in copy.execute("SELECT name FROM sqlite_master")
    }
    copy.close()


# ---- migration 3: the messages


def version_two(path: Path, clock: FixedClock) -> None:
    """A database at schema version 2: the settings, the packets and the stations with rows,
    user_version 2."""
    db = raw(path)
    for number, step in ((1, migrations_module._v1), (2, migrations_module._v2)):
        step(db)
        db.execute(f"PRAGMA user_version = {number}")
        db.execute(
            "INSERT INTO schema_history (version, name, sha256, applied) VALUES (?, ?, ?, ?)",
            (number, step.__name__, GOLDEN[number], int(clock().timestamp())),
        )
    db.execute("INSERT INTO settings (key, value) VALUES ('station/call', 'OH2GBA')")
    db.execute(
        "INSERT INTO packet (heard_at, direction, raw, source, destination, path, kind, summary, decoded) VALUES "
        "('2026-10-21T11:59:00.000000Z', 'in', x'00', 'OH2RDG', 'APN391', 'OH2RCH-2*', 'message', 'message to OH2GBA: hi {7', '{\"type\":\"message\"}')"
    )
    db.execute(
        "INSERT INTO station (call, kind, reported_by, symbol_table, symbol_code, first_heard, last_heard, last_status, last_comment, packets, last_path) VALUES "
        "('OH2RDG', 'station', '', '/', '>', '2026-10-21T11:00:00.000000Z', '2026-10-21T11:59:00.000000Z', '', '', 1, '')"
    )
    db.close()


def test_a_database_of_version_two_gets_the_message_table_and_keeps_its_rows(tmp_path: Path) -> None:
    clock = FixedClock()
    old = tmp_path / "old" / DB_NAME
    old.parent.mkdir()
    version_two(old, clock)
    migrated = opened(old, clock)
    fresh = opened(tmp_path / DB_NAME, clock)
    assert migrated.version() == fresh.version() == SCHEMA_VERSION >= 3
    assert shape(migrated.db) == shape(fresh.db), (
        "a migrated database has exactly the tables, indexes and checks of a new one"
    )
    assert {"message_calls", "station_pref"} <= {n for _, n, _ in shape(migrated.db)}
    assert migrated.db.execute("SELECT COUNT(*) FROM station_pref").fetchone()[0] == 0
    assert migrated.db.execute("SELECT COUNT(*) FROM message").fetchone()[0] == 0
    assert migrated.db.execute("SELECT key, value FROM settings").fetchall() == [("station/call", "OH2GBA")]
    assert migrated.db.execute("SELECT source, kind FROM packet").fetchall() == [
        ("OH2RDG", "message")
    ] and migrated.db.execute("SELECT call FROM station").fetchall() == [("OH2RDG",)]
    assert [(r[0], r[1]) for r in migrated.history()][2:3] == [(3, "_v3")] and migrated.history()[2][2] == GOLDEN[3]
    for s in (migrated, fresh):
        s.close()
    [copy_path] = sorted((old.parent / "backup").glob("premigrate-v2-to-v*.sqlite"))
    copy = raw(copy_path)
    assert copy.execute("PRAGMA user_version").fetchone()[0] == 2 and "message" not in {
        r[0] for r in copy.execute("SELECT name FROM sqlite_master")
    }
    copy.close()


GOOD = ("2026-10-21T12:00:00.000000Z", "out", "OH2GBA", "OH2RDG", "hello", "12", "sending", 0, None, None)
INSERT_MESSAGE = "INSERT INTO message (at, direction, from_call, to_call, text, msg_id, state, attempts, last_attempt_at, acked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"


@pytest.mark.parametrize(
    "change, name",
    [
        ({0: "yesterday"}, "message_at_form"),
        ({1: "sideways"}, "message_direction"),
        ({2: ""}, "message_from_present"),
        ({3: ""}, "message_to_present"),
        ({5: "123456"}, "message_msg_id_form"),
        ({5: "a b"}, "message_msg_id_form"),
        ({5: ""}, "message_msg_id_form"),
        ({6: "lost"}, "message_state"),
        ({7: -1}, "message_attempts_count"),
        ({8: "noon"}, "message_last_attempt_form"),
        ({9: "later"}, "message_acked_at_form"),
        ({1: "in"}, "message_in_when_heard"),
        ({6: "received"}, "message_in_when_heard"),
        ({6: "overheard"}, "message_in_when_heard"),
        ({4: None}, "NOT NULL"),
        ({7: "many"}, "cannot store"),
    ],
)
def test_the_message_table_refuses_what_the_program_cannot_produce(
    tmp_path: Path, change: dict[int, object], name: str
) -> None:
    s = opened(tmp_path / DB_NAME)
    row = list(GOOD)
    for index, value in change.items():
        row[index] = value
    with pytest.raises(sqlite3.IntegrityError, match=name):
        s.db.execute(INSERT_MESSAGE, row)
    s.close()


def test_the_message_table_takes_what_the_program_produces_and_the_index_serves_a_conversation(tmp_path: Path) -> None:
    s = opened(tmp_path / DB_NAME)
    s.db.execute(INSERT_MESSAGE, GOOD)
    s.db.execute(
        INSERT_MESSAGE, ("2026-10-21T12:01:00.000000Z", "in", "OH2RDG", "OH2GBA", "hi", None, "received", 0, None, None)
    )
    s.db.execute(
        INSERT_MESSAGE,
        ("2026-10-21T12:01:30.000000Z", "in", "OH2AAA", "OH2BBB", "overheard text", "9", "overheard", 0, None, None),
    )
    s.db.execute(
        INSERT_MESSAGE,
        (
            "2026-10-21T12:02:00.000000Z",
            "out",
            "OH2GBA",
            "OH2RDG",
            "again",
            "00013",
            "acked",
            2,
            "2026-10-21T12:02:30.000000Z",
            "2026-10-21T12:03:00.000000Z",
        ),
    )
    assert s.db.execute("SELECT id, state FROM message ORDER BY id").fetchall() == [
        (1, "sending"),
        (2, "received"),
        (3, "overheard"),
        (4, "acked"),
    ]
    plan = " ".join(
        str(r)
        for r in s.db.execute(
            "EXPLAIN QUERY PLAN SELECT id FROM message WHERE to_call = 'OH2RDG' AND from_call = 'OH2GBA' ORDER BY at"
        )
    )
    assert "message_calls" in plan
    s.close()


def say(db: sqlite3.Connection, call: object, path: object, hide: object, stamp: object) -> None:
    """What a row of PREF_INSERT said of a station, said to a database of now: the timeout is a row
    of `station_pref` (and so is a station of which nothing is said, for the table to refuse), the
    path the station's path on radio 1 in `station_path` (migration 33)."""
    if hide is not None or path is None:
        db.execute("INSERT INTO station_pref (call, hide_after_min, updated_at) VALUES (?, ?, ?)", (call, hide, stamp))
    if path is not None:
        db.execute(
            "INSERT INTO station_path (call, radio_id, path, updated_at) VALUES (?, 1, ?, ?)", (call, path, stamp)
        )


# A row of the versions before 33, where the path was a column of the table
PREF_INSERT = "INSERT INTO station_pref (call, path, hide_after_min, updated_at) VALUES (?, ?, ?, ?)"
STAMP = "2026-10-21T12:00:00.000000Z"


@pytest.mark.parametrize(
    "path, hide",
    [
        ("", None),
        ("WIDE1-1", None),
        ("WIDE1-1,WIDE2-1", 0),
        ("OH2RCH-2,WIDE2-2", 180),
        (None, 0),
        (None, 10080),
        ("", 1),
    ],
)
def test_the_station_pref_table_takes_a_path_a_timeout_or_both_and_an_empty_path_is_not_none(
    tmp_path: Path, path: str | None, hide: int | None
) -> None:
    s = opened(tmp_path / DB_NAME)
    say(s.db, "OH2RDG", path, hide, STAMP)
    assert s.db.execute(f"SELECT call, path, hide_after_min FROM {SAID}").fetchall() == [("OH2RDG", path, hide)]
    s.close()


@pytest.mark.parametrize(
    "row, name",
    [
        (("", "WIDE1-1", None, STAMP), "station_path_call_present"),
        (("", None, 5, STAMP), "station_pref_call_present"),
        (("OH2RDG", "wide1-1", None, STAMP), "station_path_form"),
        (("OH2RDG", "WIDE1-1,,WIDE2-1", None, STAMP), "station_path_form"),
        (("OH2RDG", ",WIDE1-1", None, STAMP), "station_path_form"),
        (("OH2RDG", "WIDE1-1,", None, STAMP), "station_path_form"),
        (("OH2RDG", "WIDE 1-1", None, STAMP), "station_path_form"),
        (("OH2RDG", None, -1, STAMP), "station_pref_hide_range"),
        (("OH2RDG", None, 10081, STAMP), "station_pref_hide_range"),
        (("OH2RDG", None, "never", STAMP), "cannot store"),
        (("OH2RDG", "WIDE1-1", None, "yesterday"), "station_path_updated_form"),
        (("OH2RDG", None, 5, "yesterday"), "station_pref_updated_form"),
        (("OH2RDG", None, None, STAMP), "station_pref_says_something"),
        (("OH2RDG", None, 5, None), "NOT NULL"),
    ],
)
def test_the_station_pref_table_refuses_what_the_program_cannot_produce(
    tmp_path: Path, row: tuple[object, ...], name: str
) -> None:
    s = opened(tmp_path / DB_NAME)
    with pytest.raises(sqlite3.IntegrityError, match=name):
        say(s.db, *row)
    s.close()


def test_a_station_has_one_entry(tmp_path: Path) -> None:
    s = opened(tmp_path / DB_NAME)
    say(s.db, "OH2RDG", "WIDE1-1", 5, STAMP)
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed: station_path"):
        say(s.db, "OH2RDG", "", None, STAMP)
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed: station_pref"):
        say(s.db, "OH2RDG", None, 7, STAMP)
    s.close()


# ---- migration 4: the station preferences

PATHS = [
    ("OH2RDG", "WIDE1-1,WIDE2-1", "2026-10-21T11:00:00.000000Z"),
    ("OH2XYZ", "", "2026-10-21T11:05:00.000000Z"),
    ("OH2ABC-7", "OH2RCH-2", "2026-10-21T11:10:00.000000Z"),
    ("OH2DIR-15", "RELAY-1,RELAY-2,RELAY-3,RELAY-4,RELAY-5,RELAY-6,RELAY-7,RELAY-8", "2026-10-21T11:15:00.000000Z"),
]


def version_three(path: Path, clock: FixedClock) -> None:
    """A database at schema version 3: settings, a packet, a station, messages of every kind and
    paths of stations, user_version 3."""
    version_two(path, clock)
    db = raw(path)
    migrations_module._v3(db)
    db.execute("PRAGMA user_version = 3")
    db.execute(
        "INSERT INTO schema_history (version, name, sha256, applied) VALUES (3, '_v3', ?, ?)",
        (GOLDEN[3], int(clock().timestamp())),
    )
    db.execute(INSERT_MESSAGE, GOOD)
    db.execute(
        INSERT_MESSAGE, ("2026-10-21T12:01:00.000000Z", "in", "OH2RDG", "OH2GBA", "hi", "7", "received", 0, None, None)
    )
    db.execute(
        INSERT_MESSAGE,
        ("2026-10-21T12:02:00.000000Z", "in", "OH2AAA", "OH2BBB", "overheard text", None, "overheard", 0, None, None),
    )
    for row in PATHS:
        db.execute("INSERT INTO station_path (call, path, updated_at) VALUES (?, ?, ?)", row)
    db.close()


def test_a_database_of_version_three_gets_station_pref_in_place_of_station_path_with_every_row_and_keeps_the_rest(
    tmp_path: Path,
) -> None:
    clock = FixedClock()
    old = tmp_path / "old" / DB_NAME
    old.parent.mkdir()
    version_three(old, clock)
    migrated = opened(old, clock)
    fresh = opened(tmp_path / DB_NAME, clock)
    assert migrated.version() == fresh.version() == SCHEMA_VERSION >= 4
    assert shape(migrated.db) == shape(fresh.db), (
        "a migrated database has exactly the tables, indexes and checks of a new one"
    )
    names = {n for _, n, _ in shape(migrated.db)}
    assert "station_pref" in names and "radio_id" in {
        r[1] for r in migrated.db.execute("PRAGMA table_info(station_path)")
    }, "(station_path is there again since migration 33: a station's path on a radio)"
    assert migrated.db.execute(
        f"SELECT call, path, hide_after_min, updated_at FROM {SAID} ORDER BY call"
    ).fetchall() == sorted((c, p, None, t) for c, p, t in PATHS)
    assert migrated.db.execute("SELECT state, text FROM message ORDER BY id").fetchall() == [
        ("sending", "hello"),
        ("received", "hi"),
        ("overheard", "overheard text"),
    ]
    assert migrated.db.execute("SELECT key, value FROM settings").fetchall() == [("station/call", "OH2GBA")]
    assert migrated.db.execute("SELECT source FROM packet").fetchall() == [("OH2RDG",)] and migrated.db.execute(
        "SELECT call FROM station"
    ).fetchall() == [("OH2RDG",)]
    assert [(r[0], r[1], r[2]) for r in migrated.history()][3:] == [
        (4, "_v4", GOLDEN[4]),
        (5, "_v5", GOLDEN[5]),
        (6, "_v6", GOLDEN[6]),
        (7, "_v7", GOLDEN[7]),
        (8, "_v8", GOLDEN[8]),
        (9, "_v9", GOLDEN[9]),
        (10, "_v10", GOLDEN[10]),
        (11, "_v11", GOLDEN[11]),
        (12, "_v12", GOLDEN[12]),
        (13, "_v13", GOLDEN[13]),
        (14, "_v14", GOLDEN[14]),
        (15, "_v15", GOLDEN[15]),
        (16, "_v16", GOLDEN[16]),
        (17, "_v17", GOLDEN[17]),
        (18, "_v18", GOLDEN[18]),
        (19, "_v19", GOLDEN[19]),
        (20, "_v20", GOLDEN[20]),
        (21, "_v21", GOLDEN[21]),
        (22, "_v22", GOLDEN[22]),
        (23, "_v23", GOLDEN[23]),
        (24, "_v24", GOLDEN[24]),
        (25, "_v25", GOLDEN[25]),
        (26, "_v26", GOLDEN[26]),
        (27, "_v27", GOLDEN[27]),
        (28, "_v28", GOLDEN[28]),
        (29, "_v29", GOLDEN[29]),
        (30, "_v30", GOLDEN[30]),
        (31, "_v31", GOLDEN[31]),
        (32, "_v32", GOLDEN[32]),
        (33, "_v33", GOLDEN[33]),
        (34, "_v34", GOLDEN[34]),
        (35, "_v35", GOLDEN[35]),
        (36, "_v36", GOLDEN[36]),
        (37, "_v37", GOLDEN[37]),
    ]
    # And the new table takes what the old one could not hold
    say(migrated.db, "OH2NEW", None, 0, STAMP)
    for opened_ in (migrated, fresh):
        opened_.close()
    [copy_path] = sorted((old.parent / "backup").glob("premigrate-v3-to-v*.sqlite"))
    copy = raw(copy_path)
    assert copy.execute("PRAGMA user_version").fetchone()[0] == 3 and copy.execute(
        "SELECT COUNT(*) FROM station_path"
    ).fetchone()[0] == len(PATHS)
    assert "station_pref" not in {r[0] for r in copy.execute("SELECT name FROM sqlite_master")}
    copy.close()


def test_a_database_of_version_three_without_paths_gets_an_empty_station_pref(tmp_path: Path) -> None:
    clock = FixedClock()
    old = tmp_path / DB_NAME
    version_three(old, clock)
    db = raw(old)
    db.execute("DELETE FROM station_path")
    db.close()
    s = opened(old, clock)
    assert (
        s.version() == SCHEMA_VERSION
        and s.db.execute("SELECT COUNT(*) FROM station_pref").fetchone()[0] == 0
        and s.db.execute("SELECT COUNT(*) FROM message").fetchone()[0] == 3
    )
    s.close()


@pytest.mark.expects_errors
def test_a_migration_4_that_doubts_changes_nothing_and_leaves_the_paths_where_they_were(tmp_path: Path) -> None:
    clock = FixedClock()
    old = tmp_path / DB_NAME
    version_three(old, clock)
    db = raw(old)
    db.execute("CREATE TABLE station_pref (call TEXT)")  # something is in the way
    db.close()
    ok, why = try_open(old, clock)
    assert not ok and "station_pref" in why
    db = raw(old)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 3 and db.execute(
        "SELECT COUNT(*) FROM station_path"
    ).fetchone()[0] == len(PATHS)
    assert db.execute("SELECT COUNT(*) FROM schema_history").fetchone()[0] == 3
    db.close()
    assert len(list((tmp_path / "backup").glob("premigrate-v3-to-v*.sqlite"))) == 1


# ---- migration 5: the number of attempts of a message


def version_four(path: Path, clock: FixedClock) -> None:
    """A database at schema version 4: messages of every kind (no attempts_max column) and a station
    preference, user_version 4."""
    version_three(path, clock)
    db = raw(path)
    migrations_module._v4(db)
    db.execute("PRAGMA user_version = 4")
    db.execute(
        "INSERT INTO schema_history (version, name, sha256, applied) VALUES (4, '_v4', ?, ?)",
        (GOLDEN[4], int(clock().timestamp())),
    )
    db.execute(
        INSERT_MESSAGE,
        (
            "2026-10-21T12:02:00.000000Z",
            "out",
            "OH2GBA",
            "OH2RDG",
            "again",
            "00013",
            "acked",
            2,
            "2026-10-21T12:02:30.000000Z",
            "2026-10-21T12:03:00.000000Z",
        ),
    )
    db.execute(PREF_INSERT, ("OH2NEW", None, 30, STAMP))
    db.close()


def test_a_database_of_version_four_gets_the_attempts_max_column_with_6_for_every_message_there_is_and_keeps_the_rest(
    tmp_path: Path,
) -> None:
    clock = FixedClock()
    old = tmp_path / "old" / DB_NAME
    old.parent.mkdir()
    version_four(old, clock)
    before = raw(old)
    assert "attempts_max" not in {r[1] for r in before.execute("PRAGMA table_info(message)")}
    rows = before.execute(
        "SELECT id, at, direction, from_call, to_call, text, msg_id, state, attempts, last_attempt_at, acked_at FROM message ORDER BY id"
    ).fetchall()
    before.close()
    migrated = opened(old, clock)
    fresh = opened(tmp_path / DB_NAME, clock)
    assert migrated.version() == fresh.version() == SCHEMA_VERSION >= 5
    assert shape(migrated.db) == shape(fresh.db), (
        "a migrated database has exactly the tables, indexes and checks of a new one"
    )
    assert (
        migrated.db.execute(
            "SELECT id, at, direction, from_call, to_call, text, msg_id, state, attempts, last_attempt_at, acked_at FROM message ORDER BY id"
        ).fetchall()
        == rows
    )
    assert migrated.db.execute("SELECT attempts_max FROM message ORDER BY id").fetchall() == [(6,)] * 4
    assert (
        migrated.db.execute(f"SELECT call, path, hide_after_min FROM {SAID} WHERE call = 'OH2NEW'").fetchone() is None
    ), "(its timeout was all it said: migration 17 deleted the row)"
    assert [(r[0], r[1], r[2]) for r in migrated.history()][4:5] == [(5, "_v5", GOLDEN[5])]
    migrated.db.execute(
        INSERT_MESSAGE.replace("acked_at)", "acked_at, attempts_max)").replace("?)", "?, ?)"), (*GOOD, 10)
    )
    assert migrated.db.execute("SELECT attempts_max FROM message ORDER BY id DESC LIMIT 1").fetchone() == (10,)
    for opened_ in (migrated, fresh):
        opened_.close()
    [copy_path] = sorted((old.parent / "backup").glob("premigrate-v4-to-v*.sqlite"))
    copy = raw(copy_path)
    assert copy.execute("PRAGMA user_version").fetchone()[0] == 4 and "attempts_max" not in {
        r[1] for r in copy.execute("PRAGMA table_info(message)")
    }
    copy.close()


@pytest.mark.parametrize(
    "value, ok",
    [(1, True), (6, True), (10, True), (0, False), (11, False), (-1, False), ("many", False), (None, False)],
)
def test_attempts_max_is_a_whole_number_from_1_to_10(tmp_path: Path, value: object, ok: bool) -> None:
    s = opened(tmp_path / DB_NAME)
    statement = "INSERT INTO message (at, direction, from_call, to_call, text, state, attempts_max) VALUES (?, 'out', 'A', 'B', 'x', 'sending', ?)"
    if ok:
        s.db.execute(statement, (STAMP, value))
    else:
        with pytest.raises(sqlite3.IntegrityError, match="message_attempts_max_range|cannot store|NOT NULL"):
            s.db.execute(statement, (STAMP, value))
    s.close()


def test_a_message_inserted_without_attempts_max_has_6(tmp_path: Path) -> None:
    s = opened(tmp_path / DB_NAME)
    s.db.execute(INSERT_MESSAGE, GOOD)
    assert s.db.execute("SELECT attempts_max FROM message").fetchone() == (6,)
    s.close()


# ---- migration 6: how a message reached us


def version_five(path: Path, clock: FixedClock) -> None:
    """A database at schema version 5: messages of every kind with their attempts_max, no route
    column, user_version 5."""
    version_four(path, clock)
    db = raw(path)
    migrations_module._v5(db)
    db.execute("PRAGMA user_version = 5")
    db.execute(
        "INSERT INTO schema_history (version, name, sha256, applied) VALUES (5, '_v5', ?, ?)",
        (GOLDEN[5], int(clock().timestamp())),
    )
    db.close()


def test_a_database_of_version_five_gets_the_route_column_empty_for_every_message_there_is_and_keeps_the_rest(
    tmp_path: Path,
) -> None:
    clock = FixedClock()
    old = tmp_path / "old" / DB_NAME
    old.parent.mkdir()
    version_five(old, clock)
    before = raw(old)
    assert "route" not in {r[1] for r in before.execute("PRAGMA table_info(message)")}
    rows = before.execute(
        "SELECT id, at, direction, from_call, to_call, text, msg_id, state, attempts, last_attempt_at, acked_at, attempts_max FROM message ORDER BY id"
    ).fetchall()
    before.close()
    migrated = opened(old, clock)
    fresh = opened(tmp_path / DB_NAME, clock)
    assert migrated.version() == fresh.version() == SCHEMA_VERSION >= 6
    assert shape(migrated.db) == shape(fresh.db), (
        "a migrated database has exactly the tables, indexes and checks of a new one"
    )
    assert (
        migrated.db.execute(
            "SELECT id, at, direction, from_call, to_call, text, msg_id, state, attempts, last_attempt_at, acked_at, attempts_max FROM message ORDER BY id"
        ).fetchall()
        == rows
    )
    assert migrated.db.execute("SELECT route FROM message ORDER BY id").fetchall() == [("",)] * len(rows)
    assert (
        migrated.db.execute(f"SELECT call, path, hide_after_min FROM {SAID} WHERE call = 'OH2NEW'").fetchone() is None
    ), "(its timeout was all it said: migration 17 deleted the row)"
    assert [(r[0], r[1], r[2]) for r in migrated.history()][5:] == [
        (6, "_v6", GOLDEN[6]),
        (7, "_v7", GOLDEN[7]),
        (8, "_v8", GOLDEN[8]),
        (9, "_v9", GOLDEN[9]),
        (10, "_v10", GOLDEN[10]),
        (11, "_v11", GOLDEN[11]),
        (12, "_v12", GOLDEN[12]),
        (13, "_v13", GOLDEN[13]),
        (14, "_v14", GOLDEN[14]),
        (15, "_v15", GOLDEN[15]),
        (16, "_v16", GOLDEN[16]),
        (17, "_v17", GOLDEN[17]),
        (18, "_v18", GOLDEN[18]),
        (19, "_v19", GOLDEN[19]),
        (20, "_v20", GOLDEN[20]),
        (21, "_v21", GOLDEN[21]),
        (22, "_v22", GOLDEN[22]),
        (23, "_v23", GOLDEN[23]),
        (24, "_v24", GOLDEN[24]),
        (25, "_v25", GOLDEN[25]),
        (26, "_v26", GOLDEN[26]),
        (27, "_v27", GOLDEN[27]),
        (28, "_v28", GOLDEN[28]),
        (29, "_v29", GOLDEN[29]),
        (30, "_v30", GOLDEN[30]),
        (31, "_v31", GOLDEN[31]),
        (32, "_v32", GOLDEN[32]),
        (33, "_v33", GOLDEN[33]),
        (34, "_v34", GOLDEN[34]),
        (35, "_v35", GOLDEN[35]),
        (36, "_v36", GOLDEN[36]),
        (37, "_v37", GOLDEN[37]),
    ]
    migrated.db.execute(
        "INSERT INTO message (at, direction, from_call, to_call, text, state, route) VALUES (?, 'in', 'OH2RDG', 'OH2GBA', 'hi', 'received', 'via OH2RCH-1 \u2192 OH2RCH-3')",
        (STAMP,),
    )
    assert migrated.db.execute("SELECT route FROM message ORDER BY id DESC LIMIT 1").fetchone() == (
        "via OH2RCH-1 \u2192 OH2RCH-3",
    )
    for opened_ in (migrated, fresh):
        opened_.close()
    [copy_path] = sorted((old.parent / "backup").glob("premigrate-v5-to-v*.sqlite"))
    copy = raw(copy_path)
    assert copy.execute("PRAGMA user_version").fetchone()[0] == 5 and "route" not in {
        r[1] for r in copy.execute("PRAGMA table_info(message)")
    }
    copy.close()


def test_a_message_inserted_without_a_route_has_none(tmp_path: Path) -> None:
    s = opened(tmp_path / DB_NAME)
    s.db.execute(INSERT_MESSAGE, GOOD)
    assert s.db.execute("SELECT route FROM message").fetchone() == ("",)
    s.close()


# ---- migration 7: the message board


def version_six(path: Path, clock: FixedClock) -> None:
    """A database at schema version 6: messages (with their routes), a station preference, no
    bulletin table, user_version 6."""
    version_five(path, clock)
    db = raw(path)
    migrations_module._v6(db)
    db.execute("PRAGMA user_version = 6")
    db.execute(
        "INSERT INTO schema_history (version, name, sha256, applied) VALUES (6, '_v6', ?, ?)",
        (GOLDEN[6], int(clock().timestamp())),
    )
    db.execute(
        "INSERT INTO message (at, direction, from_call, to_call, text, state, route) VALUES (?, 'in', 'OH2XYZ', 'QST', 'Club net tonight', 'overheard', 'direct')",
        (STAMP,),
    )
    db.close()


BULLETIN_INSERT = "INSERT INTO bulletin (sender, slot, group_name, text, first_heard, last_heard, times_heard) VALUES (?, ?, ?, ?, ?, ?, ?)"
LATER = "2026-10-21T13:00:00.000000Z"


def test_a_database_of_version_six_gets_the_empty_bulletin_table_and_keeps_the_rest(tmp_path: Path) -> None:
    clock = FixedClock()
    old = tmp_path / "old" / DB_NAME
    old.parent.mkdir()
    version_six(old, clock)
    before = raw(old)
    assert "bulletin" not in {r[0] for r in before.execute("SELECT name FROM sqlite_master")}
    rows = before.execute(
        "SELECT id, at, direction, from_call, to_call, text, msg_id, state, attempts, last_attempt_at, acked_at, attempts_max, route FROM message ORDER BY id"
    ).fetchall()
    before.close()
    migrated = opened(old, clock)
    fresh = opened(tmp_path / DB_NAME, clock)
    assert migrated.version() == fresh.version() == SCHEMA_VERSION >= 7
    assert shape(migrated.db) == shape(fresh.db), (
        "a migrated database has exactly the tables, indexes and checks of a new one"
    )
    assert migrated.db.execute("SELECT COUNT(*) FROM bulletin").fetchone() == (0,)
    assert (
        migrated.db.execute(
            "SELECT id, at, direction, from_call, to_call, text, msg_id, state, attempts, last_attempt_at, acked_at, attempts_max, route FROM message ORDER BY id"
        ).fetchall()
        == rows
    )
    assert [(r[0], r[1], r[2]) for r in migrated.history()][6:] == [
        (7, "_v7", GOLDEN[7]),
        (8, "_v8", GOLDEN[8]),
        (9, "_v9", GOLDEN[9]),
        (10, "_v10", GOLDEN[10]),
        (11, "_v11", GOLDEN[11]),
        (12, "_v12", GOLDEN[12]),
        (13, "_v13", GOLDEN[13]),
        (14, "_v14", GOLDEN[14]),
        (15, "_v15", GOLDEN[15]),
        (16, "_v16", GOLDEN[16]),
        (17, "_v17", GOLDEN[17]),
        (18, "_v18", GOLDEN[18]),
        (19, "_v19", GOLDEN[19]),
        (20, "_v20", GOLDEN[20]),
        (21, "_v21", GOLDEN[21]),
        (22, "_v22", GOLDEN[22]),
        (23, "_v23", GOLDEN[23]),
        (24, "_v24", GOLDEN[24]),
        (25, "_v25", GOLDEN[25]),
        (26, "_v26", GOLDEN[26]),
        (27, "_v27", GOLDEN[27]),
        (28, "_v28", GOLDEN[28]),
        (29, "_v29", GOLDEN[29]),
        (30, "_v30", GOLDEN[30]),
        (31, "_v31", GOLDEN[31]),
        (32, "_v32", GOLDEN[32]),
        (33, "_v33", GOLDEN[33]),
        (34, "_v34", GOLDEN[34]),
        (35, "_v35", GOLDEN[35]),
        (36, "_v36", GOLDEN[36]),
        (37, "_v37", GOLDEN[37]),
    ]
    # And the new table takes what the program produces
    migrated.db.execute(BULLETIN_INSERT, ("OH2XYZ", "BLN3HAMS", "HAMS", "Club net tonight", STAMP, LATER, 3))
    assert migrated.db.execute("SELECT sender, slot, group_name, text, times_heard FROM bulletin").fetchall() == [
        ("OH2XYZ", "BLN3HAMS", "HAMS", "Club net tonight", 3)
    ]
    for opened_ in (migrated, fresh):
        opened_.close()
    [copy_path] = sorted((old.parent / "backup").glob("premigrate-v6-to-v*.sqlite"))
    copy = raw(copy_path)
    assert copy.execute("PRAGMA user_version").fetchone()[0] == 6 and "bulletin" not in {
        r[0] for r in copy.execute("SELECT name FROM sqlite_master")
    }
    copy.close()


@pytest.mark.parametrize(
    "row, name",
    [
        (("", "BLN1", "", "x", STAMP, STAMP, 1), "bulletin_sender_present"),
        (("OH2XYZ", "", "", "x", STAMP, STAMP, 1), "bulletin_slot_present"),
        (("OH2XYZ", "BLN1", "", "x", "noon", STAMP, 1), "bulletin_first_heard_form"),
        (("OH2XYZ", "BLN1", "", "x", STAMP, "later", 1), "bulletin_last_heard_form"),
        (("OH2XYZ", "BLN1", "", "x", STAMP, STAMP, 0), "bulletin_times_heard_count"),
        (("OH2XYZ", "BLN1", "", "x", LATER, STAMP, 1), "bulletin_heard_in_order"),
    ],
)
def test_the_bulletin_table_refuses_what_the_program_cannot_produce(
    tmp_path: Path, row: tuple[object, ...], name: str
) -> None:
    s = opened(tmp_path / DB_NAME)
    with pytest.raises(sqlite3.IntegrityError, match=name):
        s.db.execute(BULLETIN_INSERT, row)
    s.close()


def test_the_bulletin_table_keeps_one_row_for_a_sender_and_slot(tmp_path: Path) -> None:
    s = opened(tmp_path / DB_NAME)
    s.db.execute(BULLETIN_INSERT, ("OH2XYZ", "BLN1", "", "x", STAMP, STAMP, 1))
    s.db.execute(BULLETIN_INSERT, ("OH2XYZ", "BLN2", "", "x", STAMP, STAMP, 1))
    s.db.execute(BULLETIN_INSERT, ("OH2ABC", "BLN1", "", "x", STAMP, STAMP, 1))
    with pytest.raises(sqlite3.IntegrityError):
        s.db.execute(BULLETIN_INSERT, ("OH2XYZ", "BLN1", "", "y", STAMP, STAMP, 1))
    s.close()


# ---- migration 8: the weather


def version_seven(path: Path, clock: FixedClock) -> None:
    """A database at schema version 7: packets (a weather station's among them), a bulletin, no
    weather table, user_version 7."""
    version_six(path, clock)
    db = raw(path)
    migrations_module._v7(db)
    db.execute("PRAGMA user_version = 7")
    db.execute(
        "INSERT INTO schema_history (version, name, sha256, applied) VALUES (7, '_v7', ?, ?)",
        (GOLDEN[7], int(clock().timestamp())),
    )
    db.execute(BULLETIN_INSERT, ("OH2XYZ", "BLN1", "", "Net tonight", STAMP, STAMP, 1))
    db.execute(
        "INSERT INTO packet (heard_at, direction, raw, source, destination, path, kind, summary, decoded) VALUES (?, 'in', x'00', 'OH2MUI', 'APRX29', 'OH2RCH-2*', 'position', "
        "'position 60.4072 23.8788 /_ 107/001g001t050r001p016P013h85b10284 RX Igate & WX station', '{\"type\":\"position\"}')",
        (STAMP,),
    )
    db.close()


WEATHER_INSERT = (
    "INSERT INTO weather (station, at, wind_dir, wind_kmh, gust_kmh, temp_c, humidity, pressure_hpa, rain_1h_mm, rain_24h_mm, rain_today_mm, luminosity, raw) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
GOOD_WEATHER = (
    "OH2MUI",
    STAMP,
    107,
    1.6,
    1.6,
    10.0,
    85,
    1028.4,
    0.3,
    4.1,
    3.3,
    None,
    "107/001g001t050r001p016P013h85b10284",
)


def test_a_database_of_version_seven_gets_the_empty_weather_table_and_keeps_the_rest(tmp_path: Path) -> None:
    clock = FixedClock()
    old = tmp_path / "old" / DB_NAME
    old.parent.mkdir()
    version_seven(old, clock)
    before = raw(old)
    assert "weather" not in {r[0] for r in before.execute("SELECT name FROM sqlite_master")}
    packets = before.execute("SELECT heard_at, direction, source, kind, summary FROM packet").fetchall()
    bulletins = before.execute("SELECT sender, slot, text FROM bulletin").fetchall()
    before.close()
    migrated = opened(old, clock)
    fresh = opened(tmp_path / DB_NAME, clock)
    assert migrated.version() == fresh.version() == SCHEMA_VERSION >= 8
    assert shape(migrated.db) == shape(fresh.db), (
        "a migrated database has exactly the tables, indexes and checks of a new one"
    )
    assert migrated.db.execute("SELECT COUNT(*) FROM weather").fetchone() == (0,), (
        "the migration does not make the weather: the daemon reads the packets at its start"
    )
    assert migrated.db.execute("SELECT heard_at, direction, source, kind, summary FROM packet").fetchall() == packets
    assert migrated.db.execute("SELECT sender, slot, text FROM bulletin").fetchall() == bulletins
    assert [(r[0], r[1], r[2]) for r in migrated.history()][7:] == [
        (8, "_v8", GOLDEN[8]),
        (9, "_v9", GOLDEN[9]),
        (10, "_v10", GOLDEN[10]),
        (11, "_v11", GOLDEN[11]),
        (12, "_v12", GOLDEN[12]),
        (13, "_v13", GOLDEN[13]),
        (14, "_v14", GOLDEN[14]),
        (15, "_v15", GOLDEN[15]),
        (16, "_v16", GOLDEN[16]),
        (17, "_v17", GOLDEN[17]),
        (18, "_v18", GOLDEN[18]),
        (19, "_v19", GOLDEN[19]),
        (20, "_v20", GOLDEN[20]),
        (21, "_v21", GOLDEN[21]),
        (22, "_v22", GOLDEN[22]),
        (23, "_v23", GOLDEN[23]),
        (24, "_v24", GOLDEN[24]),
        (25, "_v25", GOLDEN[25]),
        (26, "_v26", GOLDEN[26]),
        (27, "_v27", GOLDEN[27]),
        (28, "_v28", GOLDEN[28]),
        (29, "_v29", GOLDEN[29]),
        (30, "_v30", GOLDEN[30]),
        (31, "_v31", GOLDEN[31]),
        (32, "_v32", GOLDEN[32]),
        (33, "_v33", GOLDEN[33]),
        (34, "_v34", GOLDEN[34]),
        (35, "_v35", GOLDEN[35]),
        (36, "_v36", GOLDEN[36]),
        (37, "_v37", GOLDEN[37]),
    ]
    # And the new table takes what the program produces
    migrated.db.execute(WEATHER_INSERT, GOOD_WEATHER)
    assert migrated.db.execute("SELECT station, temp_c, luminosity FROM weather").fetchall() == [("OH2MUI", 10.0, None)]
    assert "weather_station_at" in {n for _, n, _ in shape(migrated.db)}
    for opened_ in (migrated, fresh):
        opened_.close()
    [copy_path] = sorted((old.parent / "backup").glob("premigrate-v7-to-v*.sqlite"))
    copy = raw(copy_path)
    assert copy.execute("PRAGMA user_version").fetchone()[0] == 7 and "weather" not in {
        r[0] for r in copy.execute("SELECT name FROM sqlite_master")
    }
    copy.close()


def with_value(index: int, value: object) -> tuple[object, ...]:
    return GOOD_WEATHER[:index] + (value,) + GOOD_WEATHER[index + 1 :]


@pytest.mark.parametrize(
    "row, name",
    [
        (with_value(0, ""), "weather_station_present"),
        (with_value(1, "noon"), "weather_at_form"),
        (with_value(2, 361), "weather_wind_dir_range"),
        (with_value(3, -1.0), "weather_wind_kmh_range"),
        (with_value(4, 1611.0), "weather_gust_kmh_range"),
        (with_value(5, 539.0), "weather_temp_c_range"),
        (with_value(5, -74.0), "weather_temp_c_range"),
        (with_value(6, 0), "weather_humidity_range"),
        (with_value(6, 101), "weather_humidity_range"),
        (with_value(7, 10001.0), "weather_pressure_hpa_range"),
        (with_value(8, -0.1), "weather_rain_1h_mm_range"),
        (with_value(9, 255.0), "weather_rain_24h_mm_range"),
        (with_value(10, 255.0), "weather_rain_today_mm_range"),
        (with_value(11, 2000), "weather_luminosity_range"),
    ],
)
def test_the_weather_table_refuses_what_the_program_cannot_produce(
    tmp_path: Path, row: tuple[object, ...], name: str
) -> None:
    s = opened(tmp_path / DB_NAME)
    with pytest.raises(sqlite3.IntegrityError, match=name):
        s.db.execute(WEATHER_INSERT, row)
    s.close()


def test_the_weather_table_takes_every_field_missing_and_keeps_every_observation(tmp_path: Path) -> None:
    s = opened(tmp_path / DB_NAME)
    s.db.execute(WEATHER_INSERT, ("OH2MUI", STAMP) + (None,) * 10 + ("",))
    s.db.execute(WEATHER_INSERT, GOOD_WEATHER)
    # A packet that came by two digipeaters is two rows
    s.db.execute(WEATHER_INSERT, GOOD_WEATHER)
    assert s.db.execute("SELECT COUNT(*) FROM weather WHERE station = 'OH2MUI'").fetchone() == (3,)
    assert "weather_station_at" in [r[1] for r in s.db.execute("PRAGMA index_list(weather)")]
    s.close()


# ---- migration 9: the attempts of a station


def version_eight(path: Path, clock: FixedClock) -> None:
    """A database at schema version 8: stations with a path, a timeout or both (no attempts column),
    messages of every kind, user_version 8."""
    version_seven(path, clock)
    db = raw(path)
    migrations_module._v8(db)
    db.execute("PRAGMA user_version = 8")
    db.execute(
        "INSERT INTO schema_history (version, name, sha256, applied) VALUES (8, '_v8', ?, ?)",
        (GOLDEN[8], int(clock().timestamp())),
    )
    db.execute(PREF_INSERT, ("OH2BOTH", "WIDE1-1", 0, "2026-10-21T12:05:00.000000Z"))
    db.close()


def test_a_database_of_version_eight_gets_the_attempts_column_empty_for_every_station_and_keeps_the_rest(
    tmp_path: Path,
) -> None:
    clock = FixedClock()
    old = tmp_path / "old" / DB_NAME
    old.parent.mkdir()
    version_eight(old, clock)
    before = raw(old)
    assert "attempts" not in {r[1] for r in before.execute("PRAGMA table_info(station_pref)")}
    prefs = before.execute("SELECT call, path, hide_after_min, updated_at FROM station_pref ORDER BY call").fetchall()
    before.close()
    assert len(prefs) == 6
    # Migration 17 clears the timeouts and deletes a row that said only that
    prefs = [(call, path, None, stamp) for call, path, hide, stamp in prefs if path is not None]
    migrated = opened(old, clock)
    fresh = opened(tmp_path / DB_NAME, clock)
    assert migrated.version() == fresh.version() == SCHEMA_VERSION >= 9
    assert shape(migrated.db) == shape(fresh.db), (
        "a migrated database has exactly the tables, indexes and checks of a new one"
    )
    assert (
        migrated.db.execute(f"SELECT call, path, hide_after_min, updated_at FROM {SAID} ORDER BY call").fetchall()
        == prefs
        and prefs
    )
    assert migrated.db.execute("SELECT COUNT(*) FROM station_pref WHERE attempts IS NOT NULL").fetchone() == (0,)
    assert migrated.db.execute("SELECT sender, slot FROM bulletin").fetchall() == [("OH2XYZ", "BLN1")]
    assert [(r[0], r[1], r[2]) for r in migrated.history()][8:9] == [(9, "_v9", GOLDEN[9])]
    # And the new column takes a count (OH2BOTH said only a path since migration 17: its row is new)
    migrated.db.execute("INSERT INTO station_pref (call, attempts, updated_at) VALUES ('OH2BOTH', 2, ?)", (STAMP,))
    migrated.db.execute("INSERT INTO station_pref (call, attempts, updated_at) VALUES ('EMAIL-2', 2, ?)", (STAMP,))
    assert migrated.db.execute(
        "SELECT call, attempts FROM station_pref WHERE attempts IS NOT NULL ORDER BY call"
    ).fetchall() == [("EMAIL-2", 2), ("OH2BOTH", 2)]
    for opened_ in (migrated, fresh):
        opened_.close()
    [copy_path] = sorted((old.parent / "backup").glob("premigrate-v8-to-v*.sqlite"))
    copy = raw(copy_path)
    assert copy.execute("PRAGMA user_version").fetchone()[0] == 8 and "attempts" not in {
        r[1] for r in copy.execute("PRAGMA table_info(station_pref)")
    }
    copy.close()


@pytest.mark.parametrize(
    "row, name",
    [
        (("OH2RDG", None, None, 0, STAMP), "station_pref_attempts_range"),
        (("OH2RDG", None, None, 11, STAMP), "station_pref_attempts_range"),
        (("OH2RDG", None, None, "twice", STAMP), "cannot store"),
        (("OH2RDG", None, None, None, STAMP), "station_pref_says_something"),
    ],
)
def test_the_station_pref_table_refuses_attempts_the_program_cannot_produce(
    tmp_path: Path, row: tuple[object, ...], name: str
) -> None:
    s = opened(tmp_path / DB_NAME)
    with pytest.raises(sqlite3.IntegrityError, match=name):
        # The second of a row was the path, which is a table of its own since 33
        s.db.execute(
            "INSERT INTO station_pref (call, hide_after_min, attempts, updated_at) VALUES (?1, ?3, ?4, ?5)", row
        )
    s.close()


@pytest.mark.parametrize("attempts", [1, 2, 6, 10])
def test_a_station_may_have_only_attempts(tmp_path: Path, attempts: int) -> None:
    s = opened(tmp_path / DB_NAME)
    s.db.execute("INSERT INTO station_pref (call, attempts, updated_at) VALUES ('EMAIL-2', ?, ?)", (attempts, STAMP))
    assert s.db.execute(f"SELECT path, hide_after_min, attempts FROM {SAID}").fetchall() == [(None, None, attempts)]
    s.close()


# ---- migration 10: the unconfirmed state


def version_nine(path: Path, clock: FixedClock) -> None:
    """A database at schema version 9: a message of every state and a station with attempts,
    user_version 9."""
    version_eight(path, clock)
    db = raw(path)
    migrations_module._v9(db)
    db.execute("PRAGMA user_version = 9")
    db.execute(
        "INSERT INTO schema_history (version, name, sha256, applied) VALUES (9, '_v9', ?, ?)",
        (GOLDEN[9], int(clock().timestamp())),
    )
    db.execute("INSERT INTO station_pref (call, attempts, updated_at) VALUES ('EMAIL-2', 2, ?)", (STAMP,))
    db.execute(
        "INSERT INTO message (at, direction, from_call, to_call, text, msg_id, state, attempts, last_attempt_at, acked_at, attempts_max, route) "
        "VALUES (?, 'out', 'OH2GBA', 'OH2RDG', 'late', '00021', 'failed', 3, ?, NULL, 3, ''), (?, 'in', 'OH2RDG', 'OH2GBA', 'heard', '5', 'received', 0, NULL, NULL, 6, 'via OH2RCH-2')",
        (STAMP, STAMP, "2026-10-21T12:09:00.000000Z"),
    )
    db.close()


def test_a_database_of_version_nine_takes_unconfirmed_messages_and_keeps_every_message_and_the_index(
    tmp_path: Path,
) -> None:
    clock = FixedClock()
    old = tmp_path / "old" / DB_NAME
    old.parent.mkdir()
    version_nine(old, clock)
    before = raw(old)
    with pytest.raises(sqlite3.IntegrityError, match="message_state"):
        before.execute(INSERT_MESSAGE, GOOD[:6] + ("unconfirmed",) + GOOD[7:])
    rows = before.execute(
        "SELECT id, at, direction, from_call, to_call, text, msg_id, state, attempts, last_attempt_at, acked_at, attempts_max, route FROM message ORDER BY id"
    ).fetchall()
    before.close()
    assert len(rows) == 7
    migrated = opened(old, clock)
    fresh = opened(tmp_path / DB_NAME, clock)
    assert migrated.version() == fresh.version() == SCHEMA_VERSION >= 10
    assert shape(migrated.db) == shape(fresh.db), (
        "a migrated database has exactly the tables, indexes and checks of a new one"
    )
    assert (
        migrated.db.execute(
            "SELECT id, at, direction, from_call, to_call, text, msg_id, state, attempts, last_attempt_at, acked_at, attempts_max, route FROM message ORDER BY id"
        ).fetchall()
        == rows
    )
    assert migrated.db.execute("SELECT call, attempts FROM station_pref WHERE attempts IS NOT NULL").fetchall() == [
        ("EMAIL-2", 2)
    ]
    assert [(r[0], r[1], r[2]) for r in migrated.history()][9:] == [
        (10, "_v10", GOLDEN[10]),
        (11, "_v11", GOLDEN[11]),
        (12, "_v12", GOLDEN[12]),
        (13, "_v13", GOLDEN[13]),
        (14, "_v14", GOLDEN[14]),
        (15, "_v15", GOLDEN[15]),
        (16, "_v16", GOLDEN[16]),
        (17, "_v17", GOLDEN[17]),
        (18, "_v18", GOLDEN[18]),
        (19, "_v19", GOLDEN[19]),
        (20, "_v20", GOLDEN[20]),
        (21, "_v21", GOLDEN[21]),
        (22, "_v22", GOLDEN[22]),
        (23, "_v23", GOLDEN[23]),
        (24, "_v24", GOLDEN[24]),
        (25, "_v25", GOLDEN[25]),
        (26, "_v26", GOLDEN[26]),
        (27, "_v27", GOLDEN[27]),
        (28, "_v28", GOLDEN[28]),
        (29, "_v29", GOLDEN[29]),
        (30, "_v30", GOLDEN[30]),
        (31, "_v31", GOLDEN[31]),
        (32, "_v32", GOLDEN[32]),
        (33, "_v33", GOLDEN[33]),
        (34, "_v34", GOLDEN[34]),
        (35, "_v35", GOLDEN[35]),
        (36, "_v36", GOLDEN[36]),
        (37, "_v37", GOLDEN[37]),
    ]
    # And the new table takes the state
    migrated.db.execute(INSERT_MESSAGE, GOOD[:6] + ("unconfirmed",) + GOOD[7:])
    assert migrated.db.execute(
        "SELECT state, attempts_max, route FROM message ORDER BY id DESC LIMIT 1"
    ).fetchone() == ("unconfirmed", 6, "")
    plan = " ".join(
        str(r)
        for r in migrated.db.execute(
            "EXPLAIN QUERY PLAN SELECT id FROM message WHERE to_call = 'OH2RDG' AND from_call = 'OH2GBA' ORDER BY at"
        )
    )
    assert "message_calls" in plan
    for opened_ in (migrated, fresh):
        opened_.close()
    [copy_path] = sorted((old.parent / "backup").glob("premigrate-v9-to-v*.sqlite"))
    copy = raw(copy_path)
    assert copy.execute("PRAGMA user_version").fetchone()[0] == 9 and copy.execute(
        "SELECT COUNT(*) FROM message"
    ).fetchone() == (7,)
    copy.close()


def test_an_unconfirmed_message_is_one_of_ours(tmp_path: Path) -> None:
    s = opened(tmp_path / DB_NAME)
    with pytest.raises(sqlite3.IntegrityError, match="message_in_when_heard"):
        s.db.execute(INSERT_MESSAGE, GOOD[:1] + ("in",) + GOOD[2:6] + ("unconfirmed",) + GOOD[7:])
    s.close()


@pytest.mark.expects_errors
def test_a_migration_10_that_doubts_changes_nothing_and_leaves_the_messages_where_they_were(tmp_path: Path) -> None:
    clock = FixedClock()
    old = tmp_path / DB_NAME
    version_nine(old, clock)
    db = raw(old)
    db.execute("CREATE TABLE message_old (x TEXT)")  # something is in the way
    db.close()
    ok, why = try_open(old, clock)
    assert not ok and "message_old" in why
    db = raw(old)
    assert (
        db.execute("PRAGMA user_version").fetchone()[0] == 9
        and db.execute("SELECT COUNT(*) FROM message").fetchone()[0] == 7
    )
    assert "message_calls" in {r[0] for r in db.execute("SELECT name FROM sqlite_master")}
    db.close()


# ---- migration 11: the delivery chain


def version_ten(path: Path, clock: FixedClock) -> None:
    """A database at schema version 10: messages of ours that were sent with attempts and one that
    came in, user_version 10."""
    version_nine(path, clock)
    db = raw(path)
    migrations_module._v10(db)
    db.execute("PRAGMA user_version = 10")
    db.execute(
        "INSERT INTO schema_history (version, name, sha256, applied) VALUES (10, '_v10', ?, ?)",
        (GOLDEN[10], int(clock().timestamp())),
    )
    db.execute(
        "INSERT INTO message (at, direction, from_call, to_call, text, msg_id, state, attempts, last_attempt_at, acked_at, attempts_max, route) "
        "VALUES (?, 'out', 'OH2GBA', 'OH2CUB-7', 'Hey mr!', '07', 'acked', 2, ?, ?, 6, '')",
        (STAMP, STAMP, STAMP),
    )
    db.close()


def test_a_database_of_version_ten_gets_the_empty_attempt_and_hop_tables_and_keeps_every_message(
    tmp_path: Path,
) -> None:
    clock = FixedClock()
    old = tmp_path / "old" / DB_NAME
    old.parent.mkdir()
    version_ten(old, clock)
    before = raw(old)
    rows = before.execute(
        "SELECT id, at, direction, from_call, to_call, text, msg_id, state, attempts, last_attempt_at, acked_at, attempts_max, route FROM message ORDER BY id"
    ).fetchall()
    assert {"message_attempt", "message_hop"} & {
        r[0] for r in before.execute("SELECT name FROM sqlite_master")
    } == set()
    before.close()
    assert len(rows) == 8
    migrated = opened(old, clock)
    fresh = opened(tmp_path / DB_NAME, clock)
    assert migrated.version() == fresh.version() == SCHEMA_VERSION >= 11
    assert shape(migrated.db) == shape(fresh.db), (
        "a migrated database has exactly the tables, indexes and checks of a new one"
    )
    assert {"message_attempt", "message_hop", "message_hop_message"} <= {n for _, n, _ in shape(migrated.db)}
    assert migrated.db.execute("SELECT COUNT(*) FROM message_attempt").fetchone() == (0,) and migrated.db.execute(
        "SELECT COUNT(*) FROM message_hop"
    ).fetchone() == (0,)
    assert (
        migrated.db.execute(
            "SELECT id, at, direction, from_call, to_call, text, msg_id, state, attempts, last_attempt_at, acked_at, attempts_max, route FROM message ORDER BY id"
        ).fetchall()
        == rows
    )
    assert [(r[0], r[1], r[2]) for r in migrated.history()][10:] == [
        (11, "_v11", GOLDEN[11]),
        (12, "_v12", GOLDEN[12]),
        (13, "_v13", GOLDEN[13]),
        (14, "_v14", GOLDEN[14]),
        (15, "_v15", GOLDEN[15]),
        (16, "_v16", GOLDEN[16]),
        (17, "_v17", GOLDEN[17]),
        (18, "_v18", GOLDEN[18]),
        (19, "_v19", GOLDEN[19]),
        (20, "_v20", GOLDEN[20]),
        (21, "_v21", GOLDEN[21]),
        (22, "_v22", GOLDEN[22]),
        (23, "_v23", GOLDEN[23]),
        (24, "_v24", GOLDEN[24]),
        (25, "_v25", GOLDEN[25]),
        (26, "_v26", GOLDEN[26]),
        (27, "_v27", GOLDEN[27]),
        (28, "_v28", GOLDEN[28]),
        (29, "_v29", GOLDEN[29]),
        (30, "_v30", GOLDEN[30]),
        (31, "_v31", GOLDEN[31]),
        (32, "_v32", GOLDEN[32]),
        (33, "_v33", GOLDEN[33]),
        (34, "_v34", GOLDEN[34]),
        (35, "_v35", GOLDEN[35]),
        (36, "_v36", GOLDEN[36]),
        (37, "_v37", GOLDEN[37]),
    ]
    for opened_ in (migrated, fresh):
        opened_.close()
    [copy_path] = sorted((old.parent / "backup").glob("premigrate-v10-to-v*.sqlite"))
    copy = raw(copy_path)
    assert copy.execute("PRAGMA user_version").fetchone()[0] == 10 and "message_hop" not in {
        r[0] for r in copy.execute("SELECT name FROM sqlite_master")
    }
    copy.close()


HOP = (7, 1, 1, "OH2RCH-2", STAMP, 0)
INSERT_HOP = (
    "INSERT INTO message_hop (message_id, attempt, position, call, heard_at, via_internet) VALUES (?, ?, ?, ?, ?, ?)"
)


@pytest.mark.parametrize(
    "change, name",
    [
        ({1: 0}, "message_hop_attempt_number"),
        ({2: 9}, "message_hop_position_range"),
        ({2: -1}, "message_hop_position_range"),
        ({3: ""}, "message_hop_call_present"),
        ({4: "noon"}, "message_hop_heard_form"),
        ({5: 2}, "message_hop_via_internet"),
        ({2: 0}, "message_hop_gate_is_internet"),
        ({3: None}, "NOT NULL"),
        ({1: "first"}, "cannot store"),
    ],
)
def test_the_hop_table_refuses_what_the_program_cannot_produce(
    tmp_path: Path, change: dict[int, object], name: str
) -> None:
    s = opened(tmp_path / DB_NAME)
    row = list(HOP)
    for index, value in change.items():
        row[index] = value
    with pytest.raises(sqlite3.IntegrityError, match=name):
        s.db.execute(INSERT_HOP, row)
    s.close()


def test_the_hop_table_takes_a_hop_by_radio_and_one_over_the_internet_and_has_each_once_and_the_index_serves_a_message(
    tmp_path: Path,
) -> None:
    s = opened(tmp_path / DB_NAME)
    s.db.execute(INSERT_HOP, HOP)
    s.db.execute(INSERT_HOP, HOP[:5] + (1,))
    s.db.execute(INSERT_HOP, (7, 1, 0, "OH7JHF-1", STAMP, 1))
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        s.db.execute(INSERT_HOP, HOP)
    assert s.db.execute(
        "SELECT position, via_internet FROM message_hop ORDER BY position, via_internet"
    ).fetchall() == [(0, 1), (1, 0), (1, 1)]
    assert "message_hop_message" in " ".join(
        str(r) for r in s.db.execute("EXPLAIN QUERY PLAN SELECT * FROM message_hop WHERE message_id = 7")
    )
    s.close()


@pytest.mark.parametrize(
    "row, name",
    [
        ((7, 0, STAMP, "OH2RCH-2"), "message_attempt_number"),
        ((7, 1, "noon", ""), "message_attempt_sent_form"),
        ((7, 1, STAMP, "oh2rch-2"), "message_attempt_path_form"),
        ((7, 1, STAMP, "OH2RCH-2,,OH2RDG"), "message_attempt_path_form"),
        ((7, 1, STAMP, None), "NOT NULL"),
    ],
)
def test_the_attempt_table_refuses_what_the_program_cannot_produce(
    tmp_path: Path, row: tuple[object, ...], name: str
) -> None:
    s = opened(tmp_path / DB_NAME)
    with pytest.raises(sqlite3.IntegrityError, match=name):
        s.db.execute("INSERT INTO message_attempt (message_id, attempt, sent_at, path) VALUES (?, ?, ?, ?)", row)
    s.db.execute(
        "INSERT INTO message_attempt (message_id, attempt, sent_at, path) VALUES (7, 1, ?, '')", (STAMP,)
    )  # (a direct path is empty)
    s.close()
