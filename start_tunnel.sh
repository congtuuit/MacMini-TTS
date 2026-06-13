#!/bin/bash

# Script khởi động Cloudflare Tunnel nhanh (Random URL)
echo "=========================================="
echo "🚀 KHỞI ĐỘNG CLOUDFLARE TUNNEL"
echo "🌐 API Local: http://localhost:8000"
echo "Đang yêu cầu URL Public từ Cloudflare..."
echo "Vui lòng chờ vài giây. Copy link có đuôi .trycloudflare.com để sử dụng!"
echo "Nhấn Ctrl+C để tắt Tunnel."
echo "=========================================="

cloudflared tunnel --url http://localhost:8000
