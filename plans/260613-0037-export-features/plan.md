# Kế hoạch Triển khai API cho các Tính năng nâng cao (Voice Cloning & Emotion Tags)

## Overview
Bản kế hoạch này nhằm mục đích xuất khẩu (export) các tính năng cao cấp của mô hình VieNeu-TTS thành các API độc lập để Client có thể dễ dàng sử dụng. Trọng tâm chính là **Tính năng nhân bản giọng nói tức thì (Zero-shot Voice Cloning)** và hướng dẫn cách dùng **Cảm xúc (Emotion Tags)** trên API hiện tại.

## Requirements
1. **Zero-shot Voice Cloning API:**
   - Cần một Endpoint mới cho phép người dùng truyền tải lên (Upload) một tệp âm thanh mẫu (từ 3-5 giây) cùng với văn bản cần đọc.
   - API sẽ xử lý và trả về âm thanh đã được clone giọng y hệt file mẫu.
   - Phải giữ được ưu điểm thiết kế cũ: Giới hạn tải (Concurrency Limit), Gửi file trực tiếp (Streaming/FileResponse), tính RTF, và không để lại tệp rác.

2. **Emotion Tags (Biểu cảm cảm xúc):**
   - Về mặt bản chất, model tự động hiểu các thẻ cảm xúc (ví dụ: `[cười]`, `[thở dài]`) khi được chèn thẳng vào biến `text`. Do đó không cần tạo API mới, chỉ cần cập nhật tài liệu hướng dẫn sử dụng.

## Architecture & Proposed Changes

### 1. Cấu trúc API mới: `POST /api/clone`
Thay vì nhận JSON Body (vì JSON không truyền file hiệu quả), API này sẽ nhận dạng `multipart/form-data`:
- `text`: Chuỗi văn bản (String).
- `ref_audio`: Tệp âm thanh mẫu (Binary File).

### 2. Quá trình xử lý (Lifecycle)
- **Bước 1:** API tiếp nhận tệp `ref_audio` do người dùng gửi lên và lưu tạm thời vào thư mục `output/ref_xxx.wav`.
- **Bước 2:** Chờ đến lượt xử lý qua `tts_semaphore`.
- **Bước 3:** Gọi `tts.infer(text, ref_audio="output/ref_xxx.wav")` để sinh âm thanh.
- **Bước 4:** Trả về kết quả thông qua `FileResponse` kèm Header chứa thông tin (RTF, Processing Time).
- **Bước 5:** Xóa CẢ HAI tệp (file kết quả và file âm thanh mẫu) tự động thông qua `BackgroundTasks` ngay sau khi người dùng tải xong.

### 3. File bị ảnh hưởng
#### [MODIFY] `~/services/VieNeu-TTS/api/main.py`
- Import thêm các module: `UploadFile`, `File`, `Form`, `shutil` từ FastAPI.
- Thêm endpoint `@app.post("/api/clone")` với logic xử lý file như đề cập.
- Viết hàm hỗ trợ xóa nhiều file cùng lúc để dọn dẹp sạch sẽ ổ cứng.

#### [MODIFY] `~/docs/api.txt`
- Thêm cú pháp Curl cho việc gọi API `/api/clone` (Sử dụng tham số `-F` của curl để upload file).
- Thêm cú pháp ví dụ dùng `/api/tts` với Emotion Tags.

## TODO List
- [ ] 1. (Code) Bổ sung Endpoint `/api/clone` vào `main.py` với khả năng upload file.
- [ ] 2. (Code) Áp dụng Semaphore để giới hạn lượt xử lý đồng thời, bảo vệ GPU.
- [ ] 3. (Code) Tích hợp `asyncio.to_thread` cho các tác vụ lưu file tạm và sinh giọng (infer) để không block Event Loop.
- [ ] 4. (Code) Cấu hình BackgroundTasks xoá toàn bộ dấu vết (file sinh ra + file upload) sau khi xong.
- [ ] 5. (Docs) Cập nhật file tài liệu `docs/api.txt`.

## Risk Assessment
- Nếu Client cố tình gửi một file âm thanh quá dài (ví dụ: 1 bài hát dài 5 phút) hoặc file không phải là âm thanh (ví dụ: file exe, pdf), model có thể báo lỗi hoặc tốn quá nhiều tài nguyên để decode.
- **Biện pháp tạm thời:** Mô hình VieNeu tự động cắt 3-5 giây đầu tiên nếu file quá dài nên sẽ không chết server, nhưng cần bao bọc trong khối `try-except` để trả về lỗi 400 Bad Request cho người dùng thay vì làm crash server.

## Success Criteria
- [ ] Endpoint `/api/clone` chạy ổn định, tiếp nhận file upload thành công.
- [ ] Trả về giọng nói có chất giọng giống mẫu truyền vào.
- [ ] Thư mục `output/` giữ nguyên trạng thái trống (0 tệp tin) sau khi Request hoàn tất.

## User Review Required
> [!IMPORTANT]
> 1. Bạn có đồng ý với việc sử dụng định dạng `multipart/form-data` cho API clone giọng để tiện cho việc upload file không?
> 2. Có cần tôi giới hạn dung lượng upload tối đa của file âm thanh mẫu không? (Mặc định FastAPI không giới hạn, nhưng đối với Voice Clone chỉ cần file mẫu từ 3-5 giây ~ 500KB là đủ).
