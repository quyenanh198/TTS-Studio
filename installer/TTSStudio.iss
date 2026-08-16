; Inno Setup script — build the portable folder first: scripts\build.ps1
#define AppName "TTS Studio"
#define AppVersion "0.1.0"
#define AppPublisher "TTS Studio"
#define SourceDir "..\dist\TTSStudio"

[Setup]
AppId={{7B0E2D6E-3F5D-4C55-9C7C-TTSSTUDIO0001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\TTSStudio
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=TTSStudio-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\python\pythonw.exe

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "wscript.exe"; Parameters: """{app}\TTS Studio (no console).vbs"""; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "wscript.exe"; Parameters: """{app}\TTS Studio (no console).vbs"""; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Tạo lối tắt trên Desktop"; GroupDescription: "Lối tắt:"

[Run]
Filename: "wscript.exe"; Parameters: """{app}\TTS Studio (no console).vbs"""; Description: "Mở {#AppName}"; Flags: nowait postinstall skipifsilent
