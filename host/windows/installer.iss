; host/windows/installer.iss — Inno Setup script for the Windows installer.
;
; Packages the PyInstaller onedir build (host/windows/margarita_tank.spec) into
; dist/Margarita-Tank-Setup.exe. Per-user install, no admin rights needed.
;
;   cd host
;   .venv/Scripts/python.exe -m PyInstaller windows/margarita_tank.spec --noconfirm
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DAppVersion=1.2.3 windows/installer.iss
;
; AppVersion defaults to a dev placeholder; CI passes the release tag.

#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif

#define AppName "Margarita Tank"
#define AppExeName "MargaritaTank.exe"
#define BuildDir "..\dist\MargaritaTank"
#define SimProcessName "clawd-tank-sim"
#define PowerShell "{sys}\WindowsPowerShell\v1.0\powershell.exe"

[Setup]
; Never change AppId: it is how upgrades and the uninstaller find an install.
AppId={{6F0C2B1E-5A7D-4C1B-9E3F-8D2A4B6C9E10}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Margarita Tank
AppPublisherURL=https://github.com/sam-wilkie/margarita-tank
AppSupportURL=https://github.com/sam-wilkie/margarita-tank/issues
AppUpdatesURL=https://github.com/sam-wilkie/margarita-tank/releases
; Per-user install into %LOCALAPPDATA%\Programs — no UAC prompt.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir=..\dist
OutputBaseFilename=Margarita-Tank-Setup
SetupIconFile={#BuildDir}\MargaritaTank.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; The tray app is killed in PrepareToInstall below; Restart Manager cannot
; close a windowless tray process gracefully anyway.
CloseApplications=no

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autoprograms}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; The app's own "Launch at Login" toggle writes this value (internal name kept
; from upstream). Remove it on uninstall so Windows does not try to start an
; exe that is gone.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "ClawdTank"; Flags: dontcreatekey uninsdeletevalue

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Runs in this order, before any file is deleted. Stop the tray first so its
; daemon cannot re-register hooks, then remove our Claude Code hook groups
; while MargaritaTank.exe still exists; otherwise Claude Code keeps invoking
; the deleted margarita-notify.exe on every hook event. Finally stop only the
; simulator this install shipped, not a development build of it.
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#AppExeName}"; Flags: runhidden waituntilterminated; RunOnceId: "KillTray"
Filename: "{app}\{#AppExeName}"; Parameters: "--uninstall-hooks"; Flags: runhidden waituntilterminated; RunOnceId: "UninstallHooks"
Filename: "{#PowerShell}"; Parameters: "{code:KillSimParams}"; Flags: runhidden waituntilterminated; RunOnceId: "KillSim"

[Code]
procedure KillImage(const ImageName: String);
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM ' + ImageName, '',
       SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

// PowerShell arguments that stop only the simulator processes whose image lives
// under {app}. `taskkill /IM` matches by name alone and would also kill a
// simulator a developer is running from a source checkout. StartsWith rather
// than -like, whose [ ] wildcards a folder name could contain; the folder is
// embedded as a single-quoted PowerShell literal, so its own quotes are doubled.
function KillSimParams(Param: String): String;
var
  AppDir: String;
begin
  AppDir := AddBackslash(ExpandConstant('{app}'));
  StringChangeEx(AppDir, '''', '''''', True);
  Result := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "' +
    '$d = ''' + AppDir + '''; ' +
    'Get-Process -Name {#SimProcessName} -ErrorAction SilentlyContinue | ' +
    'Where-Object { $_.Path -and $_.Path.StartsWith($d, [StringComparison]::OrdinalIgnoreCase) } | ' +
    'Stop-Process -Force; exit 0"';
end;

procedure KillSimUnderApp;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{#PowerShell}'), KillSimParams(''), '',
       SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  // A running tray (or its simulator) locks files in {app}; stop both so an
  // upgrade can overwrite them. The user relaunches from the last wizard page.
  KillImage('{#AppExeName}');
  KillSimUnderApp;
  Result := '';
end;
