; Inno Setup script — build the portable folder first: scripts\build.ps1
#define AppName "TTS Studio"
#define AppVersion "1.0.0"
#define AppPublisher "TTS Studio"
#define SourceDir "..\dist\TTSStudio"

[Setup]
AppId={{9C4E7A3B-6D2F-4B8E-9F1A-2D5C8E7B4A10}
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
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\assets\app.ico
WizardStyle=modern
MinVersion=10.0
AppPublisherURL=https://github.com/quyenanh198/TTS-Studio
AppSupportURL=https://github.com/quyenanh198/TTS-Studio/issues

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[UninstallDelete]
; runtime bits the app itself writes inside the install dir (pip installs into the embedded python)
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\backend"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Microsoft Edge WebView2 Evergreen bootstrapper (Microsoft-signed, ~1.7 MB). Runs only if the runtime is missing.
Source: "redist\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{group}\{#AppName}"; Filename: "wscript.exe"; Parameters: """{app}\TTS Studio (no console).vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\app.ico"
Name: "{group}\Gỡ cài đặt {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "wscript.exe"; Parameters: """{app}\TTS Studio (no console).vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\app.ico"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Tạo lối tắt trên Desktop"; GroupDescription: "Lối tắt:"

[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Đang cài Microsoft Edge WebView2 Runtime (cần internet)…"; Check: not WebView2Installed; Flags: waituntilterminated
Filename: "wscript.exe"; Parameters: """{app}\TTS Studio (no console).vbs"""; Description: "Mở {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
const
  WV2Client = 'Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function KeyHasVersion(Root: Integer; const Sub: String): Boolean;
var
  Ver: String;
begin
  Result := RegQueryStringValue(Root, Sub, 'pv', Ver) and (Ver <> '') and (Ver <> '0.0.0.0');
end;

function WebView2Installed(): Boolean;
begin
  Result := KeyHasVersion(HKLM, 'SOFTWARE\WOW6432Node' + WV2Client)
         or KeyHasVersion(HKLM, 'SOFTWARE' + WV2Client)
         or KeyHasVersion(HKCU, 'Software' + WV2Client);
end;
