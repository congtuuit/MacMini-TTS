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

class TTSRequest(BaseModel):
    text: str
    voice: str | None = None

@app.get("/api/voices")
async def get_voices():
    voices = tts.list_preset_voices()
    return {
        "success": True,
        "voices": [{"label": v[0], "id": v[1]} for v in voices]
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

        # Sử dụng to_thread để không bị block event loop của FastAPI
        audio = await asyncio.to_thread(tts.infer, req.text, voice=req.voice)
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

@app.post("/api/clone")
async def clone_voice(
    background_tasks: BackgroundTasks,
    text: str = Form(...),
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
        audio = await asyncio.to_thread(tts.infer, text=text, ref_audio=ref_filename)
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
