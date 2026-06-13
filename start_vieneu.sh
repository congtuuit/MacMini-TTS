#!/bin/bash

# Chuyển vào đúng thư mục dự án VieNeu-TTS
cd "$(dirname "$0")/VieNeu-TTS"

echo "=========================================="
echo "🚀 KHỞI ĐỘNG VIENEU-TTS API"
echo "🌐 API Local: http://localhost:8000/api/health"
echo "=========================================="

uv run uvicorn api.main:app --host 0.0.0.0 --port 8000
