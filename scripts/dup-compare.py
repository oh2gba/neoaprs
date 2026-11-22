#!/usr/bin/env python3
"""Compare a jscpd JSON report with the committed baseline (the ratchet of scripts/dup-check).

    scripts/dup-compare.py REPORT.json BASELINE.json            exit 1 and say what is new or larger
    scripts/dup-compare.py REPORT.json BASELINE.json --update   write the baseline from the report
                                                                (not larger unless --allow-growth)

A clone is the pair of files it joins; line counts are compared, not the percentage."""
import json
import os
import sys
from pathlib import Path
from typing import Any

Summary = dict[str, Any]


def relative(name: str) -> str:
    """Return a report path as the baseline writes it: relative to the repository root."""
    return os.path.relpath(name).replace(os.sep, "/") if os.path.isabs(name) else name


def summarize(report: dict[str, Any]) -> Summary:
    pairs: dict[str, dict[str, int]] = {}
    for clone in report["duplicates"]:
        key = " <-> ".join(sorted((relative(clone["firstFile"]["name"]), relative(clone["secondFile"]["name"]))))
        pair = pairs.setdefault(key, {"clones": 0, "lines": 0})
        pair["clones"] += 1
        pair["lines"] += int(clone["lines"])
    total = report["statistics"]["total"]
    return {"duplicatedLines": int(total["duplicatedLines"]), "percentage": float(total["percentage"]), "pairs": dict(sorted(pairs.items()))}


def problems(now: Summary, baseline: Summary) -> list[str]:
    out: list[str] = []
    for key, pair in now["pairs"].items():
        old = baseline["pairs"].get(key)
        if old is None:
            out.append(f"new clone: {key} ({pair['clones']} clone(s), {pair['lines']} lines): give the code one home")
        elif pair["lines"] > old["lines"] or pair["clones"] > old["clones"]:
            out.append(f"larger clone: {key} is now {pair['clones']} clone(s), {pair['lines']} lines (baseline {old['clones']}, {old['lines']})")
    if now["duplicatedLines"] > baseline["duplicatedLines"]:
        out.append(f"duplicated lines went up: {now['duplicatedLines']} ({now['percentage']}%), baseline {baseline['duplicatedLines']} ({baseline['percentage']}%)")
    return out


def tightenable(now: Summary, baseline: Summary) -> bool:
    return now["duplicatedLines"] < baseline["duplicatedLines"] or any(key not in now["pairs"] for key in baseline["pairs"])


def main(argv: list[str]) -> int:
    if argv[:1] in (["-h"], ["--help"]):
        print(__doc__)
        return 0
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 2:
        print(__doc__)
        return 2
    now = summarize(json.loads(Path(args[0]).read_text(encoding="utf-8")))
    baseline_path = Path(args[1])
    # The very first baseline accepts what is there.
    first = not baseline_path.exists()
    baseline: Summary = {"duplicatedLines": 0, "percentage": 0.0, "pairs": {}} if first else json.loads(baseline_path.read_text(encoding="utf-8"))
    found = problems(now, baseline)
    if "--update" in argv:
        if found and not first and "--allow-growth" not in argv:
            print("\n".join(found) + "\nthe baseline is not made larger; fix the clones (or pass --allow-growth and say why in the commit)")
            return 1
        baseline_path.write_text(json.dumps(now, indent=1) + "\n", encoding="utf-8")
        print(f"baseline written: {len(now['pairs'])} pair(s), {now['duplicatedLines']} duplicated lines ({now['percentage']}%)")
        return 0
    if found:
        print("\n".join(found))
        return 1
    note = "; the baseline can be tightened: scripts/dup-check --update" if tightenable(now, baseline) else ""
    print(f"no new duplication: {now['duplicatedLines']} duplicated lines ({now['percentage']}%), baseline {baseline['duplicatedLines']}{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
