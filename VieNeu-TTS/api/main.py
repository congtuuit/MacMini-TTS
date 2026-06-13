from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from vieneu import Vieneu
import uuid
import os
import time
import asyncio
import wave
import shutil
import json
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    import db
except ImportError:
    pass

# Cấu hình máy Mac Mini M4 có GPU MPS và Unified Memory.
# Để an toàn không bị nghẽn bộ nhớ GPU và đạt tốc độ tốt nhất,
# cấu hình tối ưu là 2 hoặc 3 request chạy song song.
MAX_CONCURRENT_REQUESTS = 3

tts = Vieneu(
    backbone_device="mps"
)
tts_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

app = FastAPI()
os.makedirs("output", exist_ok=True)
os.makedirs("saved_voices", exist_ok=True)

class TTSRequest(BaseModel):
    text: str
    voice: str | None = None

@app.get("/api/health")
async def health_check():
    """Endpoint để Client kiểm tra xem Server có đang sống, Model tải xong chưa và thông số tài nguyên."""
    health_data = {
        "status": "ok",
        "model": "VieNeu-TTS",
        "is_model_loaded": tts is not None,
        "timestamp": time.time()
    }
    
    if HAS_PSUTIL:
        # Lấy thông số CPU và RAM
        health_data["cpu_percent"] = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        health_data["ram_percent"] = mem.percent
        health_data["ram_used_gb"] = round(mem.used / (1024**3), 2)
        health_data["ram_total_gb"] = round(mem.total / (1024**3), 2)
        
    return health_data

@app.get("/api/voices")
async def get_voices():
    voices = tts.list_preset_voices()
    preset_voices = [{"label": v[0], "id": v[1]} for v in voices]
    
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

        ref_audio_path = None
        ref_text = None
        voice = None
        
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
                voice = req.voice

        if ref_audio_path:
            audio = await asyncio.to_thread(tts.infer, text=req.text, ref_audio=ref_audio_path, ref_text=ref_text)
        else:
            audio = await asyncio.to_thread(tts.infer, text=req.text, voice=voice)
            
        await asyncio.to_thread(tts.save, audio, filename)
        
        processing_time = time.time() - start_time
        
        # Lấy thông tin độ dài Audio
        with wave.open(filename, 'r') as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            audio_duration = frames / float(rate)
            
        rtf = processing_time / audio_duration if audio_duration > 0 else 0

        # Thêm task xóa file chạy ngầm sau khi trả HTTP Response xong
        background_tasks.add_task(remove_temp_files, filename)

        if 'db' in sys.modules:
            cpu_p = psutil.cpu_percent() if HAS_PSUTIL else 0.0
            ram_p = psutil.virtual_memory().percent if HAS_PSUTIL else 0.0
            db.log_request("VieNeu-TTS", "/api/tts", voice or "auto", len(req.text), processing_time, audio_duration, rtf, cpu_p, ram_p)

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
        audio = await asyncio.to_thread(tts.infer, text=text, ref_audio=ref_filename, ref_text=ref_text)
        await asyncio.to_thread(tts.save, audio, out_filename)
        
        processing_time = time.time() - start_time
        
        # Lấy thông tin độ dài Audio
        with wave.open(out_filename, 'r') as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            audio_duration = frames / float(rate)
            
        rtf = processing_time / audio_duration if audio_duration > 0 else 0

        # Thêm task xóa cả 2 file (file mẫu + file sinh ra)
        background_tasks.add_task(remove_temp_files, out_filename, ref_filename)

        if 'db' in sys.modules:
            cpu_p = psutil.cpu_percent() if HAS_PSUTIL else 0.0
            ram_p = psutil.virtual_memory().percent if HAS_PSUTIL else 0.0
            db.log_request("VieNeu-TTS", "/api/clone", "cloned_voice", len(text), processing_time, audio_duration, rtf, cpu_p, ram_p)

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
