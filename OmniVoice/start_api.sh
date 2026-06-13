#!/bin/bash

# Ensure we're in the right directory
cd "$(dirname "$0")"

echo "Starting OmniVoice API..."
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000
