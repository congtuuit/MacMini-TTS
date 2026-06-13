from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uuid
import os
import time
import asyncio
import wave
import shutil
import json
import numpy as np
import soundfile as sf
import torch

from omnivoice import OmniVoice

# Cấu hình máy Mac Mini M4 có GPU MPS và Unified Memory.
# Tối ưu cho tốc độ: Đặt = 1 để tránh việc macOS swap RAM gây chậm
MAX_CONCURRENT_REQUESTS = 1

#default 32
NUMBER_STEP=32

# Khởi tạo model OmniVoice
# device_map="mps" cho Apple Silicon, "cuda:0" cho NVIDIA GPU
tts = OmniVoice.from_pretrained(
    "k2-fsa/OmniVoice",
    device_map="mps",
    dtype=torch.float16
)

tts_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

app = FastAPI()
os.makedirs("output", exist_ok=True)
os.makedirs("saved_voices", exist_ok=True)

class TTSRequest(BaseModel):
    text: str
    voice: str | None = None

@app.get("/api/voices")
async def get_voices():
    # OmniVoice sử dụng instruct (prompt) thay vì danh sách ID giọng đọc tĩnh.
    # Cung cấp một số preset cơ bản.
    preset_voices = [
        {"label": "Tự động chọn (Auto)", "id": ""},
        {"label": "Nữ, giọng mặc định", "id": "female"},
        {"label": "Nam, giọng mặc định", "id": "male"},
        {"label": "Nữ, giọng trầm", "id": "female, low pitch"},
        {"label": "Nữ, giọng cao", "id": "female, high pitch"},
        {"label": "Nam, giọng trầm", "id": "male, low pitch"},
        {"label": "Nam, giọng cao", "id": "male, high pitch"},
    ]
    
    saved_dir = "saved_voices"
    if os.path.exists(saved_dir):
        for filename in os.listdir(saved_dir):
            if filename.endswith(".json"):
                try:
                    with open(os.path.join(saved_dir, filename), "r", encoding="utf-8") as f:
                        meta = json.load(f)
                        preset_voices.append({
                            "label": f"Giọng lưu: {meta.get('name', 'Không tên')}",
                            "id": meta.get("id")
                        })
                except Exception:
                    pass

    return {
        "success": True,
        "voices": preset_voices
    }

def remove_temp_files(*paths: str):
    """Xóa các file tạm ngay lập tức sau khi user đã tải xong"""
    for path in paths:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            print(f"Error removing file {path}: {e}")

@app.post("/api/tts")
async def generate(req: TTSRequest, background_tasks: BackgroundTasks):
    # Đưa vào hàng chờ xử lý dựa trên Semaphore Limit
    async with tts_semaphore:
        start_time = time.time()
        
        file_id = str(uuid.uuid4())
        filename = f"output/{file_id}.wav"

        # Kiểm tra xem tham số voice có phải là voice_id đã lưu hay không
        ref_audio_path = None
        ref_text = None
        instruct = None
        
        if req.voice:
            potential_path = f"saved_voices/{req.voice}.wav"
            potential_json = f"saved_voices/{req.voice}.json"
            if os.path.exists(potential_path):
                ref_audio_path = potential_path
                if os.path.exists(potential_json):
                    try:
                        with open(potential_json, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                            ref_text = meta.get("ref_text")
                    except Exception:
                        pass
            else:
                instruct = req.voice

        if ref_audio_path:
            # Dùng file âm thanh lưu sẵn để clone
            audio = await asyncio.to_thread(tts.generate, text=req.text, ref_audio=ref_audio_path, ref_text=ref_text, num_step=NUMBER_STEP)
        else:
            # Sinh giọng bằng instruct prompt
            audio = await asyncio.to_thread(tts.generate, text=req.text, instruct=instruct, num_step=NUMBER_STEP)
        
        # Save output
        await asyncio.to_thread(sf.write, filename, audio[0], 24000)
        
        processing_time = time.time() - start_time
        
        # Lấy thông tin độ dài Audio
        with wave.open(filename, 'r') as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            audio_duration = frames / float(rate)
            
        rtf = processing_time / audio_duration if audio_duration > 0 else 0

        # Thêm task xóa file chạy ngầm sau khi trả HTTP Response xong
        background_tasks.add_task(remove_temp_files, filename)

        # Trả về các chỉ số thông qua HTTP Headers vì body là file âm thanh
        headers = {
            "X-Processing-Time-Sec": str(round(processing_time, 3)),
            "X-Audio-Duration-Sec": str(round(audio_duration, 3)),
            "X-RTF": str(round(rtf, 3))
        }

        return FileResponse(
            path=filename, 
            media_type="audio/wav", 
            filename=f"tts_{file_id}.wav",
            headers=headers
        )

@app.post("/api/voices/save")
async def save_voice(
    voice_name: str = Form(...),
    ref_text: str | None = Form(None),
    ref_audio: UploadFile = File(...)
):
    voice_id = f"voice_{uuid.uuid4().hex[:8]}"
    wav_path = f"saved_voices/{voice_id}.wav"
    json_path = f"saved_voices/{voice_id}.json"
    
    with open(wav_path, "wb") as buffer:
        shutil.copyfileobj(ref_audio.file, buffer)
        
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"id": voice_id, "name": voice_name, "ref_text": ref_text}, f, ensure_ascii=False)
        
    return {
        "success": True,
        "voice_id": voice_id,
        "voice_name": voice_name
    }

@app.post("/api/clone")
async def clone_voice(
    background_tasks: BackgroundTasks,
    text: str = Form(...),
    ref_text: str | None = Form(None),
    ref_audio: UploadFile = File(...)
):
    # Đưa vào hàng chờ xử lý dựa trên Semaphore Limit
    async with tts_semaphore:
        start_time = time.time()
        
        file_id = str(uuid.uuid4())
        
        # Lưu file audio mẫu tạm thời
        ref_filename = f"output/ref_{file_id}_{ref_audio.filename}"
        with open(ref_filename, "wb") as buffer:
            shutil.copyfileobj(ref_audio.file, buffer)
            
        out_filename = f"output/clone_{file_id}.wav"

        # Sử dụng to_thread để không bị block event loop
        # Truyền ref_audio để clone giọng
        audio = await asyncio.to_thread(tts.generate, text=text, ref_audio=ref_filename, ref_text=ref_text, num_step=NUMBER_STEP)
        
        # Save output
        await asyncio.to_thread(sf.write, out_filename, audio[0], 24000)
        
        processing_time = time.time() - start_time
        
        # Lấy thông tin độ dài Audio
        with wave.open(out_filename, 'r') as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            audio_duration = frames / float(rate)
            
        rtf = processing_time / audio_duration if audio_duration > 0 else 0

        # Thêm task xóa cả 2 file (file mẫu + file sinh ra)
        background_tasks.add_task(remove_temp_files, out_filename, ref_filename)

        headers = {
            "X-Processing-Time-Sec": str(round(processing_time, 3)),
            "X-Audio-Duration-Sec": str(round(audio_duration, 3)),
            "X-RTF": str(round(rtf, 3))
        }

        return FileResponse(
            path=out_filename, 
            media_type="audio/wav", 
            filename=f"cloned_{file_id}.wav",
            headers=headers
        )
