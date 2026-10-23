"""`neoaprs map [--radius KM] [--maxzoom Z] [--source SRC] [--lat DEG --lon DEG] [--dry-run] [--data DIR]`: the base map's command line (neoaprs/services/mapcli.py) under the main command. It does what
the page's Estimate and Download buttons do. This module is the one place of the commands that builds the map's service, which is why `neoaprs.cli.mapcmd` is among the builders in tests/test_architecture.py."""
from neoaprs.services.mapcli import main as map_main


def main(argv: list[str]) -> int:
    return map_main(argv, prog="neoaprs map")
