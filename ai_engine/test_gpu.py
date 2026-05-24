import os
import sys

try:
    import importlib.util
    import ctypes
    if os.name == 'nt':
        cublas_spec = importlib.util.find_spec("nvidia.cublas")
        if cublas_spec and cublas_spec.submodule_search_locations:
            cublas_path = os.path.join(cublas_spec.submodule_search_locations[0], "bin")
            if os.path.exists(cublas_path):
                os.add_dll_directory(cublas_path)
                try:
                    ctypes.CDLL(os.path.join(cublas_path, "cublas64_12.dll"))
                    ctypes.CDLL(os.path.join(cublas_path, "cublasLt64_12.dll"))
                except Exception as e:
                    print("DLL load error cublas:", e)
        
        cudnn_spec = importlib.util.find_spec("nvidia.cudnn")
        if cudnn_spec and cudnn_spec.submodule_search_locations:
            cudnn_path = os.path.join(cudnn_spec.submodule_search_locations[0], "bin")
            if os.path.exists(cudnn_path):
                os.add_dll_directory(cudnn_path)
                try:
                    ctypes.CDLL(os.path.join(cudnn_path, "cudnn64_9.dll"))
                except Exception as e:
                    print("DLL load error cudnn:", e)

    from faster_whisper import WhisperModel
    print("Loading model on GPU...")
    model = WhisperModel("large-v3", device="cuda", compute_type="float16")
    print("Model loaded successfully. GPU is working!")
    
    print("Testing transcription to trigger lazy loaded DLLs...")
    import numpy as np
    dummy_audio = np.zeros((16000,), dtype=np.float32)
    segments, info = model.transcribe(dummy_audio, language="si", beam_size=5, vad_filter=False, word_timestamps=True)
    for seg in segments:
        for w in seg.words:
            pass # Just iterate to force the generator to run
    print("Transcription successful!")
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"FAILED: {e}")
