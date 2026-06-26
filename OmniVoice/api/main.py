from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
import io
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field
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
import numpy as np
import soundfile as sf
import torch
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    import db
except ImportError:
    pass

from omnivoice import OmniVoice

# Cấu hình máy Mac Mini M4 có GPU MPS và Unified Memory.
# Tối ưu cho tốc độ: Đặt = 1 để tránh việc macOS swap RAM gây chậm
MIN_CONCURRENT_REQUESTS = 2
MAX_CONCURRENT_REQUESTS = 20
RAM_THRESHOLD = 95.0

# Tối ưu hóa: Giảm từ 32 xuống 16 để tăng gấp đôi tốc độ sinh Audio
NUMBER_STEP=16

# Khởi tạo model OmniVoice
# device_map="mps" cho Apple Silicon, "cuda:0" cho NVIDIA GPU
tts = OmniVoice.from_pretrained(
    "k2-fsa/OmniVoice",
    device_map="mps",
    dtype=torch.float16
)

class AdaptiveConcurrencyLimiter:
    def __init__(self, min_concurrency=2, max_concurrency=5, ram_threshold=95.0):
        self.current_running = 0
        self.min_concurrency = min_concurrency
        self.max_concurrency = max_concurrency
        self.ram_threshold = ram_threshold
        self.cond = asyncio.Condition()

    @asynccontextmanager
    async def acquire(self, request: Request):
        async with self.cond:
            while True:
                if await request.is_disconnected():
                    print("Client disconnected, dropping queued request...")
                    raise asyncio.CancelledError("Client disconnected")
                
                # Lấy RAM sử dụng (nếu không có psutil, mặc định an toàn)
                ram_percent = 0.0
                if HAS_PSUTIL:
                    ram_percent = psutil.virtual_memory().percent
                
                # Xác định số luồng tối đa cho phép hiện tại
                if ram_percent >= self.ram_threshold:
                    allowed = self.min_concurrency
                else:
                    allowed = self.max_concurrency
                
                if self.current_running < allowed:
                    self.current_running += 1
                    break
                else:
                    # Chờ tối đa 1s để kiểm tra lại điều kiện ngắt kết nối
                    try:
                        await asyncio.wait_for(self.cond.wait(), timeout=1.0)
                    except asyncio.TimeoutError:
                        pass
        try:
            yield
        finally:
            async with self.cond:
                self.current_running -= 1
                self.cond.notify_all()

tts_semaphore = AdaptiveConcurrencyLimiter(
    min_concurrency=MIN_CONCURRENT_REQUESTS,
    max_concurrency=MAX_CONCURRENT_REQUESTS,
    ram_threshold=RAM_THRESHOLD
)

app = FastAPI()
os.makedirs("output", exist_ok=True)
os.makedirs("saved_voices", exist_ok=True)

class TTSRequest(BaseModel):
    text: str = Field(..., max_length=300, description="Tối đa 300 ký tự")
    voice: str | None = None
    seed: int | None = None
    keep_voice: bool = False

@app.get("/api/health")
async def health_check():
    """Endpoint để Client kiểm tra xem Server có đang sống, Model tải xong chưa và thông số tài nguyên."""
    health_data = {
        "status": "ok",
        "model": "OmniVoice",
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
async def generate(req: TTSRequest, request: Request, background_tasks: BackgroundTasks):
    # Đưa vào hàng chờ xử lý dựa trên Semaphore Limit
    async with tts_semaphore.acquire(request):
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
                if req.keep_voice:
                    import hashlib
                    seed_str = str(req.seed) if req.seed is not None else ""
                    cache_key = f"instruct_cache_{hashlib.md5((instruct + seed_str).encode()).hexdigest()[:16]}"
                    cache_wav = f"saved_voices/{cache_key}.wav"
                    cache_json = f"saved_voices/{cache_key}.json"
                    
                    if os.path.exists(cache_wav):
                        ref_audio_path = cache_wav
                        instruct = None # Force clone mode
                        if os.path.exists(cache_json):
                            try:
                                with open(cache_json, "r", encoding="utf-8") as f:
                                    meta = json.load(f)
                                    ref_text = meta.get("ref_text")
                            except Exception:
                                pass

        def run_tts_generation():
            # Cố định random seed để đảm bảo cùng 1 voice/instruct sẽ sinh ra cùng 1 chất giọng
            if req.seed is not None:
                torch.manual_seed(req.seed)
            elif req.voice:
                import hashlib
                seed = int(hashlib.md5(req.voice.encode()).hexdigest(), 16) % (2**32)
                torch.manual_seed(seed)
                
            if ref_audio_path:
                # Dùng file âm thanh lưu sẵn để clone
                return tts.generate(text=req.text, ref_audio=ref_audio_path, ref_text=ref_text, num_step=NUMBER_STEP)
            else:
                # Sinh giọng bằng instruct prompt
                return tts.generate(text=req.text, instruct=instruct, num_step=NUMBER_STEP)

        audio = await asyncio.to_thread(run_tts_generation)
        
        # Lưu output trực tiếp vào RAM
        wav_io = io.BytesIO()
        await asyncio.to_thread(sf.write, wav_io, audio[0], 24000, format='WAV')
        wav_bytes = wav_io.getvalue()

        # Caching the generated audio if it was generated from instruct
        if instruct and not ref_audio_path and req.keep_voice:
            try:
                with open(cache_wav, "wb") as f:
                    f.write(wav_bytes)
                with open(cache_json, "w", encoding="utf-8") as f:
                    json.dump({"id": cache_key, "name": f"Auto cached {req.voice}", "ref_text": req.text}, f, ensure_ascii=False)
            except Exception as e:
                print(f"Failed to cache instruct audio: {e}")
        
        processing_time = time.time() - start_time
        
        # Lấy thông tin độ dài Audio trực tiếp từ array
        audio_duration = len(audio[0]) / 24000.0
            
        rtf = processing_time / audio_duration if audio_duration > 0 else 0

        if 'db' in sys.modules:
            cpu_p = psutil.cpu_percent() if HAS_PSUTIL else 0.0
            ram_p = psutil.virtual_memory().percent if HAS_PSUTIL else 0.0
            db.log_request("OmniVoice", "/api/tts", req.voice or "auto", len(req.text), processing_time, audio_duration, rtf, cpu_p, ram_p)

        # Trả về các chỉ số thông qua HTTP Headers vì body là file âm thanh
        headers = {
            "X-Processing-Time-Sec": str(round(processing_time, 3)),
            "X-Audio-Duration-Sec": str(round(audio_duration, 3)),
            "X-RTF": str(round(rtf, 3))
        }

        return Response(
            content=wav_bytes, 
            media_type="audio/wav",
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
    request: Request,
    background_tasks: BackgroundTasks,
    text: str = Form(..., max_length=300, description="Tối đa 300 ký tự"),
    ref_text: str | None = Form(None),
    ref_audio: UploadFile = File(...)
):
    # Đưa vào hàng chờ xử lý dựa trên Semaphore Limit
    async with tts_semaphore.acquire(request):
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
        
        # Lưu output trực tiếp vào RAM
        wav_io = io.BytesIO()
        await asyncio.to_thread(sf.write, wav_io, audio[0], 24000, format='WAV')
        wav_bytes = wav_io.getvalue()
        
        processing_time = time.time() - start_time
        
        # Lấy thông tin độ dài Audio trực tiếp từ array
        audio_duration = len(audio[0]) / 24000.0
            
        rtf = processing_time / audio_duration if audio_duration > 0 else 0

        # Chỉ xóa file mẫu
        background_tasks.add_task(remove_temp_files, ref_filename)

        if 'db' in sys.modules:
            cpu_p = psutil.cpu_percent() if HAS_PSUTIL else 0.0
            ram_p = psutil.virtual_memory().percent if HAS_PSUTIL else 0.0
            db.log_request("OmniVoice", "/api/clone", "cloned_voice", len(text), processing_time, audio_duration, rtf, cpu_p, ram_p)

        headers = {
            "X-Processing-Time-Sec": str(round(processing_time, 3)),
            "X-Audio-Duration-Sec": str(round(audio_duration, 3)),
            "X-RTF": str(round(rtf, 3))
        }

        return Response(
            content=wav_bytes, 
            media_type="audio/wav",
            headers=headers
        )

@app.get("/api/metrics")
async def get_metrics():
    if 'db' in sys.modules:
        logs = db.get_recent_logs(20)
        return {"success": True, "logs": logs}
    return {"success": False, "msg": "DB module not loaded"}

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Server Metrics Dashboard</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background-color: #f4f4f9; }
            .container { max-width: 1200px; margin: auto; }
            .card { background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .charts { display: flex; gap: 20px; flex-wrap: wrap; }
            .chart-container { flex: 1; min-width: 400px; position: relative; height: 300px; }
            table { width: 100%; border-collapse: collapse; margin-top: 20px; }
            th, td { padding: 10px; border-bottom: 1px solid #ddd; text-align: left; }
            th { background-color: #f8f9fa; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Server Health & API Metrics Dashboard</h1>
            
            <div class="charts">
                <div class="card chart-container">
                    <h3>CPU & RAM Usage (%)</h3>
                    <canvas id="resourceChart"></canvas>
                </div>
                <div class="card chart-container">
                    <h3>Processing RTF (Real-Time Factor)</h3>
                    <canvas id="rtfChart"></canvas>
                </div>
            </div>

            <div class="card">
                <h3>Recent API Requests</h3>
                <table id="logsTable">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>App</th>
                            <th>Endpoint</th>
                            <th>Voice</th>
                            <th>Text Len</th>
                            <th>Time</th>
                            <th>Duration (s)</th>
                            <th>RTF</th>
                            <th>CPU %</th>
                            <th>RAM %</th>
                        </tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </div>
        </div>

        <script>
            let resourceChart = null;
            let rtfChart = null;

            async function loadMetrics() {
                const response = await fetch('/api/metrics');
                const data = await response.json();
                if(!data.success) return;
                const logs = data.logs;

                const tbody = document.querySelector('#logsTable tbody');
                tbody.innerHTML = '';
                logs.forEach(log => {
                    const tr = document.createElement('tr');
                    const d = new Date(log.timestamp * 1000);
                    tr.innerHTML = `
                        <td>${log.id}</td>
                        <td>${log.app_name}</td>
                        <td>${log.endpoint}</td>
                        <td>${log.voice_id}</td>
                        <td>${log.text_length}</td>
                        <td>${d.toLocaleTimeString()}</td>
                        <td>${log.audio_duration.toFixed(2)}</td>
                        <td>${log.rtf.toFixed(2)}</td>
                        <td>${log.cpu_percent}%</td>
                        <td>${log.ram_percent}%</td>
                    `;
                    tbody.appendChild(tr);
                });

                const chartLogs = [...logs].reverse();
                const labels = chartLogs.map(l => new Date(l.timestamp * 1000).toLocaleTimeString());
                const cpuData = chartLogs.map(l => l.cpu_percent);
                const ramData = chartLogs.map(l => l.ram_percent);
                const rtfData = chartLogs.map(l => l.rtf);

                if(resourceChart) resourceChart.destroy();
                resourceChart = new Chart(document.getElementById('resourceChart'), {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [
                            { label: 'CPU %', data: cpuData, borderColor: 'red', fill: false },
                            { label: 'RAM %', data: ramData, borderColor: 'blue', fill: false }
                        ]
                    },
                    options: { maintainAspectRatio: false }
                });

                if(rtfChart) rtfChart.destroy();
                rtfChart = new Chart(document.getElementById('rtfChart'), {
                    type: 'bar',
                    data: {
                        labels: labels,
                        datasets: [{ label: 'RTF', data: rtfData, backgroundColor: 'green' }]
                    },
                    options: { maintainAspectRatio: false }
                });
            }

            window.onload = loadMetrics;
            setInterval(loadMetrics, 5000);
        </script>
    </body>
    </html>
    """
    return html_content
