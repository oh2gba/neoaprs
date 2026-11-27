"""Windows: the disposable asker. Started hidden by the daemon with a program's process id, it lets go of its
own console, attaches to the program's, sends Ctrl-Break to the program's group, prints its calls as one
JSON line and exits with winchild's code for what happened. The daemon itself never touches a console.
"""

import json
import sys

from . import winchild


def main(argv: list[str]) -> int:
    try:
        pid = int(argv[0])
    except (IndexError, ValueError):
        return winchild.BAD_ARGUMENT
    steps: winchild.Steps = []
    code = winchild.send_event(pid, winchild.CTRL_BREAK_EVENT, pid, steps=steps)
    if sys.stdout is not None:  # (a program without a console may have none)
        print(json.dumps(steps), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
