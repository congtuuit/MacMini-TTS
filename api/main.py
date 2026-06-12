from fastapi import FastAPI
from pydantic import BaseModel
from vieneu import Vieneu
import uuid
import os

app = FastAPI()

tts = Vieneu(
    backbone_device="mps"
)

os.makedirs("output", exist_ok=True)

class TTSRequest(BaseModel):
    text: str
    voice: str | None = None

@app.get("/api/voices")
async def get_voices():
    # list_preset_voices() trả về list of tuples (label, voice_id)
    voices = tts.list_preset_voices()
    return {
        "success": True,
        "voices": [{"label": v[0], "id": v[1]} for v in voices]
    }

@app.post("/api/tts")
async def generate(req: TTSRequest):

    filename = f"output/{uuid.uuid4()}.wav"

    audio = tts.infer(text=req.text, voice=req.voice)

    tts.save(audio, filename)

    return {
        "success": True,
        "file": filename
    }
