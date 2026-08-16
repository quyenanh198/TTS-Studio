# TTS Studio

Ứng dụng desktop Windows: **Tạo giọng nói (TTS) · Phụ đề/Transcript (ASR) · Clone giọng đa ngôn ngữ**.
Không cần đăng nhập, không license — chạy hoàn toàn trên máy (chỉ TTS Edge/TikTok cần internet).

## Tính năng

| Mảng | Chi tiết |
|---|---|
| Nguồn văn bản | Dán text · TXT/MD · **EPUB · PDF · DOCX** · SRT (đọc theo mốc thời gian) · MOBI/AZW3 (cần Calibre). Tự tách chương (`Chương 1`, `Chapter 2`, `第三章`…), sửa/xóa chương. |
| Giọng đọc | **Microsoft Edge Neural** 300+ giọng, 20+ ngôn ngữ (miễn phí, không key) · **TikTok** (cần `sessionid`) · **Giọng clone** của bạn |
| Điều chỉnh | Tốc độ 0.5–2.0x · âm lượng · giữ/đổi cao độ · dịch cao độ ± nửa cung · WAV/MP3 |
| Xuất | Mỗi chương một file · gộp cả sách · khoảng chương/gộp theo nhóm N · theo dòng SRT (giữ timing) · **SRT tự động** · ZIP · **M4B audiobook có chương** |
| Transcript | faster-whisper offline (tiny → large-v3-turbo), CPU/GPU, mốc thời gian theo từ, sửa từng dòng, xuất **SRT/VTT/TXT/LRC** (lời bài hát), tách vocal (demucs, tùy chọn), "Gửi sang TTS" |
| Clone giọng | Mẫu 10–25 s → dùng cho **mọi ngôn ngữ**: Edge TTS đọc đúng ngôn ngữ → **Seed-VC** (zero-shot voice conversion) đổi sang chất giọng mẫu. GPU tự phát hiện, CPU fallback. |

## Kiến trúc

```
launcher.py            pywebview window (WebView2) + uvicorn trong 1 process
backend/app/
  main.py              FastAPI, mount frontend/dist, router động
  jobs.py / db.py      job thread-pool + tiến độ qua WebSocket, SQLite (jobs, voice_profiles)
  services/
    voices.py          catalog Edge (cache) + TikTok
    providers.py       edge-tts (word boundary → SRT) · TikTok API
    tts_engine.py      chunk → synth → concat → effects → export modes/ZIP/M4B
    parsers.py         TXT/EPUB/PDF/DOCX/SRT → Book{chapters}
    asr.py             faster-whisper, model manager, GPU libs
    clone.py           Seed-VC pipeline, voice profiles, preview
    audio.py/ffmpeg.py ffmpeg wrapper (tự tải build tĩnh vào %LOCALAPPDATA%\TTSStudio\bin)
frontend/              React + TypeScript + Vite + Tailwind v4 + zustand
```

Dữ liệu người dùng: `%LOCALAPPDATA%\TTSStudio\` (settings.json, studio.sqlite3, models/, output/, voices/, bin/ffmpeg).

## Chạy phát triển

```bash
# 1. Python 3.12 venv (uv)
pip install uv
python -m uv venv --python 3.12 .venv
python -m uv pip install --python .venv/Scripts/python.exe -e ".[dev]"

# 2. Frontend
cd frontend && npm install && npm run build && cd ..

# 3. Chạy desktop
.venv/Scripts/python.exe launcher.py
#    hoặc dev (backend :8765 + Vite :5173 hot reload)
.venv/Scripts/python.exe launcher.py --dev      # rồi: cd frontend && npm run dev
```

Lần đầu vào **Cài đặt → Tải FFmpeg**. Whisper model tải trong trang Transcript. Clone giọng: trang Clone → **Cài đặt** (PyTorch + seed-vc, 2–3 GB; tự chọn CUDA nếu có NVIDIA).

## Kiểm thử

```bash
.venv/Scripts/python.exe -m pytest -q
```

## Đóng gói (portable + installer)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1        # → dist\TTSStudio\ (Python nhúng + deps + UI, ~420 MB)
powershell -ExecutionPolicy Bypass -File scripts\installer.ps1    # → dist\TTSStudio-Setup-1.0.0.exe (~94 MB, cần Inno Setup 6)
```

`dist\TTSStudio\TTS Studio.bat` chạy trực tiếp; `TTS Studio (no console).vbs` chạy ẩn console. Torch/seed-vc và model được tải khi người dùng bấm cài trong app (giữ installer nhỏ).

Installer cài per-user vào `%LOCALAPPDATA%\Programs\TTSStudio` (không cần quyền admin), tạo shortcut Start Menu/Desktop, gỡ qua Settings → Apps. Yêu cầu Windows 10+ và Microsoft Edge WebView2 Runtime (app tự kiểm tra và mở trang tải nếu thiếu). Log chạy: `%LOCALAPPDATA%\TTSStudio\logs\app.log`.

## Ghi chú kỹ thuật

- Edge TTS: dùng rate/volume/pitch native của dịch vụ (chất lượng tốt hơn xử lý hậu kỳ); word boundary → gộp thành cue phụ đề, gắn lại dấu câu từ văn bản gốc.
- TikTok/clone: hiệu ứng tốc độ/cao độ qua FFmpeg (`atempo`, `asetrate`), timestamp SRT được scale theo.
- SRT đầu vào: mỗi dòng phụ đề được đọc riêng rồi ép khớp thời lượng (đệm im lặng / tăng tốc tối đa 1.35x).
- Seed-VC (GPL-3.0) được cài dưới dạng gói pip riêng khi người dùng chọn — mã nguồn app không nhúng.
- TikTok TTS là API không chính thức; có thể ngừng hoạt động bất kỳ lúc nào.
