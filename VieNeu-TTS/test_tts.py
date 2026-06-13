from vieneu import Vieneu

tts = Vieneu(
    backbone_device="mps"
)

audio = tts.infer(
    text="Xin chào, đây là hệ thống VieNeu TTS trên Mac Mini M4."
)

tts.save(audio, "output.wav")
