; Inno Setup script of the Windows installer, NeoAPRS-Setup-VERSION.exe.
; Per user: no administrator rights, no UAC prompt, nothing done to the Windows Firewall (the Mercury
; modem in bin\mercury\ listens on this computer only). The app goes to %LOCALAPPDATA%\Programs\NeoAPRS.
; The Start menu gets "NeoAPRS" (the desktop app neoaprs-app.exe: a window and a tray icon that starts the
; daemon itself), "Stop NeoAPRS" and "NeoAPRS support logs" (neoaprs.exe support: the logs in one file on
; the Desktop). A task makes a desktop shortcut and a task, on by default, starts the app in the tray at
; sign-in (value NeoAPRS of the user's Run key, `neoaprs-app.exe --tray`). The data folder
; (%LOCALAPPDATA%\NeoAPRS) is never touched by the installer or uninstaller.
; Build from the repository root after packaging/windows/neoaprs.spec has made dist\NeoAPRS:
;     iscc /DAppVersion=0.1.0 /Qp packaging\windows\neoaprs.iss        (makes dist-installer\NeoAPRS-Setup-0.1.0.exe)
; Silent: NeoAPRS-Setup-VERSION.exe /VERYSILENT /SUPPRESSMSGBOXES /CURRENTUSER /NORESTART [/LOG=file]
;     [/DIR=folder] [/TASKS=""]  (the last: no start at sign-in, no desktop shortcut).
; Installing over a running NeoAPRS: before Setup replaces any file the code below ends the app and then
; the daemon cleanly (neoaprs-app.exe --quit, neoaprs.exe stop), so the user is not asked to close them.
; Setup's own files-in-use check (Restart Manager) is off: it also names Windows services that read our
; files for a moment (Cryptographic Services, Application Identity), which a per-user Setup cannot close,
; and a silent run then gave up.
; Update now (neoaprs/services/selfinstall.py) runs it silently with /NOCLOSEAPPLICATIONS and two values
; of its own: /NEOAPRSDATA=folder (the data folder of the daemon that runs it) and
; /NEOAPRSRESTART=app or daemon (what was running, started again on that folder once the files are in place).
#ifndef AppVersion
  #error Give the version: iscc /DAppVersion=0.1.0 packaging\windows\neoaprs.iss
#endif
#ifndef BuildDir
  #define BuildDir "..\..\dist\NeoAPRS"
#endif

[Setup]
AppId={{5AE53960-2902-4F1B-99E1-03E486EA7B36}
AppName=NeoAPRS
AppVersion={#AppVersion}
AppVerName=NeoAPRS {#AppVersion}
AppPublisher=OH2GBA
AppPublisherURL=https://github.com/oh2gba/neoaprs
AppSupportURL=https://github.com/oh2gba/neoaprs/issues
AppUpdatesURL=https://github.com/oh2gba/neoaprs/releases
DefaultDirName={localappdata}\Programs\NeoAPRS
DefaultGroupName=NeoAPRS
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
OutputBaseFilename=NeoAPRS-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\neoaprs-app.exe
UninstallDisplayName=NeoAPRS
OutputDir=..\..\dist-installer
; no files-in-use check of Setup's own (see above); the code section ends NeoAPRS
CloseApplications=no

[Tasks]
Name: "autostart"; Description: "Start NeoAPRS when I sign in"; Flags: checkedonce
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

; The Mercury folder is made again by every install, so DLLs of an older Mercury (hamlib, libusb, the
; MinGW runtime) do not stay after an update. The pmtiles program and its licence in bin\ are obsolete:
; the app cuts the map itself.
[InstallDelete]
Type: filesandordirs; Name: "{app}\bin\mercury"
Type: filesandordirs; Name: "{app}\bin\direwolf"
Type: files; Name: "{app}\bin\pmtiles.exe"
Type: files; Name: "{app}\bin\pmtiles-LICENSE.txt"

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\NeoAPRS"; Filename: "{app}\neoaprs-app.exe"; Comment: "NeoAPRS: the window and the tray icon (starts the daemon if it is not running)"
Name: "{group}\Stop NeoAPRS"; Filename: "{app}\neoaprsw.exe"; Parameters: "stop"; Comment: "End NeoAPRS"
; the console program, so that its window shows what it made and where; --pause keeps the window
; until Enter is pressed
Name: "{group}\NeoAPRS support logs"; Filename: "{app}\neoaprs.exe"; Parameters: "support --show --pause"; Comment: "Collect the logs into one file on the Desktop, to send to the developer"
Name: "{autodesktop}\NeoAPRS"; Filename: "{app}\neoaprs-app.exe"; Tasks: desktopicon

[Registry]
; the same value that `neoaprs service install` writes for the daemon: one start at sign-in, and the
; app's own checkbox in the tray menu reads and writes it too
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "NeoAPRS"; ValueData: """{app}\neoaprs-app.exe"" --tray{code:EncryptionArg}"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\neoaprs-app.exe"; Parameters: "{code:EncryptionArg}"; Description: "Open NeoAPRS now"; Flags: postinstall nowait skipifsilent
; after a silent update that NeoAPRS started itself: what was running starts again, the app (which
; starts the daemon) or the daemon alone
Filename: "{app}\neoaprs-app.exe"; Parameters: "{code:DataArgs}{code:EncryptionArg}"; Flags: nowait; Check: RestartWanted('app')
Filename: "{app}\neoaprsw.exe"; Parameters: "run {code:DataArgs}{code:EncryptionArg}"; Flags: nowait runhidden; Check: RestartWanted('daemon')

[UninstallRun]
; the app first (it stops the daemon it started), then whatever daemon is left (one that was running
; before the app), then the start at sign-in of a daemon that `neoaprs service install` made
Filename: "{app}\neoaprs-app.exe"; Parameters: "--quit"; Flags: runhidden waituntilterminated; RunOnceId: "QuitNeoAPRSApp"
Filename: "{app}\neoaprs.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated; RunOnceId: "StopNeoAPRS"
Filename: "{app}\neoaprs.exe"; Parameters: "service remove"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveStartAtSignIn"

[Code]
var
  Encryption: Boolean;

// Whether NeoAPRS runs with encrypted messages (`--encryption`), read before anything is written: Update
// now passes it (/NEOAPRSENCRYPTION=1), and an update by hand finds it in the start at sign-in this installer
// or the app's tray wrote. Without it an update would drop the flag from the start at sign-in.
function InitializeSetup(): Boolean;
var
  SignIn: String;
begin
  Encryption := ExpandConstant('{param:NEOAPRSENCRYPTION|}') = '1';
  if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'NeoAPRS', SignIn) and (Pos('--encryption', SignIn) > 0) then
    Encryption := True;
  Result := True;
end;

// ` --encryption` when NeoAPRS ran with encrypted messages, else nothing: for the restart, the start at sign-in and Open NeoAPRS now.
function EncryptionArg(Param: String): String;
begin
  Result := '';
  if Encryption then
    Result := ' --encryption';
end;

// `--data "folder"` for the data folder Update now named (/NEOAPRSDATA), else nothing: the default folder.
function DataArgs(Param: String): String;
begin
  Result := '';
  if ExpandConstant('{param:NEOAPRSDATA|}') <> '' then
    Result := '--data "' + ExpandConstant('{param:NEOAPRSDATA|}') + '"';
end;

// Is this the silent update of Update now, after which `What` (app or daemon) is started again?
function RestartWanted(What: String): Boolean;
begin
  Result := WizardSilent and (CompareText(ExpandConstant('{param:NEOAPRSRESTART|}'), What) = 0);
end;

// End the installed NeoAPRS: the app first (it stops the daemon it started), then any daemon left; each is waited for.
procedure EndRunningNeoAPRS();
var
  Code: Integer;
begin
  if FileExists(ExpandConstant('{app}\neoaprs-app.exe')) then
    Exec(ExpandConstant('{app}\neoaprs-app.exe'), Trim('--quit ' + DataArgs('')), '', SW_HIDE, ewWaitUntilTerminated, Code);
  if FileExists(ExpandConstant('{app}\neoaprs.exe')) then
    Exec(ExpandConstant('{app}\neoaprs.exe'), Trim('stop ' + DataArgs('')), '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

// An update over a running NeoAPRS: Setup calls this before replacing any file, so the app and daemon end
// cleanly and the user is not asked to close them. (A silent update of Update now restarts what was running
// by the [Run] entries; any other silent update leaves it to the next sign-in.)
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  EndRunningNeoAPRS();
  Result := '';
end;

// The same once more right before the files are replaced: the safety net for an app or a daemon started in between.
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    EndRunningNeoAPRS();
end;
