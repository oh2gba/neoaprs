; Inno Setup script of the Windows installer: NeoAPRS-Setup-VERSION.exe. Per user (no administrator rights, no UAC prompt): the app goes to %LOCALAPPDATA%\Programs\NeoAPRS, the Start menu gets "NeoAPRS" (the desktop
; app, neoaprs-app.exe: a window and a tray icon; it starts the daemon itself) and "Stop NeoAPRS", a task makes a desktop shortcut, and a task, on by default, makes the app start in the tray when the user signs in
; (the value NeoAPRS of the Run key of the user, `neoaprs-app.exe --tray`; the daemon is the app's to start). The data (%LOCALAPPDATA%\NeoAPRS: settings, messages, packets, the map)
; is the program's own and is never touched by the installer or the uninstaller. Build, from the repository root, after packaging/windows/neoaprs.spec has made dist\NeoAPRS:
;     iscc /DAppVersion=0.1.0 /Qp packaging\windows\neoaprs.iss        (makes dist-installer\NeoAPRS-Setup-0.1.0.exe)
; Silent: NeoAPRS-Setup-VERSION.exe /VERYSILENT /SUPPRESSMSGBOXES /CURRENTUSER /NORESTART [/LOG=file] [/DIR=folder] [/TASKS=""]  (the last one: no start at sign-in, no desktop shortcut).
; Update now (neoaprs/services/selfinstall.py) runs it silently with /NOCLOSEAPPLICATIONS (the code below ends the app and the daemon, in that order, before a file is replaced) and two values of its own:
; /NEOAPRSDATA=folder (the data folder of the daemon that runs it) and /NEOAPRSRESTART=app or daemon (what was running, and is started again on that folder once the files are in place).
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

[Tasks]
Name: "autostart"; Description: "Start NeoAPRS when I sign in"
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\NeoAPRS"; Filename: "{app}\neoaprs-app.exe"; Comment: "NeoAPRS: the window and the tray icon (starts the daemon if it is not running)"
Name: "{group}\Stop NeoAPRS"; Filename: "{app}\neoaprsw.exe"; Parameters: "stop"; Comment: "End NeoAPRS"
Name: "{autodesktop}\NeoAPRS"; Filename: "{app}\neoaprs-app.exe"; Tasks: desktopicon

[Registry]
; the same value that `neoaprs service install` writes for the daemon: one start at sign-in, and the app's own checkbox in the tray menu reads and writes it too
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "NeoAPRS"; ValueData: """{app}\neoaprs-app.exe"" --tray"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\neoaprs-app.exe"; Description: "Open NeoAPRS now"; Flags: postinstall nowait skipifsilent
; after a silent update that NeoAPRS started itself: what was running starts again, the app (which starts the daemon) or the daemon alone
Filename: "{app}\neoaprs-app.exe"; Parameters: "{code:DataArgs}"; Flags: nowait; Check: RestartWanted('app')
Filename: "{app}\neoaprsw.exe"; Parameters: "run {code:DataArgs}"; Flags: nowait runhidden; Check: RestartWanted('daemon')

[UninstallRun]
; the app first (it stops the daemon it started), then whatever daemon is left (one that was running before the app), then the start at sign-in of a daemon that `neoaprs service install` made
Filename: "{app}\neoaprs-app.exe"; Parameters: "--quit"; Flags: runhidden waituntilterminated; RunOnceId: "QuitNeoAPRSApp"
Filename: "{app}\neoaprs.exe"; Parameters: "stop"; Flags: runhidden waituntilterminated; RunOnceId: "StopNeoAPRS"
Filename: "{app}\neoaprs.exe"; Parameters: "service remove"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveStartAtSignIn"

[Code]
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

// An update over a NeoAPRS that is running: the app and the daemon are ended first, or their files cannot be replaced. (The last page's "Open NeoAPRS now" starts the app again; a silent update of Update now
// starts again what was running, by the [Run] entries above; any other silent update leaves it to the next sign-in.)
procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
begin
  if CurStep = ssInstall then
  begin
    if FileExists(ExpandConstant('{app}\neoaprs-app.exe')) then
      Exec(ExpandConstant('{app}\neoaprs-app.exe'), Trim('--quit ' + DataArgs('')), '', SW_HIDE, ewWaitUntilTerminated, Code);
    if FileExists(ExpandConstant('{app}\neoaprs.exe')) then
      Exec(ExpandConstant('{app}\neoaprs.exe'), Trim('stop ' + DataArgs('')), '', SW_HIDE, ewWaitUntilTerminated, Code);
  end;
end;
