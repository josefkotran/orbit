; Orbit installer (Inno Setup 6.7). Built by build\build_installer.py, which passes:
;   /DAppVersion=<app/version.py>  /DSourceDir=<build\dist\Orbit>  /DOutputDir=<build\output>
;   and when signing is set up: /DSign=1 /Sorbitsign=<signtool command>
; Per user, no admin: the app goes to %LOCALAPPDATA%\Programs\Orbit, Orbit keeps its data in %LOCALAPPDATA%\Orbit.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\build\dist\Orbit"
#endif
#ifndef OutputDir
  #define OutputDir "..\build\output"
#endif

[Setup]
; never change the AppId: updates and the uninstaller find the installed Orbit by it
AppId={{5F014547-976E-46B8-86BA-23A1A44CBF3A}
AppName=Orbit
AppVersion={#AppVersion}
AppVerName=Orbit {#AppVersion}
AppPublisher=Josef Kotran
AppCopyright=© Josef Kotran
VersionInfoVersion={#AppVersion}
VersionInfoProductName=Orbit
VersionInfoDescription=Orbit – instalace
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\Orbit
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Windows 10 1809: the oldest Windows Qt 6 supports
MinVersion=10.0.17763
; Orbit's single-instance mutex (app/winutil.py). Inno passes the name to OpenMutex as it is, so the Local\
; prefix works: Setup runs in the user's session, the same namespace Orbit created it in.
AppMutex=Local\Orbit-single-instance
SetupMutex=OrbitSetup-5F014547
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=no
SetupIconFile={#SourceDir}\assets\orbit.ico
UninstallDisplayIcon={app}\assets\orbit.ico
UninstallDisplayName=Orbit
WizardStyle=modern dark
OutputDir={#OutputDir}
OutputBaseFilename=Orbit-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
LanguageDetectionMethod=uilanguage
ShowLanguageDialog=auto
#ifdef Sign
SignTool=orbitsign
SignedUninstaller=yes
#endif

[Languages]
; Czech first: the default when the Windows language is neither Czech nor English (the dialog then offers both)
Name: "cs"; MessagesFile: "compiler:Languages\Czech.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
cs.LaunchOrbit=Spustit Orbit
en.LaunchOrbit=Start Orbit
cs.ShortcutComment=Diktování česky a přehled Clauda
en.ShortcutComment=Czech dictation and a Claude overview
cs.DeleteUserData=Smazat i data Orbitu?%n%n%1%n%nJe tam nastavení, slovník, nahrávky a stažené modely (i několik GB). Když je necháš, Orbit na ně po nové instalaci naváže.
en.DeleteUserData=Also delete Orbit's data?%n%n%1%n%nIt holds the settings, vocabulary, recordings and downloaded models (up to several GB). Keep it and a new install picks up where you left off.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; an update replaces these folders whole, so files a newer version dropped don't linger. Not runtime\ itself:
; Claude Code may start runtime\python.exe for Orbit's hooks and status line at any moment (they need only the
; stdlib next to it), and without it they failed until [Files] put it back. [Files] replaces those files one by one
; (MoveAsideIfInUse); a new Python minor version would leave the old ones there, unused. app\ last: [Files] writes
; it among the first.
Type: filesandordirs; Name: "{app}\runtime\Lib"
Type: files; Name: "{app}\runtime\*.orbit-old"
Type: filesandordirs; Name: "{app}\assets"
Type: filesandordirs; Name: "{app}\whisper"
Type: filesandordirs; Name: "{app}\app"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; BeforeInstall: MoveAsideIfInUse

[Icons]
; -s: never the user's own %APPDATA%\Python\Python313\site-packages (the ._pth without "import site" keeps it out
; already, for the starts Orbit makes itself without -s: the Run key, Claude Code's hooks and status line)
Name: "{autoprograms}\Orbit"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-s ""{app}\Orbit.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\orbit.ico"; Comment: "{cm:ShortcutComment}"; AppUserModelID: "Orbit"
Name: "{autodesktop}\Orbit"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-s ""{app}\Orbit.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\orbit.ico"; Comment: "{cm:ShortcutComment}"; AppUserModelID: "Orbit"; Tasks: desktopicon

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: "-s ""{app}\Orbit.pyw"""; WorkingDir: "{app}"; Description: "{cm:LaunchOrbit}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; removes this installation's Claude Code hooks, its status line (the previous one comes back) and its Run key;
; entries of another Orbit copy stay
Filename: "{app}\runtime\python.exe"; Parameters: "-s ""{app}\Orbit.pyw"" --cleanup"; WorkingDir: "{app}"; Flags: runhidden waituntilterminated; RunOnceId: "OrbitCleanup"

[UninstallDelete]
; what Python and Orbit wrote next to the installed files (bytecode cache, generated sounds, logs)
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\assets"
Type: filesandordirs; Name: "{app}\whisper"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: dirifempty; Name: "{app}"

[Code]
var
  MovedAside: TStringList;

function InitializeSetup: Boolean;
begin
  MovedAside := TStringList.Create;
  Result := True;
end;

{ Before each file. A file in use can't be replaced: Setup would stop with an error, and /SUPPRESSMSGBOXES
  (install.ps1) answers it with Abort. Claude Code may be running Orbit's runtime\python.exe for a hook or the
  status line right then. A running .exe or a loaded .dll can't be deleted but can be renamed, so the old one
  moves aside, the new one takes its place and the hook finishes with the old one. }
procedure MoveAsideIfInUse;
var
  Dest: String;
begin
  Dest := ExpandConstant(CurrentFileName);
  if not FileExists(Dest) or DeleteFile(Dest) then
    Exit;
  DeleteFile(Dest + '.orbit-old');
  if RenameFile(Dest, Dest + '.orbit-old') then begin
    Log('In use, moved aside: ' + Dest);
    MovedAside.Add(Dest + '.orbit-old');
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  I: Integer;
begin
  { a hook takes a fraction of a second; what is still in use goes with the next update or the uninstall }
  if CurStep = ssPostInstall then
    for I := 0 to MovedAside.Count - 1 do
      DelayDeleteFile(MovedAside.Strings[I], 8);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;
  { the user's data (settings, vocabulary, recordings, ~3 GB of models): kept unless they say otherwise;
    a silent uninstall always keeps it }
  DataDir := ExpandConstant('{localappdata}\Orbit');
  if DirExists(DataDir) and not UninstallSilent then
    if MsgBox(FmtMessage(CustomMessage('DeleteUserData'), [DataDir]), mbConfirmation,
              MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(DataDir, True, True, True);
end;
