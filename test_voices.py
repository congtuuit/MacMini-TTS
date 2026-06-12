import wave
import numpy as np
from vieneu import Vieneu
tts = Vieneu()

wav1 = tts.infer("Xin chào Việt Nam", voice="Ngọc Lan")
wav2 = tts.infer("Xin chào Việt Nam", voice="Gia Bảo")
wav3 = tts.infer("Xin chào Việt Nam", voice="Thái Sơn")

def get_mean(wav):
    return np.mean(np.abs(wav))

print(f"Ngọc Lan mean: {get_mean(wav1)}")
print(f"Gia Bảo mean: {get_mean(wav2)}")
print(f"Thái Sơn mean: {get_mean(wav3)}")

if np.allclose(wav1, wav2) and np.allclose(wav1, wav3):
    print("ALL VOICES PRODUCED IDENTICAL AUDIO!")
else:
    print("Voices produced different audio.")
