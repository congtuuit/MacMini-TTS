# Kế hoạch triển khai VieNeu-TTS Deployment

## Overview
Triển khai hệ thống TTS tiếng Việt sử dụng mã nguồn mở VieNeu-TTS trên thiết bị Mac Mini M4. Hệ thống sẽ chạy mô hình AI thông qua GPU Apple Silicon (MPS), cung cấp REST API bằng FastAPI, và được public ra Internet qua Cloudflare Tunnel. Cuối cùng, cấu hình tự động khởi động các dịch vụ này khi reboot máy.

## Requirements
- **Thiết bị**: Mac Mini M4
- **OS**: macOS Sequoia mới nhất, đã cài đặt Xcode Command Line Tools.
- **Dependencies**: Homebrew, eSpeak, uv (cho Python package management), git.
- **Tài khoản**: Cần tài khoản Cloudflare và domain để cấu hình Tunnel.

## Architecture
- **Hardware Layer**: Apple Silicon GPU (MPS)
- **Application Layer**: VieNeu-TTS Model -> FastAPI (Backend) -> Uvicorn (Server)
- **Networking Layer**: Localhost (Port 8000) -> Cloudflare Tunnel (cloudflared) -> Internet (Domain `tts.domain.com`)
- **System Management**: macOS LaunchAgents (`launchd`) để quản lý background services tự động chạy lại khi khởi động máy.

## User Review Required
> [!IMPORTANT]
> - Cần xác nhận domain thực tế sẽ sử dụng để cấu hình Cloudflare Tunnel (thay vì `tts.domain.com`).
> - Cần bạn (người dùng) trực tiếp thực hiện lệnh `cloudflared tunnel login` vì nó yêu cầu mở trình duyệt để xác thực tài khoản Cloudflare.
> - Cần xác nhận đường dẫn thư mục lưu trữ mã nguồn. Trong plan đang để là thư mục `~/services/VieNeu-TTS`.
> - Xác nhận tên tài khoản macOS thực tế (`USERNAME`) để điền vào file `config.yml` và các file LaunchAgents.

## Open Questions
- Thư mục `~/services/` sẽ tạo ở `/Users/tuvan/services/` phải không? (Trong file setup.md đang ghi là `~/services`).
- Bạn đã có domain trên Cloudflare và có quyền truy cập để login chưa? Domain dự kiến của bạn là gì?

## Implementation Steps & Proposed Changes

Quá trình này chủ yếu thực hiện qua các lệnh Terminal và tạo file cấu hình.

### Môi trường và Dependencies
- Cài đặt / cập nhật các công cụ cơ bản: Xcode CLI, Homebrew, eSpeak, uv.
- Clone repository `VieNeu-TTS` vào thư mục `~/services/VieNeu-TTS`.
- Cài đặt Python environment với lệnh `uv sync --group gpu`.

### FastAPI Service
#### [NEW] `~/services/VieNeu-TTS/api/main.py`
Tạo file API backend cung cấp endpoint `/tts` để nhận text và trả về đường dẫn file audio.

#### [NEW] Thư mục `~/services/VieNeu-TTS/output/`
Để lưu trữ các file audio `.wav` sinh ra từ API.

### Cloudflare Tunnel
#### [NEW] `~/.cloudflared/config.yml`
Tạo file cấu hình cho phép điều hướng request từ domain public về `http://localhost:8000`.

### System LaunchAgents (Auto Start)
#### [NEW] `~/Library/LaunchAgents/com.vieneu.api.plist`
Cấu hình hệ thống để tự động chạy FastAPI service khi user login vào máy.
#### [NEW] `~/Library/LaunchAgents/com.vieneu.tunnel.plist`
Cấu hình hệ thống để tự động chạy Cloudflare Tunnel.

## TODO List

- [ ] 1. Kiểm tra và cài đặt Xcode Command Line Tools, Homebrew.
- [ ] 2. Cài đặt các công cụ hệ thống: `brew install espeak cloudflared`.
- [ ] 3. Cài đặt công cụ quản lý Python: `uv`.
- [ ] 4. Clone mã nguồn `pnnbao97/VieNeu-TTS` vào `~/services/VieNeu-TTS`.
- [ ] 5. Chạy `uv sync --group gpu` để cài đặt các thư viện Python.
- [ ] 6. Chạy file script test MPS và test TTS local đảm bảo model hoạt động trên máy M4.
- [ ] 7. Xây dựng FastAPI service tại file `api/main.py`.
- [ ] 8. Chờ người dùng đăng nhập Cloudflare: `cloudflared tunnel login`.
- [ ] 9. Tạo tunnel, route DNS và thiết lập file `config.yml` của cloudflared.
- [ ] 10. Tạo file LaunchAgent `com.vieneu.api.plist` và load để chạy API ngầm.
- [ ] 11. Tạo file LaunchAgent `com.vieneu.tunnel.plist` và load để chạy ngầm Tunnel.
- [ ] 12. Kiểm tra log hoạt động của uvicorn và cloudflared.

## Risk Assessment
- **Compatibility**: Model TTS có thể bị ảnh hưởng nếu cập nhật thay đổi đột ngột giữa version của PyTorch hoặc thiết bị MPS.
- **Security**: Endpoint API hiện tại chưa có Authentication. Bất cứ ai biết URL cũng có thể gọi tạo giọng nói, gây tốn tài nguyên Mac Mini.
- **Network Stability**: Kết nối ngầm của Cloudflare Tunnel có thể ngắt quãng nếu mạng chập chờn, cần đảm bảo `cloudflared` tự động khởi động lại (đã set KeepAlive trong plist).

## Success Criteria
- [ ] Lệnh `uv run python test_mps.py` thực thi thành công và in ra `True`.
- [ ] API chạy trơn tru, sinh ra audio hợp lệ từ endpoint `/tts`.
- [ ] Trang Swagger UI khả dụng tại đường dẫn `https://<ten-domain-cua-ban>/docs`.
- [ ] Sau khi Reboot Mac Mini, ứng dụng và Tunnel đều tự động chạy trở lại bình thường.

## Verification Plan
### Automated Tests
- Chạy script kiểm tra kết nối với Apple GPU: `uv run python test_mps.py`
- Chạy script kiểm tra output file mẫu: `uv run python test_tts.py`

### Manual Verification
- Mở Swagger UI của API trên trình duyệt từ một thiết bị khác qua mạng ngoài.
- Dùng chức năng 'Try it out' trong Swagger để gửi văn bản tiếng Việt mẫu, download file wav trả về và nghe thử.
- Khởi động lại máy (Restart) và gửi request lại ngay sau khi đăng nhập để đảm bảo LaunchAgent hoạt động thành công.
