# The systemd unit

One line per unit file in the repository; `tests/test_hygiene.py` fails when a unit is added without a line here, or a line names a unit that is gone.

This is the user unit that `neoaprs service install` writes on Linux. **The file is a template and is part of the package** (`neoaprs/cli/neoaprs.service`, package data of the wheel): it is never copied into a
system folder as it stands. `neoaprs service install` fills its places in (`@COMMAND@`, the interpreter that runs the command with `-m neoaprs`, or the AppImage file when it runs from an AppImage, `@DATA@`, the data folder, `@WORKING_DIRECTORY@` and `@DOCUMENTATION@`, the clone's
folder and its README when NeoAPRS runs from a git clone, else the project's web address and no working directory) and writes the result to `~/.config/systemd/user/neoaprs.service` (`$XDG_CONFIG_HOME/systemd/user`)
under a first line that says it wrote it, runs `systemctl --user daemon-reload` and `enable --now`, and restarts the service if what the unit does changed. `neoaprs service remove` stops and disables the service and
deletes that file. A change to the template reaches systemd by running `neoaprs service install` again. A file at that place that the command did not write is never touched. `scripts/install.sh` is the same command for a clone: `.venv/bin/python -m neoaprs service install --data DIR/data --clone DIR --linger`.

The user who runs the unit must be in the group that owns the serial devices (`dialout` on Debian, Ubuntu, Fedora and openSUSE, `uucp` on Arch), or the radio's port stays closed; the command says so, and gives the
command that cures it, when the user is not. `neoaprs service install --linger` also runs `loginctl enable-linger`, so that the service starts at boot and survives a logout.

| unit | what it does |
|---|---|
| `neoaprs/cli/neoaprs.service` | the daemon: `PYTHON -m neoaprs --data DATA`, web page on 7303; restarts always, but not on exit 2 (the database cannot be used: a restart would only repeat it), and after five starts within ten minutes it stays `failed` instead of hiding a crash loop (`StartLimitBurst`); SIGTERM stops it cleanly within 10 seconds. It sets `DBUS_SESSION_BUS_ADDRESS=unix:path=%t/bus` (`%t` is the user's runtime folder, `/run/user/UID`): the message alert runs `notify-send` and a user service does not get the desktop session's environment, so without it the notification has no bus to find (the command gets that variable and a few others through `neoaprs/childenv.py`, not the daemon's whole environment) |
