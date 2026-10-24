# Installing NeoAPRS

Every file is on the [releases page](https://github.com/oh2gba/neoaprs/releases/latest). `<version>` below stands for the number of the release you download.

| system | what to get |
|---|---|
| Windows | `NeoAPRS-Setup-<version>.exe` ([Windows](#windows)) |
| Linux with a desktop | `NeoAPRS-<version>-x86_64.AppImage` ([AppImage](#linux-appimage)) |
| Raspberry Pi, Debian, Ubuntu | `neoaprs_<version>_arm64.deb` or `_amd64.deb` ([.deb](#raspberry-pi-debian-ubuntu-deb)) |
| Linux, macOS, Raspberry Pi | the install line ([install line](#install-line-linux-and-macos)) |
| any system with Python 3.13 | the wheel, with `uv` or `pip` ([wheel](#the-wheel-with-uv-or-pip)) |

After installing, [start.md](start.md) takes you through the first start. The data you make (settings, messages, packets, the map) is kept in the data folder, which no installer, update or removal touches.

## Windows

Run `NeoAPRS-Setup-<version>.exe`. It installs for your user only, so it needs no administrator rights, into `%LOCALAPPDATA%\Programs\NeoAPRS`.

The installer is not signed. Windows SmartScreen may say "Windows protected your PC" the first times: choose **More info**, then **Run anyway**.

- The Start menu group NeoAPRS has **NeoAPRS** (the [desktop app](desktop.md), which starts the daemon if none is running), **Stop NeoAPRS** and the uninstaller.
- The task **Desktop shortcut** is off by default.
- The task **Start NeoAPRS when I sign in** is on by default. It starts the app in the tray when you sign in.
- The last page offers **Open NeoAPRS now**.
- Installing over an older version ends the running app and daemon first. **Open NeoAPRS now** on the last page starts the app again; a silent update leaves that to the next sign-in, except the one of **Update now** ([Updating](#updating)), which starts again what was running.
- The uninstaller ends the app and the daemon, removes the program, the start at sign-in and the service entry, and leaves the data folder `%LOCALAPPDATA%\NeoAPRS`.

A silent install: `NeoAPRS-Setup-<version>.exe /VERYSILENT /SUPPRESSMSGBOXES /CURRENTUSER`. Add `/TASKS=""` for no start at sign-in and no desktop shortcut, `/DIR=` for another folder, `/LOG=FILE` for an install log.

The installer puts three programs in the folder: `neoaprs.exe` (the command, with a console), `neoaprsw.exe` (the same without a console window; it starts the daemon) and `neoaprs-app.exe` (the desktop app).

Windows asks whether to let NeoAPRS through its firewall the first time you allow access from the network. Allow it on private networks ([network.md](network.md)).

The radio is a COM port. The page lists the ports of the computer to pick from ([radio.md](radio.md)).

## Linux AppImage

`NeoAPRS-<version>-x86_64.AppImage` is one file with Python, NeoAPRS and the desktop app's web engine inside (about 150 MB). Nothing is installed. It runs on x86_64 Linux with glibc 2.34 or newer (Ubuntu 22.04, Debian 12, Fedora 35 and newer) and the usual desktop libraries.

```bash
chmod +x NeoAPRS-<version>-x86_64.AppImage
./NeoAPRS-<version>-x86_64.AppImage                 # no arguments: the desktop app
./NeoAPRS-<version>-x86_64.AppImage doctor          # arguments: the neoaprs command (--version, open, stop, service install, map ...)
```

- **Data** is where every install keeps it, `~/.local/share/neoaprs` (`$XDG_DATA_HOME/neoaprs`). A newer AppImage in place of the old one finds its settings, messages and map, and the file can be deleted without touching them.
- **The radio's port** needs the group that owns serial devices: `sudo usermod -aG dialout $USER` (`uucp` on Arch), then log out and in. `doctor` says so.
- **FUSE.** The file mounts itself with `fusermount`, which the `fuse3` (or `fuse`) package provides; `libfuse2` is not needed. Without FUSE (a container, a minimal install) start it with `--appimage-extract-and-run` as the first argument, which unpacks it into a temporary folder at every start. Or run `--appimage-extract` once and start `squashfs-root/AppRun`.
- **Start at login.** `./NeoAPRS-<version>-x86_64.AppImage service install` writes a user service that starts the AppImage file. The tray menu's *Start at sign-in* writes the same file into the autostart entry. Move the file where you want it first, then run the command from there; after an update by hand run it again from the new file (**Update now** keeps the file's name, so there is nothing to do).
- **The window.** The web engine's sandbox needs user namespaces. Where the system refuses them (the AppArmor of Ubuntu 24.04) the AppImage starts the engine without it, which is safe because the window shows only NeoAPRS's own page.
- **The map tool.** The `pmtiles` program that cuts the map is fetched into the `bin/` folder of the data folder the first time the map is made ([page.md](page.md#the-base-map)).

## Raspberry Pi, Debian, Ubuntu (.deb)

`neoaprs_<version>_arm64.deb` is for a Raspberry Pi with 64-bit Raspberry Pi OS, `neoaprs_<version>_amd64.deb` for a PC with Debian or Ubuntu. It is meant for a machine without a screen. Debian 12, Ubuntu 22.04 and Raspberry Pi OS (Bookworm) and newer are supported.

NeoAPRS needs Python 3.13, which Raspberry Pi OS and Debian 12 do not have, so the package brings its own Python and libraries (about 20 MB to download, 60 to 70 MB installed). It uses nothing of the system's Python and does not include the desktop app.

```bash
sudo apt install ./neoaprs_<version>_arm64.deb      # apt, not dpkg -i; the file name must start with ./
neoaprs service install --linger                    # as your own user, not root: starts it at boot and keeps it running
neoaprs doctor                                      # what is wrong with this computer, if anything
```

- **What is installed.** Everything is in `/opt/neoaprs`, plus a link `/usr/bin/neoaprs` and the documents in `/usr/share/doc/neoaprs` (the licence, the manual, the README, the changelog). There is no manual page and no system service.
- **The service is yours.** The package writes nothing in anyone's home and starts nothing at install. `neoaprs service install` makes a user service from your own account. The installer ends by saying so, with the `usermod -aG dialout $USER` line for the serial port.
- **Upgrading.** `sudo apt install ./neoaprs_<new>.deb` replaces the files and restarts the NeoAPRS service of each logged-in user who has one running. Where that cannot be done it says that a running NeoAPRS keeps the old version until you run `systemctl --user restart neoaprs`.
- **Removing.** `sudo apt remove neoaprs` takes the program, the link and the documents away and leaves your data and the unit in your home, which can no longer start. Run `neoaprs service remove` before removing the package, or afterwards `systemctl --user disable --now neoaprs && rm ~/.config/systemd/user/neoaprs.service`.

## Install line (Linux and macOS)

```bash
curl -LsSf https://github.com/oh2gba/neoaprs/releases/latest/download/install.sh | sh
```

The script needs no root. It installs [uv](https://docs.astral.sh/uv/) with Astral's installer if there is none, then NeoAPRS with Python 3.13 from the release's wheel. It then runs `neoaprs service install` (a systemd user unit on Linux, a launchd agent on macOS) and restarts the service if this was an update.

If you are not in the group that owns serial devices (`dialout`, `uucp` on Arch) it prints the `usermod` line. It ends by printing the address of the page and running `neoaprs doctor`. Run the line again to update.

## The wheel with uv or pip

Needs Python 3.13 (`uv` fetches one if the system has none).

```bash
uv tool install neoaprs-<version>-py3-none-any.whl      # or: pip install neoaprs-<version>-py3-none-any.whl
neoaprs doctor                                          # what is wrong with this computer, if anything
neoaprs                                                 # the daemon; open http://127.0.0.1:7303/
neoaprs service install                                 # start it at login from now on
neoaprs open                                            # the page in your browser, starting NeoAPRS first if it is not running
```

The command `neoaprsw` is the same without a console window. The [desktop app](desktop.md) needs the extra `app`: `uv tool install "neoaprs[app]"` or `pip install "neoaprs[app]"`. To run from a clone of the repository see [`docs/development.md`](../development.md).

## Start at login

`neoaprs service install` sets NeoAPRS up to start when you log in and keeps it running, the way each system does it. It runs the same Python and the data folder given with `--data` (else the default).

- `neoaprs service remove` takes it away again and leaves the data. `neoaprs service status` says whether it is set up and whether the daemon answers; the exit code is 0 when both are true. `neoaprs service logs` prints the end of the log.
- **Linux** writes a systemd user unit, `~/.config/systemd/user/neoaprs.service` (`$XDG_CONFIG_HOME/systemd/user`), and runs `systemctl --user daemon-reload` and `enable --now`, then `try-restart` when what the unit does changed. Running it again after an update brings the unit up to date. A file there that `neoaprs service install` did not write is never touched; the command stops and says so.
- `--linger` on Linux also runs `loginctl enable-linger`, so the service starts at boot and survives a logout. It checks that you are in the group that owns the serial devices and prints the exact `usermod` command when you are not. `journalctl --user -u neoaprs -f` is the journal.
- **Windows** adds the value `NeoAPRS` to your login list (the key `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`, which Settings, Apps, Startup shows) and starts the daemon at once if none runs. It is not a Windows service, because a service has no desktop and not your profile, and the COM port, the data folder and the page belong to the logged-in user. `remove` deletes the value; a daemon that is running goes on until you stop it or log out.
- **macOS** writes a launchd agent, `~/Library/LaunchAgents/eu.oh2gba.neoaprs.plist`. It is loaded with `launchctl bootstrap gui/UID` and unloaded with `bootout`. It starts at login and starts again 30 seconds after it ends with a failure. Its own output, such as an error before the daemon logs anything, is `launchd.log` in the data folder.

The page is on port 7303, on this computer only unless you allow access from the network ([network.md](network.md)). `--web-port N` takes another port for one run. The service does not restart when the daemon ends with exit code 2, which means the database cannot be used or another NeoAPRS is running on the same data folder.

## Updating

NeoAPRS asks once a day whether a newer version is out ([the update check](#the-update-check)). When one is, **Update to <version>** appears in the footer under the panel; on a phone the header has a small badge with the new number, because the map has no footer.

A click opens a window in the middle of the page: **NeoAPRS <version> is available**, the version you have, what is new (the project's note and a button to the release notes), and what to do for the way this copy was installed. Your settings, messages, packets and map stay in every case, and open pages load the new version by themselves.

### Update now (Windows installer, AppImage)

Where NeoAPRS can update itself, the window has an **Update now** button. NeoAPRS then:

1. downloads the file of exactly the announced version from the project's release page on GitHub, and the release's list of checksums (`SHA256SUMS`), showing how far the download is (**Cancel** stops it);
2. checks that the file's SHA-256 checksum is the one the list gives it. A file that does not match is deleted and nothing is installed;
3. installs it and starts again:
   - **Windows:** the installer runs without a window. It ends the app and the daemon, replaces the program and starts again what was running (the app, or the daemon alone), on the same data folder. The page says *Installing… NeoAPRS restarts in a moment* and connects again by itself;
   - **AppImage:** the new file takes the place of the old one, under the old file's name, so that a service or a start at login finds it. The old file is kept beside it as `<name>.old` until the new version has started. NeoAPRS then starts the file again with the same arguments.

Nothing is downloaded or installed unless you press the button. When something goes wrong the window says so in plain words, offers **Try again** and shows the steps by hand. An AppImage in a folder you cannot write to has no Update now: the window shows the steps.

### By hand

The window shows the steps for this copy, each file as a button and each command with a **Copy** button. Under Update now they are folded away as **Or update by hand**.

| installed as | the steps |
|---|---|
| Windows installer | download `NeoAPRS-Setup-<version>.exe` and run it; it ends the running app and daemon and replaces the program; **Open NeoAPRS now** on its last page starts the app again |
| AppImage | download `NeoAPRS-<version>-x86_64.AppImage`, make it executable (in its file properties, or `chmod +x`), quit NeoAPRS and start the new file instead of the old one, then delete the old file. If a service starts the AppImage (the service names the old file), run `./NeoAPRS-<version>-x86_64.AppImage service install` once in the folder of the new file |
| .deb (Raspberry Pi, Debian, Ubuntu) | download the package for your computer (`neoaprs_<version>_arm64.deb` on a Raspberry Pi, `_amd64.deb` on a PC; the window picks the right one) and run `sudo apt install ./neoaprs_<version>_arm64.deb` in the folder you downloaded it to. It replaces `/opt/neoaprs` and restarts a running service; if the service still runs the old version, `systemctl --user restart neoaprs` |
| install line | run the line again in a terminal; it installs the new version and restarts the service |
| pip | `pip install -U` the release's wheel (the window has the whole command) in the environment NeoAPRS is installed in, then `neoaprs service install` restarts a service, else quit NeoAPRS and start it again |
| a clone of the repository | `git pull`, `uv sync`, then `systemctl --user restart neoaprs` for a service, else quit and start it again |

**Open pages follow by themselves.** A page is built for one version of NeoAPRS, and the daemon says its version when a page connects. When they differ the page loads itself again once, in a browser tab and in the desktop app's window alike. It does so for the next update too.

## The update check

Once a day the daemon asks the project's version page whether a newer NeoAPRS is out, so that you hear of it and the project can count how many copies are in use. The first question comes a minute after the daemon starts, then one every 24 hours. A desktop app and the daemon it starts count once, and opening the page asks nothing.

- **What is sent.** One request with the version and the kind of system in the address, `https://oh2gba.eu/neoaprs/version.php?v=<version>&os=linux`, and a User-Agent that says the same. The system is `windows`, `macos`, `linux`, `linux-appimage` or `linux-arm` (a Raspberry Pi). Nothing else: no call, no position, no setting, no identifier.
- **What is kept.** The server adds a line with the time (to the minute, UTC), the version and the system to a log, and hands the same three values to the project's status page, where they are counted. Your address is used only to tell two copies of the same version and system apart in the count, and is not stored. The source of the page is `server/version.php` in the repository.
- **The answer** is a few lines of JSON: the latest release, the address of the project page and an optional note. When it is newer than yours, the footer shows it and the note is its hover text. A page that cannot be reached, or answers something else, is ignored: nothing is shown and the next question is the next day.
- **Switching it off.** The check has no setting. `NEOAPRS_UPDATE_CHECK=0` in the environment switches it off for one run. The setting `update/url` can point at a page of your own (`neoaprs db set update/url ADDRESS`).
- **Check now** is a button in the Settings tab, in the Update check group. It asks at once and says in the toast at the bottom `up to date (<version>)` or why there was no answer; when a newer version is out, the update window opens. It works with the daily check switched off, and does not move the daily schedule.
