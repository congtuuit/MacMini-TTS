---
description: Lưu trữ context, kiến trúc và trạng thái hiện tại của dự án để sử dụng cho các phiên sau
---

# /save-brain - Lưu Trữ Context Phiên Làm Việc (Save Brain)

## Mục đích
Tổng hợp lại những thay đổi, kiến trúc, quyết định thiết kế (design decisions) và state của dự án từ đầu phiên làm việc đến hiện tại để lưu trữ lâu dài. Giúp các phiên làm việc tiếp theo của AI và người dùng nhanh chóng nạp lại context (load brain).

## Workflow

### 1. Thu thập thông tin
- Phân tích lại các công việc vừa được thực hiện trong phiên làm việc.
- Liệt kê các file quan trọng đã được sửa đổi hoặc tạo mới.
- Ghi nhận các cấu hình môi trường, framework, thư viện và flow logic hiện tại.

### 2. Tạo hoặc cập nhật tài liệu
- Viết hoặc cập nhật vào các file tài liệu hệ thống trong thư mục `docs/` (ví dụ: `docs/architecture.md`, `docs/session_summary.md`).
- Nếu người dùng yêu cầu, có thể tạo dưới dạng Artifact (ví dụ: `walkthrough.md` hoặc `knowledge_item.md`).

### 3. Cấu trúc nội dung Summary

```markdown
# 🧠 Brain Dump: [Chủ đề phiên làm việc]

## 1. Context & Trạng thái hiện tại
- Tóm tắt ngắn gọn mục tiêu của dự án tính đến thời điểm này.
- Các thiết lập môi trường (ví dụ: chạy trên Mac M4, dùng MPS, Python 3.10...).

## 2. Kiến trúc & Thiết kế
- Cấu trúc thư mục chính.
- Luồng hoạt động của hệ thống (API flow, Data flow).

## 3. Các thay đổi chính
- [x] Task 1 (Các file liên quan: `...`)
- [x] Task 2 (Các file liên quan: `...`)

## 4. Open Issues / Next Steps
- Việc chưa làm xong.
- Ý tưởng hoặc các vấn đề tiềm ẩn cần theo dõi ở phiên sau.
```

## Nguyên tắc
- Viết mạch lạc, sử dụng bullet point hoặc Markdown (bảng, khối code) để agent có thể đọc, hiểu và parse nhanh ở phiên làm việc mới.
- Lưu ý ghi rõ những thứ ĐÃ thử nhưng thất bại (để không lặp lại sai lầm).
