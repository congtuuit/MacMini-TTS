# VieNeu-TTS Deployment Workflow (Mac Mini M4 + Cloudflare Tunnel)

## 1. Mục tiêu

Triển khai hệ thống TTS tiếng Việt sử dụng VieNeu-TTS trên Mac Mini M4:

- Chạy local bằng GPU Apple Silicon (MPS)
- Cung cấp REST API
- Truy cập từ Internet qua Cloudflare Tunnel
- Tự khởi động khi reboot
- Dùng cá nhân hoặc lưu lượng thấp

Kiến trúc:

Internet
↓
Cloudflare Tunnel
↓
FastAPI
↓
VieNeu-TTS
↓
MPS (Apple GPU)

---

## 2. Chuẩn bị môi trường

### Cập nhật macOS

Khuyến nghị:

- macOS Sequoia mới nhất
- Xcode Command Line Tools

```bash
xcode-select --install
```

---

### Cài Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Kiểm tra:

```bash
brew --version
```

---

## 3. Cài đặt phụ thuộc

### eSpeak

VieNeu yêu cầu eSpeak.

```bash
brew install espeak
```

Kiểm tra:

```bash
espeak --version
```

---

### uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Reload shell:

```bash
source ~/.zshrc
```

Kiểm tra:

```bash
uv --version
```

---

## 4. Tải source

```bash
mkdir -p ~/services

cd ~/services

git clone https://github.com/pnnbao97/VieNeu-TTS.git

cd VieNeu-TTS
```

---

## 5. Tạo môi trường Python

Cài đầy đủ GPU package:

```bash
uv sync --group gpu
```

Kiểm tra:

```bash
uv run python
```

---

## 6. Kiểm tra MPS

Tạo file:

test_mps.py

```python
import torch

print(torch.backends.mps.is_available())
```

Chạy:

```bash
uv run python test_mps.py
```

Kết quả mong muốn:

```text
True
```

---

## 7. Test TTS local

Tạo file:

test_tts.py

```python
from vieneu import Vieneu

tts = Vieneu(
    backbone_device="mps"
)

audio = tts.infer(
    text="Xin chào, đây là hệ thống VieNeu TTS trên Mac Mini M4."
)

tts.save(audio, "output.wav")
```

Chạy:

```bash
uv run python test_tts.py
```

Kiểm tra file:

```text
output.wav
```

---

## 8. Tạo FastAPI Service

Cấu trúc:

```text
api/
├── main.py
├── output/
└── requirements
```

main.py

```python
from fastapi import FastAPI
from pydantic import BaseModel
from vieneu import Vieneu
import uuid
import os

app = FastAPI()

tts = Vieneu(
    backbone_device="mps"
)

os.makedirs("output", exist_ok=True)

class TTSRequest(BaseModel):
    text: str

@app.post("/tts")
async def generate(req: TTSRequest):

    filename = f"output/{uuid.uuid4()}.wav"

    audio = tts.infer(req.text)

    tts.save(audio, filename)

    return {
        "success": True,
        "file": filename
    }
```

---

## 9. Chạy API

```bash
uv run uvicorn api.main:app \
    --host 0.0.0.0 \
    --port 8000
```

Kiểm tra:

```text
http://localhost:8000/docs
```

Swagger sẽ xuất hiện.

---

## 10. Cài Cloudflare Tunnel

### Cài cloudflared

```bash
brew install cloudflared
```

---

### Login

```bash
cloudflared tunnel login
```

---

### Tạo tunnel

```bash
cloudflared tunnel create vieneu
```

---

### Tạo DNS

```bash
cloudflared tunnel route dns vieneu tts.domain.com
```

---

### File config

~/.cloudflared/config.yml

```yaml
tunnel: TUNNEL_ID

credentials-file: /Users/USERNAME/.cloudflared/TUNNEL_ID.json

ingress:
  - hostname: tts.domain.com
    service: http://localhost:8000

  - service: http_status:404
```

---

### Test tunnel

```bash
cloudflared tunnel run vieneu
```

Kiểm tra:

```text
https://tts.domain.com/docs
```

---

## 11. Auto Start FastAPI

Tạo LaunchAgent.

```text
~/Library/LaunchAgents/com.vieneu.api.plist
```

Nội dung:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">

<plist version="1.0">
<dict>

<key>Label</key>
<string>com.vieneu.api</string>

<key>ProgramArguments</key>
<array>
<string>/bin/zsh</string>
<string>-c</string>
<string>cd /Users/USERNAME/services/VieNeu-TTS && uv run uvicorn api.main:app --host 0.0.0.0 --port 8000</string>
</array>

<key>RunAtLoad</key>
<true/>

<key>KeepAlive</key>
<true/>

</dict>
</plist>
```

Load:

```bash
launchctl load ~/Library/LaunchAgents/com.vieneu.api.plist
```

---

## 12. Auto Start Cloudflare Tunnel

Tạo:

```text
~/Library/LaunchAgents/com.vieneu.tunnel.plist
```

Chạy:

```bash
cloudflared tunnel run vieneu
```

Load:

```bash
launchctl load ~/Library/LaunchAgents/com.vieneu.tunnel.plist
```

---

## 13. Monitoring

Kiểm tra process:

```bash
ps aux | grep uvicorn
```

Kiểm tra tunnel:

```bash
ps aux | grep cloudflared
```

Kiểm tra log:

```bash
tail -f logs/api.log
```

---

## 14. Backup

Backup định kỳ:

- Source code
- Config tunnel
- Voice clone models
- API configuration

Lưu trên:

- GitHub Private
- iCloud Drive
- NAS

---

## 15. Nâng cấp tương lai

Giai đoạn 1:

- TTS cơ bản

Giai đoạn 2:

- Clone Voice

Giai đoạn 3:

- MP3 output
- Queue xử lý

Giai đoạn 4:

- Redis
- Background worker
- Rate limit
- API Key

Giai đoạn 5:

- Multi-user
- Dashboard quản lý
- Billing
