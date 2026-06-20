#!/bin/bash

# Chuyển vào đúng thư mục dự án OmniVoice
cd "$(dirname "$0")/OmniVoice"

echo "=========================================="
echo "🚀 KHỞI ĐỘNG OMNIVOICE API"
echo "🌐 Bảng điều khiển: http://localhost:8000/dashboard"
echo "=========================================="

uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --loop uvloop
