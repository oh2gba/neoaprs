"""`python -m neoaprs`: the command `neoaprs` (neoaprs/cli/): with flags and no command it runs the daemon (neoaprs/daemon.py)."""
import sys

from neoaprs.cli import main

if __name__ == "__main__":
    sys.exit(main())
