#!/bin/bash

# Thêm đường dẫn chứa uv vào PATH
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"

# Di chuyển vào thư mục chứa mã nguồn
cd "/Users/tuvan/Documents/vieneu-local/VieNeu-TTS"

echo "Đang khởi động VieNeu-TTS API..."
echo "Swagger UI sẽ có sẵn tại: http://localhost:8000/docs"
echo "Bấm Ctrl+C để dừng server."

# Khởi chạy uvicorn
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000
