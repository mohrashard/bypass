import os, sys, json, subprocess, shutil
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageChops

def process_with_ai_stack(input_wav_path: str, output_wav_path: str) -> None:
    import numpy as np
    import soundfile as sf
    from pedalboard import Pedalboard, NoiseGate, HighpassFilter, Compressor, Limiter, Gain
    from df.enhance import enhance, init_df, load_audio
    print("[⚙️] Initializing DeepFilterNet3...")
    model, df_state, _ = init_df(post_filter=False)

    print("[⚙️] Loading audio at 48kHz full-band...")
    audio_df, sr_df = load_audio(input_wav_path, sr=df_state.sr())

    print("[⚙️] Running Studio Grade AI deep filtering...")
    enhanced_tensor = enhance(model, df_state, audio_df)

    enhanced_np = enhanced_tensor.cpu().numpy()
    orig_np = audio_df.cpu().numpy()

    # THE ROBO-VOICE FIX: 85% AI, 15% Original Room Tone
    WET = 0.85
    audio_np = (WET * enhanced_np) + ((1.0 - WET) * orig_np)

    # Pre-normalize for the compressor
    peak_vol = np.max(np.abs(audio_np))
    if peak_vol > 0:
        audio_np = audio_np / peak_vol * 0.8  

    sr_orig = df_state.sr()

    print("[⚙️] Building pro signal chain (Pedalboard)...")
    board = Pedalboard([
        NoiseGate(threshold_db=-55.0, ratio=10.0, attack_ms=2.0, release_ms=250.0),
        HighpassFilter(cutoff_frequency_hz=80.0),
        Compressor(threshold_db=-18.0, ratio=3.5, attack_ms=8.0, release_ms=120.0),
        Gain(gain_db=4.0),
        Limiter(threshold_db=-1.0, release_ms=50.0),
    ])

    print("[⚙️] Processing through pro signal chain...")
    processed = board(audio_np, sr_orig)

    print("[⚙️] Applying voice EQ and -14 LUFS Broadcast Normalization...")
    tmp_pre_eq = input_wav_path.replace(".wav", "_pre_eq.wav")
    sf.write(tmp_pre_eq, processed.T, sr_orig, subtype='PCM_16')

    eq_filter = (
        "equalizer=f=200:t=h:w=200:g=-2,"
        "equalizer=f=3500:t=h:w=1000:g=3,"
        "equalizer=f=8000:t=h:w=2000:g=2"
    )

    subprocess.run([
        "ffmpeg", "-i", tmp_pre_eq,
        "-af", f"{eq_filter},loudnorm=I=-14:TP=-1:LRA=11",
        output_wav_path, "-y"
    ], check=True, capture_output=True)

    if os.path.exists(tmp_pre_eq):
        os.remove(tmp_pre_eq)

    print("[✅] Done — broadcast-quality voice audio.")

# ─────────────────────────────────────────────
# 2. THE SILENCE CHOPPER
# ─────────────────────────────────────────────

def stage_remove_silence(video_path: str) -> str:
    from pydub import AudioSegment
    from pydub.silence import detect_nonsilent

    print("[⚙️] Extracting audio for silence detection...")
    base_dir = os.path.dirname(os.path.abspath(video_path))
    temp_wav = os.path.join(base_dir, "_silence_detect.wav")
    output_vid = os.path.splitext(video_path)[0] + "_chopped.mp4"
    list_file = os.path.join(base_dir, "_concat_list.txt")

    subprocess.run(
        ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", temp_wav, "-y"],
        check=True, capture_output=True
    )

    print("[⚙️] Analyzing waveforms...")
    audio = AudioSegment.from_wav(temp_wav)
    
    # Detect the parts where people are ACTUALLY talking
    nonsilent_chunks = detect_nonsilent(audio, min_silence_len=400, silence_thresh=-42)
    
    print(f"[🎬] Found {len(nonsilent_chunks)} active video segments. Slicing...")

    # Write the FFmpeg concat demuxer file
    with open(list_file, "w", encoding="utf-8") as f:
        for start_ms, end_ms in nonsilent_chunks:
            # Add a tiny 100ms padding so words don't get abruptly cut off
            start_sec = max(0, (start_ms - 100) / 1000.0)
            end_sec = (end_ms + 100) / 1000.0
            
            # Format the absolute path cleanly for FFmpeg on Windows
            safe_path = video_path.replace('\\', '/')
            f.write(f"file '{safe_path}'\n")
            f.write(f"inpoint {start_sec:.3f}\n")
            f.write(f"outpoint {end_sec:.3f}\n")

    print("[⚙️] Re-compiling video (Fast Render)...")
    # We use a fast h264 preset here to ensure exact frame-accurate cuts
    subprocess.run([
        "ffmpeg", "-f", "concat", "-safe", "0", "-i", list_file,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", 
        "-c:a", "aac", "-b:a", "192k", 
        output_vid, "-y"
    ], check=True, capture_output=True)

    for f in [temp_wav, list_file]:
        if os.path.exists(f): os.remove(f)

    print(f"[✅] Dead air eliminated: {output_vid}")
    return output_vid

# ─────────────────────────────────────────────
# 3. PIPELINE ORCHESTRATION
# ─────────────────────────────────────────────

def extract_audio(video_path: str, out_path: str) -> None:
    subprocess.run(["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "48000", "-ac", "1", out_path, "-y"], check=True, capture_output=True)

def mux_audio(video_path: str, audio_path: str, output_path: str) -> None:
    subprocess.run(["ffmpeg", "-i", video_path, "-i", audio_path, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-map", "0:v:0", "-map", "1:a:0", "-shortest", output_path, "-y"], check=True, capture_output=True)

def stage_studio_audio(video_path: str) -> str:
    base_dir = os.path.dirname(os.path.abspath(video_path))
    temp_raw = os.path.join(base_dir, "_tmp_raw.wav")
    temp_ai  = os.path.join(base_dir, "_tmp_ai.wav")
    output   = os.path.splitext(video_path)[0] + "_studio.mp4"

    try:
        print("[⚙️] Extracting audio...")
        extract_audio(video_path, temp_raw)
        process_with_ai_stack(temp_raw, temp_ai)
        print("[⚙️] Muxing enhanced audio back to video...")
        mux_audio(video_path, temp_ai, output)
        print(f"[✅] Saved: {output}")
        return output
    finally:
        for f in (temp_raw, temp_ai):
            if os.path.exists(f): os.remove(f)

# ─────────────────────────────────────────────
# 4. PRO MAX CINEMATIC COLOR ENGINE
# ─────────────────────────────────────────────

