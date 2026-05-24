import sys
import json
import os
import subprocess
import io
import warnings
import pathlib
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageChops

# ─── Windows Fix ─────────────────────────────
if os.name == 'nt':
    pathlib.PosixPath = pathlib.WindowsPath
    import importlib.util
    for pkg in ["nvidia.cublas", "nvidia.cudnn"]:
        spec = importlib.util.find_spec(pkg)
        if spec and spec.submodule_search_locations:
            bin_path = os.path.join(spec.submodule_search_locations[0], "bin")
            if os.path.exists(bin_path):
                os.environ["PATH"] = bin_path + os.pathsep + os.environ.get("PATH", "")

warnings.filterwarnings("ignore")
os.environ["PYTHONWARNINGS"] = "ignore"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
os.environ["GLOG_minloglevel"] = "3"

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)


# ─────────────────────────────────────────────
# 1. STUDIO AUDIO ENGINE
# ─────────────────────────────────────────────

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

def stage_cinematic_color(video_path: str, color_options: dict) -> str:
    print("[⚙️] Applying Algorithmic Color Grade...")
    base_dir = os.path.dirname(os.path.abspath(video_path))
    output_vid = os.path.splitext(video_path)[0] + "_graded.mp4"

    # Extract grade style from frontend (Default to Apple HDR)
    grade_style = color_options.get("colorGradeStyle", "pro-max")

    if grade_style == "neon-blue":
        # 🟦 NEON BLUE STUDIO (Matches the uploaded blue background)
        # 1. colorbalance: Pushes heavy blue/cyan into shadows (bs=0.25) and midtones (bm=0.10).
        # 2. eq: Drops gamma to 0.86 to match the dark room, pushes contrast to keep it punchy.
        print("      ↳ Mode: Neon Blue Studio (Ambient Bounce Simulation)")
        filter_chain = "colorbalance=rs=-0.15:gs=-0.05:bs=0.25:rm=-0.05:bm=0.10,eq=contrast=1.12:saturation=1.10:gamma=0.86,unsharp=5:5:0.8:3:3:0.0"
        
    elif grade_style == "cyber-warm":
        # 🟧 HOLLYWOOD TEAL & ORANGE
        # Pushes warm orange into highlights, cool teal into shadows.
        print("      ↳ Mode: Hollywood Teal & Orange")
        filter_chain = "colorbalance=rs=0.15:bs=-0.15:rm=0.10:bm=-0.10:rh=0.05:bh=-0.05,eq=contrast=1.10:saturation=1.20:gamma=0.90,unsharp=5:5:0.8:3:3:0.0"
        
    else:
        # 📱 PRO MAX DEFAULT (Standard Natural Enhancement)
        print("      ↳ Mode: iPhone Pro Max (Smart HDR)")
        filter_chain = "eq=contrast=1.08:saturation=1.15:gamma=0.90,unsharp=5:5:0.8:3:3:0.0"

    try:
        subprocess.run([
            "ffmpeg", "-i", video_path,
            "-vf", filter_chain,
            "-c:v", "libx264", "-preset", "fast", "-crf", "16",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            output_vid, "-y"
        ], check=True, capture_output=True)
        
        print(f"[✅] Cinematic aesthetic baked in: {output_vid}")
        return output_vid
        
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        print(f"[❌] Color grading failed: {err_msg}")
        return video_path


# ─────────────────────────────────────────────
# 5. WHISPER CAPTION ENGINE (Glass Silver Montserrat)
# ─────────────────────────────────────────────

def stage_burn_captions(video_path: str, cap_options: dict) -> str:
    import json, shutil, subprocess, os
    from playwright.sync_api import sync_playwright

    print("[⚙️] Loading Whisper large-v3 (GPU-accelerated)...")
    try:
        from faster_whisper import WhisperModel
        w_model = WhisperModel("large-v3", device="cuda", compute_type="float16")
    except Exception:
        w_model = WhisperModel("large-v3", device="cpu", compute_type="int8")

    base_dir   = os.path.dirname(os.path.abspath(video_path))
    output_vid = os.path.splitext(video_path)[0] + "_captioned.mp4"
    ovr_dir    = os.path.join(base_dir, "_cap_overlays")
    os.makedirs(ovr_dir, exist_ok=True)

    # Extract template options from frontend
    font_family = cap_options.get("captionFont", "Montserrat")
    p_class = cap_options.get("captionPrimaryStyle", "p-glass-silver")
    s_class = cap_options.get("captionSecondaryStyle", "s-hormozi-yellow")

    # ── Whisper transcription ──────────────────────────────────
    temp_audio = os.path.join(base_dir, "_whisper_audio.wav")
    subprocess.run(
        ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
         "-ar", "16000", "-ac", "1", temp_audio, "-y"],
        check=True, capture_output=True
    )
    print("[⚙️] Transcribing with Whisper large-v3...")
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
                })

    # ── Video dimensions ───────────────────────────────────────
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate",
         "-of", "json", video_path],
        capture_output=True, text=True
    )
    info  = json.loads(probe.stdout)["streams"][0]
    W, H  = int(info["width"]), int(info["height"])

    # ── HARDCODED PREMIUM TEMPLATES ────────────────────────────
    def make_base_html(width: int, height: int) -> str:
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Anton&family=Bangers&family=Montserrat:wght@800;900&family=Oswald:wght@700&family=Poppins:wght@800;900&display=swap');
  
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{
    width: {width}px; height: {height}px;
    background: transparent; overflow: hidden;
  }}
  .caption-wrap {{
    position: absolute; bottom: {int(height * 0.22)}px;
    left: 0; right: 0; display: flex; align-items: baseline;
    flex-wrap: wrap; justify-content: center; padding: 0 {int(width * 0.05)}px;
  }}
  
  /* Shared Base Typography */
  .base-cap {{
    font-weight: 900; letter-spacing: -1px; line-height: 1; white-space: nowrap;
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text; color: transparent;
  }}
  .highlight-align {{
    letter-spacing: -0.5px; align-self: flex-end;
  }}

  /* --- PRIMARY TEMPLATES (Base Text) --- */
  
  /* 1. Original Glass Silver */
  .p-glass-silver {{
    background-image: linear-gradient(160deg, #fff 0%, #d2e8ff 30%, #b4d7ff 55%, #ebf6ff 75%, #fff 100%);
    filter: drop-shadow(0 0 10px rgba(140,185,255,0.50)) drop-shadow(0 1px 3px rgba(60,100,200,0.35));
  }}
  /* 2. Crisp Clean White */
  .p-clean-white {{
    background-image: linear-gradient(to bottom, #ffffff 0%, #e0e0e0 100%);
    filter: drop-shadow(0 3px 6px rgba(0,0,0,0.8));
  }}
  /* 3. Heavy Stroke (Classic Meme/Impact) */
  .p-heavy-stroke {{
    background-image: linear-gradient(to bottom, #ffffff, #ffffff);
    filter: drop-shadow(2px 0 0 #000) drop-shadow(-2px 0 0 #000) 
            drop-shadow(0 2px 0 #000) drop-shadow(0 -2px 0 #000) 
            drop-shadow(0 5px 12px rgba(0,0,0,0.9));
  }}
  /* 4. Soft Pastel Yellow */
  .p-soft-yellow {{
    background-image: linear-gradient(to bottom, #FFFDE7 0%, #FFF176 100%);
    filter: drop-shadow(0 2px 4px rgba(0,0,0,0.7));
  }}
  /* 5. Neon Base White */
  .p-neon-base {{
    background-image: linear-gradient(to bottom, #ffffff 0%, #e0f7fa 100%);
    filter: drop-shadow(0 0 10px rgba(0,255,255,0.4)) drop-shadow(0 2px 2px rgba(0,0,0,0.8));
  }}

  /* --- SECONDARY TEMPLATES (Highlight Words) --- */

  /* 1. Original Electric Teal */
  .s-electric-teal {{
    background-image: linear-gradient(to right, #00dcc8 0%, #00c3d2 50%, #00aadc 100%);
    filter: drop-shadow(0 0 8px rgba(0,210,200,0.75)) drop-shadow(0 1px 3px rgba(0,150,180,0.55));
  }}
  /* 2. Hormozi Bold Yellow */
  .s-hormozi-yellow {{
    background-image: linear-gradient(to bottom, #FFE81F 0%, #FF8A00 100%);
    filter: drop-shadow(0 0 15px rgba(255,165,0,0.6)) drop-shadow(0 3px 6px rgba(0,0,0,0.9));
  }}
  /* 3. Aggressive Crimson Red */
  .s-crimson-red {{
    background-image: linear-gradient(to bottom, #ff4b4b 0%, #b30000 100%);
    filter: drop-shadow(0 0 12px rgba(255,0,0,0.6)) drop-shadow(0 3px 5px rgba(0,0,0,0.9));
  }}
  /* 4. Cyberpunk Purple/Pink */
  .s-cyber-purple {{
    background-image: linear-gradient(to right, #d500f9 0%, #651fff 100%);
    filter: drop-shadow(0 0 15px rgba(213,0,249,0.7)) drop-shadow(0 2px 4px rgba(0,0,0,0.8));
  }}
  /* 5. Luxury Metallic Gold */
  .s-luxury-gold {{
    background-image: linear-gradient(160deg, #FFF7D6 0%, #F3DA7C 30%, #D4AF37 70%, #AA7700 100%);
    filter: drop-shadow(0 0 12px rgba(212,175,55,0.5)) drop-shadow(0 2px 5px rgba(0,0,0,0.8));
  }}
</style>
</head>
<body>
  <div class="caption-wrap" id="wrap">
    <span class="base-cap" id="w1"></span>
    <span class="base-cap highlight-align" id="w2" style="display: none;"></span>
  </div>
</body>
</html>"""

    print("[⚙️] Launching headless Chrome for caption rendering...")

    segments = []
    rendered_pairs = {}
    i = 0
    while i < len(word_events):
        w1 = word_events[i]["word"]
        t_s = word_events[i]["start"]
        w1_len = len(w1)

        if w1_len >= 9 or i + 1 >= len(word_events):
            w2 = None
            t_e = word_events[i]["end"]
            i += 1
        else:
            w2 = word_events[i + 1]["word"]
            w2_len = len(w2)
            if (w1_len + w2_len) > 15:
                w2 = None
                t_e = word_events[i]["end"]
                i += 1
            else:
                t_e = word_events[i + 1]["end"]
                i += 2

        key = (w1, w2 or "")
        if key not in rendered_pairs:
            png_path = os.path.join(ovr_dir, f"cap_{len(rendered_pairs):04d}.png")
            rendered_pairs[key] = png_path

        segments.append((t_s, t_e, rendered_pairs[key], w1, w2))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1)
        page = context.new_page()

        page.set_content(make_base_html(W, H), wait_until="networkidle")

        rendered_done = set()
        for t_s, t_e, png_path, w1, w2 in segments:
            key = (w1, w2 or "")
            if key in rendered_done: continue

            w1_len = len(w1)
            combined_len = len(w1) + (len(w2) if w2 else 0)

            if w1_len <= 4: primary_size = int(H * 0.075)
            elif w1_len <= 6: primary_size = int(H * 0.065)
            elif w1_len <= 9: primary_size = int(H * 0.055)
            elif w1_len <= 12: primary_size = int(H * 0.047)
            else: primary_size = int(H * 0.038)

            secondary_size = int(primary_size * 0.52)

            if combined_len > 14:
                shrink = max(0.65, 1.0 - (combined_len - 14) * 0.018)
                primary_size = int(primary_size * shrink)
                secondary_size = int(secondary_size * shrink)

            primary_size = max(primary_size, 18)
            secondary_size = max(secondary_size, 12)
            gap_px = int(primary_size * 0.15)
            padding_bottom_px = int(primary_size * 0.05)

            # Assign classes dynamically via Javascript
            page.evaluate("""
                (args) => {
                    const w1El = document.getElementById('w1');
                    const w2El = document.getElementById('w2');
                    const wrapEl = document.getElementById('wrap');
                    
                    w1El.textContent = args.w1;
                    w1El.style.fontSize = args.primary_size + 'px';
                    w1El.style.fontFamily = `'${args.font_family}', Impact, sans-serif`;
                    w1El.className = 'base-cap ' + args.p_class;
                    
                    if (args.w2) {
                        w2El.textContent = args.w2;
                        w2El.style.display = 'inline';
                        w2El.style.fontSize = args.secondary_size + 'px';
                        w2El.style.paddingBottom = args.padding_bottom_px + 'px';
                        w2El.style.fontFamily = `'${args.font_family}', Impact, sans-serif`;
                        
                        // If user disables secondary highlight, force it to match primary
                        if (args.s_class === 'none') {
                             w2El.className = 'base-cap highlight-align ' + args.p_class;
                        } else {
                             w2El.className = 'base-cap highlight-align ' + args.s_class;
                        }
                    } else {
                        w2El.textContent = '';
                        w2El.style.display = 'none';
                    }
                    
                    wrapEl.style.gap = args.gap_px + 'px';
                }
            """, {
                "w1": w1, "w2": w2,
                "primary_size": primary_size,
                "secondary_size": secondary_size,
                "gap_px": gap_px,
                "padding_bottom_px": padding_bottom_px,
                "font_family": font_family,
                "p_class": p_class,
                "s_class": s_class
            })

            page.screenshot(path=png_path, full_page=False, omit_background=True)
            rendered_done.add(key)

        browser.close()

    # ── FFmpeg overlay — batched with Dynamic Mathematical Animations ──
    print("[⚙️] Compositing with cinematic motion math...")

    CHUNK = 50
    current_video = video_path
    
    # Extract animation preference from frontend
    anim_style = cap_options.get("captionAnimation", "spring-up")
    dur = 0.15 # 150ms base animation duration

    for chunk_start in range(0, len(segments), CHUNK):
        chunk = segments[chunk_start : chunk_start + CHUNK]
        chunk_out = os.path.join(base_dir, f"_chunk_{chunk_start:04d}.mp4")

        inputs = ["ffmpeg", "-i", current_video]
        for _, _, path, _, _ in chunk: 
            inputs += ["-i", path]

        filter_parts = []
        for idx, (t_s, t_e, _, _, _) in enumerate(chunk):
            in_lbl = f"[v{idx}]" if idx > 0 else "[0:v]"
            out_lbl = f"[v{idx+1}]"
            inp_lbl = f"[{idx+1}]"
            
            enable_expr = f"enable='between(t,{t_s:.3f},{t_e:.3f})'"
            
            # --- PREMIERE PRO TIER MATH ANIMATIONS ---
            # t_prog: normalized time from 0 to 1 over the duration
            # inv_p: inverted time (1 to 0) for ease-out calculations
            t_prog = f"(t-{t_s:.3f})/{dur}"
            inv_p = f"(1-{t_prog})"
            ease_out_cubic = f"({inv_p}*{inv_p}*{inv_p})"
            
            if anim_style == "slide-up":
                # Smooth ease-out slide up from 60px below
                y_expr = f"if(lte(t,{t_s:.3f}+{dur}), 60*{ease_out_cubic}, 0)"
                overlay_cmd = f"x=0:y='{y_expr}':{enable_expr}"
                
            elif anim_style == "slide-right":
                # Smooth ease-out slide in from 60px to the left
                x_expr = f"if(lte(t,{t_s:.3f}+{dur}), -60*{ease_out_cubic}, 0)"
                overlay_cmd = f"x='{x_expr}':y=0:{enable_expr}"
                
            elif anim_style == "spring-up":
                # Hormozi style bouncy spring (overshoots then settles using a damped cosine wave)
                spring_dur = 0.25
                sp = f"(t-{t_s:.3f})/{spring_dur}"
                y_expr = f"if(lte(t,{t_s:.3f}+{spring_dur}), 80*(1-{sp})*cos({sp}*6.5), 0)"
                overlay_cmd = f"x=0:y='{y_expr}':{enable_expr}"
                
            else:
                # Hard Cut (None)
                overlay_cmd = f"x=0:y=0:{enable_expr}"

            filter_parts.append(f"{in_lbl}{inp_lbl}overlay={overlay_cmd}{out_lbl}")

        cmd = inputs + [
            "-filter_complex", ";".join(filter_parts),
            "-map", f"[v{len(chunk)}]", "-map", "0:a:0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "17",
            "-pix_fmt", "yuv420p", "-c:a", "copy", chunk_out, "-y"
        ]
        
        subprocess.run(cmd, check=True, capture_output=True)

        if current_video != video_path and os.path.exists(current_video):
            os.remove(current_video)
        current_video = chunk_out

    if current_video != video_path: 
        os.replace(current_video, output_vid)
    else: 
        shutil.copy(video_path, output_vid)

    shutil.rmtree(ovr_dir, ignore_errors=True)
    if os.path.exists(temp_audio): 
        os.remove(temp_audio)

    print(f"[✅] Perfect CSS captions burned with '{anim_style}' animation: {output_vid}")
    return output_vid

def get_perfect_sinhala_transcript(audio_path: str, api_key_opt: str = None) -> list:
    import google.generativeai as genai
    import time
    import json
    import os

    # Grab this from Google AI Studio (it's free)
    api_key = api_key_opt or "AIzaSyAeo8khvjWySFpQp4tVsMQnRLkB1bsFLz0"
    if not api_key or api_key == "YOUR_FREE_API_KEY":
        print("[⚠️] GEMINI_API_KEY not found in environment. Proceeding without forced alignment.")
        return []
    
    genai.configure(api_key=api_key)
    print("[⚙️] Uploading audio to Gemini API...")
    
    try:
        # 1. Upload the extracted .wav file to Gemini
        audio_file = genai.upload_file(path=audio_path)
        
        # 2. Wait for processing (required for audio)
        while audio_file.state.name == "PROCESSING":
            print(".", end="", flush=True)
            time.sleep(2)
            audio_file = genai.get_file(audio_file.name)
        print("\n[✅] Audio processed by Gemini.")

        # 3. Use Gemini Flash Latest (Universal free tier fallback)
        model = genai.GenerativeModel('gemini-flash-latest')

        # 4. The strict prompt to prevent hallucination and force formatting
        prompt = """
        Listen to this audio. It is a mix of Sinhala and English (Singlish).
        Write down EXACTLY what is said, verbatim.
        
        CRITICAL RULES: 
        1. DO NOT add words. DO NOT guess words. DO NOT fix broken sentences. If the audio mumbles, transcribe the mumble. Strictly stick to the voice.
        2. Break the text into short, logical phrases of exactly 3 to 5 words each.
        3. TRANSLITERATE ENGLISH: If an English technical word is spoken, type it in English letters (e.g., "AC", "pipe"). 
        4. NUMBER FORMATTING: Convert all spoken Sinhala or English numbers into actual digits (e.g., "රුපියල් පන්දහක්" must become "රුපියල් 5000").
        5. SLANG CORRECTION: Fix casual Singlish slang ONLY IF it matches the audio timing (e.g., if "engineer කෙනෙක්" keep it as "engineer කෙනෙක්", keep "direct වැඩගන්න"  "direct වැඩගන්න").
        
        You must provide the approximate start and end times for each phrase in seconds.
        Output strictly as a JSON array. Example:
        [
          {"phrase": "ඔයාගෙත් leak වෙනවද", "start": 0.1, "end": 1.2},
          {"phrase": "රුපියල් 5000 ක් නිකන්ම", "start": 1.3, "end": 2.5}
        ]
        Do not include any markdown formatting. Just the raw JSON array.
        """

        print("[⚙️] Generating 99% accurate transcript...")
        response = model.generate_content([prompt, audio_file])
        
        # Clean up the file from Google's servers
        genai.delete_file(audio_file.name)
        
        # Strip potential markdown formatting just in case
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        word_list = json.loads(clean_text)
        print(f"[✅] Successfully extracted {len(word_list)} phrases from Gemini.")
        
        # --- NEW: PRINT EXACT GEMINI OUTPUT TO TERMINAL ---
        preview_text = " ".join([w.get("phrase", w.get("word", "")) for w in word_list])
        print("\n" + "="*50)
        print("[🔍] RAW GEMINI TEXT DUMP:")
        print(preview_text)
        print("="*50 + "\n")
        # --------------------------------------------------

        return word_list
    except Exception as e:
        print(f"[❌] Gemini API Error: {e}")
        return []

def align_phrases_to_whisper(gemini_phrases: list, whisper_words: list) -> list:
    """
    Time-window alignment — does NOT count words at all.

    Strategy:
      1. Gemini gives us a rough time window per phrase (e.g. 1.0s–2.5s).
         These timestamps drift but the *order* is reliable.
      2. Whisper gives us accurate per-word timestamps but wrong Sinhala text.
      3. For each Gemini phrase we:
           a) Find the Whisper word whose start time is closest to Gemini's
              start — that becomes our actual_start.
           b) The actual_end is taken from the Whisper word that sits just
              before the *next* phrase's start (i.e. we use the gap between
              phrases as the natural cut point).
      4. A small minimum display duration (MIN_DUR) prevents flicker on
         very short phrases.
    """
    MIN_DUR = 0.40  # seconds — captions show for at least this long

    if not whisper_words:
        return [{"phrase": p.get("phrase",""), "start": p["start"], "end": p["end"]}
                for p in gemini_phrases if p.get("phrase","").strip()]

    # Build a flat list of all Whisper start times for fast binary search
    whisper_starts = [w["start"] for w in whisper_words]

    def nearest_whisper_idx(t: float) -> int:
        """Return index of the Whisper word whose start is closest to t."""
        import bisect
        pos = bisect.bisect_left(whisper_starts, t)
        if pos == 0:
            return 0
        if pos >= len(whisper_starts):
            return len(whisper_starts) - 1
        # Pick whichever neighbour is closer
        before = pos - 1
        if abs(whisper_starts[before] - t) <= abs(whisper_starts[pos] - t):
            return before
        return pos

    aligned = []
    phrases = [p for p in gemini_phrases if p.get("phrase","").strip()]

    for i, item in enumerate(phrases):
        phrase = item["phrase"].strip()
        g_start = float(item.get("start", 0))
        g_end   = float(item.get("end",   g_start + 1.0))

        # ── actual_start: nearest Whisper word to Gemini's start ──────
        snap_idx = nearest_whisper_idx(g_start)
        actual_start = whisper_words[snap_idx]["start"]

        # ── actual_end: use the Whisper word just before next phrase ──
        # Look at where the NEXT Gemini phrase starts and find the last
        # Whisper word that ends before that point. This fills the full
        # duration of the phrase without over-running into the next one.
        if i + 1 < len(phrases):
            next_g_start = float(phrases[i + 1].get("start", g_end))
            # Find the last Whisper word that starts before next_g_start
            next_snap_idx = nearest_whisper_idx(next_g_start)
            # Step back one word so we don't bleed into the next phrase
            end_word_idx = max(snap_idx, next_snap_idx - 1)
            actual_end = whisper_words[end_word_idx]["end"]
        else:
            # Last phrase — use Gemini's end time (nothing after it)
            # but also clamp against the last Whisper word
            actual_end = max(g_end, whisper_words[-1]["end"])

        # ── enforce minimum display duration ──────────────────────────
        if actual_end - actual_start < MIN_DUR:
            actual_end = actual_start + MIN_DUR

        # ── sanity: never go backwards ────────────────────────────────
        if aligned and actual_start < aligned[-1]["end"]:
            actual_start = aligned[-1]["end"]
            if actual_end - actual_start < MIN_DUR:
                actual_end = actual_start + MIN_DUR

        aligned.append({"phrase": phrase, "start": actual_start, "end": actual_end})

        print(f"    [{i+1:02d}] {phrase[:35]:<35}  "
              f"gemini={g_start:.2f}-{g_end:.2f}s  →  "
              f"snapped={actual_start:.2f}-{actual_end:.2f}s")

    return aligned


def stage_burn_sinhala_captions(video_path: str, cap_options: dict) -> str:
    import json, shutil, subprocess, os
    from playwright.sync_api import sync_playwright

    base_dir   = os.path.dirname(os.path.abspath(video_path))
    output_vid = os.path.splitext(video_path)[0] + "_si_captioned.mp4"
    ovr_dir    = os.path.join(base_dir, "_cap_overlays_si")
    os.makedirs(ovr_dir, exist_ok=True)

    p_class = cap_options.get("captionPrimaryStyle", "p-glass-silver")
    
    # 1. Extract Audio
    temp_audio = os.path.join(base_dir, "_gemini_audio.wav")
    subprocess.run(["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", temp_audio, "-y"], check=True, capture_output=True)
    
    # 2. Get Perfect Phrases + Rough Timestamps from Gemini
    gemini_phrases = get_perfect_sinhala_transcript(temp_audio, cap_options.get("geminiApiKey"))
    
    if not gemini_phrases:
        print("[❌] FATAL: Gemini failed. Cannot render captions.")
        if os.path.exists(temp_audio): os.remove(temp_audio)
        return video_path

    print(f"[⚙️] Extracted {len(gemini_phrases)} Singlish phrases from Gemini.")

    # ── STEP 2: Whisper for accurate word-level timestamps ────────────
    print("[⚙️] Running Whisper (base) for frame-accurate timestamps...")
    try:
        from faster_whisper import WhisperModel
        try:
            w_model = WhisperModel("base", device="cuda", compute_type="int8")
        except Exception:
            w_model = WhisperModel("base", device="cpu", compute_type="int8")

        # NO language= param — language-agnostic mode gives far more reliable
        # word-boundary timestamps on Sinhala/mixed audio. We only use the
        # timestamps; the text content is irrelevant and thrown away.
        w_segments_raw, _ = w_model.transcribe(
            temp_audio,
            word_timestamps=True,
            vad_filter=True,              # trims silence → tighter boundaries
            condition_on_previous_text=False
        )
        # faster-whisper returns a generator — consume it once into a list
        w_segments_list = list(w_segments_raw)
        whisper_words = []
        for seg in w_segments_list:
            for w in (seg.words or []):
                if w.word.strip():
                    whisper_words.append({"word": w.word.strip(), "start": w.start, "end": w.end})

        # If word-level timestamps are too sparse (common on non-Latin audio),
        # fall back to segment-level boundaries which are always rock-solid
        if len(whisper_words) < len(gemini_phrases):
            print(f"[⚠️] Only {len(whisper_words)} word anchors for {len(gemini_phrases)} phrases — using segment boundaries.")
            whisper_words = [{"word": "[seg]", "start": seg.start, "end": seg.end}
                             for seg in w_segments_list]

        print(f"[⚙️] Whisper found {len(whisper_words)} timestamp anchors.")
    except Exception as e:
        print(f"[⚠️] Whisper timing failed ({e}). Falling back to Gemini timestamps.")
        whisper_words = []

    # ── STEP 3: Snap Gemini phrases onto Whisper timing ──────────────
    if whisper_words:
        segments_data = align_phrases_to_whisper(gemini_phrases, whisper_words)
        print(f"[✅] Alignment done — {len(segments_data)} synced phrases.")
    else:
        # Graceful fallback — use Gemini timestamps with a small static offset
        print("[⚠️] Using Gemini timestamps with +0.10s offset as fallback.")
        segments_data = [{"phrase": p["phrase"], "start": p["start"] + 0.10, "end": p["end"] + 0.10} for p in gemini_phrases]

    # 3. Video dimensions
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate", "-of", "json", video_path], capture_output=True, text=True)
    info_json = json.loads(probe.stdout)["streams"][0]
    W, H  = int(info_json["width"]), int(info_json["height"])


    def make_base_html(width: int, height: int) -> str:
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Gemunu+Libre:wght@700;800&family=Montserrat:wght@800;900&display=swap');
  
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ width: {width}px; height: {height}px; background: transparent; overflow: hidden; }}
  .caption-wrap {{
    position: absolute; bottom: {int(height * 0.22)}px; left: 0; right: 0; 
    padding: 0 {int(width * 0.08)}px; 
    text-align: center; /* Center the stacked text */
  }}
  .phrase-cap {{
    display: inline-block;
    line-height: 1.3;
    margin: 0 6px; /* THIS FIXES THE MISSING SPACES */
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text; color: transparent;
  }}

  /* STYLE 1: SINHALA */
  .sin-blue {{
    font-family: 'Gemunu Libre', sans-serif; font-weight: 800;
    background-image: linear-gradient(to bottom, #82cfff 0%, #0077ff 100%);
    filter: drop-shadow(0 0 12px rgba(0, 100, 255, 0.9)) drop-shadow(0 3px 5px rgba(0,0,0,0.9));
  }}

  /* STYLE 2: ENGLISH */
  .eng-silver {{
    font-family: 'Montserrat', sans-serif; font-weight: 900; letter-spacing: -0.5px;
    background-image: linear-gradient(160deg, #ffffff 0%, #d2e8ff 30%, #b4d7ff 60%, #ffffff 100%);
    filter: drop-shadow(0 0 10px rgba(140,185,255,0.5)) drop-shadow(0 2px 4px rgba(0,0,0,0.8));
  }}

  /* STYLE 3: NUMBERS */
  .num-gold {{
    font-family: 'Montserrat', sans-serif; font-weight: 900; letter-spacing: -1px;
    background-image: linear-gradient(to bottom, #FFE81F 0%, #FF8A00 100%);
    filter: drop-shadow(0 0 15px rgba(255,165,0,0.6)) drop-shadow(0 3px 6px rgba(0,0,0,0.9));
  }}
</style>
</head>
<body>
  <div class="caption-wrap" id="wrap">
    <div id="phrase_box"></div>
  </div>
</body>
</html>"""

    segments_arr = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1)
        page = context.new_page()
        page.set_content(make_base_html(W, H), wait_until="networkidle")

        for i, item in enumerate(segments_data):
            phrase_text = str(item.get("phrase", "")).strip()
            if not phrase_text: continue
            
            # Use Whisper-aligned timestamps directly — no offset hack needed
            start_time = float(item.get("start", 0))
            end_time = float(item.get("end", start_time + 1.0))
            
            png_path = os.path.join(ovr_dir, f"cap_phrase_{i:04d}.png")
            
            char_count = len(phrase_text)
            if char_count <= 15: font_size = int(H * 0.055)
            elif char_count <= 25: font_size = int(H * 0.045)
            else: font_size = int(H * 0.038)

            # THE PRO STACKED JS PARSER
            page.evaluate("""
                (args) => {
                    const el = document.getElementById('phrase_box');
                    // Filter removes accidental double spaces
                    const words = args.text.split(' ').filter(w => w.trim() !== '');
                    let innerHtml = '';
                    
                    // Find the exact middle of the phrase to insert the line break
                    const midPoint = Math.ceil(words.length / 2);

                    words.forEach((word, index) => {
                        let className = '';
                        let size = args.fontSize;

                        if (/\\d+/.test(word)) {
                            className = 'num-gold';
                        } else if (/[A-Za-z]/.test(word)) {
                            className = 'eng-silver';
                        } else {
                            className = 'sin-blue';
                            size += 5; 
                        }

                        innerHtml += `<span class="phrase-cap ${className}" style="font-size: ${size}px;">${word}</span>`;
                        
                        // Insert a line break if the phrase is 3+ words and we hit the middle
                        if (words.length >= 3 && index === midPoint - 1) {
                            innerHtml += '<br>';
                        }
                    });

                    el.innerHTML = innerHtml;
                }
            """, {"text": phrase_text, "fontSize": font_size})

            page.screenshot(path=png_path, full_page=False, omit_background=True)
            segments_arr.append((start_time, end_time, png_path, phrase_text, None))

        browser.close()

    # ── FFmpeg overlay — batched with Dynamic Mathematical Animations ──
    print("[⚙️] Compositing Sinhala captions with cinematic motion math...")

    CHUNK = 50
    current_video = video_path
    anim_style = cap_options.get("captionAnimation", "spring-up")
    dur = 0.15 

    for chunk_start in range(0, len(segments_arr), CHUNK):
        chunk = segments_arr[chunk_start : chunk_start + CHUNK]
        chunk_out = os.path.join(base_dir, f"_chunk_{chunk_start:04d}.mp4")

        inputs = ["ffmpeg", "-i", current_video]
        for _, _, path, _, _ in chunk: 
            inputs += ["-i", path]

        filter_parts = []
        for idx, (t_s, t_e, _, _, _) in enumerate(chunk):
            in_lbl = f"[v{idx}]" if idx > 0 else "[0:v]"
            out_lbl = f"[v{idx+1}]"
            inp_lbl = f"[{idx+1}]"
            
            enable_expr = f"enable='between(t,{t_s:.3f},{t_e:.3f})'"
            
            t_prog = f"(t-{t_s:.3f})/{dur}"
            inv_p = f"(1-{t_prog})"
            ease_out_cubic = f"({inv_p}*{inv_p}*{inv_p})"
            
            if anim_style == "slide-up":
                y_expr = f"if(lte(t,{t_s:.3f}+{dur}), 60*{ease_out_cubic}, 0)"
                overlay_cmd = f"x=0:y='{y_expr}':{enable_expr}"
                
            elif anim_style == "slide-right":
                x_expr = f"if(lte(t,{t_s:.3f}+{dur}), -60*{ease_out_cubic}, 0)"
                overlay_cmd = f"x='{x_expr}':y=0:{enable_expr}"
                
            elif anim_style == "spring-up":
                spring_dur = 0.25
                sp = f"(t-{t_s:.3f})/{spring_dur}"
                y_expr = f"if(lte(t,{t_s:.3f}+{spring_dur}), 80*(1-{sp})*cos({sp}*6.5), 0)"
                overlay_cmd = f"x=0:y='{y_expr}':{enable_expr}"
                
            else:
                overlay_cmd = f"x=0:y=0:{enable_expr}"

            filter_parts.append(f"{in_lbl}{inp_lbl}overlay={overlay_cmd}{out_lbl}")

        cmd = inputs + [
            "-filter_complex", ";".join(filter_parts),
            "-map", f"[v{len(chunk)}]", "-map", "0:a:0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "17",
            "-pix_fmt", "yuv420p", "-c:a", "copy", chunk_out, "-y"
        ]
        
        subprocess.run(cmd, check=True, capture_output=True)

        if current_video != video_path and os.path.exists(current_video):
            os.remove(current_video)
        current_video = chunk_out

    if current_video != video_path: 
        os.replace(current_video, output_vid)
    else: 
        shutil.copy(video_path, output_vid)

    shutil.rmtree(ovr_dir, ignore_errors=True)
    if os.path.exists(temp_audio): 
        os.remove(temp_audio)

    print(f"[✅] Perfect Sinhala CSS captions burned with '{anim_style}' animation: {output_vid}")
    return output_vid

# ─────────────────────────────────────────────
# 6. CINEMATIC BOTTOM GLOW ENGINE
# ─────────────────────────────────────────────

def stage_bottom_glow(video_path: str, color_hex: str) -> str:
    print(f"[⚙️] Adding cinematic bottom glow ({color_hex})...")
    base_dir = os.path.dirname(os.path.abspath(video_path))
    output_vid = os.path.splitext(video_path)[0] + "_glow.mp4"
    overlay_png = os.path.join(base_dir, "_bottom_glow.png")

    # 1. Grab exact video dimensions
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "json", video_path],
        capture_output=True, text=True
    )
    info = json.loads(probe.stdout)["streams"][0]
    W, H = int(info["width"]), int(info["height"])

    # 2. Parse Hex Color and Generate Smooth Gradient PNG
    color_hex = color_hex.lstrip('#')
    if len(color_hex) != 6:
        color_hex = "000000" # Fallback to black
    r, g, b = tuple(int(color_hex[i:i+2], 16) for i in (0, 2, 4))

    img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Start the gradient 45% down the screen
    start_y = int(H * 0.45)
    for y in range(start_y, H):
        progress = (y - start_y) / (H - start_y)
        # Using ** 2.5 applies cubic easing for a super smooth, cinematic fade
        alpha = int(255 * (progress ** 2.5))
        draw.line([(0, y), (W, y)], fill=(r, g, b, alpha))
    
    img.save(overlay_png)

    # 3. Composite via FFmpeg
    subprocess.run([
        "ffmpeg", "-i", video_path, "-i", overlay_png,
        "-filter_complex", "[0:v][1:v]overlay=0:0[outv]",
        "-map", "[outv]", "-map", "0:a?", # '?' makes audio optional in case it was muted
        "-c:v", "libx264", "-preset", "fast", "-crf", "17",
        "-pix_fmt", "yuv420p", "-c:a", "copy",
        output_vid, "-y"
    ], check=True, capture_output=True)

    if os.path.exists(overlay_png):
        os.remove(overlay_png)

    print(f"[✅] Bottom glow applied: {output_vid}")
    return output_vid

# ─────────────────────────────────────────────
# 7. AI BACKGROUND FX ENGINE (MediaPipe)
# ─────────────────────────────────────────────

def stage_background_fx(video_path: str, bg_options: dict) -> str:
    import cv2
    import numpy as np
    import mediapipe as mp
    import subprocess, os

    print("[⚙️] Booting MediaPipe AI Background Engine...")
    base_dir = os.path.dirname(os.path.abspath(video_path))
    temp_vid = os.path.join(base_dir, "_temp_bg_fx.mp4")
    output_vid = os.path.splitext(video_path)[0] + "_bgfx.mp4"
    temp_audio = os.path.join(base_dir, "_temp_audio.wav")

    mode = bg_options.get("bgMode", "blur")
    hex_color = bg_options.get("bgColor", "#09090b").lstrip('#')
    bg_image_path = bg_options.get("bgImagePath", "")
    keying_mode = bg_options.get("keyingMode", "ai") # 'ai' or 'chroma'
    
    # Convert Hex to BGR for OpenCV fallback
    bgr_color = tuple(int(hex_color[i:i+2], 16) for i in (4, 2, 0)) if len(hex_color) == 6 else (11, 9, 9)

    subprocess.run(["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "48000", "-ac", "1", temp_audio, "-y"], check=True, capture_output=True)

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(temp_vid, fourcc, fps, (w, h))

    # Pre-load and scale the custom background image if provided
    custom_bg_img = None
    if mode == "image" and bg_image_path and os.path.exists(bg_image_path):
        print(f"[⚙️] Loading custom background image: {os.path.basename(bg_image_path)}")
        custom_bg_img = cv2.imread(bg_image_path)
        if custom_bg_img is not None:
            # Resize image to match video exact dimensions (w, h)
            custom_bg_img = cv2.resize(custom_bg_img, (w, h))

    engine_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(engine_dir, "pretrained_models", "selfie_segmenter.tflite")
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    if not os.path.exists(model_path):
        print("[⚙️] Downloading MediaPipe Selfie Segmenter model...")
        import urllib.request
        urllib.request.urlretrieve("https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite", model_path)

    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision
    
    base_options = mp_python.BaseOptions(model_asset_path=model_path)
    options = vision.ImageSegmenterOptions(base_options=base_options, output_confidence_masks=True)

    with vision.ImageSegmenter.create_from_options(options) as segmenter:
        while cap.isOpened():
            success, frame = cap.read()
            if not success: break

            # --- 1. DETERMINE THE BACKGROUND TO APPLY ---
            if mode == "blur":
                bg_frame = cv2.GaussianBlur(frame, (99, 99), 0)
                bg_frame = cv2.addWeighted(bg_frame, 0.7, np.zeros_like(bg_frame), 0.3, 0) 
            elif mode == "image" and custom_bg_img is not None:
                bg_frame = custom_bg_img
            else:
                bg_frame = np.full(frame.shape, bgr_color, dtype=np.uint8)

            # --- 2. GENERATE THE MASK BASED ON SELECTED MODE ---
            if keying_mode == "chroma":
                # Pure Math: Fast Green Screen Keying
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                # Broad green target (adjust these if your lighting is very dark/bright)
                lower_green = np.array([35, 40, 40])
                upper_green = np.array([85, 255, 255])
                
                raw_mask = cv2.inRange(hsv, lower_green, upper_green)
                
                # Morphological noise reduction
                kernel = np.ones((3,3), np.uint8)
                mask = cv2.morphologyEx(raw_mask, cv2.MORPH_OPEN, kernel, iterations=1)
                mask = cv2.dilate(mask, kernel, iterations=1)
                
                # Feather the edges mathematically
                mask = cv2.GaussianBlur(mask, (5, 5), 0)
                
                # Normalize mask for smooth blending (1.0 = Background, 0.0 = Subject)
                blend_ratio = np.stack((mask,) * 3, axis=-1) / 255.0
                output_frame = (frame * (1.0 - blend_ratio) + bg_frame * blend_ratio).astype(np.uint8)
                
            else:
                # Fallback: Heavy AI Neural Net Processing
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
                results = segmenter.segment(mp_image)
                
                # The confidence mask for person is a single channel float array
                mask = np.squeeze(results.confidence_masks[0].numpy_view())
                condition = np.stack((mask,) * 3, axis=-1) > 0.5
                output_frame = np.where(condition, frame, bg_frame)

            out.write(output_frame)

    cap.release()
    out.release()

    print("[⚙️] Remuxing audio to processed video...")
    subprocess.run([
        "ffmpeg", "-i", temp_vid, "-i", temp_audio,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-map", "0:v:0", "-map", "1:a:0",
        "-shortest", output_vid, "-y"
    ], check=True, capture_output=True)

    for f in [temp_vid, temp_audio]:
        if os.path.exists(f): os.remove(f)

    print(f"[✅] Background FX applied: {output_vid}")
    return output_vid

# ─────────────────────────────────────────────
# 8. SEMANTIC SMART-ZOOM ENGINE (NLP)
# ─────────────────────────────────────────────

def stage_semantic_zoom(video_path: str, zoom_options: dict) -> str:
    import subprocess, os, json

    print("[⚙️] Analyzing semantic context for Smart Zooms...")
    base_dir = os.path.dirname(os.path.abspath(video_path))
    output_vid = os.path.splitext(video_path)[0] + "_smartzoom.mp4"
    temp_audio = os.path.join(base_dir, "_zoom_audio.wav")

    # 1. Extract audio for fast analysis
    subprocess.run(["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", temp_audio, "-y"], check=True, capture_output=True)

    # Use the 'base' model for lightning-fast keyword spotting
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
    )

    # 2. Viral Hook Dictionary (Customize these to your niche)
    hook_words = [
        "important", "secret", "listen", "stop", "never", "always", 
        "money", "hack", "trick", "reason", "best", "worst", "look", 
        "insane", "crazy", "truth", "give", "warning", "attention"
    ]

    zoom_intervals = []
    
    # 3. Find exactly when these words are spoken
    for seg in list(w_segments_raw):
        for w in (seg.words or []):
            clean_word = w.word.strip().lower()
            clean_word = ''.join(e for e in clean_word if e.isalnum())

            if clean_word in hook_words:
                # Trigger a zoom for 2.5 seconds starting at this exact word
                start = w["start"]
                end = start + 2.5
                zoom_intervals.append((start, end))

    if not zoom_intervals:
        print("[⚙️] No hook words found. Skipping Smart Zoom.")
        if os.path.exists(temp_audio): os.remove(temp_audio)
        return video_path

    print(f"[🎬] Found {len(zoom_intervals)} semantic impact moments. Rendering smooth zoompans...")

    # 4. Grab dimensions and exact framerate to calculate buttery smooth motion
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate", "-of", "json", video_path], capture_output=True, text=True)
    info = json.loads(probe.stdout)["streams"][0]
    W, H = int(info["width"]), int(info["height"])
    
    fps_str = info.get("r_frame_rate", "30/1")
    num, den = fps_str.split('/')
    fps = int(num) / int(den)

    # 5. Build the dynamic FFmpeg zoompan mathematical expression
    intensity = float(zoom_options.get("zoomIntensity", 1.15))
    
    # Grab the speed from the frontend (defaults to 0.75s if missing)
    duration = float(zoom_options.get("zoomSpeed", 0.5))
    
    # Calculate smooth speed (reaches max zoom in X seconds based on video FPS)
    zoom_speed = (intensity - 1.0) / (fps * duration)
    
    # The Math: 'time' is the current second. 'pzoom' is the zoom level of the last frame.
    z_expr = "1"
    for (start, end) in zoom_intervals:
        z_expr = f"if(between(time,{start:.2f},{end:.2f}), min(pzoom+{zoom_speed:.5f},{intensity}), {z_expr})"

    # Keep the camera perfectly centered while zooming
    x_expr = f"({W}-({W}/zoom))/2"
    y_expr = f"({H}-({H}/zoom))/2"

    # d=1 means 1 output frame per input frame (crucial for processing video)
    filter_complex = f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d=1:s={W}x{H}:fps={fps}"

    try:
        subprocess.run([
            "ffmpeg", "-i", video_path,
            "-vf", filter_complex,
            "-c:v", "libx264", "-preset", "fast", "-crf", "17",
            "-pix_fmt", "yuv420p", "-c:a", "copy",
            output_vid, "-y"
        ], check=True, capture_output=True)

        if os.path.exists(temp_audio): os.remove(temp_audio)
        print(f"[✅] Semantic Smooth Zoom applied: {output_vid}")
        return output_vid

    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        print(f"[❌] Smart Zoom failed: {err_msg}")
        return video_path

# ─────────────────────────────────────────────
# 9. CAPCUT OVERLAY EXPORT — ENGLISH
# ─────────────────────────────────────────────

def export_captions_overlay_en(video_path: str, options: dict) -> str:
    """
    Renders the styled English captions onto a fully transparent MP4.
    The output has NO original footage — just captions floating on alpha.
    Drag it onto any CapCut/Premiere timeline above your footage.

    Pipeline:
      1. Re-use the exact same Whisper transcription + Playwright screenshot
         pipeline from stage_burn_captions — same fonts, same styles.
      2. Build a transparent base video using FFmpeg's 'color=black:size=WxH'
         source with libx264rgb + yuva420p (true alpha channel).
      3. Overlay every caption PNG onto that transparent base using the same
         animation math (spring-up / slide-up / etc.) as the burn pipeline.
    """
    import shutil
    from playwright.sync_api import sync_playwright

    print("[⚙️] [OVERLAY EXPORT] Starting English caption overlay render...")
    base_dir   = os.path.dirname(os.path.abspath(video_path))
    output_vid = os.path.splitext(video_path)[0] + "_captions_overlay_en.webm"
    ovr_dir    = os.path.join(base_dir, "_cap_ovr_en")
    os.makedirs(ovr_dir, exist_ok=True)

    font_family = options.get("captionFont", "Montserrat")
    p_class     = options.get("captionPrimaryStyle", "p-clean-white")
    s_class     = options.get("captionSecondaryStyle", "s-hormozi-yellow")
    anim_style  = options.get("captionAnimation", "spring-up")

    # ── Get video dimensions + duration ────────────────────────────────
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate",
         "-show_entries", "format=duration",
         "-of", "json", video_path],
        capture_output=True, text=True
    )
    info = json.loads(probe.stdout)
    W = int(info["streams"][0]["width"])
    H = int(info["streams"][0]["height"])
    duration = float(info["format"]["duration"])
    fps_str = info["streams"][0].get("r_frame_rate", "30/1")
    num, den = fps_str.split("/")
    fps = float(num) / float(den)

    # ── Whisper transcription (same as burn pipeline) ──────────────────
    temp_audio = os.path.join(base_dir, "_ovr_en_audio.wav")
    subprocess.run(
        ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
         "-ar", "16000", "-ac", "1", temp_audio, "-y"],
        check=True, capture_output=True
    )
    print("[⚙️] Loading Whisper large-v3 (GPU-accelerated)...")
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
                word_events.append({"word": w.word.strip(), "start": w.start, "end": w.end})

    # ── Build segment list (same word-pair logic as burn pipeline) ─────
    segments = []
    rendered_pairs = {}
    i = 0
    while i < len(word_events):
        w1    = word_events[i]["word"]
        t_s   = word_events[i]["start"]
        w1_len = len(w1)
        if w1_len >= 9 or i + 1 >= len(word_events):
            w2, t_e = None, word_events[i]["end"]
            i += 1
        else:
            w2     = word_events[i + 1]["word"]
            w2_len = len(w2)
            if (w1_len + w2_len) > 15:
                w2, t_e = None, word_events[i]["end"]
                i += 1
            else:
                t_e = word_events[i + 1]["end"]
                i += 2
        key = (w1, w2 or "")
        if key not in rendered_pairs:
            rendered_pairs[key] = os.path.join(ovr_dir, f"cap_{len(rendered_pairs):04d}.png")
        segments.append((t_s, t_e, rendered_pairs[key], w1, w2))

    # ── Playwright renders (reuse make_base_html from stage_burn_captions) ─
    # We inline the HTML builder here so this function is self-contained
    def _make_html(width, height):
        return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Anton&family=Bangers&family=Montserrat:wght@800;900&family=Oswald:wght@700&family=Poppins:wght@800;900&display=swap');
  *{{margin:0;padding:0;box-sizing:border-box}}
  html,body{{width:{width}px;height:{height}px;background:transparent;overflow:hidden}}
  .caption-wrap{{position:absolute;bottom:{int(height*0.22)}px;left:0;right:0;display:flex;align-items:baseline;flex-wrap:wrap;justify-content:center;padding:0 {int(width*0.05)}px}}
  .base-cap{{font-weight:900;letter-spacing:-1px;line-height:1;white-space:nowrap;-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;color:transparent}}
  .highlight-align{{letter-spacing:-0.5px;align-self:flex-end}}
  .p-glass-silver{{background-image:linear-gradient(160deg,#fff 0%,#d2e8ff 30%,#b4d7ff 55%,#ebf6ff 75%,#fff 100%);filter:drop-shadow(0 0 10px rgba(140,185,255,.5)) drop-shadow(0 1px 3px rgba(60,100,200,.35))}}
  .p-clean-white{{background-image:linear-gradient(to bottom,#fff 0%,#e0e0e0 100%);filter:drop-shadow(0 3px 6px rgba(0,0,0,.8))}}
  .p-heavy-stroke{{background-image:linear-gradient(to bottom,#fff,#fff);filter:drop-shadow(2px 0 0 #000) drop-shadow(-2px 0 0 #000) drop-shadow(0 2px 0 #000) drop-shadow(0 -2px 0 #000) drop-shadow(0 5px 12px rgba(0,0,0,.9))}}
  .p-soft-yellow{{background-image:linear-gradient(to bottom,#FFFDE7 0%,#FFF176 100%);filter:drop-shadow(0 2px 4px rgba(0,0,0,.7))}}
  .p-neon-base{{background-image:linear-gradient(to bottom,#fff 0%,#e0f7fa 100%);filter:drop-shadow(0 0 10px rgba(0,255,255,.4)) drop-shadow(0 2px 2px rgba(0,0,0,.8))}}
  .s-electric-teal{{background-image:linear-gradient(to right,#00dcc8 0%,#00c3d2 50%,#00aadc 100%);filter:drop-shadow(0 0 8px rgba(0,210,200,.75)) drop-shadow(0 1px 3px rgba(0,150,180,.55))}}
  .s-hormozi-yellow{{background-image:linear-gradient(to bottom,#FFE81F 0%,#FF8A00 100%);filter:drop-shadow(0 0 15px rgba(255,165,0,.6)) drop-shadow(0 3px 6px rgba(0,0,0,.9))}}
  .s-crimson-red{{background-image:linear-gradient(to bottom,#ff4b4b 0%,#b30000 100%);filter:drop-shadow(0 0 12px rgba(255,0,0,.6)) drop-shadow(0 3px 5px rgba(0,0,0,.9))}}
  .s-cyber-purple{{background-image:linear-gradient(to right,#d500f9 0%,#651fff 100%);filter:drop-shadow(0 0 15px rgba(213,0,249,.7)) drop-shadow(0 2px 4px rgba(0,0,0,.8))}}
  .s-luxury-gold{{background-image:linear-gradient(160deg,#FFF7D6 0%,#F3DA7C 30%,#D4AF37 70%,#AA7700 100%);filter:drop-shadow(0 0 12px rgba(212,175,55,.5)) drop-shadow(0 2px 5px rgba(0,0,0,.8))}}
</style></head><body>
  <div class="caption-wrap" id="wrap">
    <span class="base-cap" id="w1"></span>
    <span class="base-cap highlight-align" id="w2" style="display:none"></span>
  </div>
</body></html>"""

    print("[⚙️] [OVERLAY EXPORT] Rendering caption PNGs...")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx     = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1)
        page    = ctx.new_page()
        page.set_content(_make_html(W, H), wait_until="networkidle")
        rendered_done = set()
        for t_s, t_e, png_path, w1, w2 in segments:
            key = (w1, w2 or "")
            if key in rendered_done: continue
            w1_len = len(w1)
            combined_len = len(w1) + (len(w2) if w2 else 0)
            if w1_len <= 4:   primary_size = int(H * 0.075)
            elif w1_len <= 6: primary_size = int(H * 0.065)
            elif w1_len <= 9: primary_size = int(H * 0.055)
            elif w1_len <= 12:primary_size = int(H * 0.047)
            else:             primary_size = int(H * 0.038)
            secondary_size = int(primary_size * 0.52)
            if combined_len > 14:
                shrink = max(0.65, 1.0 - (combined_len - 14) * 0.018)
                primary_size   = int(primary_size   * shrink)
                secondary_size = int(secondary_size * shrink)
            primary_size   = max(primary_size,   18)
            secondary_size = max(secondary_size, 12)
            gap_px            = int(primary_size * 0.15)
            padding_bottom_px = int(primary_size * 0.05)
            page.evaluate("""(args) => {
                const w1El = document.getElementById('w1');
                const w2El = document.getElementById('w2');
                const wrapEl = document.getElementById('wrap');
                w1El.textContent = args.w1;
                w1El.style.fontSize = args.primary_size + 'px';
                w1El.style.fontFamily = `'${args.font_family}', Impact, sans-serif`;
                w1El.className = 'base-cap ' + args.p_class;
                if (args.w2) {
                    w2El.textContent = args.w2;
                    w2El.style.display = 'inline';
                    w2El.style.fontSize = args.secondary_size + 'px';
                    w2El.style.paddingBottom = args.padding_bottom_px + 'px';
                    w2El.style.fontFamily = `'${args.font_family}', Impact, sans-serif`;
                    w2El.className = 'base-cap highlight-align ' + (args.s_class === 'none' ? args.p_class : args.s_class);
                } else {
                    w2El.textContent = ''; w2El.style.display = 'none';
                }
                wrapEl.style.gap = args.gap_px + 'px';
            }""", {"w1": w1, "w2": w2, "primary_size": primary_size,
                   "secondary_size": secondary_size, "gap_px": gap_px,
                   "padding_bottom_px": padding_bottom_px,
                   "font_family": font_family, "p_class": p_class, "s_class": s_class})
            page.screenshot(path=png_path, full_page=False, omit_background=True)
            rendered_done.add(key)
        browser.close()

    # ── Composite captions in CHUNKS of 40 (stays under FFmpeg's input file limit) ──
    print("[⚙️] [OVERLAY EXPORT] Compositing onto transparent QuickTime canvas...")
    dur   = 0.15
    CHUNK = 40  

    def _build_overlay_filter(chunk, anim_style, dur):
        parts = ["[0:v]format=rgba[rgba_base]"]
        for idx, (t_s, t_e, _, _, _) in enumerate(chunk):
            in_lbl  = "[rgba_base]" if idx == 0 else f"[v{idx}]"
            out_lbl = f"[v{idx+1}]"
            inp_lbl = f"[{idx+1}]"
            enable_expr    = f"enable='between(t,{t_s:.3f},{t_e:.3f})'"
            t_prog         = f"(t-{t_s:.3f})/{dur}"
            inv_p          = f"(1-{t_prog})"
            ease_out_cubic = f"({inv_p}*{inv_p}*{inv_p})"
            if anim_style == "slide-up":
                y_expr      = f"if(lte(t,{t_s:.3f}+{dur}), 60*{ease_out_cubic}, 0)"
                overlay_cmd = f"x=0:y='{y_expr}':{enable_expr}"
            elif anim_style == "slide-right":
                x_expr      = f"if(lte(t,{t_s:.3f}+{dur}), -60*{ease_out_cubic}, 0)"
                overlay_cmd = f"x='{x_expr}':y=0:{enable_expr}"
            elif anim_style == "spring-up":
                spring_dur  = 0.25
                sp          = f"(t-{t_s:.3f})/{spring_dur}"
                y_expr      = f"if(lte(t,{t_s:.3f}+{spring_dur}), 80*(1-{sp})*cos({sp}*6.5), 0)"
                overlay_cmd = f"x=0:y='{y_expr}':{enable_expr}"
            else:
                overlay_cmd = f"x=0:y=0:{enable_expr}"
                
            # FORCE RGB OVERLAY TO PRESERVE ALPHA
            parts.append(
                f"{in_lbl}{inp_lbl}overlay={overlay_cmd}:format=rgb:eof_action=pass{out_lbl}"
            )
        return parts

    current_base = None
    chunk_files  = []
    output_vid = os.path.splitext(video_path)[0] + "_captions_overlay_en.mov"

    for chunk_start in range(0, len(segments), CHUNK):
        chunk     = segments[chunk_start: chunk_start + CHUNK]
        chunk_out = os.path.join(base_dir, f"_ovr_en_chunk_{chunk_start:04d}.mov")
        chunk_files.append(chunk_out)

        if current_base is None:
            # Force RGBA directly on the lavfi generation to guarantee a transparent background
            inputs_cmd = [
                "ffmpeg",
                "-f", "lavfi", "-i",
                f"color=c=black@0.0:size={W}x{H}:rate={fps}:duration={duration},format=rgba"
            ]
        else:
            # Tell FFmpeg to decode the previous chunk preserving alpha
            inputs_cmd = ["ffmpeg", "-vcodec", "qtrle", "-i", current_base]

        for _, _, path, _, _ in chunk:
            inputs_cmd += ["-i", path]

        filter_parts = _build_overlay_filter(chunk, anim_style, dur)

        # Final output forced to RGBA, encoded using QuickTime Animation (qtrle) + argb
        cmd = inputs_cmd + [
            "-filter_complex", ";".join(filter_parts) + f";[v{len(chunk)}]format=rgba[final_out]",
            "-map", "[final_out]",
            "-c:v", "qtrle", 
            "-pix_fmt", "argb",
            chunk_out, "-y"
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
            print(f"[\u274c] FFmpeg chunk {chunk_start} failed:\n{err[-800:]}")
            raise

        current_base = chunk_out

    os.replace(current_base, output_vid)
    for f in chunk_files[:-1]:
        if os.path.exists(f): os.remove(f)

    shutil.rmtree(ovr_dir, ignore_errors=True)
    if os.path.exists(temp_audio): os.remove(temp_audio)

    print(f"[✅] [OVERLAY EXPORT] CapCut overlay saved: {output_vid}")
    print(f"[📋] Drag '{os.path.basename(output_vid)}' onto your CapCut timeline above your footage.")
    return output_vid


# ─────────────────────────────────────────────
# 10. CAPCUT OVERLAY EXPORT — SINHALA
# ─────────────────────────────────────────────

def export_captions_overlay_si(video_path: str, options: dict) -> str:
    """
    Same idea as export_captions_overlay_en but uses the full
    Gemini + Whisper alignment pipeline for perfect Sinhala timing.
    Output: transparent .mov with animated Singlish captions.
    """
    import shutil
    from playwright.sync_api import sync_playwright

    print("[⚙️] [OVERLAY EXPORT] Starting Sinhala caption overlay render...")
    base_dir   = os.path.dirname(os.path.abspath(video_path))
    output_vid = os.path.splitext(video_path)[0] + "_captions_overlay_si.webm"
    ovr_dir    = os.path.join(base_dir, "_cap_ovr_si")
    os.makedirs(ovr_dir, exist_ok=True)

    p_class    = options.get("captionPrimaryStyle", "p-glass-silver")
    anim_style = options.get("captionAnimation", "spring-up")

    # ── Extract audio ──────────────────────────────────────────────────
    temp_audio = os.path.join(base_dir, "_ovr_si_audio.wav")
    subprocess.run(
        ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
         "-ar", "16000", "-ac", "1", temp_audio, "-y"],
        check=True, capture_output=True
    )

    # ── Gemini transcript + Whisper alignment (reuse shared functions) ─
    gemini_phrases = get_perfect_sinhala_transcript(temp_audio, options.get("geminiApiKey"))
    if not gemini_phrases:
        print("[❌] [OVERLAY EXPORT] Gemini failed. Aborting.")
        if os.path.exists(temp_audio): os.remove(temp_audio)
        return video_path

    print("[⚙️] [OVERLAY EXPORT] Running Whisper for timestamp anchors...")
    try:
        from faster_whisper import WhisperModel
        try:
            w_model = WhisperModel("base", device="cuda", compute_type="int8")
        except Exception:
            w_model = WhisperModel("base", device="cpu",  compute_type="int8")
        w_segs_raw, _ = w_model.transcribe(
            temp_audio, word_timestamps=True,
            vad_filter=True, condition_on_previous_text=False
        )
        w_segs_list  = list(w_segs_raw)
        whisper_words = [{"word": w.word.strip(), "start": w.start, "end": w.end}
                         for seg in w_segs_list for w in (seg.words or []) if w.word.strip()]
        if len(whisper_words) < len(gemini_phrases):
            whisper_words = [{"word": "[seg]", "start": seg.start, "end": seg.end}
                             for seg in w_segs_list]
    except Exception as e:
        print(f"[⚠️] Whisper failed ({e}). Falling back to Gemini timestamps.")
        whisper_words = []

    segments_data = align_phrases_to_whisper(gemini_phrases, whisper_words) \
                    if whisper_words else \
                    [{"phrase": p["phrase"], "start": p["start"], "end": p["end"]}
                     for p in gemini_phrases if p.get("phrase","").strip()]

    # ── Video dimensions + duration ────────────────────────────────────
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate",
         "-show_entries", "format=duration",
         "-of", "json", video_path],
        capture_output=True, text=True
    )
    info     = json.loads(probe.stdout)
    W        = int(info["streams"][0]["width"])
    H        = int(info["streams"][0]["height"])
    duration = float(info["format"]["duration"])
    fps_str  = info["streams"][0].get("r_frame_rate", "30/1")
    num, den = fps_str.split("/")
    fps      = float(num) / float(den)

    # ── Playwright Sinhala HTML builder (mirrors stage_burn_sinhala_captions) ─
    def _make_si_html(width, height):
        return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Gemunu+Libre:wght@700;800&family=Montserrat:wght@800;900&display=swap');
  *{{margin:0;padding:0;box-sizing:border-box}}
  html,body{{width:{width}px;height:{height}px;background:transparent;overflow:hidden}}
  .caption-wrap{{position:absolute;bottom:{int(height*0.22)}px;left:0;right:0;padding:0 {int(width*0.08)}px;text-align:center}}
  .phrase-cap{{display:inline-block;line-height:1.3;margin:0 6px;-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;color:transparent}}
  .sin-blue{{font-family:'Gemunu Libre',sans-serif;font-weight:800;background-image:linear-gradient(to bottom,#82cfff 0%,#0077ff 100%);filter:drop-shadow(0 0 12px rgba(0,100,255,.9)) drop-shadow(0 3px 5px rgba(0,0,0,.9))}}
  .eng-silver{{font-family:'Montserrat',sans-serif;font-weight:900;letter-spacing:-.5px;background-image:linear-gradient(160deg,#fff 0%,#d2e8ff 30%,#b4d7ff 60%,#fff 100%);filter:drop-shadow(0 0 10px rgba(140,185,255,.5)) drop-shadow(0 2px 4px rgba(0,0,0,.8))}}
  .num-gold{{font-family:'Montserrat',sans-serif;font-weight:900;letter-spacing:-1px;background-image:linear-gradient(to bottom,#FFE81F 0%,#FF8A00 100%);filter:drop-shadow(0 0 15px rgba(255,165,0,.6)) drop-shadow(0 3px 6px rgba(0,0,0,.9))}}
</style></head><body>
  <div class="caption-wrap" id="wrap"><div id="phrase_box"></div></div>
</body></html>"""

    print("[⚙️] [OVERLAY EXPORT] Rendering Sinhala caption PNGs...")
    segments_arr = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx     = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1)
        page    = ctx.new_page()
        page.set_content(_make_si_html(W, H), wait_until="networkidle")
        for i, item in enumerate(segments_data):
            phrase_text = str(item.get("phrase","")).strip()
            if not phrase_text: continue
            t_s = float(item.get("start", 0))
            t_e = float(item.get("end",   t_s + 1.0))
            png_path   = os.path.join(ovr_dir, f"cap_si_{i:04d}.png")
            char_count = len(phrase_text)
            if char_count <= 15:   font_size = int(H * 0.055)
            elif char_count <= 25: font_size = int(H * 0.045)
            else:                  font_size = int(H * 0.038)
            page.evaluate("""(args) => {
                const el = document.getElementById('phrase_box');
                const words = args.text.split(' ').filter(w => w.trim() !== '');
                let html = '';
                const mid = Math.ceil(words.length / 2);
                words.forEach((word, idx) => {
                    let cls = /\\d+/.test(word) ? 'num-gold' : /[A-Za-z]/.test(word) ? 'eng-silver' : 'sin-blue';
                    let sz  = /[A-Za-z\\d]/.test(word) ? args.fontSize : args.fontSize + 5;
                    html += `<span class="phrase-cap ${cls}" style="font-size:${sz}px">${word}</span>`;
                    if (words.length >= 3 && idx === mid - 1) html += '<br>';
                });
                el.innerHTML = html;
            }""", {"text": phrase_text, "fontSize": font_size})
            page.screenshot(path=png_path, full_page=False, omit_background=True)
            segments_arr.append((t_s, t_e, png_path, phrase_text, None))
        browser.close()

    # ── Composite Sinhala captions in CHUNKS of 40 ──
    print("[⚙️] [OVERLAY EXPORT] Compositing Sinhala captions onto transparent QuickTime canvas...")
    dur   = 0.15
    CHUNK = 40

    def _build_si_filter(chunk, anim_style, dur):
        parts = ["[0:v]format=rgba[rgba_base]"]
        for idx, (t_s, t_e, _, _, _) in enumerate(chunk):
            in_lbl  = "[rgba_base]" if idx == 0 else f"[v{idx}]"
            out_lbl = f"[v{idx+1}]"
            inp_lbl = f"[{idx+1}]"
            enable_expr    = f"enable='between(t,{t_s:.3f},{t_e:.3f})'"
            t_prog         = f"(t-{t_s:.3f})/{dur}"
            inv_p          = f"(1-{t_prog})"
            ease_out_cubic = f"({inv_p}*{inv_p}*{inv_p})"
            if anim_style == "slide-up":
                y_expr      = f"if(lte(t,{t_s:.3f}+{dur}), 60*{ease_out_cubic}, 0)"
                overlay_cmd = f"x=0:y='{y_expr}':{enable_expr}"
            elif anim_style == "slide-right":
                x_expr      = f"if(lte(t,{t_s:.3f}+{dur}), -60*{ease_out_cubic}, 0)"
                overlay_cmd = f"x='{x_expr}':y=0:{enable_expr}"
            elif anim_style == "spring-up":
                spring_dur  = 0.25
                sp          = f"(t-{t_s:.3f})/{spring_dur}"
                y_expr      = f"if(lte(t,{t_s:.3f}+{spring_dur}), 80*(1-{sp})*cos({sp}*6.5), 0)"
                overlay_cmd = f"x=0:y='{y_expr}':{enable_expr}"
            else:
                overlay_cmd = f"x=0:y=0:{enable_expr}"
                
            # FORCE RGB OVERLAY TO PRESERVE ALPHA
            parts.append(
                f"{in_lbl}{inp_lbl}overlay={overlay_cmd}:format=rgb:eof_action=pass{out_lbl}"
            )
        return parts

    current_base = None
    chunk_files  = []
    output_vid = os.path.splitext(video_path)[0] + "_captions_overlay_si.mov"

    for chunk_start in range(0, len(segments_arr), CHUNK):
        chunk     = segments_arr[chunk_start: chunk_start + CHUNK]
        chunk_out = os.path.join(base_dir, f"_ovr_si_chunk_{chunk_start:04d}.mov")
        chunk_files.append(chunk_out)

        if current_base is None:
            # Force RGBA directly on the lavfi generation
            inputs_cmd = [
                "ffmpeg",
                "-f", "lavfi", "-i",
                f"color=c=black@0.0:size={W}x{H}:rate={fps}:duration={duration},format=rgba"
            ]
        else:
            # Tell FFmpeg to decode the previous chunk preserving alpha
            inputs_cmd = ["ffmpeg", "-vcodec", "qtrle", "-i", current_base]

        for _, _, path, _, _ in chunk:
            inputs_cmd += ["-i", path]

        filter_parts = _build_si_filter(chunk, anim_style, dur)

        # Final output forced to RGBA, encoded using QuickTime Animation (qtrle) + argb
        cmd = inputs_cmd + [
            "-filter_complex", ";".join(filter_parts) + f";[v{len(chunk)}]format=rgba[final_out]",
            "-map", "[final_out]",
            "-c:v", "qtrle", 
            "-pix_fmt", "argb",
            chunk_out, "-y"
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
            print(f"[\u274c] FFmpeg SI chunk {chunk_start} failed:\n{err[-800:]}")
            raise

        current_base = chunk_out

    os.replace(current_base, output_vid)
    for f in chunk_files[:-1]:
        if os.path.exists(f): os.remove(f)

    shutil.rmtree(ovr_dir, ignore_errors=True)
    if os.path.exists(temp_audio): os.remove(temp_audio)

    print(f"[✅] [OVERLAY EXPORT] CapCut overlay saved: {output_vid}")
    print(f"[📋] Drag '{os.path.basename(output_vid)}' onto your CapCut timeline above your footage.")
    return output_vid


def run_pipeline(video_path: str, options_json: str) -> None:
    options = json.loads(options_json)
    print(f"\n[🎬] STARTING LOCAL RENDER ENGINE: {os.path.basename(video_path)}\n")

    current_video = video_path

    # Stage order matters for efficiency:
    # 1. Chop dead air first — don't waste CPU grading silence
    # 2. Enhance the audio on the chopped clip
    # 3. Bake the color grade last — audio is already locked via -c:a copy
    if options.get("removeSilence"):
        current_video = stage_remove_silence(current_video)

    if options.get("studioAudio"):
        current_video = stage_studio_audio(current_video)

    # NEW: Auto-Zoom Punch-ins
    if options.get("autoZoom"):
        current_video = stage_semantic_zoom(current_video, options)

    if options.get("cinematicColor"):
        current_video = stage_cinematic_color(current_video, options)

    if options.get("blurBackground"):
        current_video = stage_background_fx(current_video, options)

    if options.get("bottomGlow"):
        color = options.get("glowColor", "#000000")
        current_video = stage_bottom_glow(current_video, color)

    if options.get("burnCaptions"):
        if options.get("captionLanguage") == "si":
            current_video = stage_burn_sinhala_captions(current_video, options)
        else:
            current_video = stage_burn_captions(current_video, options)

    # ── CapCut overlay export (runs independently, doesn't change current_video) ──
    if options.get("exportCaptionOverlay"):
        lang = options.get("captionLanguage", "en")
        if lang == "si":
            export_captions_overlay_si(current_video, options)
        else:
            export_captions_overlay_en(current_video, options)

    print(f"\n[🚀] PIPELINE COMPLETE. Final output: {current_video}")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        run_pipeline(sys.argv[1], sys.argv[2])
    else:
        print("Usage: pipeline.py <video_path> <options_json>")