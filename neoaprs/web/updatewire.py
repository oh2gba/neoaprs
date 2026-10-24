"""Update now on the wire: the topic `update` (what the update the daemon does itself is doing) and the commands that start and cancel it. Models like the rest of the protocol, listed in `neoaprs/web/protocol.py`."""
from typing import Literal

from pydantic import Field

from .wirebase import _Command, _Model


class UpdateState(_Model):
    """Update now (neoaprs/services/selfupdate.py): whether this copy can update itself, and the steps of the update it is doing. The value of the topic `update`, told whole as it changes, at most four times a second."""
    supported: bool = Field(description="this copy can update itself (the Windows installer, an AppImage in a folder its user can write): the page offers Update now; else it shows the steps")
    state: Literal["idle", "downloading", "verifying", "installing", "restarting", "error"] = Field(
        description="`idle`: no update is running. `downloading`: SHA256SUMS and then the file of the release are fetched (`percent`). `verifying`: the file's SHA-256 is held to SHA256SUMS. `installing`: the file is put in place. "
                    "`restarting`: NeoAPRS ends and starts again as the new version (the page loses its socket and finds the new daemon). `error`: the update failed, `problem` says how")
    version: str = Field(description="the version being installed; empty while idle")
    percent: int | None = Field(ge=0, le=100, description="how much of the file has come; null when the server did not say its size")
    downloaded: int = Field(ge=0, description="the bytes of the file so far")
    total: int | None = Field(ge=0, description="the size of the file in bytes, when the server said it")
    problem: Literal["", "download", "no_checksum", "checksum", "install", "no_restart"] = Field(
        description="for `error`: `download` (the file or SHA256SUMS could not be fetched), `no_checksum` (SHA256SUMS does not name the file), `checksum` (the file's SHA-256 is not the one SHA256SUMS gives it: it was deleted), "
                    "`install` (it could not be put in place, or the installer could not be started), `no_restart` (it was installed but NeoAPRS did not restart); empty otherwise")
    detail: str = Field(description="the English sentence of the problem, for the log and the page's details; empty when all is well")


class UpdateNow(_Command):
    """Starts Update now to `version`, which must be the version the update check announced (the `update` of `status`): the daemon fetches the file for this copy and SHA256SUMS from the GitHub release of exactly that
    version, checks the file's SHA-256 and installs it, and NeoAPRS restarts. The progress is the topic `update`. An `error` when this copy cannot update itself (`update.unsupported`, `update.blocked`), the version
    is not the one announced (`update.not_announced`) or an update is running (`update.busy`)."""
    cmd: Literal["update_now"]
    version: str = Field(min_length=1, max_length=40)


class UpdateCancel(_Command):
    """Ends the download of Update now; nothing of it is left. An `error` (`update.not_running`) when no download is running: an install that has begun is not stopped."""
    cmd: Literal["update_cancel"]
