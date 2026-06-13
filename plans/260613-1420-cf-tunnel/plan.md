# Triển Khai Cloudflare Tunnel (CF)

## Overview
Đưa hệ thống API Sách nói (chạy trên port 8000 của Mac Mini) ra môi trường Public Internet một cách bảo mật thông qua Cloudflare Tunnel (`cloudflared`). Cách này giúp Client có thể gọi API từ bất cứ đâu mà không cần thiết lập NAT/Port Forwarding trên cục phát WiFi.

## Requirements
- Bypass tường lửa cục bộ, không cần IP tĩnh.
- Cung cấp HTTPS Endpoint an toàn.
- Phần cứng: Mac Mini M4.

## Architecture
Mô hình định tuyến:
`Client (Internet)` --> `Cloudflare Edge` --> `cloudflared daemon (trên Mac Mini)` --> `localhost:8000`

## Implementation Steps
1. **Cài đặt công cụ**: Chạy lệnh `brew install cloudflare/cloudflare/cloudflared` trên Mac Mini.
2. **Tạo Script**: Tạo file `start_tunnel.sh` để bạn chỉ cần click là nó tự động map port 8000 ra ngoài Internet.
3. **Xác nhận chế độ (Cần quyết định)**:
   - **Cách 1 (Quick Tunnel)**: Chạy phát ăn ngay. CF sẽ cấp 1 link ngẫu nhiên (vd: `https://tom-cat-dog.trycloudflare.com`). Nhược điểm: Mỗi lần tắt bật lại server sẽ bị đổi link.
   - **Cách 2 (Persistent Tunnel)**: Gắn link cố định với tên miền của bạn (vd: `api.domaincuaban.com`). Ưu điểm: Đẹp, chuyên nghiệp, cố định. Nhược điểm: Bạn phải có tài khoản Cloudflare và sở hữu 1 tên miền.

## TODO List
- [ ] Tải và cài đặt `cloudflared`.
- [ ] Viết `start_tunnel.sh`.
- [ ] (Tuỳ chọn) Thiết lập `cloudflared service` để tự động chạy ngầm khi Mac Mini bật lên.

## Risk Assessment
- **Đứt kết nối tạm thời**: Nếu mạng nhà bạn rớt, Tunnel cũng rớt theo. Tuy nhiên Cloudflare sẽ tự động nối lại ngay khi có mạng.
- **Bảo mật**: Public API ra ngoài đồng nghĩa ai có link cũng có thể gọi vào model của bạn (tốn RAM). Có thể cân nhắc làm thêm 1 lớp check Token đơn giản nếu chọn Cách 2.

## Success Criteria
- Dùng điện thoại (mạng 4G) truy cập vào `https://<url_cloudflare>/dashboard` và thấy Dashboard hiện lên mượt mà.
