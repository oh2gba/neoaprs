"""The size ratchet: a module of neoaprs/ has at most 500 lines of code, a class 400, a function 80 and a
complexity of 12 (docs/ARCHITECTURE.md). What is over today is listed in tests/size_baseline.json
with its current size as ceiling: new code is under the limits, a listed unit never grows, and a
shrunk one is tightened.
"""

import pytest

from tests.support.codemap import LIMITS, Tree, complexity_of, load_baseline, load_tree, measure, offenders, tighten

Sizes = dict[str, dict[str, int]]


def problems(now: Sizes, baseline: Sizes) -> list[str]:
    """What is wrong between today's sizes and the baseline: grown, new, loose, or no longer needed."""
    out: list[str] = []
    for kind, limit in LIMITS.items():
        for key, size in sorted(now[kind].items()):
            ceiling = baseline[kind].get(key)
            if ceiling is None and size > limit:
                out.append(f"{kind}: {key} is {size} (limit {limit}); split it, new code obeys the limits")
            elif ceiling is not None and size > ceiling:
                out.append(f"{kind}: {key} grew from {ceiling} to {size}; a listed unit may only shrink")
            elif ceiling is not None and limit < size < ceiling:
                out.append(
                    f"{kind}: {key} shrank from {ceiling} to {size}; lower its ceiling (python -m tests.support.codemap --tighten)"
                )
            elif ceiling is not None and size <= limit:
                out.append(
                    f"{kind}: {key} is {size}, within the limit {limit}; delete it from tests/size_baseline.json (python -m tests.support.codemap --tighten)"
                )
        out.extend(
            f"{kind}: {key} is in the baseline but does not exist any more; delete it (python -m tests.support.codemap --tighten)"
            for key in sorted(baseline[kind])
            if key not in now[kind]
        )
    return out


def test_the_code_is_within_the_limits_or_listed_at_its_current_size() -> None:
    found = problems(measure(load_tree()), load_baseline())
    assert not found, "\n".join(found)


def test_the_baseline_only_lists_what_is_over_a_limit() -> None:
    baseline = load_baseline()
    assert all(ceiling > LIMITS[kind] for kind, entries in baseline.items() for ceiling in entries.values())
    assert baseline == offenders(baseline), "the baseline has the right shape"


# ---- the rules fail on made-up numbers -----------------------------------------------------------


def sizes(**kinds: dict[str, int]) -> Sizes:
    return {kind: kinds.get(kind, {}) for kind in LIMITS}


def test_a_new_unit_over_a_limit_is_found() -> None:
    assert problems(sizes(functions={"neoaprs/x.py::f": 81}), sizes()) == [
        "functions: neoaprs/x.py::f is 81 (limit 80); split it, new code obeys the limits"
    ]
    assert (
        problems(
            sizes(
                functions={"neoaprs/x.py::f": 80},
                modules={"neoaprs/x.py": 500},
                classes={"neoaprs/x.py::C": 400},
                complexity={"neoaprs/x.py::f": 12},
            ),
            sizes(),
        )
        == []
    )


def test_a_listed_unit_that_grew_is_found() -> None:
    now, base = sizes(modules={"neoaprs/big.py": 601}), sizes(modules={"neoaprs/big.py": 600})
    assert problems(now, base) == ["modules: neoaprs/big.py grew from 600 to 601; a listed unit may only shrink"]


def test_a_listed_unit_that_shrank_must_lower_its_ceiling() -> None:
    now, base = sizes(classes={"neoaprs/x.py::C": 450}), sizes(classes={"neoaprs/x.py::C": 500})
    assert problems(now, base) == [
        "classes: neoaprs/x.py::C shrank from 500 to 450; lower its ceiling (python -m tests.support.codemap --tighten)"
    ]


def test_a_listed_unit_back_within_its_limit_or_gone_must_leave_the_list() -> None:
    base = sizes(complexity={"neoaprs/x.py::f": 20, "neoaprs/x.py::gone": 14})
    found = problems(sizes(complexity={"neoaprs/x.py::f": 12}), base)
    assert len(found) == 2
    assert found[0].startswith("complexity: neoaprs/x.py::f is 12, within the limit 12")
    assert found[1].startswith("complexity: neoaprs/x.py::gone is in the baseline but does not exist")


def test_tighten_lowers_drops_and_never_raises_or_adds() -> None:
    base = sizes(functions={"a::f": 120, "a::g": 110, "a::h": 100, "a::i": 90})
    now = sizes(functions={"a::f": 90, "a::g": 50, "a::h": 115, "a::i": 90, "a::new": 81})
    new, refused = tighten(base, now)
    # F lowered, g dropped, h kept at its old ceiling, nothing added
    assert new["functions"] == {"a::f": 90, "a::h": 100, "a::i": 90}
    assert sorted(refused) == [
        "functions a::h: 115 is over its ceiling 100",
        "functions a::new: 81 is over the limit 80 and not in the baseline",
    ]


def test_the_measures_lines_and_complexity_of_a_made_up_module() -> None:
    source = (
        "class C:\n"
        "    def f(self, xs):\n"
        "        for x in xs:\n"
        "            if x and x > 1:\n"
        "                try:\n"
        "                    g(x)\n"
        "                except ValueError:\n"
        "                    pass\n"
        "        return [y for y in xs if y]\n"
        "\n"
        "async def top(a):\n"
        "    while a:\n"
        "        a -= 1\n"
        "    else:\n"
        "        return 0\n"
        "    def inner():\n"
        "        if a:\n"
        "            return 1\n"
    )
    tree: Tree = {"neoaprs/m.py": source}
    got = measure(tree)
    assert got["modules"] == {"neoaprs/m.py": 17}  # the blank line is not counted
    assert got["classes"] == {"neoaprs/m.py::C": 9}
    assert got["functions"] == {"neoaprs/m.py::C.f": 8, "neoaprs/m.py::top": 8}
    # f: 1 + for + if + except + the comprehension = 5 (the `and` and the comprehension's own `if`
    # do not count); top: 1 + while + its else + the nested function's if = 4
    assert got["complexity"] == {"neoaprs/m.py::C.f": 5, "neoaprs/m.py::top": 4}


@pytest.mark.parametrize(
    "body, expected",
    [
        ("pass", 1),
        ("if a:\n    pass\nelif b:\n    pass", 3),
        ("match a:\n    case 1:\n        pass\n    case _:\n        pass", 3),
        ("x = [1 for i in a for j in b]", 3),
    ],
)
def test_complexity_counts_what_mccabe_counts(body: str, expected: int) -> None:
    import ast

    func = ast.parse("def f(a, b):\n" + "".join(f"    {line}\n" for line in body.splitlines()))
    assert complexity_of(func) == expected
