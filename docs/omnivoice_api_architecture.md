# 🧠 Brain Dump: Triển khai API cho OmniVoice Model

## 1. Context & Trạng thái hiện tại
- **Mục tiêu**: Tách model OmniVoice thành một API phục vụ việc tạo audio (TTS) và clone giọng. Chạy local trên Mac Mini M4. Cấu trúc API được xây dựng đồng bộ/tương thích hoàn toàn với cấu trúc API của `VieNeu-TTS` hiện có để tận dụng lại các công cụ phía Client.
- **Trạng thái**: Đã hoàn tất setup thư mục project `OmniVoice/`, đã lập trình xong các endpoint API và có sẵn bash script khởi chạy.
- **Thiết lập môi trường**:
  - Máy chủ: Mac Mini M4.
  - Framework Model: Sử dụng inference backend của Apple Silicon `MPS` (`device_map="mps"`, `dtype=torch.float16`).
  - Khung Web Server: `FastAPI` chạy bằng `uvicorn`.

## 2. Kiến trúc & Thiết kế
- **Cấu trúc thư mục**:
  - Root project `OmniVoice/`
    - `api/main.py`: File controller chính của FastAPI. Wrap OmniVoice model.
    - `start_api.sh`: Bash script tự động run server ở port 8000.
    - `pyproject.toml`: Khai báo các module bổ trợ `fastapi`, `uvicorn`, `python-multipart`.
    - `output/`: Thư mục tạm lưu trữ Audio trước khi stream cho Client.
- **Cơ chế chống quá tải và tăng tốc**: Sử dụng `asyncio.Semaphore(1)` (chỉ chạy 1 request mỗi thời điểm) để ép máy Mac luôn sử dụng tối đa sức mạnh của Unified Memory, tránh hiện tượng Swap Memory cực kỳ chậm của macOS khi bị thiếu RAM.
  - **Tối ưu Diffusion**: Truyền tham số `num_step=16` (thay vì 32 mặc định) vào hàm `generate` giúp tăng gấp đôi tốc độ sinh Voice/Clone mà không làm giảm đáng kể chất lượng.
  - **Tối ưu ASR (Whisper Bypass)**: Để tránh việc OmniVoice tự gọi model Whisper ra dịch ngược audio mẫu thành text (gây chậm nghiêm trọng), API đã bổ sung tham số `ref_text` để cung cấp sẵn bản dịch của audio mẫu.
  - **Thread-safe**: Call model thông qua `asyncio.to_thread(tts.generate, ...)` nhằm giữ cho Event Loop của FastAPI không bị block.
  - **Quản lý bộ nhớ tạm**: File output (WAV) và reference audio sau khi generate sẽ trả về thông qua `FileResponse`. Kèm theo một tác vụ chạy ngầm (`BackgroundTasks`) sẽ tự động clean/xoá file ngay sau khi Client kết thúc việc download.
  - **Telemetry**: HTTP Header trả về chứa các tham số đo lường tốc độ: `X-Processing-Time-Sec`, `X-Audio-Duration-Sec` và `X-RTF`.

## 3. Các thay đổi chính
- [x] Tích hợp model nguyên bản từ repo `k2-fsa/OmniVoice`, loại bỏ các folder dư thừa (`docs/`, `examples/`...) để tạo không gian sạch cho source web.
- [x] Tạo endpoint `GET /api/voices`: Trả về các preset prompt cho tính năng "Voice Design" của OmniVoice (Thay vì danh sách Voice ID tĩnh như VieNeu).
- [x] Tạo endpoint `POST /api/tts`: Hỗ trợ sinh giọng đọc theo Text và `instruct` (prompt mô tả đặc điểm giọng).
- [x] Tạo endpoint `POST /api/voices/save` và cập nhật `POST /api/clone`: Hỗ trợ upload `ref_audio` và truyền `ref_text` để clone giọng nhanh chóng mà không gọi Whisper.

## 4. Open Issues / Next Steps
- **Cần theo dõi tài nguyên Memory (RAM)**: OmniVoice là một model sử dụng kiến trúc Diffusion khá lớn. Khi chạy lần đầu, server sẽ tải các file weights từ HuggingFace. Cần theo dõi dung lượng RAM mà MPS cấp phát, nếu bị OOM (Out of Memory) thì vào `api/main.py` để chỉnh `MAX_CONCURRENT_REQUESTS` xuống `1` hoặc `2`.
- **Thử nghiệm và tuỳ chỉnh Prompts**: Danh sách preset voices trong `GET /api/voices` hiện nay đang hard-code một số prompt mẫu như `female, low pitch`, `male`. Người dùng cần tự thử nghiệm tính năng Voice Design để điền vào danh sách prompt này những cấu hình có chất lượng output tốt nhất.
- **Triển khai Auto-start (Tuỳ chọn)**: Có thể viết thêm cấu hình cho macOS `launchctl` (giống cách làm ở VieNeu) để tự động khởi động OmniVoice API mỗi khi máy restart.
