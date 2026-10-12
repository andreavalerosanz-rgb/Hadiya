#!/usr/bin/env python3
"""Voice note -> text on stdout, on CPU. Run by server.py in a throwaway process so the model's RAM is freed afterwards.
Needs: python3 -m venv data/whisper-venv && data/whisper-venv/bin/pip install faster-whisper   (the 'small' model downloads on first use)"""
import sys
from faster_whisper import WhisperModel

model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=4)
segments, _ = model.transcribe(sys.argv[1], beam_size=1, vad_filter=True)  # language is detected (es/en/ca)
print(" ".join(s.text.strip() for s in segments))
