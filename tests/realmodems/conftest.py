"""The tests of tests/realmodems start real modems: they are collected only with NEOAPRS_REAL_MODEMS=1,
and stations.refusal decides whether they may run here (docs/realmodems.md)."""

import os

collect_ignore_glob = [] if os.environ.get("NEOAPRS_REAL_MODEMS") == "1" else ["test_*.py"]
