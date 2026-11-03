; The one thing here that asks for administrator rights is a Windows Firewall rule, "NeoAPRS Mercury", that blocks the network from the Mercury modem (bin\mercury\mercury.exe): Mercury listens on every network interface with no password
; of its own, and anyone on the LAN could key the transmitter through it; the rule leaves the daemon's own connections on this computer alone. It is added once (a UAC prompt, which may be declined: the daemon then does not start Mercury and says why), and removed by the uninstaller.
; Inno Setup script of the Windows installer: NeoAPRS-Setup-VERSION.exe. Per user (no administrator rights, no UAC prompt): the app goes to %LOCALAPPDATA%\Programs\NeoAPRS, the Start menu gets "NeoAPRS" (the desktop
; app, neoaprs-app.exe: a window and a tray icon; it starts the daemon itself), "Stop NeoAPRS" and "NeoAPRS support logs" (neoaprs.exe support: the logs in one file on the Desktop), a task makes a desktop shortcut, and a task, on by default, makes the app start in the tray when the user signs in
; (the value NeoAPRS of the Run key of the user, `neoaprs-app.exe --tray`; the daemon is the app's to start). The data (%LOCALAPPDATA%\NeoAPRS: settings, messages, packets, the map)
; is the program's own and is never touched by the installer or the uninstaller. Build, from the repository root, after packaging/windows/neoaprs.spec has made dist\NeoAPRS:
;     iscc /DAppVersion=0.1.0 /Qp packaging\windows\neoaprs.iss        (makes dist-installer\NeoAPRS-Setup-0.1.0.exe)
; Silent: NeoAPRS-Setup-VERSION.exe /VERYSILENT /SUPPRESSMSGBOXES /CURRENTUSER /NORESTART [/LOG=file] [/DIR=folder] [/TASKS=""]  (the last one: no start at sign-in, no desktop shortcut).
; Installing over a NeoAPRS that is running: the code below ends the app and then the daemon cleanly (neoaprs-app.exe --quit, neoaprs.exe stop, each waiting until the process has gone) before Setup looks for files in use, so
; that the user is not asked to close them and the daemon ends as it does at a stop, not terminated; Setup's own files-in-use check (CloseApplications) stays as the safety net for anything else that holds a file.
; Update now (neoaprs/services/selfinstall.py) runs it silently with /NOCLOSEAPPLICATIONS (the same clean ending, and no check) and two values of its own:
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
; the console program, so that its window shows what it made and where; --pause keeps the window until Enter is pressed
Name: "{group}\NeoAPRS support logs"; Filename: "{app}\neoaprs.exe"; Parameters: "support --show --pause"; Comment: "Collect the logs into one file on the Desktop, to send to the developer"
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

// Ends the NeoAPRS that is installed and running: the app first (it stops the daemon it started), then whatever daemon is left; each is waited for. Nothing happens when none runs.
procedure EndRunningNeoAPRS();
var
  Code: Integer;
begin
  if FileExists(ExpandConstant('{app}\neoaprs-app.exe')) then
    Exec(ExpandConstant('{app}\neoaprs-app.exe'), Trim('--quit ' + DataArgs('')), '', SW_HIDE, ewWaitUntilTerminated, Code);
  if FileExists(ExpandConstant('{app}\neoaprs.exe')) then
    Exec(ExpandConstant('{app}\neoaprs.exe'), Trim('stop ' + DataArgs('')), '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

// An update over a NeoAPRS that is running: Setup calls this before it looks for files in use, so the app and the daemon are ended cleanly here and the user is not asked to close them. (The last page's
// "Open NeoAPRS now" starts the app again; a silent update of Update now starts again what was running, by the [Run] entries above; any other silent update leaves it to the next sign-in.)
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  EndRunningNeoAPRS();
  Result := '';
end;

// Is there a Windows Firewall rule of that name? `show rule` needs no rights: exit code 0 when it exists, 1 when not. When netsh cannot be run at all, the answer is "yes", so that no prompt is made for nothing.
function FirewallRuleExists(): Boolean;
var
  Code: Integer;
begin
  Result := True;
  if Exec(ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall show rule name="NeoAPRS Mercury"', '', SW_HIDE, ewWaitUntilTerminated, Code) then
    Result := (Code = 0);
end;

// Blocks the network from the installed Mercury: it listens on every interface with no password, and the daemon reaches it on this computer, which the Firewall does not filter. Adding a rule needs administrator
// rights and this installer has none, so the netsh that adds it runs with `runas` (the UAC prompt); declining leaves the rule out and the installation goes on (the daemon does not start Mercury without it).
// A silent update of a copy that already has the rule finds it (the program's path does not change) and asks nothing. A copy updated from a version before Mercury has no rule and, with a silent update, may never
// see the prompt: the HF radio's box then has a button that makes the same rule (neoaprs/mercuryrule.py).
procedure AddMercuryFirewallRule();
var
  Code: Integer;
begin
  if FirewallRuleExists() then
    Exit;
  ShellExec('runas', ExpandConstant('{sys}\netsh.exe'),
    'advfirewall firewall add rule name="NeoAPRS Mercury" dir=in action=block program="' + ExpandConstant('{app}\bin\mercury\mercury.exe') + '"'
    + ' description="NeoAPRS: the Mercury HF modem is reached by NeoAPRS on this computer only"',
    '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

// The rule goes with the program; declining the prompt leaves a rule that points at a file that is gone, which does no harm.
procedure RemoveMercuryFirewallRule();
var
  Code: Integer;
begin
  if not FirewallRuleExists() then
    Exit;
  ShellExec('runas', ExpandConstant('{sys}\netsh.exe'), 'advfirewall firewall delete rule name="NeoAPRS Mercury"', '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

// The same once more right before the files are replaced: the safety net for an app or a daemon started in between. And, with the files in place, the firewall rule for Mercury.
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    EndRunningNeoAPRS();
  if CurStep = ssPostInstall then
    AddMercuryFirewallRule();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemoveMercuryFirewallRule();
end;
