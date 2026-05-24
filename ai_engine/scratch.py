import os

target = r"c:\Projects\capcut-bypass\ai_engine\pipeline.py"
with open(target, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Windows Fix
content = content.replace(
"""# ─── Windows Fix ─────────────────────────────
if os.name == 'nt':
    pathlib.PosixPath = pathlib.WindowsPath""",
"""# ─── Windows Fix ─────────────────────────────
if os.name == 'nt':
    pathlib.PosixPath = pathlib.WindowsPath
    import importlib.util
    for pkg in ["nvidia.cublas", "nvidia.cudnn"]:
        spec = importlib.util.find_spec(pkg)
        if spec and spec.submodule_search_locations:
            bin_path = os.path.join(spec.submodule_search_locations[0], "bin")
            if os.path.exists(bin_path):
                os.environ["PATH"] = bin_path + os.pathsep + os.environ.get("PATH", "")"""
)

# 2. stage_burn_captions (Import + Loading)
content = content.replace(
"""    import whisper
    import json, shutil, subprocess, os
    from playwright.sync_api import sync_playwright

    print("[⚙️] Loading Whisper model...")
    model = whisper.load_model("large")""",
"""    import json, shutil, subprocess, os
    from playwright.sync_api import sync_playwright

    print("[⚙️] Loading Whisper large-v3 (GPU-accelerated)...")
    try:
        from faster_whisper import WhisperModel
        w_model = WhisperModel("large-v3", device="cuda", compute_type="float16")
    except Exception:
        w_model = WhisperModel("large-v3", device="cpu", compute_type="int8")"""
)

# 3. stage_burn_captions (Transcription)
content = content.replace(
"""    print("[⚙️] Transcribing with Whisper...")
    result = model.transcribe(temp_audio, word_timestamps=True, verbose=False)

    word_events = []
    for seg in result.get("segments", []):
        for w in seg.get("words", []):
            word_events.append({
                "word":  w["word"].strip(),
                "start": w["start"],
                "end":   w["end"]
            })""",
"""    print("[⚙️] Transcribing with Whisper large-v3...")
    w_segments_raw, _ = w_model.transcribe(
        temp_audio,
        word_timestamps=True,
        vad_filter=True,
        condition_on_previous_text=False
    )
    
    word_events = []
    for seg in list(w_segments_raw):
        for w in (seg.words or []):
            if w.word.strip():
                word_events.append({
                    "word":  w.word.strip(),
                    "start": w.start,
                    "end":   w.end
                })"""
)

# 4. stage_semantic_zoom (Import)
content = content.replace(
"""    import whisper
    import subprocess, os, json""",
"""    import subprocess, os, json"""
)

# 5. stage_semantic_zoom (Transcription)
content = content.replace(
"""    # Use the 'base' model for lightning-fast keyword spotting
    model = whisper.load_model("base")
    result = model.transcribe(temp_audio, word_timestamps=True, verbose=False)""",
"""    # Use the 'base' model for lightning-fast keyword spotting
    try:
        from faster_whisper import WhisperModel
        w_model = WhisperModel("base", device="cuda", compute_type="float16")
    except Exception:
        w_model = WhisperModel("base", device="cpu", compute_type="int8")
        
    w_segments_raw, _ = w_model.transcribe(
        temp_audio,
        word_timestamps=True,
        vad_filter=True,
        condition_on_previous_text=False
    )"""
)

# 6. stage_semantic_zoom (Word extraction)
content = content.replace(
"""    # 3. Find exactly when these words are spoken
    for seg in result.get("segments", []):
        for w in seg.get("words", []):
            clean_word = w["word"].strip().lower()
            clean_word = ''.join(e for e in clean_word if e.isalnum())""",
"""    # 3. Find exactly when these words are spoken
    for seg in list(w_segments_raw):
        for w in (seg.words or []):
            clean_word = w.word.strip().lower()
            clean_word = ''.join(e for e in clean_word if e.isalnum())"""
)

# 7. export_captions_overlay_en (Import)
content = content.replace(
"""    import whisper, shutil
    from playwright.sync_api import sync_playwright""",
"""    import shutil
    from playwright.sync_api import sync_playwright"""
)

# 8. export_captions_overlay_en (Transcription)
content = content.replace(
"""    print("[⚙️] [OVERLAY EXPORT] Transcribing with Whisper...")
    model = whisper.load_model("large")
    result = model.transcribe(temp_audio, word_timestamps=True, verbose=False)
    word_events = []
    for seg in result.get("segments", []):
        for w in seg.get("words", []):
            word_events.append({"word": w["word"].strip(), "start": w["start"], "end": w["end"]})""",
"""    print("[⚙️] Loading Whisper large-v3 (GPU-accelerated)...")
    try:
        from faster_whisper import WhisperModel
        w_model = WhisperModel("large-v3", device="cuda", compute_type="float16")
    except Exception:
        w_model = WhisperModel("large-v3", device="cpu", compute_type="int8")
        
    print("[⚙️] [OVERLAY EXPORT] Transcribing with Whisper large-v3...")
    w_segments_raw, _ = w_model.transcribe(
        temp_audio,
        word_timestamps=True,
        vad_filter=True,
        condition_on_previous_text=False
    )
    
    word_events = []
    for seg in list(w_segments_raw):
        for w in (seg.words or []):
            if w.word.strip():
                word_events.append({"word": w.word.strip(), "start": w.start, "end": w.end})"""
)

# 9. stage_burn_sinhala_captions (Remove redundant importlib fix)
content = content.replace(
"""    print("[⚙️] Running Whisper (base) for frame-accurate timestamps...")
    try:
        from faster_whisper import WhisperModel
        import importlib.util
        if os.name == 'nt':
            for pkg in ["nvidia.cublas", "nvidia.cudnn"]:
                spec = importlib.util.find_spec(pkg)
                if spec and spec.submodule_search_locations:
                    bin_path = os.path.join(spec.submodule_search_locations[0], "bin")
                    if os.path.exists(bin_path):
                        os.environ["PATH"] = bin_path + os.pathsep + os.environ.get("PATH", "")
        try:
            w_model = WhisperModel("base", device="cuda", compute_type="int8")""",
"""    print("[⚙️] Running Whisper (base) for frame-accurate timestamps...")
    try:
        from faster_whisper import WhisperModel
        try:
            w_model = WhisperModel("base", device="cuda", compute_type="int8")"""
)

with open(target, "w", encoding="utf-8") as f:
    f.write(content)

print("Done replacing.")
