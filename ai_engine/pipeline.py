import sys
import json
import os
import subprocess
import io
import warnings
import pathlib
from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=env_path)
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

def stage_remove_silence(video_path: str, options: dict = None) -> str:
    from pydub import AudioSegment
    from pydub.silence import detect_nonsilent
    import json
    import subprocess
    import os

    print("[⚙️] Analyzing waveforms for cinematic algorithmic cuts...")
    base_dir = os.path.dirname(os.path.abspath(video_path))
    temp_wav = os.path.join(base_dir, "_silence_detect.wav")
    output_vid = os.path.splitext(video_path)[0] + "_chopped.mp4"
    script_path = os.path.join(base_dir, "_filter_script.txt")

    subprocess.run(
        ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", temp_wav, "-y"],
        check=True, capture_output=True
    )

    audio = AudioSegment.from_wav(temp_wav)
    # Using 400ms min silence to avoid cutting mid-breath
    nonsilent_chunks = detect_nonsilent(audio, min_silence_len=400, silence_thresh=-42)

    if not nonsilent_chunks:
        if os.path.exists(temp_wav): os.remove(temp_wav)
        return video_path

    print(f"[🎬] Found {len(nonsilent_chunks)} active segments. Generating V-Fades & Camera Angles...")

    # Extract exact dimensions and sample rate to prevent concat crashes
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", video_path],
        capture_output=True, text=True
    )
    info = json.loads(probe.stdout)["streams"][0]
    W, H = int(info["width"]), int(info["height"])

    filter_lines = []
    concat_v = ""
    concat_a = ""

    for i, (start_ms, end_ms) in enumerate(nonsilent_chunks):
        # 1. Expand the audio envelope slightly for a smoother J-Cut breathing feel
        start_sec = max(0, (start_ms - 150) / 1000.0) 
        end_sec = (end_ms + 100) / 1000.0
        dur = end_sec - start_sec

        # 2. VISUAL: The Algorithmic Camera Switch 
        # Punch in 15% on alternating clips to mask the jump cut
        v_base = f"[0:v]trim=start={start_sec:.3f}:end={end_sec:.3f},setpts=PTS-STARTPTS"
        if i % 2 == 1:
            v_filter = f"{v_base},crop=iw/1.15:ih/1.15,scale={W}:{H},setsar=1[v{i}];"
        else:
            v_filter = f"{v_base},setsar=1[v{i}];"

        # 3. AUDIO: The Anti-Click V-Fade
        # 40ms micro-crossfades kill all popping/clicking from hard cuts
        a_filter = f"[0:a]atrim=start={start_sec:.3f}:end={end_sec:.3f},asetpts=PTS-STARTPTS," \
                   f"afade=t=in:st=0:d=0.04,afade=t=out:st={dur-0.04:.3f}:d=0.04[a{i}];"

        filter_lines.append(v_filter)
        filter_lines.append(a_filter)
        concat_v += f"[v{i}][a{i}]"

    # Bundle everything into the master concat filter
    filter_lines.append(f"{concat_v}concat=n={len(nonsilent_chunks)}:v=1:a=1[outv][outa]")

    # Bypass Windows CLI string limits by saving the massive command to a text file
    with open(script_path, "w", encoding="utf-8") as f:
        f.write("\n".join(filter_lines))

    print("[⚙️] Rendering master timeline via filter_complex script...")
    subprocess.run([
        "ffmpeg", "-i", video_path,
        "-filter_complex_script", script_path,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        output_vid, "-y"
    ], check=True, capture_output=True)

    for f in [temp_wav, script_path]:
        if os.path.exists(f): os.remove(f)

    print(f"[✅] Cinematic Jump Cuts applied: {output_vid}")
    return output_vid

# ─────────────────────────────────────────────
# 3. PIPELINE ORCHESTRATION
# ─────────────────────────────────────────────

def extract_audio(video_path: str, out_path: str) -> None:
    subprocess.run(["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "48000", "-ac", "1", out_path, "-y"], check=True, capture_output=True)

def stage_extract_mp3(video_path: str) -> str:
    import subprocess
    import os
    
    print("[⚙️] Extracting MP3 audio track...")
    base_dir = os.path.dirname(os.path.abspath(video_path))
    output_mp3 = os.path.splitext(video_path)[0] + "_audio.mp3"
    
    try:
        # Uses libmp3lame with Variable Bitrate (VBR) quality level 2 (~190 kbps)
        subprocess.run([
            "ffmpeg", "-i", video_path, 
            "-vn", "-acodec", "libmp3lame", "-q:a", "2", 
            output_mp3, "-y"
        ], check=True, capture_output=True)
        print(f"[✅] MP3 Audio saved: {output_mp3}")
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        print(f"[❌] MP3 Extraction failed: {err_msg}")
        
    return video_path

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
    import whisper
    import json, shutil, subprocess, os
    from playwright.sync_api import sync_playwright
 
    print("[⚙️] Loading Whisper model...")
    model = whisper.load_model("large")
 
    base_dir   = os.path.dirname(os.path.abspath(video_path))
    output_vid = os.path.splitext(video_path)[0] + "_captioned.mp4"
    ovr_dir    = os.path.join(base_dir, "_cap_overlays")
    os.makedirs(ovr_dir, exist_ok=True)
 
    # Extract template options from frontend
    font_family = cap_options.get("captionFont", "Montserrat")
    p_class = cap_options.get("captionPrimaryStyle", "p-glass-silver")
    s_class = cap_options.get("captionSecondaryStyle", "s-hormozi-yellow")

    # NEW: Grab the percentage and convert to decimal
    cap_bottom_pct = float(cap_options.get("captionBottomPercent", 22)) / 100.0
 
    # ── Whisper transcription ──────────────────────────────────
    temp_audio = os.path.join(base_dir, "_whisper_audio.wav")
    subprocess.run(
        ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
         "-ar", "16000", "-ac", "1", temp_audio, "-y"],
        check=True, capture_output=True
    )
    print("[⚙️] Transcribing with Whisper...")
    result = model.transcribe(temp_audio, word_timestamps=True, verbose=False)
 
    word_events = []
    for seg in result.get("segments", []):
        for w in seg.get("words", []):
            word_events.append({
                "word":  w["word"].strip(),
                "start": w["start"],
                "end":   w["end"]
            })
 
    # ── NEW: Extract Whisper Punctuation for the Transition Engine ──
    flash_times = []
    for i, w_info in enumerate(word_events):
        word_text = w_info["word"]
        if "." in word_text or "?" in word_text or "!" in word_text:
            if i + 1 < len(word_events):
                flash_times.append(float(word_events[i+1]["start"]))
                
    with open(os.path.join(base_dir, "_flash_times.json"), "w") as f:
        json.dump(flash_times, f)

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
    position: absolute; bottom: {int(height * cap_bottom_pct)}px;
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
    from dotenv import load_dotenv

    engine_dir = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(engine_dir, ".env"))
 
    # Grab this from Google AI Studio (it's free)
    api_key = api_key_opt or os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "YOUR_FREE_API_KEY":
        print("[⚠️] GEMINI_API_KEY not found in environment. Proceeding without forced alignment.")
        return []

    def _run_gemini(current_key):
        genai.configure(api_key=current_key)
        print("[⚙️] Uploading audio to Gemini API...")
        
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
        3. TRANSLITERATE ENGLISH: If an English technical word is spoken, type it in English letters (e.g., "AC", "pipe", "commission"). 
        4. NUMBER FORMATTING: Convert all spoken numbers into actual digits (e.g., "රුපියල් 5000").
        5. SLANG CORRECTION: Fix casual Singlish slang ONLY IF it matches the audio timing (e.g., keep "direct වැඩගන්න", "බාස්").
        6. KEYWORDS: Professional field engineer, commission, field engineer, direct, scam, skill, follow, comment, බාස්.
        7. NO GRAMMAR/PUNCTUATION (CRITICAL): Do absolutely NOT use periods (.), commas (,), or question marks (?) anywhere in your text. You are writing modern, fast-paced video captions. No punctuation allowed.
        8. THE DIRECTOR'S CUT (CRITICAL): You are editing a viral video. You have a strict budget of exactly 5 to 8 cinematic camera flashes. Place a pipe symbol "|" at the end of a phrase ONLY when one of these specific narrative beats happens:
           - THE HOOK: The very first attention-grabbing statement or question.
           - THE HARSH TRUTH / CORE MESSAGE: Dropping a heavy fact, a big number, or a controversial statement (e.g., "ලොකුම scam එකක් |").
           - THE VOCAL SHIFT: When the speaker takes a noticeable breath, drops their tone, or pauses slightly before changing the topic.
           DO NOT place a "|" just because a sentence ended. DO NOT exceed 8 pipes in total.
        
        You must provide the approximate start and end times for each phrase in seconds.
        Output strictly as a JSON array. Example:
        [
          {"phrase": "ඔයාගෙත් leak වෙනවද |", "start": 0.1, "end": 1.2},
          {"phrase": "ඔව් මං මේ කියන්නේ", "start": 1.3, "end": 2.2},
          {"phrase": "රුපියල් 5000ක් නිකන්ම |", "start": 2.3, "end": 3.5}
        ]
        Do not include any markdown formatting. Just the raw JSON array.
        """
 
        print("[⚙️] Generating 99% accurate transcript...")
        response = model.generate_content(
            [prompt, audio_file],
            generation_config={"response_mime_type": "application/json"}
        )
        
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

    try:
        return _run_gemini(api_key)
    except Exception as e:
        print(f"[❌] Gemini API Error with primary key: {e}")
        bypass_key = os.getenv("GEMINI_API_KEY_BYPASS")
        if bypass_key:
            print("[⚙️] Retrying with GEMINI_API_KEY_BYPASS...")
            try:
                return _run_gemini(bypass_key)
            except Exception as e2:
                print(f"[❌] Gemini API Error with bypass key as well: {e2}")
                return []
        else:
            print("[❌] No bypass key found. Aborting.")
            return []
 
# ─────────────────────────────────────────────────────────────────────────────
# DROP-IN REPLACEMENT: align_phrases_to_whisper + stage_burn_sinhala_captions
#
# THE PROBLEM (diagnosed):
#   Gemini's phrase timestamps are systematically EARLY — it fires the start
#   timestamp the moment it "predicts" the phrase, not when the audio lands.
#   On Sinhala/mixed audio Whisper also hallucinates word boundaries during
#   silence, so snapping to "nearest word" just snaps to a ghost.
#
# THE 3-LAYER FIX:
#   Layer 1 — Global drift correction
#             Sample N Gemini↔Whisper pairs and compute the median offset.
#             Shift ALL Gemini timestamps by that amount before any snapping.
#   Layer 2 — Segment-anchored snapping (not word-anchored)
#             Use Whisper's rock-solid SEGMENT boundaries as anchors.
#             Find the segment whose [start, end] window best contains the
#             drift-corrected phrase start. This is immune to word-level noise.
#   Layer 3 — Gap-fill smoothing
#             After all phrases are placed, fill any dead gap between
#             phrase[i].end and phrase[i+1].start so the caption holds
#             on screen until the next word begins (no flicker, no early exit).
# ─────────────────────────────────────────────────────────────────────────────

import bisect
import statistics
from typing import List, Dict, Tuple, Optional


def align_phrases_to_whisper(gemini_phrases: list, whisper_words: list) -> list:
    """
    DYNAMIC TIME WARPING (Elastic Projection)
    Fixes the "sometimes fast, sometimes slow" bug by treating Gemini's 
    hallucinated timestamps as relative percentages, mapping them to 
    Whisper's absolute real-world VAD timeline.
    """
    phrases = [p for p in gemini_phrases if p.get("phrase", "").strip()]
    if not phrases: return []
    
    # If whisper failed entirely, return gemini as-is
    if not whisper_words: 
        return phrases

    # Whisper anchors are guaranteed to be real spoken sound
    anchors = sorted(whisper_words, key=lambda x: x["start"])
    
    # ── 1. Timeline Normalization ──
    g_starts = [float(p.get("start", 0)) for p in phrases]
    g_min, g_max = min(g_starts), max(g_starts)
    
    # Failsafe for 0-duration Gemini outputs
    if g_max == g_min: g_max = g_min + 1.0 

    w_starts = [float(a["start"]) for a in anchors]
    w_min, w_max = min(w_starts), max(w_starts)
    if w_max == w_min: w_max = w_min + 1.0

    aligned = []
    last_end = 0.0
    MIN_DUR = 0.40

    for i, p in enumerate(phrases):
        g_time = float(p.get("start", 0))
        
        # ── 2. Calculate Elastic Progress ──
        # Where are we in the Gemini timeline? (0.0 to 1.0)
        progress = (g_time - g_min) / (g_max - g_min)
        
        # Project this progress onto the Whisper absolute timeline
        projected_w_time = w_min + progress * (w_max - w_min)
        
        # ── 3. Forward-Only Snapping ──
        # Find the nearest actual spoken anchor that hasn't been passed yet
        valid_anchors = [a for a in anchors if a["start"] >= last_end - 0.1]
        
        if valid_anchors:
            best_anchor = min(valid_anchors, key=lambda a: abs(a["start"] - projected_w_time))
            actual_start = best_anchor["start"]
        else:
            actual_start = max(last_end, projected_w_time)

        # Strict overlap prevention
        actual_start = max(actual_start, last_end) 

        # ── 4. Dynamic End Time Prediction ──
        if i + 1 < len(phrases):
            next_g_time = float(phrases[i+1].get("start", g_time + 1.0))
            next_prog = (next_g_time - g_min) / (g_max - g_min)
            next_proj_w = w_min + next_prog * (w_max - w_min)
            
            valid_next = [a for a in anchors if a["start"] > actual_start]
            if valid_next:
                next_anchor = min(valid_next, key=lambda a: abs(a["start"] - next_proj_w))
                # Cut the caption right before the next word hits
                actual_end = next_anchor["start"] - 0.05
            else:
                actual_end = next_proj_w - 0.05
        else:
            # Last phrase caps at the final Whisper anchor
            actual_end = anchors[-1]["end"] if anchors[-1]["end"] > actual_start else actual_start + 1.0

        # Enforce minimum readability duration
        if actual_end - actual_start < MIN_DUR:
            actual_end = actual_start + MIN_DUR

        aligned.append({
            "phrase": p["phrase"],
            "start": actual_start,
            "end": actual_end
        })
        last_end = actual_end

    # ── 5. Gap Fill Smoothing ──
    # Stretches captions across micro-pauses so the screen doesn't flicker black
    for i in range(len(aligned) - 1):
        gap = aligned[i + 1]["start"] - aligned[i]["end"]
        if 0 < gap <= 0.80:
            aligned[i]["end"] += gap * 0.85 

    return aligned


# ─────────────────────────────────────────────────────────────────────────────
# UPDATED stage_burn_sinhala_captions
# Key change: force Whisper into SEGMENT mode for Sinhala audio.
# Segment boundaries are 100% reliable; word boundaries on Sinhala are not.
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# UPDATED stage_burn_sinhala_captions
# Key change: Template Engine + Segment anchors
# ─────────────────────────────────────────────────────────────────────────────

def stage_burn_sinhala_captions(video_path: str, cap_options: dict) -> str:
    import json, shutil, subprocess, os
    from playwright.sync_api import sync_playwright

    base_dir   = os.path.dirname(os.path.abspath(video_path))
    output_vid = os.path.splitext(video_path)[0] + "_si_captioned.mp4"
    ovr_dir    = os.path.join(base_dir, "_cap_overlays_si")
    os.makedirs(ovr_dir, exist_ok=True)

    si_main_class = cap_options.get("siMainStyle", "si-main-blue")
    si_pri_class  = cap_options.get("siPrimaryStyle", "si-pri-silver")
    si_sec_class  = cap_options.get("siSecondaryStyle", "si-sec-gold")

    # NEW
    cap_bottom_pct = float(cap_options.get("captionBottomPercent", 22)) / 100.0

    # 1. Extract Audio
    temp_audio = os.path.join(base_dir, "_gemini_audio.wav")
    subprocess.run(
        ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
         "-ar", "16000", "-ac", "1", temp_audio, "-y"],
        check=True, capture_output=True
    )

    # 2. Get Perfect Phrases + Rough Timestamps from Gemini
    gemini_phrases = get_perfect_sinhala_transcript(temp_audio, cap_options.get("geminiApiKey"))

    if not gemini_phrases:
        print("[❌] FATAL: Gemini failed. Cannot render captions.")
        if os.path.exists(temp_audio): os.remove(temp_audio)
        return video_path

    print(f"[⚙️] Extracted {len(gemini_phrases)} Singlish phrases from Gemini.")

    # ── STEP 2: Whisper — SEGMENT MODE (most reliable for Sinhala) ───────────
    print("[⚙️] Running Whisper (base) — SEGMENT-ANCHOR mode for Sinhala...")
    whisper_words = []
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
            w_model = WhisperModel("base", device="cuda", compute_type="int8")
        except Exception:
            w_model = WhisperModel("base", device="cpu", compute_type="int8")

        w_segments_raw, _ = w_model.transcribe(
            temp_audio,
            word_timestamps=True,
            vad_filter=True,
            condition_on_previous_text=False
        )
        w_segments_list = list(w_segments_raw)

        for seg in w_segments_list:
            whisper_words.append({
                "word":  "[seg]",
                "start": seg.start,
                "end":   seg.end
            })

        word_anchors = []
        for seg in w_segments_list:
            for w in (seg.words or []):
                if w.word.strip():
                    word_anchors.append({
                        "word":  w.word.strip(),
                        "start": w.start,
                        "end":   w.end
                    })

        if len(word_anchors) >= len(gemini_phrases) * 1.5:
            combined = whisper_words + word_anchors
            combined.sort(key=lambda x: x["start"])
            deduped = [combined[0]] if combined else []
            for a in combined[1:]:
                if a["start"] - deduped[-1]["start"] > 0.05:
                    deduped.append(a)
            whisper_words = deduped
            print(f"[⚙️] Using {len(w_segments_list)} segment + {len(word_anchors)} word anchors "
                  f"→ {len(whisper_words)} total after dedup.")
        else:
            print(f"[⚙️] Using {len(whisper_words)} segment-level anchors "
                  f"(word anchors too sparse: {len(word_anchors)}).")

    except Exception as e:
        print(f"[⚠️] Whisper failed ({e}). Falling back to Gemini timestamps.")
        whisper_words = []

    # ── STEP 3: Drift-corrected alignment ────────────────────────────────────
    if whisper_words:
        segments_data = align_phrases_to_whisper(gemini_phrases, whisper_words)
        print(f"[✅] Alignment done — {len(segments_data)} synced phrases.")
    else:
        print("[⚠️] Using Gemini timestamps with +0.10s offset as fallback.")
        segments_data = [
            {"phrase": p["phrase"],
             "start":  p["start"] + 0.10,
             "end":    p["end"]   + 0.10}
            for p in gemini_phrases
        ]

    # ── NEW: Extract the Director's Cuts (|) for the Transition Engine ──
    flash_times = []
    for i, item in enumerate(segments_data):
        phrase_text = str(item.get("phrase", ""))
        
        # Look for the pipe symbol Gemini dropped
        if "|" in phrase_text:
            # We want the transition to hit exactly as the NEXT sentence starts
            if i + 1 < len(segments_data):
                flash_times.append(float(segments_data[i+1]["start"]))
                
    with open(os.path.join(base_dir, "_flash_times.json"), "w") as f:
        json.dump(flash_times, f)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate",
         "-of", "json", video_path],
        capture_output=True, text=True
    )
    info_json = json.loads(probe.stdout)["streams"][0]
    W, H = int(info_json["width"]), int(info_json["height"])

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
    position: absolute; bottom: {int(height * cap_bottom_pct)}px; left: 0; right: 0;
    padding: 0 {int(width * 0.08)}px;
    text-align: center;
  }}
  .phrase-cap {{
    display: inline-block; line-height: 1.3; margin: 0 6px;
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text; color: transparent;
  }}
  .si-font-main {{ font-family: 'Gemunu Libre', sans-serif; font-weight: 800; }}
  .si-font-pri {{ font-family: 'Montserrat', sans-serif; font-weight: 900; letter-spacing: -0.5px; }}
  .si-font-sec {{ font-family: 'Montserrat', sans-serif; font-weight: 900; letter-spacing: -1px; }}

  /* Main (Sinhala) */
  .si-main-blue {{ background-image: linear-gradient(to bottom, #82cfff 0%, #0077ff 100%); filter: drop-shadow(0 0 12px rgba(0, 100, 255, 0.9)) drop-shadow(0 3px 5px rgba(0,0,0,0.9)); }}
  .si-main-emerald {{ background-image: linear-gradient(to bottom, #34d399 0%, #059669 100%); filter: drop-shadow(0 0 10px rgba(16, 185, 129, 0.6)) drop-shadow(0 2px 4px rgba(0,0,0,0.8)); }}
  .si-main-crimson {{ background-image: linear-gradient(to bottom, #fb7185 0%, #e11d48 100%); filter: drop-shadow(0 0 12px rgba(225, 29, 72, 0.7)) drop-shadow(0 3px 6px rgba(0,0,0,0.9)); }}
  .si-main-amber {{ background-image: linear-gradient(to bottom, #fcd34d 0%, #d97706 100%); filter: drop-shadow(0 0 10px rgba(217, 119, 6, 0.6)) drop-shadow(0 2px 4px rgba(0,0,0,0.9)); }}
  .si-main-purple {{ background-image: linear-gradient(to right, #e879f9 0%, #a21caf 100%); filter: drop-shadow(0 0 12px rgba(192, 38, 211, 0.7)) drop-shadow(0 2px 5px rgba(0,0,0,0.9)); }}
  .si-main-white {{ background-image: linear-gradient(to bottom, #ffffff 0%, #e5e5e5 100%); filter: drop-shadow(0 4px 6px rgba(0,0,0,1)) drop-shadow(0 1px 3px rgba(0,0,0,0.8)); }}

  /* Primary (English) */
  .si-pri-silver {{ background-image: linear-gradient(160deg, #ffffff 0%, #d2e8ff 30%, #b4d7ff 60%, #ffffff 100%); filter: drop-shadow(0 0 10px rgba(140,185,255,0.5)) drop-shadow(0 2px 4px rgba(0,0,0,0.8)); }}
  .si-pri-gold {{ background-image: linear-gradient(160deg, #fef08a 0%, #eab308 50%, #ca8a04 100%); filter: drop-shadow(0 0 8px rgba(234, 179, 8, 0.4)) drop-shadow(0 2px 4px rgba(0,0,0,0.8)); }}
  .si-pri-cyan {{ background-image: linear-gradient(to bottom, #67e8f9 0%, #06b6d4 100%); filter: drop-shadow(0 0 10px rgba(6, 182, 212, 0.6)) drop-shadow(0 2px 4px rgba(0,0,0,0.9)); }}
  .si-pri-magenta {{ background-image: linear-gradient(to right, #f472b6 0%, #db2777 100%); filter: drop-shadow(0 0 10px rgba(219, 39, 119, 0.6)) drop-shadow(0 2px 4px rgba(0,0,0,0.9)); }}
  .si-pri-slate {{ background-image: linear-gradient(to bottom, #cbd5e1 0%, #64748b 100%); filter: drop-shadow(0 3px 8px rgba(0,0,0,1)) drop-shadow(0 1px 2px rgba(0,0,0,0.9)); }}
  .si-pri-neon-green {{ background-image: linear-gradient(to bottom, #bef264 0%, #65a30d 100%); filter: drop-shadow(0 0 12px rgba(101, 163, 13, 0.7)) drop-shadow(0 2px 4px rgba(0,0,0,0.9)); }}

  /* Secondary (Numbers) */
  .si-sec-gold {{ background-image: linear-gradient(to bottom, #FFE81F 0%, #FF8A00 100%); filter: drop-shadow(0 0 15px rgba(255,165,0,0.6)) drop-shadow(0 3px 6px rgba(0,0,0,0.9)); }}
  .si-sec-red {{ background-image: linear-gradient(to bottom, #fca5a5 0%, #dc2626 100%); filter: drop-shadow(0 0 12px rgba(220, 38, 38, 0.8)) drop-shadow(0 3px 5px rgba(0,0,0,0.9)); }}
  .si-sec-lime {{ background-image: linear-gradient(to bottom, #d9f99d 0%, #65a30d 100%); filter: drop-shadow(0 0 12px rgba(132, 204, 22, 0.8)) drop-shadow(0 3px 5px rgba(0,0,0,0.9)); }}
  .si-sec-pink {{ background-image: linear-gradient(to bottom, #f9a8d4 0%, #db2777 100%); filter: drop-shadow(0 0 12px rgba(219, 39, 119, 0.8)) drop-shadow(0 3px 5px rgba(0,0,0,0.9)); }}
  .si-sec-aqua {{ background-image: linear-gradient(to bottom, #7dd3fc 0%, #0284c7 100%); filter: drop-shadow(0 0 12px rgba(2, 132, 199, 0.8)) drop-shadow(0 3px 5px rgba(0,0,0,0.9)); }}
  .si-sec-white {{ background-image: linear-gradient(to bottom, #ffffff 0%, #f3f4f6 100%); filter: drop-shadow(0 0 15px rgba(255,255,255,0.5)) drop-shadow(0 4px 6px rgba(0,0,0,1)); }}
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
            # Grab the raw text first
            raw_text = str(item.get("phrase", "")).strip()
            if not raw_text: continue
            
            # THE MAGIC TRICK: Strip the pipe and any weird punctuation so it never renders on screen
            phrase_text = raw_text.replace("|", "").replace(".", "").replace(",", "").strip()

            start_time = float(item.get("start", 0))
            end_time   = float(item.get("end", start_time + 1.0))

            png_path   = os.path.join(ovr_dir, f"cap_phrase_{i:04d}.png")

            char_count = len(phrase_text)
            if   char_count <= 15: font_size = int(H * 0.055)
            elif char_count <= 25: font_size = int(H * 0.045)
            else:                  font_size = int(H * 0.038)

            page.evaluate("""
                (args) => {
                    const el = document.getElementById('phrase_box');
                    const words = args.text.split(' ').filter(w => w.trim() !== '');
                    let innerHtml = '';
                    const midPoint = Math.ceil(words.length / 2);
                    words.forEach((word, index) => {
                        let className = '';
                        let baseClass = '';
                        let size = args.fontSize;
                        if (/\\d+/.test(word)) {
                            className = args.secClass;
                            baseClass = 'si-font-sec';
                        } else if (/[A-Za-z]/.test(word)) {
                            className = args.priClass;
                            baseClass = 'si-font-pri';
                        } else {
                            className = args.mainClass;
                            baseClass = 'si-font-main';
                            size += 5;
                        }
                        innerHtml += `<span class="phrase-cap ${baseClass} ${className}" style="font-size: ${size}px;">${word}</span>`;
                        if (words.length >= 3 && index === midPoint - 1) {
                            innerHtml += '<br>';
                        }
                    });
                    el.innerHTML = innerHtml;
                }
            """, {
                "text": phrase_text, "fontSize": font_size,
                "mainClass": si_main_class, "priClass": si_pri_class, "secClass": si_sec_class
            })

            page.screenshot(path=png_path, full_page=False, omit_background=True)
            segments_arr.append((start_time, end_time, png_path, phrase_text, None))

        browser.close()

    # ── FFmpeg overlay — batched with Dynamic Mathematical Animations ─────────
    print("[⚙️] Compositing Sinhala captions with cinematic motion math...")

    CHUNK = 50
    current_video = video_path
    anim_style = cap_options.get("captionAnimation", "spring-up")
    dur = 0.15

    for chunk_start in range(0, len(segments_arr), CHUNK):
        chunk     = segments_arr[chunk_start: chunk_start + CHUNK]
        chunk_out = os.path.join(base_dir, f"_chunk_{chunk_start:04d}.mp4")

        inputs = ["ffmpeg", "-i", current_video]
        for _, _, path, _, _ in chunk:
            inputs += ["-i", path]

        filter_parts = []
        for idx, (t_s, t_e, _, _, _) in enumerate(chunk):
            in_lbl  = f"[v{idx}]" if idx > 0 else "[0:v]"
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

            filter_parts.append(f"{in_lbl}{inp_lbl}overlay={overlay_cmd}{out_lbl}")

        cmd = inputs + [
            "-filter_complex", ";".join(filter_parts),
            "-map", f"[v{len(chunk)}]", "-map", "0:a:0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "17",
            "-pix_fmt", "yuv420p", "-c:a", "copy", chunk_out, "-y"
        ]

        import subprocess as _sp
        _sp.run(cmd, check=True, capture_output=True)

        if current_video != video_path and os.path.exists(current_video):
            os.remove(current_video)
        current_video = chunk_out

    if current_video != video_path:
        os.replace(current_video, output_vid)
    else:
        import shutil
        shutil.copy(video_path, output_vid)

    import shutil
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

    # 2. Viral Hook Dictionaries (English + Sinhala/Singlish)
    en_hooks = [
        "important", "secret", "listen", "stop", "never", "always", 
        "money", "hack", "trick", "reason", "best", "worst", "look", 
        "insane", "crazy", "truth", "give", "warning", "attention"
    ]
    si_hooks = [
        "වැදගත්", "රහස", "අහන්න", "බලන්න", "සල්ලි", "හේතුව", "හොඳම", 
        "පිස්සුවක්", "ඇත්ත", "අනිවාර්යයෙන්", "scam", "trick", "money", 
        "direct", "skill" , "professional field engineer" , "field engineer"
    ]

    zoom_intervals = []
    lang = zoom_options.get("captionLanguage", "en")

    # 3. Branching Logic: Gemini for Sinhala, Whisper for English
    if lang == "si":
        print("[⚙️] Using Gemini to detect Sinhala hook words for zooming...")
        # Re-using your custom Gemini extraction function
        phrases = get_perfect_sinhala_transcript(temp_audio, zoom_options.get("geminiApiKey"))
        
        for p in phrases:
            phrase_text = p.get("phrase", "").lower()
            # Check if any hook word exists inside the Gemini phrase
            if any(hook in phrase_text for hook in si_hooks + en_hooks):
                start = float(p.get("start", 0))
                zoom_intervals.append((start, start + 2.5))
    else:
        print("[⚙️] Using Whisper to detect English hook words for zooming...")
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

        for seg in list(w_segments_raw):
            for w in (seg.words or []):
                clean_word = w.word.strip().lower()
                clean_word = ''.join(e for e in clean_word if e.isalnum())

                if clean_word in en_hooks:
                    start = w["start"]
                    zoom_intervals.append((start, start + 2.5))

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
    duration = float(zoom_options.get("zoomSpeed", 0.5))
    zoom_speed = (intensity - 1.0) / (fps * duration)
    
    z_expr = "1"
    for (start, end) in zoom_intervals:
        z_expr = f"if(between(time,{start:.2f},{end:.2f}), min(pzoom+{zoom_speed:.5f},{intensity}), {z_expr})"

    x_expr = f"({W}-({W}/zoom))/2"
    y_expr = f"({H}-({H}/zoom))/2"

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

    # ── Composite captions in CHUNKS of 40 ──
    print("[⚙️] [OVERLAY EXPORT] Compositing onto Green Screen MP4...")
    dur   = 0.15
    CHUNK = 40  

    def _build_overlay_filter(chunk, anim_style, dur):
        parts = []
        for idx, (t_s, t_e, _, _, _) in enumerate(chunk):
            in_lbl  = "[0:v]" if idx == 0 else f"[v{idx}]"
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
                
            # FIXED: Removed eof_action=pass. FFmpeg will now hold the image correctly.
            parts.append(
                f"{in_lbl}{inp_lbl}overlay={overlay_cmd}{out_lbl}"
            )
        return parts

    current_base = None
    chunk_files  = []
    output_vid = os.path.splitext(video_path)[0] + "_captions_overlay_en.mp4"

    for chunk_start in range(0, len(segments), CHUNK):
        chunk     = segments[chunk_start: chunk_start + CHUNK]
        chunk_out = os.path.join(base_dir, f"_ovr_en_chunk_{chunk_start:04d}.mp4")
        chunk_files.append(chunk_out)

        if current_base is None:
            # Generate pure Green Screen base
            inputs_cmd = [
                "ffmpeg", "-f", "lavfi", "-i",
                f"color=c=green:size={W}x{H}:rate={fps}:duration={duration}"
            ]
        else:
            inputs_cmd = ["ffmpeg", "-i", current_base]

        for _, _, path, _, _ in chunk:
            inputs_cmd += ["-i", path]

        filter_parts = _build_overlay_filter(chunk, anim_style, dur)

        # Standard compressed MP4 output
        cmd = inputs_cmd + [
            "-filter_complex", ";".join(filter_parts),
            "-map", f"[v{len(chunk)}]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", 
            "-pix_fmt", "yuv420p",
            chunk_out, "-y"
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        current_base = chunk_out

    os.replace(current_base, output_vid)
    for f in chunk_files[:-1]:
        if os.path.exists(f): os.remove(f)

    shutil.rmtree(ovr_dir, ignore_errors=True)
    if os.path.exists(temp_audio): os.remove(temp_audio)

    print(f"[✅] [OVERLAY EXPORT] Green Screen overlay saved: {output_vid}")
    print(f"[📋] Import into CapCut and use 'Remove BG -> Chroma Key -> Pick Green'.")
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
temp_audio, 
            word_timestamps=True,
            vad_filter=True,              # ← Turn this back ON to trim silence
            condition_on_previous_text=False               # ← Force Sinhala so it doesn't bail out
        )
        w_segs_list  = list(w_segs_raw)
        whisper_words = []
        for seg in w_segs_list:
            for w in (seg.words or []):
                if w.word.strip():
                    whisper_words.append({"word": w.word.strip(), "start": w.start, "end": w.end})
        if len(whisper_words) < len(gemini_phrases) // 2:
            print(f"[⚠️] Sparse word timestamps ({len(whisper_words)}) — using segment boundaries.")
            whisper_words = [{"word": "[seg]", "start": seg.start, "end": seg.end}
                             for seg in w_segs_list]
        print(f"[⚙️] Whisper found {len(whisper_words)} timestamp anchors.")
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
    print("[⚙️] [OVERLAY EXPORT] Compositing Sinhala captions onto Green Screen MP4...")
    dur   = 0.15
    CHUNK = 40

    def _build_si_filter(chunk, anim_style, dur):
        parts = []
        for idx, (t_s, t_e, _, _, _) in enumerate(chunk):
            in_lbl  = "[0:v]" if idx == 0 else f"[v{idx}]"
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
                
            # FIXED: Removed eof_action=pass
            parts.append(
                f"{in_lbl}{inp_lbl}overlay={overlay_cmd}{out_lbl}"
            )
        return parts

    current_base = None
    chunk_files  = []
    output_vid = os.path.splitext(video_path)[0] + "_captions_overlay_si.mp4"

    for chunk_start in range(0, len(segments_arr), CHUNK):
        chunk     = segments_arr[chunk_start: chunk_start + CHUNK]
        chunk_out = os.path.join(base_dir, f"_ovr_si_chunk_{chunk_start:04d}.mp4")
        chunk_files.append(chunk_out)

        if current_base is None:
            # Generate pure Green Screen base
            inputs_cmd = [
                "ffmpeg", "-f", "lavfi", "-i",
                f"color=c=green:size={W}x{H}:rate={fps}:duration={duration}"
            ]
        else:
            inputs_cmd = ["ffmpeg", "-i", current_base]

        for _, _, path, _, _ in chunk:
            inputs_cmd += ["-i", path]

        filter_parts = _build_si_filter(chunk, anim_style, dur)

        cmd = inputs_cmd + [
            "-filter_complex", ";".join(filter_parts),
            "-map", f"[v{len(chunk)}]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", 
            "-pix_fmt", "yuv420p",
            chunk_out, "-y"
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        current_base = chunk_out

    os.replace(current_base, output_vid)
    for f in chunk_files[:-1]:
        if os.path.exists(f): os.remove(f)

    shutil.rmtree(ovr_dir, ignore_errors=True)
    if os.path.exists(temp_audio): os.remove(temp_audio)

    print(f"[✅] [OVERLAY EXPORT] Green Screen overlay saved: {output_vid}")
    print(f"[📋] Import into CapCut and use 'Remove BG -> Chroma Key -> Pick Green'.")
    return output_vid


# ─────────────────────────────────────────────
# 11. AUTO TRANSITIONS ENGINE
# ─────────────────────────────────────────────

def stage_hardcode_flash(video_path: str, options: dict) -> str:
    import subprocess
    import os
    import json

    print("[⚙️] Loading AI Director timestamps for Hardcoded Camera Flashes...")
    base_dir = os.path.dirname(os.path.abspath(video_path))
    output_vid = os.path.splitext(video_path)[0] + "_flashes.mp4"
    json_path = os.path.join(base_dir, "_flash_times.json")
    
    engine_dir = os.path.dirname(os.path.abspath(__file__))
    sfx_audio = os.path.join(engine_dir, "assets", "whoosh_sfx.MP3") 

    flash_times = []
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            flash_times = json.load(f)
        os.remove(json_path) # Clean up

    if not flash_times:
        print("[⚙️] No cinematic cuts (|) detected. Skipping transitions.")
        return video_path

    print(f"[🎬] Found {len(flash_times)} precise Director cuts. Compositing Camera Flashes...")

    # 1. VISUAL: Hardcode the math for the camera flash fade
    # This spikes the brightness to 1.0 (pure white) and fades to 0.0 (normal) over 0.3 seconds
    exprs = []
    for t in flash_times:
        exprs.append(f"if(between(t,{t:.3f},{t+0.3:.3f}), 1-(t-{t:.3f})/0.3, 0)")
    
    full_expr = " + ".join(exprs)
    vf_chain = f"eq=eval=frame:brightness='{full_expr}'"

    # 2. AUDIO: Map your whoosh_sfx.MP3 to the exact same timestamps
    inputs = ["-i", video_path]
    filter_complex_a = ""
    audio_mix_inputs = "[0:a]"
    audio_map = "0:a"
    
    has_sfx = os.path.exists(sfx_audio)
    if has_sfx:
        inputs.extend(["-i", sfx_audio])
        for idx, t_start in enumerate(flash_times):
            aud_out = f"[a_delayed_{idx}]"
            delay_ms = int(max(0, t_start) * 1000)
            # [1:a] is the SFX file
            filter_complex_a += f"[1:a]adelay={delay_ms}|{delay_ms}{aud_out};"
            audio_mix_inputs += aud_out
            
        total_inputs = len(flash_times) + 1
        filter_complex_a += f"{audio_mix_inputs}amix=inputs={total_inputs}:duration=first:dropout_transition=2:normalize=0[a_final]"
        audio_map = "[a_final]"
    else:
        print("[⚠️] whoosh_sfx.MP3 missing in assets/. Proceeding with visual flash only.")

    # 3. Execution
    cmd = ["ffmpeg"] + inputs
    
    if has_sfx:
        cmd.extend(["-filter_complex", filter_complex_a])
    
    cmd.extend([
        "-vf", vf_chain,
        "-map", "0:v",
        "-map", audio_map,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        output_vid, "-y"
    ])

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"[✅] Hardcoded Camera Flashes applied over everything: {output_vid}")
        return output_vid
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        print(f"[❌] Flashes failed: {err_msg}")
        return video_path


# ─────────────────────────────────────────────
# 12. AI CONTEXTUAL B-ROLL ENGINE (Native Playwright Record)
# ─────────────────────────────────────────────

def stage_ai_broll(video_path: str, options: dict) -> str:
    import os
    import json
    import time
    import shutil
    import subprocess
    import google.generativeai as genai
    from playwright.sync_api import sync_playwright

    print("[⚙️] Booting AI B-Roll Director Engine (Real-Time Record Mode)...")
    api_key = options.get("geminiApiKey") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[❌] FATAL: Gemini API Key required for AI B-Roll.")
        return video_path

    base_dir = os.path.dirname(os.path.abspath(video_path))
    temp_audio = os.path.join(base_dir, "_broll_audio.wav")
    output_vid = os.path.splitext(video_path)[0] + "_with_broll.mp4"
    
    engine_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(engine_dir, "assets", "broll-template.html")

    if not os.path.exists(template_path):
        print(f"[❌] FATAL: Template not found at {template_path}")
        return video_path

    # 1. Extract Audio & Get Gemini Data
    subprocess.run(["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", temp_audio, "-y"], check=True, capture_output=True)

    def _run_broll_gemini(current_key):
        genai.configure(api_key=current_key)
        print("[⚙️] Uploading audio to Gemini for structural analysis...")
        audio_file = genai.upload_file(path=temp_audio)
        
        while audio_file.state.name == "PROCESSING":
            time.sleep(2)
            audio_file = genai.get_file(audio_file.name)

        prompt = """
        Listen to this audio. Act as a high-end YouTube Video Editor.
        Identify EXACTLY 1 or 2 highly impactful 'hook' moments in the speech.
        For each moment, design a cinematic kinetic typography B-Roll screen.
        
        Return a JSON array of objects. EACH OBJECT MUST HAVE:
        - text: 2 to 4 words summarizing the moment. Use \\n for a line break.
        - icon: A Phosphor icon name (e.g., "lightning", "money", "rocket").
        - color: A vibrant hex color (e.g., "#ef4444", "#10b981").
        - start: Exact start time of the phrase in seconds.
        - duration: How long the B-Roll stays on screen (between 2.5 and 4.0 seconds).
        
        Output strictly as raw JSON.
        """
        print("[⚙️] AI Director is choosing the B-Roll moments...")
        model = genai.GenerativeModel('gemini-flash-latest')
        response = model.generate_content([prompt, audio_file], generation_config={"response_mime_type": "application/json"})
        genai.delete_file(audio_file.name)

        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        moments = json.loads(clean_text)
        print(f"[🎬] AI Director found {len(moments)} key moments.")
        return moments

    broll_moments = None
    if api_key:
        try:
            broll_moments = _run_broll_gemini(api_key)
        except Exception as e:
            print(f"[⚠️] Gemini API Error with primary key: {e}")
            from dotenv import load_dotenv
            load_dotenv(os.path.join(engine_dir, ".env")) # Ensure fresh keys
            bypass_key = os.getenv("GEMINI_API_KEY_BYPASS")
            if bypass_key:
                print("[⚙️] Retrying with GEMINI_API_KEY_BYPASS...")
                try:
                    broll_moments = _run_broll_gemini(bypass_key)
                except Exception as e2:
                    print(f"[❌] Gemini API Error with bypass key as well: {e2}")
            else:
                print("[❌] No bypass key found.")

    if not broll_moments:
        return video_path

    # 2. RECORD VIDEO NATIVELY VIA PLAYWRIGHT
    broll_video_files = []
    playwright_vid_dir = os.path.join(base_dir, "_playwright_vids")
    os.makedirs(playwright_vid_dir, exist_ok=True)
    
    with sync_playwright() as p:
        # Launch with hardware acceleration
        browser = p.chromium.launch(
            headless=True,
            args=["--enable-gpu", "--use-gl=egl", "--mute-audio"]
        )
        
        # ── THE MAGIC: Tell Playwright to natively record the screen to .webm ──
        context = browser.new_context(
            viewport={"width": 1080, "height": 1920},
            device_scale_factor=1,
            record_video_dir=playwright_vid_dir,
            record_video_size={"width": 1080, "height": 1920}
        )
        
        for idx, moment in enumerate(broll_moments):
            print(f"  ↳ Recording Template {idx+1}: '{moment['text'].replace(chr(10), ' ')}'")
            page = context.new_page()
            
            # Load the file, wait for fonts
            page.goto(f"file://{os.path.abspath(template_path)}")
            page.wait_for_load_state("networkidle")

            dur = float(moment.get("duration", 3.0))
            
            # Trigger the animation
            page.evaluate(f"""
                window.injectData(
                    `{moment['text']}`, '{moment['icon']}', '{moment['color']}', {dur}
                );
            """)

            # ── The Engine just waits while Chromium records itself ──
            print(f"    [⏳] Recording {dur} seconds of video in real-time...")
            page.wait_for_timeout(int(dur * 1000))
            
            # Closing the page flushes the video file to disk
            page.close()
            
            # Playwright saves it with a random hash name. We grab it and rename it.
            recorded_vid_path = page.video.path()
            final_clip_path = os.path.join(base_dir, f"_broll_clip_{idx}.webm")
            os.rename(recorded_vid_path, final_clip_path)
            
            broll_video_files.append({"path": final_clip_path, "start": float(moment["start"]), "dur": dur})

        browser.close()

    # 3. Composite the B-Roll clips over the main video timeline
    print("[⚙️] Compositing B-Roll layers into main timeline...")
    
    inputs_cmd = ["ffmpeg", "-i", video_path]
    for b in broll_video_files:
        inputs_cmd += ["-i", b["path"]]

    filter_complex = ""
    last_out = "[0:v]"
    
    for idx, b in enumerate(broll_video_files):
        stream_idx = idx + 1
        start_t = b["start"]
        dur_t = b["dur"]
        
        shifted_lbl = f"[broll_{idx}_shifted]"
        filter_complex += f"[{stream_idx}:v]setpts=PTS-STARTPTS+{start_t}/TB{shifted_lbl};"
        
        out_lbl = f"[v_out_{idx}]"
        filter_complex += f"{last_out}{shifted_lbl}overlay=enable='between(t,{start_t},{start_t}+{dur_t})':eof_action=pass{out_lbl};"
        last_out = out_lbl

    filter_complex = filter_complex.rstrip(';')

    cmd = inputs_cmd + [
        "-filter_complex", filter_complex,
        "-map", last_out,
        "-map", "0:a", 
        "-c:v", "libx264", "-preset", "fast", "-crf", "17",
        "-pix_fmt", "yuv420p", "-c:a", "copy",
        output_vid, "-y"
    ]
    
    subprocess.run(cmd, check=True, capture_output=True)

    # Clean up temp clips and the Playwright recording directory
    for b in broll_video_files:
        if os.path.exists(b["path"]): os.remove(b["path"])
    shutil.rmtree(playwright_vid_dir, ignore_errors=True)
    if os.path.exists(temp_audio): os.remove(temp_audio)

    print(f"[✅] AI Contextual B-Roll injected: {output_vid}")
    return output_vid

def stage_mask_engine(video_path: str, options: dict) -> str:
    import subprocess, os, json
    from PIL import Image, ImageDraw

    print("[⚙️] Applying Mask Engine (GPU-Accelerated)...")
    base_dir = os.path.dirname(os.path.abspath(video_path))
    output_vid = os.path.splitext(video_path)[0] + "_masked.mp4"
    mask_png   = os.path.join(base_dir, "_rounded_mask.png")

    ratio_str     = options.get("maskRatio", "9:16")
    border_radius = int(options.get("maskBorderRadius", 30))
    mask_scale    = float(options.get("maskScale", 85)) / 100.0
    bg_mode       = options.get("maskBgMode", "color")
    bg_color      = options.get("maskBgColor", "#09090b").lstrip('#')
    bg_image      = options.get("maskBgImagePath", "")

    # ── 1. Probe source dimensions ────────────────────────────────────────
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "json", video_path],
        capture_output=True, text=True
    )
    info = json.loads(probe.stdout)["streams"][0]
    W, H = int(info["width"]), int(info["height"])

    try:
        rw, rh = map(int, ratio_str.split(':'))
    except Exception:
        rw, rh = 9, 16

    # ── 2. Compute crop + mask dimensions ────────────────────────────────
    if (W / H) > (rw / rh):
        orig_crop_h = H
        orig_crop_w = int(H * (rw / rh))
    else:
        orig_crop_w = W
        orig_crop_h = int(W * (rh / rw))

    max_w = int(W * mask_scale)
    max_h = int(H * mask_scale)

    if (max_w / max_h) > (rw / rh):
        mask_h = max_h
        mask_w = int(max_h * (rw / rh))
    else:
        mask_w = max_w
        mask_h = int(max_w * (rh / rw))

    # Force even numbers (required by libx264 / NVENC)
    mask_w = mask_w - (mask_w % 2)
    mask_h = mask_h - (mask_h % 2)
    orig_crop_w = orig_crop_w - (orig_crop_w % 2)
    orig_crop_h = orig_crop_h - (orig_crop_h % 2)

    # ── 3. Pre-bake the rounded-corner alpha mask (PIL, CPU once) ─────────
    mask_img = Image.new("L", (mask_w, mask_h), 0)
    draw = ImageDraw.Draw(mask_img)
    draw.rounded_rectangle((0, 0, mask_w, mask_h), radius=border_radius, fill=255)
    mask_img.save(mask_png)

    # ── 4. Detect GPU availability ────────────────────────────────────────
    def _gpu_available() -> bool:
        try:
            out = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                capture_output=True, text=True
            ).stdout
            return "h264_nvenc" in out
        except Exception:
            return False

    use_gpu = _gpu_available()
    if use_gpu:
        print("[⚙️] NVENC GPU detected — using hardware acceleration.")
    else:
        print("[⚙️] No NVENC found — falling back to CPU libx264.")

    # ── 5. Build filter graph ─────────────────────────────────────────────
    #
    # CPU path  — same alphamerge logic you had, but tighter.
    # GPU path  — upload to CUDA, scale on GPU, stay in GPU memory for encode.
    #
    # The key speed win on GPU is:
    #   hwupload_cuda → scale_cuda (GPU resize, no CPU round-trip)
    #   → hwdownload (only for the overlay composite, which is CPU-side)
    #   Then NVENC encodes directly from GPU memory.
    #
    # alphamerge itself is a CPU filter so we keep it there, but the heavy
    # resize and encode are offloaded — that's where 80% of the time goes.

    inputs = ["ffmpeg",
              "-i", video_path,          # [0] source video
              "-loop", "1", "-i", mask_png]  # [1] mask image

    bg_idx = 2

    if bg_mode == "image" and os.path.exists(bg_image):
        inputs.extend(["-loop", "1", "-i", bg_image])
        bg_filter = (
            f"[{bg_idx}:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H}[bg];"
        )
    else:
        # Solid colour background — generated inline (no extra input stream)
        bg_filter = f"color=c=0x{bg_color}:s={W}x{H}[bg];"
        # bg_idx not consumed so overlay index is correct either way

    if use_gpu:
        # Crop + scale on GPU, alphamerge on CPU (alphamerge has no CUDA variant)
        v_filter = (
            # Crop source to target ratio, scale to mask size, keep in CUDA
            f"[0:v]crop={orig_crop_w}:{orig_crop_h}:"
            f"(in_w-{orig_crop_w})/2:(in_h-{orig_crop_h})/2,"
            f"hwupload_cuda,scale_cuda={mask_w}:{mask_h},"
            f"hwdownload,format=rgba[cropped];"
            # alphamerge = apply rounded-corner transparency
            f"[cropped][1:v]alphamerge[masked];"
            # Composite masked clip over background
            f"{bg_filter}"
            f"[bg][masked]overlay=(W-w)/2:(H-h)/2:eof_action=pass[outv]"
        )
        encode_flags = [
            "-c:v", "h264_nvenc",
            "-preset", "p4",          # balanced quality/speed (p1=fastest … p7=best)
            "-rc", "vbr",
            "-cq", "19",              # visually lossless on NVENC
            "-b:v", "0",
            "-pix_fmt", "yuv420p",
        ]
    else:
        v_filter = (
            f"[0:v]crop={orig_crop_w}:{orig_crop_h}:"
            f"(in_w-{orig_crop_w})/2:(in_h-{orig_crop_h})/2,"
            f"scale={mask_w}:{mask_h},format=rgba[cropped];"
            f"[cropped][1:v]alphamerge[masked];"
            f"{bg_filter}"
            f"[bg][masked]overlay=(W-w)/2:(H-h)/2:eof_action=pass[outv]"
        )
        encode_flags = [
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
        ]

    cmd = inputs + [
        "-filter_complex", v_filter,
        "-map", "[outv]",
        "-map", "0:a?",
        *encode_flags,
        # ── Threading hints for the CPU filters (crop/alphamerge) ──
        "-threads", "0",          # use all CPU cores
        output_vid, "-y"
    ]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True)
        if os.path.exists(mask_png):
            os.remove(mask_png)
        print(f"[✅] Mask Engine done ({'NVENC' if use_gpu else 'CPU'}): {output_vid}")
        return output_vid
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        if os.path.exists(mask_png):
            os.remove(mask_png)
        print(f"[❌] Mask Engine failed: {err_msg}")
        return video_path
# ─────────────────────────────────────────────
# 13. 3D DEPTH ENGINE (TEXT BEHIND SUBJECT)
# ─────────────────────────────────────────────

def stage_3d_depth(raw_vid_path: str, cap_vid_path: str) -> str:
    import cv2, numpy as np, mediapipe as mp, subprocess, os
    
    print("[⚙️] Booting 3D Depth Engine (Compositing Text Behind Subject)...")
    base_dir = os.path.dirname(os.path.abspath(raw_vid_path))
    temp_vid = os.path.join(base_dir, "_temp_3d_depth.mp4")
    output_vid = os.path.splitext(cap_vid_path)[0] + "_3d.mp4"

    engine_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(engine_dir, "pretrained_models", "selfie_segmenter.tflite")
    
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision
    
    base_options = mp_python.BaseOptions(model_asset_path=model_path)
    options = vision.ImageSegmenterOptions(base_options=base_options, output_confidence_masks=True)

    cap_raw = cv2.VideoCapture(raw_vid_path)
    cap_cap = cv2.VideoCapture(cap_vid_path)

    fps = cap_raw.get(cv2.CAP_PROP_FPS)
    w = int(cap_raw.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap_raw.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(temp_vid, fourcc, fps, (w, h))

    print("[⚙️] Sandwiching layers frame-by-frame...")
    with vision.ImageSegmenter.create_from_options(options) as segmenter:
        while cap_raw.isOpened() and cap_cap.isOpened():
            ret_r, frame_r = cap_raw.read()
            ret_c, frame_c = cap_cap.read()
            if not ret_r or not ret_c: break

            # Segment the pristine RAW frame (no text in the way)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame_r, cv2.COLOR_BGR2RGB))
            results = segmenter.segment(mp_image)

            # Extract mask and apply a cinematic soft feather to the edges
            mask = np.squeeze(results.confidence_masks[0].numpy_view())
            mask_blur = cv2.GaussianBlur(mask, (5, 5), 0)
            alpha = np.stack((mask_blur,) * 3, axis=-1)

            # Pro Alpha Blend: Subject (Raw) on top, Captions (Cap) on the bottom
            output_frame = (frame_r * alpha + frame_c * (1.0 - alpha)).astype(np.uint8)
            out.write(output_frame)

    cap_raw.release()
    cap_cap.release()
    out.release()

    print("[⚙️] Remuxing final audio...")
    subprocess.run([
        "ffmpeg", "-i", temp_vid, "-i", cap_vid_path,
        "-c:v", "libx264", "-preset", "fast", "-crf", "17",
        "-c:a", "copy", "-map", "0:v:0", "-map", "1:a:0",
        "-shortest", output_vid, "-y"
    ], check=True, capture_output=True)

    if os.path.exists(temp_vid): os.remove(temp_vid)
    print(f"[✅] 3D Depth effect perfectly applied: {output_vid}")
    return output_vid


def run_pipeline(video_path: str, options_json: str) -> None:
    options = json.loads(options_json)
    print(f"\n[🎬] STARTING LOCAL RENDER ENGINE: {os.path.basename(video_path)}\n")

    if not os.path.exists(video_path):
        print(f"[❌] FATAL: Input video not found at path: {video_path}")
        print("Please re-select the video in the UI.")
        return

    current_video = video_path

    # ── NEW: Extract MP3 independently of the video pipeline ──
    if options.get("extractMp3"):
        stage_extract_mp3(current_video)

    # Stage order matters for efficiency:
    # 1. Chop dead air first — don't waste CPU grading silence
    # 2. Enhance the audio on the chopped clip
    # 3. Bake the color grade last — audio is already locked via -c:a copy
    if options.get("removeSilence"):
        current_video = stage_remove_silence(current_video, options)

    # ── NEW: AI Director injects the GSAP B-Roll ──
    if options.get("aiBroll"):
        current_video = stage_ai_broll(current_video, options)

    if options.get("studioAudio"):
        current_video = stage_studio_audio(current_video)

    if options.get("autoZoom"):
        current_video = stage_semantic_zoom(current_video, options)

    if options.get("cinematicColor"):
        current_video = stage_cinematic_color(current_video, options)

    # Add this block right here
    if options.get("maskEngine"):
        current_video = stage_mask_engine(current_video, options)

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

    # ── MOVED TO THE BOTTOM SO FLASHES COVER THE CAPTIONS ──
    if options.get("autoTransitions"):
        current_video = stage_hardcode_flash(current_video, options)

    # ── CapCut overlay export ──
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