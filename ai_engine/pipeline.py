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
        try:
            spec = importlib.util.find_spec(pkg)
            if spec and spec.submodule_search_locations:
                bin_path = os.path.join(spec.submodule_search_locations[0], "bin")
                if os.path.exists(bin_path):
                    os.environ["PATH"] = bin_path + os.pathsep + os.environ.get("PATH", "")
        except Exception:
            pass

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

    WET = 0.85
    audio_np = (WET * enhanced_np) + ((1.0 - WET) * orig_np)

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
    nonsilent_chunks = detect_nonsilent(audio, min_silence_len=400, silence_thresh=-42)

    if not nonsilent_chunks:
        if os.path.exists(temp_wav): os.remove(temp_wav)
        return video_path

    print(f"[🎬] Found {len(nonsilent_chunks)} active segments. Generating V-Fades & Camera Angles...")

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
        start_sec = max(0, (start_ms - 150) / 1000.0)
        end_sec = (end_ms + 100) / 1000.0
        dur = end_sec - start_sec

        v_base = f"[0:v]trim=start={start_sec:.3f}:end={end_sec:.3f},setpts=PTS-STARTPTS"
        if i % 2 == 1:
            v_filter = f"{v_base},crop=iw/1.15:ih/1.15,scale={W}:{H},setsar=1[v{i}];"
        else:
            v_filter = f"{v_base},setsar=1[v{i}];"

        a_filter = (
            f"[0:a]atrim=start={start_sec:.3f}:end={end_sec:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d=0.04,afade=t=out:st={dur-0.04:.3f}:d=0.04[a{i}];"
        )

        filter_lines.append(v_filter)
        filter_lines.append(a_filter)
        concat_v += f"[v{i}][a{i}]"

    filter_lines.append(f"{concat_v}concat=n={len(nonsilent_chunks)}:v=1:a=1[outv][outa]")

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
# 3. PIPELINE ORCHESTRATION HELPERS
# ─────────────────────────────────────────────

def extract_audio(video_path: str, out_path: str) -> None:
    subprocess.run(
        ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
         "-ar", "48000", "-ac", "1", out_path, "-y"],
        check=True, capture_output=True
    )

def mux_audio(video_path: str, audio_path: str, output_path: str) -> None:
    subprocess.run(
        ["ffmpeg", "-i", video_path, "-i", audio_path,
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-map", "0:v:0", "-map", "1:a:0", "-shortest", output_path, "-y"],
        check=True, capture_output=True
    )

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
    grade_style = color_options.get("colorGradeStyle", "pro-max")

    if grade_style == "neon-blue":
        print("      ↳ Mode: Neon Blue Studio (Ambient Bounce Simulation)")
        filter_chain = "colorbalance=rs=-0.15:gs=-0.05:bs=0.25:rm=-0.05:bm=0.10,eq=contrast=1.12:saturation=1.10:gamma=0.86,unsharp=5:5:0.8:3:3:0.0"
    elif grade_style == "cyber-warm":
        print("      ↳ Mode: Hollywood Teal & Orange")
        filter_chain = "colorbalance=rs=0.15:bs=-0.15:rm=0.10:bm=-0.10:rh=0.05:bh=-0.05,eq=contrast=1.10:saturation=1.20:gamma=0.90,unsharp=5:5:0.8:3:3:0.0"
    else:
        print("      ↳ Mode: iPhone Pro Max (Smart HDR)")
        filter_chain = "eq=contrast=1.08:saturation=1.15:gamma=0.90,unsharp=5:5:0.8:3:3:0.0"

    try:
        subprocess.run([
            "ffmpeg", "-i", video_path,
            "-vf", filter_chain,
            "-c:v", "libx264", "-preset", "fast", "-crf", "16",
            "-pix_fmt", "yuv420p", "-c:a", "copy",
            output_vid, "-y"
        ], check=True, capture_output=True)
        print(f"[✅] Cinematic aesthetic baked in: {output_vid}")
        return output_vid
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        print(f"[❌] Color grading failed: {err_msg}")
        return video_path


# ─────────────────────────────────────────────
# 5. WHISPER CAPTION ENGINE (English)
# ─────────────────────────────────────────────
import os
import json
import subprocess
import whisper
from playwright.sync_api import sync_playwright

def stage_burn_captions(video_path: str, cap_options: dict) -> str:
    print("[⚙️] Loading Whisper model...")
    model = whisper.load_model("large")

    base_dir   = os.path.dirname(os.path.abspath(video_path))
    output_vid = os.path.splitext(video_path)[0] + "_captioned.mp4"
    ovr_dir    = os.path.join(base_dir, "_cap_overlays")
    os.makedirs(ovr_dir, exist_ok=True)

    font_family = cap_options.get("captionFont", "Montserrat")
    p_class     = cap_options.get("captionPrimaryStyle", "p-clean-white")
    s_class     = cap_options.get("captionSecondaryStyle", "s-electric-teal")
    cap_bottom_pct = float(cap_options.get("captionBottomPercent", 22)) / 100.0
    mixed_style = cap_options.get("captionMixedStyle", False)

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

    # 🚀 UPGRADED: Much larger chunks (up to 6 words) to build multi-line blocks
    phrases = []
    current_phrase = []
    char_count = 0
    for w_info in word_events:
        current_phrase.append(w_info)
        char_count += len(w_info["word"])
        
        # Break phrase if it gets too long, hits 6 words, or ends in punctuation
        if char_count >= 35 or len(current_phrase) >= 6 or any(p in w_info["word"] for p in ['.', '?', '!']):
            phrases.append(current_phrase)
            current_phrase = []
            char_count = 0
            
    if current_phrase:
        phrases.append(current_phrase)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate",
         "-of", "json", video_path],
        capture_output=True, text=True
    )
    info = json.loads(probe.stdout)["streams"][0]
    W, H = int(info["width"]), int(info["height"])

    def make_base_html(width: int, height: int) -> str:
        # 🚀 UPGRADED CSS: Centers the block, but Left-Aligns the text inside!
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Anton&family=Bangers&family=Great+Vibes&family=Montserrat:wght@800;900&family=Oswald:wght@700&family=Poppins:wght@800;900&display=swap');
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ width: {width}px; height: {height}px; background: transparent; overflow: hidden; }}
  
  .caption-wrap {{
    position: absolute; bottom: {int(height * cap_bottom_pct)}px;
    left: 50%; transform: translateX(-50%);
    display: flex; flex-direction: column; align-items: flex-start;
    width: max-content; padding: 0;
  }}
  
  .base-cap {{
    font-weight: 900; letter-spacing: -1px; line-height: 1; white-space: nowrap;
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text; color: transparent;
  }}
  
  .p-glass-silver {{ background-image: linear-gradient(160deg, #fff 0%, #d2e8ff 30%, #b4d7ff 55%, #ebf6ff 75%, #fff 100%); filter: drop-shadow(0 0 10px rgba(140,185,255,0.50)) drop-shadow(0 1px 3px rgba(60,100,200,0.35)); }}
  .p-clean-white  {{ background-image: linear-gradient(to bottom, #ffffff 0%, #e0e0e0 100%); filter: drop-shadow(0 3px 6px rgba(0,0,0,0.8)); }}
  .p-heavy-stroke {{ background-image: linear-gradient(to bottom, #ffffff, #ffffff); filter: drop-shadow(2px 0 0 #000) drop-shadow(-2px 0 0 #000) drop-shadow(0 2px 0 #000) drop-shadow(0 -2px 0 #000) drop-shadow(0 5px 12px rgba(0,0,0,0.9)); }}
  .p-soft-yellow  {{ background-image: linear-gradient(to bottom, #FFFDE7 0%, #FFF176 100%); filter: drop-shadow(0 2px 4px rgba(0,0,0,0.7)); }}
  .p-neon-base    {{ background-image: linear-gradient(to bottom, #ffffff 0%, #e0f7fa 100%); filter: drop-shadow(0 0 10px rgba(0,255,255,0.4)) drop-shadow(0 2px 2px rgba(0,0,0,0.8)); }}
  .p-silver-translucent {{ background-image: linear-gradient(160deg, rgba(255,255,255,0.9) 0%, rgba(200,225,255,0.6) 100%); filter: drop-shadow(0 0 10px rgba(180,200,255,0.4)) drop-shadow(0 1px 2px rgba(0,0,0,0.8)); }}
  .p-sunset-glow  {{ background-image: linear-gradient(160deg, #ff7e5f 0%, #feb47b 100%); filter: drop-shadow(0 0 12px rgba(255,126,95,0.6)) drop-shadow(0 2px 4px rgba(0,0,0,0.9)); }}

  .s-electric-teal  {{ background-image: linear-gradient(to right, #00dcc8 0%, #00c3d2 50%, #00aadc 100%); filter: drop-shadow(0 0 8px rgba(0,210,200,0.75)) drop-shadow(0 1px 3px rgba(0,150,180,0.55)); }}
  .s-hormozi-yellow {{ background-image: linear-gradient(to bottom, #FFE81F 0%, #FF8A00 100%); filter: drop-shadow(0 0 15px rgba(255,165,0,0.6)) drop-shadow(0 3px 6px rgba(0,0,0,0.9)); }}
  .s-crimson-red    {{ background-image: linear-gradient(to bottom, #ff4b4b 0%, #b30000 100%); filter: drop-shadow(0 0 12px rgba(255,0,0,0.6)) drop-shadow(0 3px 5px rgba(0,0,0,0.9)); }}
  .s-cyber-purple   {{ background-image: linear-gradient(to right, #d500f9 0%, #651fff 100%); filter: drop-shadow(0 0 15px rgba(213,0,249,0.7)) drop-shadow(0 2px 4px rgba(0,0,0,0.8)); }}
  .s-luxury-gold    {{ background-image: linear-gradient(160deg, #FFF7D6 0%, #F3DA7C 30%, #D4AF37 70%, #AA7700 100%); filter: drop-shadow(0 0 12px rgba(212,175,55,0.5)) drop-shadow(0 2px 5px rgba(0,0,0,0.8)); }}
  .s-dark-blue-glow {{ background-image: linear-gradient(to bottom, #4facfe 0%, #001ba8 100%); filter: drop-shadow(0 0 16px rgba(0,40,200,0.85)) drop-shadow(0 3px 5px rgba(0,0,0,0.9)); }}
  .s-matrix-green   {{ background-image: linear-gradient(to bottom, #00FF00 0%, #008000 100%); filter: drop-shadow(0 0 15px rgba(0,255,0,0.7)) drop-shadow(0 2px 4px rgba(0,0,0,0.9)); }}
</style>
</head>
<body>
  <div class="caption-wrap" id="wrap"></div>
</body>
</html>"""

    print("[⚙️] Launching headless Chrome for dynamic staggered rendering...")

    segments = []
    rendered_pairs = {}
    
    for phrase in phrases:
        phrase_start = phrase[0]["start"] 
        phrase_words = tuple(w["word"] for w in phrase)
        
        for active_idx, w_info in enumerate(phrase):
            t_s = w_info["start"]
            if active_idx + 1 < len(phrase):
                t_e = phrase[active_idx + 1]["start"]
            else:
                t_e = w_info["end"]

            key = (phrase_words, active_idx)
            if key not in rendered_pairs:
                png_path = os.path.join(ovr_dir, f"cap_{len(rendered_pairs):04d}.png")
                rendered_pairs[key] = png_path
            
            segments.append((t_s, t_e, rendered_pairs[key], phrase_words, active_idx, phrase_start))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1)
        page = context.new_page()
        page.set_content(make_base_html(W, H), wait_until="networkidle")

        rendered_done = set()
        for t_s, t_e, png_path, phrase_words, active_idx, phrase_start in segments:
            key = (phrase_words, active_idx)
            if key in rendered_done: continue

            # 🚀 UPGRADED: Smart Row Line-Breaking Logic in JavaScript
            page.evaluate("""
                (args) => {
                    const wrapEl = document.getElementById('wrap');
                    wrapEl.innerHTML = ''; 
                    
                    const isHeavy = (word) => word.replace(/[^a-zA-Z0-9]/g, '').length > 4;
                    
                    // 1. Start with a slightly smaller base size overall
                    let baseSize = args.H * 0.045; 
                    const totalChars = args.words.join('').length;
                    const wordCount = args.words.length;

                    // 2. Aggressive shrink if the engine detects a multi-line paragraph
                    if (wordCount >= 5 || totalChars > 25) {
                        baseSize *= 0.65; // Shrink by 35% for big blocks
                    } else if (wordCount >= 3 || totalChars > 15) {
                        baseSize *= 0.80; // Shrink by 20% for medium blocks
                    }

                    let currentRow = document.createElement('div');
                    currentRow.style.display = 'flex';
                    currentRow.style.alignItems = 'baseline';
                    currentRow.style.gap = (baseSize * 0.2) + 'px';
                    wrapEl.appendChild(currentRow);
                    
                    let wordsInRow = 0;
                    let charsInRow = 0;

                    args.words.forEach((word, index) => {
                        const heavy = isHeavy(word) && word.replace(/[^a-zA-Z0-9]/g, '').length > 5;
                        
                        if (wordsInRow > 0 && (wordsInRow >= 3 || (wordsInRow >= 2 && charsInRow > 12) || (args.mixed_style && heavy))) {
                            currentRow = document.createElement('div');
                            currentRow.style.display = 'flex';
                            currentRow.style.alignItems = 'baseline';
                            currentRow.style.gap = (baseSize * 0.2) + 'px';
                            
                            // 3. Tighter vertical stacking (pulls rows much closer together)
                            currentRow.style.marginTop = -(baseSize * 0.25) + 'px'; 
                            
                            wrapEl.appendChild(currentRow);
                            wordsInRow = 0;
                            charsInRow = 0;
                        }

                        const span = document.createElement('span');
                        span.textContent = word;
                        
                        if (args.mixed_style && heavy) {
                            span.style.fontFamily = "'Great Vibes', cursive";
                            span.style.fontWeight = 'normal';
                            // 4. Slightly reduced cursive multiplier so it doesn't blow out the height
                            span.style.fontSize = (baseSize * 1.45) + 'px'; 
                            span.style.padding = '0 ' + (baseSize * 0.05) + 'px'; 
                            span.className = 'base-cap ' + args.s_class;
                        } else {
                            span.style.fontFamily = `'${args.font_family}', Impact, sans-serif`;
                            span.style.fontWeight = '900';
                            span.style.fontSize = baseSize + 'px';
                            span.className = 'base-cap ' + args.p_class;
                        }
                        
                        if (index > args.active_index) {
                            span.style.visibility = 'hidden'; 
                        }
                        
                        currentRow.appendChild(span);
                        wordsInRow++;
                        charsInRow += word.length;
                    });
                }
            """, {
                "words": list(phrase_words),
                "active_index": active_idx,
                "H": H,
                "font_family": font_family,
                "p_class": p_class,
                "s_class": s_class,
                "mixed_style": mixed_style
            })
            page.screenshot(path=png_path, full_page=False, omit_background=True)
            rendered_done.add(key)

        browser.close()

    print("[⚙️] Compositing with cinematic motion math...")

    CHUNK      = 50
    current_video = video_path
    anim_style = cap_options.get("captionAnimation", "spring-up")
    dur        = 0.15

    for chunk_start in range(0, len(segments), CHUNK):
        chunk     = segments[chunk_start: chunk_start + CHUNK]
        chunk_out = os.path.join(base_dir, f"_chunk_{chunk_start:04d}.mp4")

        inputs = ["ffmpeg", "-i", current_video]
        for _, _, path, _, _, _ in chunk:
            inputs += ["-i", path]

        filter_parts = []
        for idx, (t_s, t_e, _, _, _, phrase_start) in enumerate(chunk):
            in_lbl  = f"[v{idx}]" if idx > 0 else "[0:v]"
            out_lbl = f"[v{idx+1}]"
            inp_lbl = f"[{idx+1}]"

            enable_expr = f"enable='between(t,{t_s:.3f},{t_e:.3f})'"
            
            if anim_style == "slide-up":
                t_prog = f"(t-{phrase_start:.3f})/{dur}"
                inv_p  = f"(1-{t_prog})"
                ease_out_cubic = f"({inv_p}*{inv_p}*{inv_p})"
                y_expr = f"if(lte(t,{phrase_start:.3f}+{dur}), 60*{ease_out_cubic}, 0)"
                overlay_cmd = f"x=0:y='{y_expr}':{enable_expr}"
                
            elif anim_style == "ease-slide-up":
                slide_dur = 0.25 
                t_prog = f"(t-{phrase_start:.3f})/{slide_dur}"
                inv_p = f"(1-{t_prog})"
                ease_out_quart = f"({inv_p}*{inv_p}*{inv_p}*{inv_p})"
                y_expr = f"if(lte(t,{phrase_start:.3f}+{slide_dur}), 30*{ease_out_quart}, 0)"
                overlay_cmd = f"x=0:y='{y_expr}':{enable_expr}"

            elif anim_style == "slide-right":
                t_prog = f"(t-{phrase_start:.3f})/{dur}"
                inv_p  = f"(1-{t_prog})"
                ease_out_cubic = f"({inv_p}*{inv_p}*{inv_p})"
                x_expr = f"if(lte(t,{phrase_start:.3f}+{dur}), -60*{ease_out_cubic}, 0)"
                overlay_cmd = f"x='{x_expr}':y=0:{enable_expr}"
                
            elif anim_style == "spring-up":
                spring_dur = 0.25
                sp = f"(t-{phrase_start:.3f})/{spring_dur}"
                y_expr = f"if(lte(t,{phrase_start:.3f}+{spring_dur}), 80*(1-{sp})*cos({sp}*6.5), 0)"
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
        import shutil
        shutil.copy(video_path, output_vid)

    import shutil
    shutil.rmtree(ovr_dir, ignore_errors=True)
    if os.path.exists(temp_audio):
        os.remove(temp_audio)

    print(f"[✅] Perfect Kinetic staggered phrases burned with '{anim_style}' animation: {output_vid}")
    return output_vid


# ─────────────────────────────────────────────────────────────────────────────
# 6. SINHALA TRANSCRIPT via GEMINI
# ─────────────────────────────────────────────────────────────────────────────

def get_perfect_sinhala_transcript(audio_path: str, api_key_opt: str = None) -> list:
    import google.generativeai as genai
    import time
    import json
    import os
 
    # Grab this from Google AI Studio (it's free)
    api_key = api_key_opt or os.getenv("GEMINI_API_KEY")
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
        # 4. The strict prompt to prevent hallucination and force formatting
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
    except Exception as e:
        print(f"[❌] Gemini API Error: {e}")
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

    # ── NEW: Extract your Full-Stops for the Transition Engine ──
    flash_times = []
    for i, item in enumerate(segments_data):
        phrase_text = str(item.get("phrase", ""))
        # If the AI marked this phrase with a full stop or question mark
        if "." in phrase_text or "?" in phrase_text or "!" in phrase_text:
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
    position: absolute; bottom: {int(height * 0.22)}px; left: 0; right: 0;
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
# 10. CINEMATIC BOTTOM GLOW ENGINE
# ─────────────────────────────────────────────

def stage_bottom_glow(video_path: str, color_hex: str) -> str:
    print(f"[⚙️] Adding cinematic bottom glow ({color_hex})...")
    base_dir    = os.path.dirname(os.path.abspath(video_path))
    output_vid  = os.path.splitext(video_path)[0] + "_glow.mp4"
    overlay_png = os.path.join(base_dir, "_bottom_glow.png")

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", video_path],
        capture_output=True, text=True
    )
    info = json.loads(probe.stdout)["streams"][0]
    W, H = int(info["width"]), int(info["height"])

    color_hex = color_hex.lstrip('#')
    if len(color_hex) != 6:
        color_hex = "000000"
    r, g, b = tuple(int(color_hex[i:i+2], 16) for i in (0, 2, 4))

    img  = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    start_y = int(H * 0.45)
    for y in range(start_y, H):
        progress = (y - start_y) / (H - start_y)
        alpha    = int(255 * (progress ** 2.5))
        draw.line([(0, y), (W, y)], fill=(r, g, b, alpha))

    img.save(overlay_png)

    subprocess.run([
        "ffmpeg", "-i", video_path, "-i", overlay_png,
        "-filter_complex", "[0:v][1:v]overlay=0:0[outv]",
        "-map", "[outv]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "17",
        "-pix_fmt", "yuv420p", "-c:a", "copy",
        output_vid, "-y"
    ], check=True, capture_output=True)

    if os.path.exists(overlay_png):
        os.remove(overlay_png)

    print(f"[✅] Bottom glow applied: {output_vid}")
    return output_vid


# ─────────────────────────────────────────────
# 11. AI BACKGROUND FX ENGINE (MediaPipe)
# ─────────────────────────────────────────────

def stage_background_fx(video_path: str, bg_options: dict) -> str:
    import cv2
    import numpy as np
    import mediapipe as mp

    print("[⚙️] Booting MediaPipe AI Background Engine...")
    base_dir   = os.path.dirname(os.path.abspath(video_path))
    temp_vid   = os.path.join(base_dir, "_temp_bg_fx.mp4")
    output_vid = os.path.splitext(video_path)[0] + "_bgfx.mp4"
    temp_audio = os.path.join(base_dir, "_temp_audio.wav")

    mode          = bg_options.get("bgMode", "blur")
    hex_color     = bg_options.get("bgColor", "#09090b").lstrip('#')
    bg_image_path = bg_options.get("bgImagePath", "")
    keying_mode   = bg_options.get("keyingMode", "ai")

    bgr_color = tuple(int(hex_color[i:i+2], 16) for i in (4, 2, 0)) if len(hex_color) == 6 else (11, 9, 9)

    subprocess.run(
        ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
         "-ar", "48000", "-ac", "1", temp_audio, "-y"],
        check=True, capture_output=True
    )

    cap  = cv2.VideoCapture(video_path)
    fps  = cap.get(cv2.CAP_PROP_FPS)
    w    = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h    = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out  = cv2.VideoWriter(temp_vid, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))

    custom_bg_img = None
    if mode == "image" and bg_image_path and os.path.exists(bg_image_path):
        print(f"[⚙️] Loading custom background: {os.path.basename(bg_image_path)}")
        custom_bg_img = cv2.imread(bg_image_path)
        if custom_bg_img is not None:
            custom_bg_img = cv2.resize(custom_bg_img, (w, h))

    engine_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(engine_dir, "pretrained_models", "selfie_segmenter.tflite")
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    if not os.path.exists(model_path):
        print("[⚙️] Downloading MediaPipe Selfie Segmenter model...")
        import urllib.request
        urllib.request.urlretrieve(
            "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite",
            model_path
        )

    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    base_options = mp_python.BaseOptions(model_asset_path=model_path)
    options      = vision.ImageSegmenterOptions(base_options=base_options, output_confidence_masks=True)

    with vision.ImageSegmenter.create_from_options(options) as segmenter:
        while cap.isOpened():
            success, frame = cap.read()
            if not success: break

            if mode == "blur":
                import numpy as np
                bg_frame = cv2.GaussianBlur(frame, (99, 99), 0)
                bg_frame = cv2.addWeighted(bg_frame, 0.7, np.zeros_like(bg_frame), 0.3, 0)
            elif mode == "image" and custom_bg_img is not None:
                bg_frame = custom_bg_img
            else:
                import numpy as np
                bg_frame = np.full(frame.shape, bgr_color, dtype=np.uint8)

            if keying_mode == "chroma":
                import numpy as np
                hsv         = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                lower_green = np.array([35, 40, 40])
                upper_green = np.array([85, 255, 255])
                raw_mask    = cv2.inRange(hsv, lower_green, upper_green)
                kernel      = np.ones((3, 3), np.uint8)
                mask        = cv2.morphologyEx(raw_mask, cv2.MORPH_OPEN, kernel, iterations=1)
                mask        = cv2.dilate(mask, kernel, iterations=1)
                mask        = cv2.GaussianBlur(mask, (5, 5), 0)
                blend_ratio = np.stack((mask,) * 3, axis=-1) / 255.0
                output_frame = (frame * (1.0 - blend_ratio) + bg_frame * blend_ratio).astype(np.uint8)
            else:
                import numpy as np
                frame_rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image     = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
                results      = segmenter.segment(mp_image)
                mask         = np.squeeze(results.confidence_masks[0].numpy_view())
                condition    = np.stack((mask,) * 3, axis=-1) > 0.5
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
# 12. SEMANTIC SMART-ZOOM ENGINE
# ─────────────────────────────────────────────

def stage_semantic_zoom(video_path: str, zoom_options: dict) -> str:
    print("[⚙️] Analyzing semantic context for Smart Zooms...")
    base_dir   = os.path.dirname(os.path.abspath(video_path))
    output_vid = os.path.splitext(video_path)[0] + "_smartzoom.mp4"
    temp_audio = os.path.join(base_dir, "_zoom_audio.wav")

    subprocess.run(
        ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
         "-ar", "16000", "-ac", "1", temp_audio, "-y"],
        check=True, capture_output=True
    )

    en_hooks = [
        "important", "secret", "listen", "stop", "never", "always",
        "money", "hack", "trick", "reason", "best", "worst", "look",
        "insane", "crazy", "truth", "give", "warning", "attention"
    ]
    si_hooks = [
        "වැදගත්", "රහස", "අහන්න", "බලන්න", "සල්ලි", "හේතුව", "හොඳම",
        "පිස්සුවක්", "ඇත්ත", "අනිවාර්යයෙන්", "scam", "trick", "money",
        "direct", "skill", "professional field engineer", "field engineer"
    ]

    zoom_intervals = []
    lang = zoom_options.get("captionLanguage", "en")

    if lang == "si":
        print("[⚙️] Using Gemini to detect Sinhala hook words for zooming...")
        phrases = get_perfect_sinhala_transcript(temp_audio, zoom_options.get("geminiApiKey"))
        for p in phrases:
            phrase_text = p.get("phrase", "").lower()
            if any(hook in phrase_text for hook in si_hooks + en_hooks):
                start = float(p.get("start", 0))
                zoom_intervals.append((start, start + 2.5))
    else:
        print("[⚙️] Using Whisper to detect English hook words for zooming...")
        try:
            from faster_whisper import WhisperModel
            try:
                w_model = WhisperModel("base", device="cuda", compute_type="float16")
            except Exception:
                w_model = WhisperModel("base", device="cpu", compute_type="int8")

            w_segments_raw, _ = w_model.transcribe(
                temp_audio, word_timestamps=True, vad_filter=True,
                condition_on_previous_text=False
            )

            for seg in list(w_segments_raw):
                for w in (seg.words or []):
                    clean_word = ''.join(e for e in w.word.strip().lower() if e.isalnum())
                    if clean_word in en_hooks:
                        zoom_intervals.append((w.start, w.start + 2.5))
        except Exception as e:
            print(f"[⚠️] Whisper zoom detection failed: {e}")

    if not zoom_intervals:
        print("[⚙️] No hook words found. Skipping Smart Zoom.")
        if os.path.exists(temp_audio): os.remove(temp_audio)
        return video_path

    print(f"[🎬] Found {len(zoom_intervals)} impact moments. Rendering smooth zoompans...")

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate",
         "-of", "json", video_path],
        capture_output=True, text=True
    )
    info = json.loads(probe.stdout)["streams"][0]
    W, H = int(info["width"]), int(info["height"])
    fps_str  = info.get("r_frame_rate", "30/1")
    num, den = fps_str.split('/')
    fps      = int(num) / int(den)

    intensity  = float(zoom_options.get("zoomIntensity", 1.15))
    duration   = float(zoom_options.get("zoomSpeed", 0.5))
    zoom_speed = (intensity - 1.0) / (fps * duration)

    z_expr = "1"
    for (start, end) in zoom_intervals:
        z_expr = f"if(between(time,{start:.2f},{end:.2f}), min(pzoom+{zoom_speed:.5f},{intensity}), {z_expr})"

    x_expr         = f"({W}-({W}/zoom))/2"
    y_expr         = f"({H}-({H}/zoom))/2"
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
# 13. AUTO TRANSITIONS ENGINE
# ─────────────────────────────────────────────

def stage_hardcode_flash(video_path: str, options: dict) -> str:
    print("[⚙️] Loading AI Director timestamps for Camera Flashes...")
    base_dir   = os.path.dirname(os.path.abspath(video_path))
    output_vid = os.path.splitext(video_path)[0] + "_flashes.mp4"
    json_path  = os.path.join(base_dir, "_flash_times.json")

    engine_dir = os.path.dirname(os.path.abspath(__file__))
    sfx_audio  = os.path.join(engine_dir, "assets", "whoosh_sfx.MP3")

    flash_times = []
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            flash_times = json.load(f)
        os.remove(json_path)

    if not flash_times:
        print("[⚙️] No cinematic cuts detected. Skipping transitions.")
        return video_path

    print(f"[🎬] Found {len(flash_times)} Director cuts. Compositing Camera Flashes...")

    exprs     = []
    for t in flash_times:
        exprs.append(f"if(between(t,{t:.3f},{t+0.3:.3f}), 1-(t-{t:.3f})/0.3, 0)")

    full_expr = " + ".join(exprs)
    vf_chain  = f"eq=eval=frame:brightness='{full_expr}'"

    inputs           = ["-i", video_path]
    filter_complex_a = ""
    audio_mix_inputs = "[0:a]"
    audio_map        = "0:a"

    has_sfx = os.path.exists(sfx_audio)
    if has_sfx:
        inputs.extend(["-i", sfx_audio])
        for idx, t_start in enumerate(flash_times):
            aud_out   = f"[a_delayed_{idx}]"
            delay_ms  = int(max(0, t_start) * 1000)
            filter_complex_a += f"[1:a]adelay={delay_ms}|{delay_ms}{aud_out};"
            audio_mix_inputs += aud_out
        total_inputs      = len(flash_times) + 1
        filter_complex_a += (
            f"{audio_mix_inputs}amix=inputs={total_inputs}"
            f":duration=first:dropout_transition=2:normalize=0[a_final]"
        )
        audio_map = "[a_final]"
    else:
        print("[⚠️] whoosh_sfx.MP3 missing. Visual flash only.")

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
        print(f"[✅] Camera Flashes applied: {output_vid}")
        return output_vid
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        print(f"[❌] Flashes failed: {err_msg}")
        return video_path


# ─────────────────────────────────────────────
# 15. MP4 → MP3 CONVERSION ENGINE
# ─────────────────────────────────────────────

def stage_mp4_to_mp3(video_path: str, options: dict = None) -> str:
    """
    Converts an MP4 (or any video) to a high-quality MP3 / FLAC audio file.

    Options keys (all optional):
      mp3Quality  : "128k" | "192k" | "320k" | "lossless"  (default: "192k")
      mp3Normalize: True/False — apply -14 LUFS broadcast loudness normalisation
      mp3Metadata : dict with "title", "artist", "album" for ID3 tags
    """
    if options is None:
        options = {}

    quality     = options.get("mp3Quality", "192k")
    normalize   = options.get("mp3Normalize", False)
    metadata    = options.get("mp3Metadata", {})

    base_dir    = os.path.dirname(os.path.abspath(video_path))
    stem        = os.path.splitext(os.path.basename(video_path))[0]

    # ── Decide output format ──────────────────────────────────────────────────
    if quality == "lossless":
        out_ext   = ".flac"
        codec_args = ["-c:a", "flac", "-compression_level", "8"]
        print("[⚙️] MP4 → FLAC (lossless) export...")
    else:
        out_ext   = ".mp3"
        # Validate bitrate; fall back to 192k on unknown input
        valid_bitrates = {"128k", "192k", "320k"}
        bitrate   = quality if quality in valid_bitrates else "192k"
        codec_args = ["-c:a", "libmp3lame", "-b:a", bitrate, "-q:a", "0"]
        print(f"[⚙️] MP4 → MP3 at {bitrate} export...")

    output_path = os.path.join(base_dir, stem + out_ext)

    # ── Build FFmpeg command ──────────────────────────────────────────────────
    cmd = ["ffmpeg", "-i", video_path, "-vn"]

    # Optional loudness normalisation (-14 LUFS broadcast standard)
    if normalize:
        print("[⚙️] Applying -14 LUFS loudness normalisation...")
        # Two-pass loudnorm: detect → apply
        probe_cmd = [
            "ffmpeg", "-i", video_path, "-vn",
            "-af", "loudnorm=I=-14:TP=-1:LRA=11:print_format=json",
            "-f", "null", "-"
        ]
        probe_result = subprocess.run(
            probe_cmd, capture_output=True, text=True
        )
        # Extract measured values from stderr (loudnorm prints to stderr)
        stderr_text = probe_result.stderr
        try:
            import re
            json_match = re.search(r'\{[^{}]+\}', stderr_text, re.DOTALL)
            if json_match:
                loud_data  = json.loads(json_match.group())
                input_i    = loud_data.get("input_i",    "-23.0")
                input_tp   = loud_data.get("input_tp",   "-2.0")
                input_lra  = loud_data.get("input_lra",  "7.0")
                input_thresh = loud_data.get("input_thresh", "-30.0")
                af_filter  = (
                    f"loudnorm=I=-14:TP=-1:LRA=11"
                    f":measured_I={input_i}:measured_TP={input_tp}"
                    f":measured_LRA={input_lra}:measured_thresh={input_thresh}"
                    f":offset=0:linear=true"
                )
            else:
                af_filter = "loudnorm=I=-14:TP=-1:LRA=11"
        except Exception:
            af_filter = "loudnorm=I=-14:TP=-1:LRA=11"

        cmd += ["-af", af_filter]

    cmd += codec_args

    # Optional ID3 metadata tags
    for tag_key, tag_val in metadata.items():
        if tag_key in ("title", "artist", "album", "genre", "date", "comment"):
            cmd += ["-metadata", f"{tag_key}={tag_val}"]

    # Write sample rate + stereo explicitly so output is always predictable
    cmd += ["-ar", "44100", "-ac", "2", output_path, "-y"]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"[✅] Audio exported → {os.path.basename(output_path)}  ({size_mb:.2f} MB)")
        return output_path
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        print(f"[❌] MP4 → MP3 conversion failed: {err_msg}")
        raise


# ─────────────────────────────────────────────
# 14. MAIN PIPELINE ORCHESTRATION
# ─────────────────────────────────────────────

def run_pipeline(video_path: str, options_json: str) -> None:
    options = json.loads(options_json)
    print(f"\n[🎬] STARTING LOCAL RENDER ENGINE: {os.path.basename(video_path)}\n")

    if not os.path.exists(video_path):
        print(f"[❌] FATAL: Input video not found: {video_path}")
        print("Please re-select the video in the UI.")
        return

    current_video = video_path

    if options.get("removeSilence"):
        current_video = stage_remove_silence(current_video, options)

    if options.get("aiBroll"):
        current_video = stage_ai_broll(current_video, options)

    if options.get("studioAudio"):
        current_video = stage_studio_audio(current_video)

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

    if options.get("autoTransitions"):
        current_video = stage_hardcode_flash(current_video, options)

    if options.get("exportCaptionOverlay"):
        lang = options.get("captionLanguage", "en")
        if lang == "si":
            export_captions_overlay_si(current_video, options)
        else:
            export_captions_overlay_en(current_video, options)

    if options.get("mp4ToMp3"):
        stage_mp4_to_mp3(current_video, options)

    print(f"\n[🚀] PIPELINE COMPLETE. Final output: {current_video}")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        run_pipeline(sys.argv[1], sys.argv[2])
    else:
        print("Usage: pipeline.py <video_path> <options_json>")