# Báo cáo Chi tiết Hệ thống: OmniVoice Audiobooks API

Tài liệu này tổng hợp toàn bộ kiến trúc, thông số hiệu suất và hướng dẫn vận hành cho hệ thống **OmniVoice API** chạy trên nền tảng **Mac Mini M4**. Hệ thống được tối ưu hóa đặc biệt cho mục đích sản xuất **Sách nói (Audiobooks)** hàng loạt.

---

## 1. Tổng quan Phần cứng & Kiến trúc

Hệ thống được thiết kế theo mô hình **Client-Server Bất đồng bộ (Micro-batching)**, tận dụng sức mạnh của kiến trúc Unified Memory trên Apple Silicon.

| Thành phần | Đặc tả |
| :--- | :--- |
| **Phần cứng Host** | Mac Mini (Chip M4), Unified Memory (16GB) |
| **Backend Framework** | FastAPI (Python) |
| **Mô hình cốt lõi** | OmniVoice (Diffusion Language Model) |
| **Gia tốc phần cứng** | Apple MPS (Metal Performance Shaders) / FP16 |
| **Cổng mạng (Network)** | Cloudflare Tunnel (`cloudflared`) |
| **Hệ thống Giám sát** | SQLite (`metrics.db`) + Chart.js Dashboard |

> [!NOTE]
> Mọi request gọi vào OmniVoice đều được đẩy vào một hàng đợi (Queue) nội bộ thông qua `asyncio.Semaphore(1)` để đảm bảo RAM tĩnh luôn duy trì dưới mức an toàn (<15GB), tuyệt đối không để xảy ra hiện tượng **Swap RAM** (gây suy giảm tốc độ x10 lần).

---

## 2. Thông số Hiệu năng (Performance Benchmarks)

Các chỉ số dưới đây được đo đạc từ bài kiểm tra thực tế (Stress Test 100 concurrent users) với các Chunk văn bản dài trung bình 150 ký tự (~8 đến 10 giây âm thanh).

### Các Chỉ Số Cốt Lõi
- **RTF (Real-Time Factor):** `~0.55` (Máy mất 0.55 giây để sinh ra 1 giây âm thanh).
- **Thời gian Render 1 Chunk:** `3.5 - 4.0 giây`
- **Năng suất theo Thời gian (Throughput):** 
  - `16 - 17 Request / Phút`.
  - Tuơng đương sản xuất **1.8 tiếng Sách nói** mỗi 1 tiếng cắm máy chạy.

### Giới Hạn Mạng (Network Limits)
- **Max Concurrent Connections (Local):** Không giới hạn.
- **Max Concurrent Connections (Qua Cloudflare):** `~27 Request đồng thời`.
  
> [!WARNING]
> Nếu Client gửi song song > 27 request qua Cloudflare, những request cuối cùng sẽ phải chờ xếp hàng trong Mac Mini quá lâu. Cloudflare sẽ tự động kích hoạt **Hard Timeout Limit ở mốc 100 giây**, dẫn đến việc ngắt kết nối đột ngột và ném ra lỗi `524 A Timeout Occurred`.

---

## 3. Hệ sinh thái API (Endpoints)

Hệ thống cung cấp một tập hợp các REST API chuẩn mực để Client giao tiếp:

| Phương thức | Endpoint | Chức năng |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Ping kiểm tra server sống hay chết, trả về % RAM/CPU hiện tại. |
| `POST` | `/api/voices/save` | Lưu một giọng nói xịn vào server kèm `ref_text` để làm Preset. |
| `GET` | `/api/voices` | Lấy danh sách các giọng mặc định và giọng đã được lưu. |
| `POST` | `/api/tts` | Gửi Text + VoiceID để lấy file `.wav` thành phẩm. |
| `POST` | `/api/clone` | Gửi Text + File Audio + Ref Text để clone nóng (Zero-shot). |
| `GET` | `/dashboard` | Giao diện Web hiển thị biểu đồ CPU, RAM và Log các Request. |

---

## 4. Tối ưu hóa Mô hình (Model Optimizations)

Để đạt được tốc độ `3.6s/chunk` ấn tượng trên Mac M4, 2 kĩ thuật lõi đã được áp dụng:

1. **Điều chỉnh `num_step` (Diffusion Steps):**
   - Giảm số bước khử nhiễu (num_step) từ mặc định xuống mức cân bằng giữa tốc độ và chất lượng.
2. **Bypass Whisper (ASR):**
   - OmniVoice mặc định sẽ tốn rất nhiều RAM và CPU để chạy mô hình Whisper nhằm phân tích văn bản từ file âm thanh mẫu.
   - Hệ thống của chúng ta yêu cầu lưu kèm `ref_text` (Transcript) khi tạo giọng. Khi Client gọi API, hệ thống nhét thẳng `ref_text` này vào hàm Generate, bỏ qua hoàn toàn sự hiện diện của Whisper.

---

## 5. Cẩm nang Thiết kế Client (Bắt buộc)

> [!IMPORTANT]
> Để tránh gây treo mạng và đảm bảo chất lượng giọng đọc cảm xúc nhất, kĩ sư lập trình phần Client (App/Web) **BẮT BUỘC** phải tuân thủ 3 nguyên tắc sau:

1. **Chặt nhỏ Văn bản (Semantic Chunking):**
   - Không ném cả chương truyện 2000 chữ lên Server. 
   - Client phải tự chặt văn bản thành các Chunk ngắn (150 - 200 ký tự). Chú ý: Phải chặt theo dấu chấm câu (`.`, `?`, `!`, `\n`) để model hiểu ngữ cảnh và ngắt nghỉ tự nhiên.
2. **Gửi Tuần Tự (Sequential Processing):**
   - **Tối kỵ:** Sử dụng `Promise.all()` hoặc chạy đa luồng để gửi tất cả các Chunk lên cùng lúc. (Sẽ dính lỗi 524 của Cloudflare).
   - **Bắt buộc:** Gửi Chunk 1 -> Nhận Audio -> Gửi Chunk 2 -> Nhận Audio...
3. **Nối File (Audio Stitching):**
   - Khi nối các đoạn `.wav` nhỏ lại thành file MP3 lớn bằng FFmpeg, Client nên chủ động chèn thêm khoảng `0.3s - 0.5s` khoảng lặng (Silence) vào giữa các Chunk. Điều này giả lập nhịp thở tự nhiên của người đọc sách.

---
*Tài liệu được sinh tự động bởi hệ thống Quản lý MLOps.*
