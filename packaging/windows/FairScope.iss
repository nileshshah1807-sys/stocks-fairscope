#define MyAppName "DR. NILESH SHAH - STOCKS FAIRSCOPE"
#define MyAppVersion "10.4.1"
#define MyAppPublisher "DR. NILESH SHAH"
#define MyAppExeName "DrNileshShahStocksFairScope.exe"

[Setup]
SourceDir=..\..
AppId={{6D45AE79-2057-4E75-A07E-D9875FB358A3}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Dr Nilesh Shah\Stocks FairScope
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=packaging\windows\EULA.txt
OutputDir=installer_output
OutputBaseFilename=Dr_Nilesh_Shah_Stocks_FairScope_Setup_x64_v10.4.1
SetupIconFile=assets\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=yes
RestartApplications=no
VersionInfoVersion=10.4.1.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "dist\DrNileshShahStocksFairScope\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
