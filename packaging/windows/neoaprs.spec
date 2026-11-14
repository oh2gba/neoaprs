# PyInstaller spec of the Windows app: a folder (not one file: a one-file program unpacks itself into the temp folder at every start, which is slow and what virus scanners dislike) with three programs,
# `neoaprs.exe` (console), `neoaprsw.exe` (no console: the daemon) and `neoaprs-app.exe` (no console: the desktop app, with the icon), sharing one set of libraries. The app is not called NeoAPRS.exe: Windows
# names are not case sensitive, and that would be neoaprs.exe. Run it from the repository root with NeoAPRS and its extra `app` installed in the build environment (the wheel, not the clone):
#     pyinstaller --noconfirm --distpath dist --workpath build packaging/windows/neoaprs.spec
import re
import tempfile
from pathlib import Path

import neoaprs
import neoaprs.desktop
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules
from PyInstaller.utils.win32.versioninfo import FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo

# The commands are imported by name when they are used (neoaprs/cli/__init__.py, servicecmd.backend_for), and pyserial loads its URL handlers by name: PyInstaller cannot see either.
hidden = collect_submodules("neoaprs") + ["serial.urlhandler.protocol_socket", "serial.urlhandler.protocol_loop", "serial.tools.list_ports_windows"]
# The app's toolkits: the shell of Windows is imported by name (neoaprs/desktop/cmd.py, shell.choose), pystray picks its backend by name, and pywebview drives WebView2 through pythonnet (clr_loader brings the
# runtime it loads). pywebview's own PyInstaller hook adds its scripts and its DLLs.
hidden += ["webview", "webview.platforms.winforms", "webview.platforms.edgechromium", "pystray", "pystray._win32", "PIL.Image"]
dotnet = [collect_all(name) for name in ("pythonnet", "clr_loader")]
dotnet_datas = [item for datas_, _bins, _hidden in dotnet for item in datas_]
dotnet_binaries = [item for _datas, bins, _hidden in dotnet for item in bins]
hidden += [item for _datas, _bins, hidden_ in dotnet for item in hidden_]
icon = str(Path(neoaprs.desktop.__file__).parent / "icon.ico")
# The page, the placeholder page, the sample capture and the world map (neoaprs/maps/, which the daemon serves until a map of the area is made: neoaprs/worldmap.py looks for it in _internal); the systemd unit template is of no use on Windows.
datas = collect_data_files("neoaprs", excludes=["**/*.service", "**/__pycache__/**"]) + dotnet_datas + collect_data_files("certifi")          # (certifi's cacert.pem: the roots trusted beside the system's, neoaprs/httpstrust.py)

# (PySide6 is the shell of the other systems: the app of Windows has no use for it, even if a build environment has it)
a = Analysis(["neoaprs_entry.py"], pathex=[SPECPATH], binaries=dotnet_binaries, datas=datas, hiddenimports=hidden, excludes=["tkinter", "PySide6", "shiboken6"], noarchive=False)
pyz = PYZ(a.pure)

# Each program says what it is (its file properties: product, publisher, description, version): an unsigned program that says nothing is what Windows Defender's guess takes for a trojan (4 Nov 2026).
VERSION_DIR = Path(tempfile.mkdtemp(prefix="neoaprs-version-"))
NUMBERS = tuple(int(n) for n in re.findall(r"\d+", neoaprs.VERSION)[:3]) + (0,)


def version_file(name: str, description: str) -> str:
    """The version resource of `name`.exe, as the text file PyInstaller reads (`version=`)."""
    strings = [("CompanyName", "OH2GBA"), ("FileDescription", description), ("FileVersion", neoaprs.VERSION), ("InternalName", name), ("LegalCopyright", "GNU GPL v3 or later"),
               ("OriginalFilename", f"{name}.exe"), ("ProductName", "NeoAPRS"), ("ProductVersion", neoaprs.VERSION)]
    info = VSVersionInfo(ffi=FixedFileInfo(filevers=NUMBERS, prodvers=NUMBERS), kids=[StringFileInfo([StringTable("040904B0", [StringStruct(k, v) for k, v in strings])]),
                                                                                       VarFileInfo([VarStruct("Translation", [1033, 1200])])])
    path = VERSION_DIR / f"{name}.txt"
    path.write_text(str(info), encoding="utf-8")
    return str(path)


common = dict(exclude_binaries=True, debug=False, strip=False, upx=False)
console = EXE(pyz, a.scripts, [], name="neoaprs", console=True, icon=icon, version=version_file("neoaprs", "NeoAPRS, the command"), **common)
windowed = EXE(pyz, a.scripts, [], name="neoaprsw", console=False, icon=icon, version=version_file("neoaprsw", "NeoAPRS, the APRS client that runs in the background"), **common)
app = EXE(pyz, a.scripts, [], name="neoaprs-app", console=False, icon=icon, version=version_file("neoaprs-app", "NeoAPRS, the window and the tray icon"), **common)
coll = COLLECT(console, windowed, app, a.binaries, a.datas, strip=False, upx=False, name="NeoAPRS")
