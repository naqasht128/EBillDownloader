; E-Bill Downloader - Inno Setup Installer Script
; Produces a modern, professional, per-user Windows Setup Wizard

#ifndef AppVersion
#define AppVersion "1.0.13"
#endif

#ifndef OutputBaseFilename
#define OutputBaseFilename "EBillDownloader-Setup"
#endif

#define AppName "E-Bill Downloader"
#define AppPublisher "TN Developers Co."
#define AppExeName "EBillDownloader.exe"

[Setup]
AppId={{5D4A83A1-55DA-43FF-B2BD-35BF2EFC89DE}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=mailto:tahir.naqash4@gmail.com
AppSupportURL=https://wa.me/923339962474
DefaultDirName={localappdata}\Programs\EBillDownloader
DisableDirPage=yes
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename={#OutputBaseFilename}
SetupIconFile=assets\app.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
MinVersion=10.0
PrivilegesRequired=lowest
CloseApplications=force
RestartApplications=no
ChangesAssociations=yes
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}
VersionInfoCopyright=Copyright (C) 2026 {#AppPublisher}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Clean up previous monolithic onefile executable when upgrading
Type: files; Name: "{app}\{#AppExeName}"
Type: files; Name: "{autodesktop}\{#AppName}.lnk"
Type: files; Name: "{autoprograms}\{#AppName}.lnk"

[Files]
; The modern onedir distribution built by PyInstaller
Source: "dist\EBillDownloader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\assets\app.ico"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon; IconFilename: "{app}\assets\app.ico"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent shellexec; WorkingDir: "{app}"
Filename: "{app}\{#AppExeName}"; Flags: nowait shellexec; Check: ShouldLaunchSilent; WorkingDir: "{app}"

[Code]
function SetEnvironmentVariable(lpName, lpValue: string): BOOL;
external 'SetEnvironmentVariableW@kernel32.dll stdcall';

function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  // Clear any inherited PyInstaller variables so the relaunched app unpacks cleanly
  SetEnvironmentVariable('_MEIPASS2', '');
  SetEnvironmentVariable('_MEIPASS', '');
  SetEnvironmentVariable('PYTHONHOME', '');
  SetEnvironmentVariable('PYTHONPATH', '');

  // Terminate any running or lingering instances of EBillDownloader.exe
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM EBillDownloader.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(400);
  Result := True;
end;

function ShouldLaunchSilent: Boolean;
begin
  Result := WizardSilent or (ExpandConstant('{param:AUTOUPDATE|0}') = '1');
end;
