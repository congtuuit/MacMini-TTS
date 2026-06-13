import requests
import numpy as np
import wave

def get_mean_from_url(voice_name, filename):
    url = "http://localhost:8000/api/tts"
    payload = {"text": "Xin chào Việt Nam", "voice": voice_name}
    r = requests.post(url, json=payload)
    with open(filename, "wb") as f:
        f.write(r.content)
    
    with wave.open(filename, "r") as w:
        frames = w.readframes(w.getnframes())
        arr = np.frombuffer(frames, dtype=np.int16)
        return np.mean(np.abs(arr))

m1 = get_mean_from_url("Ngọc Lan", "out_lan_api.wav")
m2 = get_mean_from_url("Gia Bảo", "out_bao_api.wav")

print(f"Ngọc Lan API mean: {m1}")
print(f"Gia Bảo API mean: {m2}")
