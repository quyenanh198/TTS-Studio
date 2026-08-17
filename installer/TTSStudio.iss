; Inno Setup script — build the portable folder first: scripts\build.ps1
#define AppName "TTS Studio"
#ifndef AppVersion
#define AppVersion "0.0.0-dev"
#endif
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

[Types]
Name: "recommended"; Description: "Đề xuất (tự phát hiện GPU)"
Name: "minimal"; Description: "Tối thiểu (chỉ ứng dụng — tải thêm sau trong app)"
Name: "custom"; Description: "Tuỳ chọn"; Flags: iscustom

[Components]
Name: "core"; Description: "Ứng dụng TTS Studio (bắt buộc)"; Types: recommended minimal custom; Flags: fixed
Name: "ffmpeg"; Description: "FFmpeg — bắt buộc cho mọi tính năng audio (~90 MB, tải khi cài)"; Types: recommended custom
Name: "clone"; Description: "Clone giọng — PyTorch + Seed-VC (2–3 GB, tự chọn bản CUDA/CPU theo GPU)"; Types: custom
Name: "f5vi"; Description: "F5-TTS Việt — giọng Việt có cảm xúc, offline (model ~1.5 GB; kèm PyTorch nếu chưa có)"; Types: custom
Name: "whispergpu"; Description: "Tăng tốc GPU cho Whisper — cuBLAS/cuDNN (~1 GB, chỉ máy NVIDIA)"; Types: custom

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
; Optional components are downloaded/installed by the app's own installers (visible console for progress)
Filename: "{app}\python\python.exe"; Parameters: """{app}\postinstall.py"" {code:ComponentArgs}"; WorkingDir: "{app}"; StatusMsg: "Đang tải thành phần tuỳ chọn (FFmpeg / PyTorch)…"; Check: HasOptionalComponents; Flags: waituntilterminated
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
  Result := KeyHasVersion(HKLM, 'SOFTWARE\WOW6432Node\' + WV2Client)
         or KeyHasVersion(HKLM, 'SOFTWARE\' + WV2Client)
         or KeyHasVersion(HKCU, 'Software\' + WV2Client);
end;

{ NVIDIA GPU present? (driver ships nvidia-smi.exe into System32 and registers itself) }
function HasNvidiaGpu(): Boolean;
begin
  Result := FileExists(ExpandConstant('{sys}\nvidia-smi.exe'))
         or RegKeyExists(HKLM, 'SOFTWARE\NVIDIA Corporation\Global\NVSMI')
         or RegKeyExists(HKLM, 'SOFTWARE\NVIDIA Corporation\Installer2\Drivers');
end;

function ComponentArgs(Param: String): String;
begin
  Result := '';
  if WizardIsComponentSelected('ffmpeg') then Result := Result + ' --ffmpeg';
  if WizardIsComponentSelected('clone') then Result := Result + ' --clone';
  if WizardIsComponentSelected('f5vi') then Result := Result + ' --f5';
  if WizardIsComponentSelected('whispergpu') then Result := Result + ' --whisper-gpu';
  Result := Trim(Result);
end;

function HasOptionalComponents(): Boolean;
begin
  Result := ComponentArgs('') <> '';
end;

{ Default selection: GPU machines get the clone engine + Whisper GPU libs pre-ticked. }
procedure InitializeWizard();
begin
  { Respect explicit /COMPONENTS= and silent installs; otherwise pre-select by hardware. }
  if WizardSilent() or (ExpandConstant('{param:COMPONENTS|}') <> '') then
    exit;
  if HasNvidiaGpu() then
    WizardSelectComponents('core,ffmpeg,clone,whispergpu')
  else
    WizardSelectComponents('core,ffmpeg');
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpSelectComponents then
  begin
    if HasNvidiaGpu() then
      WizardForm.ComponentsList.Hint := 'Phát hiện GPU NVIDIA — nên cài Clone giọng và tăng tốc Whisper.'
    else
      WizardForm.ComponentsList.Hint := 'Không phát hiện GPU NVIDIA — Clone giọng sẽ chạy CPU (rất chậm).';
  end;
end;
