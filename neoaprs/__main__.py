"""Entry point for `python -m neoaprs`; runs the command line in neoaprs/cli/."""
import sys

from neoaprs.cli import main

if __name__ == "__main__":
    sys.exit(main())
