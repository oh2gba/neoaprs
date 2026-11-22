"""`neoaprs map`: make the base map of the operator's area.

The command line is in neoaprs/services/mapcli.py. `neoaprs map --world` makes the bundled
world map instead."""

from neoaprs.services.mapcli import main as map_main


def main(argv: list[str]) -> int:
    if argv[:1] == ["--world"]:
        from .worldcmd import main as world_main

        return world_main(argv[1:])
    return map_main(argv, prog="neoaprs map")
