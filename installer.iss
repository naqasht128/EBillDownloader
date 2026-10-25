; E-Bill Downloader - Inno Setup Installer Script
; Produces a modern, professional, per-user Windows Setup Wizard

#ifndef AppVersion
#define AppVersion "1.0.7"
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

[Files]
Source: "dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs
#ifdef IncludeVCRedist
Source: "redist\vc_redist.x86.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall
#endif

[InstallDelete]
Type: files; Name: "{autodesktop}\{#AppName}.lnk"
Type: files; Name: "{autoprograms}\{#AppName}.lnk"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\assets\app.ico"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon; IconFilename: "{app}\assets\app.ico"

[Run]
#ifdef IncludeVCRedist
Filename: "{tmp}\vc_redist.x86.exe"; Parameters: "/install /passive /norestart"; Check: VCRedistNeedsInstall; Flags: waituntilterminated; StatusMsg: "Configuring Microsoft Visual C++ Runtime..."
#endif
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent shellexec; WorkingDir: "{app}"
Filename: "{app}\{#AppExeName}"; Flags: nowait shellexec; Check: ShouldLaunchSilent; WorkingDir: "{app}"

[Code]
function SetEnvironmentVariable(lpName, lpValue: string): BOOL;
external 'SetEnvironmentVariableW@kernel32.dll stdcall';

function VCRedistNeedsInstall: Boolean;
var
  Installed: Cardinal;
begin
  Result := True;
  // Check Visual C++ 2015-2022 Redistributable (32-bit x86 runtime)
  if RegQueryDWordValue(HKLM, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X86', 'Installed', Installed) then
  begin
    if Installed = 1 then
      Result := False;
  end;
  // Also check WOW6432Node if on 64-bit Windows
  if Result and RegQueryDWordValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\X86', 'Installed', Installed) then
  begin
    if Installed = 1 then
      Result := False;
  end;
end;

function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
  Version: TWindowsVersion;
begin
  GetWindowsVersionEx(Version);

  // Require Windows 7 Service Pack 1 (Build 7601+) or later
  if (Version.Major = 6) and (Version.Minor = 1) and (Version.ServicePackMajor < 1) then
  begin
    SuppressibleMsgBox(
      'E-Bill Downloader requires Windows 7 Service Pack 1 (SP1) or later.' + #13#10 +
      'Please update your Windows 7 to Service Pack 1 to use this application.',
      mbCriticalError, MB_OK, MB_OK
    );
    Result := False;
    Exit;
  end;

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
