# Kế hoạch Tối ưu và Nâng cấp Hệ thống API VieNeu-TTS

## Overview
Bản kế hoạch này nhằm đáp ứng yêu cầu nâng cấp API sinh giọng nói hiện tại: bổ sung cơ chế thống kê và đo lường hiệu năng (RTF, Processing Time), kiểm soát quá tải (Concurrency Limit), dọn dẹp rác (Garbage Collection cho file audio) và cải tiến cấu trúc Response trả về cho người dùng.

## Trả lời thắc mắc: Nên gửi Base64 hay Link File?
> [!TIP]
> **Khuyến nghị: Dùng giải pháp "Gửi File trực tiếp qua Response (Streaming) hoặc Base64" nếu không cần lưu trữ.**
> 
> Dưới đây là phân tích ưu / nhược của từng giải pháp để bạn quyết định:
> 
> **1. Trả về Link tải file (Cách hiện tại đang có ý định nâng cấp):**
> - *Ưu điểm:* Response JSON cực nhẹ, dễ tích hợp với các thẻ `<audio>` trên web.
> - *Nhược điểm:* Bạn PHẢI đối mặt với bài toán dọn dẹp rác. Nếu dọn quá nhanh, user chưa kịp tải đã lỗi 404. Nếu dọn quá chậm, server sẽ bị đầy ổ cứng. Kẻ gian có thể cào (crawl) lại link cũ nếu chưa hết hạn.
> 
> **2. Trả về mã hoá Base64 trong JSON:**
> - *Ưu điểm:* Xóa file ngay lập tức sau khi tạo xong (hoặc thậm chí không cần lưu file cứng mà encode trực tiếp từ RAM). Không bao giờ có rác.
> - *Nhược điểm:* Payload JSON trả về bị phình to hơn khoảng 30% so với dung lượng file gốc, tốn tài nguyên parse JSON ở phía Client.
> 
> **3. Trả về File trực tiếp qua API (StreamingResponse) - [ĐỀ XUẤT TỐT NHẤT]:**
> - *Ưu điểm:* Client nhận trực tiếp file audio như khi tải một file MP3. File tạm sinh ra trên server có thể được dọn dẹp **ngay lập tức** thông qua cơ chế `BackgroundTask` của FastAPI sau streaming xong. Tránh hoàn toàn rác ổ cứng, không lo quản lý thời gian expire.
> 
> *Trong bản plan này, tôi sẽ triển khai theo hướng **trả về Link File** kèm cơ chế dọn dẹp định kỳ để bám sát mô tả ban đầu của bạn. Nếu bạn muốn đổi, hãy báo tôi nhé!*

## Requirements
- **Thống kê:** Tính tổng thời gian xử lý (Processing Time), tính thời lượng Audio sinh ra, từ đó suy ra chỉ số RTF (Real-Time Factor).
- **Cân bằng tải / Chống quá tải:** Giới hạn số lượng request xử lý song song (Concurrency Limit) bằng `asyncio.Semaphore` vì Mac Mini M4 có giới hạn VRAM.
- **Dọn rác:** Tạo tiến trình chạy ngầm (Background Task) để tự động xóa file quá hạn.
- **Response:** Cập nhật lại format trả về với nhiều metadata.

## Architecture & Proposed Changes
### 1. Phân luồng Cân bằng tải (Concurrency Limit)
- Dùng `asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)`. 
- Các request vượt quá con số này sẽ đưa vào queue hàng chờ chờ tới lượt xử lý.

### 2. Thu thập chỉ số (Metrics)
- **Time:** Lấy thời gian kết thúc trừ thời gian bắt đầu.
- **Audio Duration:** `len(audio) / sample_rate`.
- **RTF:** `Processing Time / Audio Duration`.

### 3. Cơ chế phục vụ File & Dọn rác
- **Serve File tĩnh:** Mount một thư mục ảo `/download` ánh xạ vào thư mục `output/`.
- **Dọn rác:** Một loop ngầm bằng `@app.on_event("startup")` quét thư mục `output/` mỗi 60 giây. Nếu file nào có `os.path.getmtime` vượt quá số phút cho phép -> `os.remove`.

#### [MODIFY] `~/services/VieNeu-TTS/api/main.py`
Sửa file `main.py` để bổ sung:
- `import asyncio, time`
- Thêm `asyncio.Semaphore`.
- Thêm logic dọn rác background.

## TODO List
- [ ] 1. Thống nhất với user về cơ chế trả file.
- [ ] 2. (Code) Cấu hình biến `MAX_CONCURRENT_REQUESTS` và Semaphore.
- [ ] 3. (Code) Cập nhật endpoint `POST /api/tts` để tính thời gian và độ dài audio.
- [ ] 4. (Code) Tính toán RTF.
- [ ] 5. (Code) Viết hàm dọn dẹp `cleanup_old_files()` chạy ngầm.
- [ ] 6. (Code) Cập nhật format Response trả về: `processing_time`, `rtf`, `file_url`, `expires_in_minutes` v.v.

## Risk Assessment
- Nếu lượng request hàng đợi quá dài, người dùng có thể bị Timeout phía Client.
- Xoá file ngầm phải cẩn thận chỉ target thư mục `output/` và định dạng `*.wav`.

## Success Criteria
- [ ] Response trả về đầy đủ các chỉ số như yêu cầu.
- [ ] Hệ thống không bị crash nếu test tải.
- [ ] Rác file cũ tự động biến mất.

## User Review Required
> [!IMPORTANT]
> 1. Vui lòng xác nhận bạn muốn dùng cách trả về **Link Tải**, hay đổi sang **Base64** hoặc **StreamingResponse**?
> 2. Bạn muốn cho phép xử lý tối đa bao nhiêu Request cùng lúc? (Tôi đề xuất `2` để an toàn cho RAM).
> 3. Thời gian hết hạn (xóa file) mong muốn là bao lâu? (Ví dụ: 5 phút).
