from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
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

        if 'db' in sys.modules:
            cpu_p = psutil.cpu_percent() if HAS_PSUTIL else 0.0
            ram_p = psutil.virtual_memory().percent if HAS_PSUTIL else 0.0
            db.log_request("OmniVoice", "/api/clone", "cloned_voice", len(text), processing_time, audio_duration, rtf, cpu_p, ram_p)

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
