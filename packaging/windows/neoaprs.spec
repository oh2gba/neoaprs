# PyInstaller spec of the Windows app: a folder (not one file: a one-file program unpacks itself into the temp folder at every start, which is slow and what virus scanners dislike) with three programs,
# `neoaprs.exe` (console), `neoaprsw.exe` (no console: the daemon) and `neoaprs-app.exe` (no console: the desktop app, with the icon), sharing one set of libraries. The app is not called NeoAPRS.exe: Windows
# names are not case sensitive, and that would be neoaprs.exe. Run it from the repository root with NeoAPRS and its extra `app` installed in the build environment (the wheel, not the clone):
#     pyinstaller --noconfirm --distpath dist --workpath build packaging/windows/neoaprs.spec
# pmtiles.exe is added next to them in bin/ by packaging/windows/bundle_pmtiles.py (neoaprs/pmtilestool.py finds it there).
from pathlib import Path

import neoaprs.desktop
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

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
# The page, the placeholder page, the sample capture; the systemd unit template is of no use on Windows.
datas = collect_data_files("neoaprs", excludes=["**/*.service", "**/__pycache__/**"]) + dotnet_datas

# (PySide6 is the shell of the other systems: the app of Windows has no use for it, even if a build environment has it)
a = Analysis(["neoaprs_entry.py"], pathex=[SPECPATH], binaries=dotnet_binaries, datas=datas, hiddenimports=hidden, excludes=["tkinter", "PySide6", "shiboken6"], noarchive=False)
pyz = PYZ(a.pure)

common = dict(exclude_binaries=True, debug=False, strip=False, upx=False)
console = EXE(pyz, a.scripts, [], name="neoaprs", console=True, icon=icon, **common)
windowed = EXE(pyz, a.scripts, [], name="neoaprsw", console=False, icon=icon, **common)
app = EXE(pyz, a.scripts, [], name="neoaprs-app", console=False, icon=icon, **common)
coll = COLLECT(console, windowed, app, a.binaries, a.datas, strip=False, upx=False, name="NeoAPRS")
