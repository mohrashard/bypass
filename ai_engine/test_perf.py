import os
import sys
import time

import importlib.util
if os.name == 'nt':
    cublas_spec = importlib.util.find_spec("nvidia.cublas")
    if cublas_spec and cublas_spec.submodule_search_locations:
        cublas_path = os.path.join(cublas_spec.submodule_search_locations[0], "bin")
        if os.path.exists(cublas_path):
            os.environ["PATH"] = cublas_path + os.pathsep + os.environ["PATH"]
            
    cudnn_spec = importlib.util.find_spec("nvidia.cudnn")
    if cudnn_spec and cudnn_spec.submodule_search_locations:
        cudnn_path = os.path.join(cudnn_spec.submodule_search_locations[0], "bin")
        if os.path.exists(cudnn_path):
            os.environ["PATH"] = cudnn_path + os.pathsep + os.environ["PATH"]

try:
    from faster_whisper import WhisperModel
    import numpy as np
    
    print("Loading large-v3 model...")
    t0 = time.time()
    model = WhisperModel("large-v3", device="cuda", compute_type="int8")
    print(f"Model loaded in {time.time()-t0:.2f}s")
    
    print("Preparing dummy audio...")
    dummy_audio = np.zeros((16000,), dtype=np.float32)
    
    print("Running inference WITHOUT VAD...")
    t0 = time.time()
    segments, info = model.transcribe(dummy_audio, language="si", beam_size=5, vad_filter=False, word_timestamps=True)
    for seg in segments:
        for w in seg.words: pass
    print(f"Inference NO-VAD done in {time.time()-t0:.2f}s")
    
    print("Running inference WITH VAD...")
    t0 = time.time()
    segments, info = model.transcribe(dummy_audio, language="si", beam_size=5, vad_filter=True, word_timestamps=True)
    for seg in segments:
        for w in seg.words: pass
    print(f"Inference VAD done in {time.time()-t0:.2f}s")

except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"FAILED: {e}")
