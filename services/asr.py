"""
services/asr.py — Local Automatic Speech Recognition using faster-whisper.
"""

import io
import os
from faster_whisper import WhisperModel
from config import ASR_MODEL_ID

# --- Point Windows to PyTorch's bundled CUDA libraries ---
try:
    import torch
    torch_lib_path = os.path.join(os.path.dirname(torch.__file__), "lib")
    os.add_dll_directory(torch_lib_path)  # Python 3.8+ DLL loading
    os.environ["PATH"] = torch_lib_path + os.pathsep + os.environ.get("PATH", "")
except ImportError:
    print("[ASR] PyTorch not found. cuBLAS DLLs may not be loaded.")
# --------------------------------------------------------------

print(f"[ASR] Loading faster-whisper model '{ASR_MODEL_ID}' on GPU...")
model = WhisperModel(ASR_MODEL_ID, device="cuda", compute_type="default")
print("[ASR] Model loaded successfully on GPU.")

def transcribe_audio(audio_bytes: bytes) -> str:
    """
    Transcribe raw audio bytes using the local faster-whisper model.
    """
    global model
    audio_file = io.BytesIO(audio_bytes)
    
    # Force the model to output English
    segments, info = model.transcribe(audio_file, beam_size=5, language="en")
    
    # segments is a generator, so we must consume it to get the text
    text = " ".join([segment.text for segment in segments])
    return text.strip()
