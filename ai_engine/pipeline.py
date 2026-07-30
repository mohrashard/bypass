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


import os
import subprocess

import numpy as np
import soundfile as sf
from pedalboard import Pedalboard, NoiseGate, HighpassFilter, Compressor, Limiter, Gain
from df.enhance import enhance, init_df, load_audio


def process_with_ai_stack(
    input_wav_path: str,
    output_wav_path: str,
    wet: float = 0.95,
    atten_lim_db: float | None = None,
) -> None:
    print("[⚙️] Initializing DeepFilterNet3...")
    model, df_state, _ = init_df(post_filter=False)

    print("[⚙️] Loading audio at 48kHz full-band...")
    audio_df, sr_df = load_audio(input_wav_path, sr=df_state.sr())

    print("[⚙️] Running Studio Grade AI deep filtering...")
    # atten_lim_db=None = no ceiling on suppression, i.e. DeepFilterNet can
    # remove as much stationary noise (fan/AC/room tone) as it's able to.
    # Only pass a number (e.g. 20) if voices start sounding underwater/artifacted.
    enhanced_tensor = enhance(model, df_state, audio_df, atten_lim_db=atten_lim_db)

    enhanced_np = enhanced_tensor.cpu().numpy()
    orig_np = audio_df.cpu().numpy()

    # every % of "dry" mixed back in reintroduces the noise DF just removed
    audio_np = (wet * enhanced_np) + ((1.0 - wet) * orig_np)

    peak_vol = np.max(np.abs(audio_np))
    if peak_vol > 0:
        audio_np = audio_np / peak_vol * 0.8

    sr_orig = df_state.sr()

    print("[⚙️] Building pro signal chain (Pedalboard)...")
    board = Pedalboard([
        # highpass FIRST — strips sub-bass rumble/mains hum before the gate
        # sees it, so low-freq fan drone can't hold the gate open in silence
        HighpassFilter(cutoff_frequency_hz=90.0),
        NoiseGate(threshold_db=-50.0, ratio=15.0, attack_ms=2.0, release_ms=200.0),
        Compressor(threshold_db=-18.0, ratio=3.5, attack_ms=8.0, release_ms=120.0),
        Gain(gain_db=4.0),
        Limiter(threshold_db=-1.0, release_ms=50.0),
    ])

    print("[⚙️] Processing through pro signal chain...")
    processed = board(audio_np, sr_orig)

    print("[⚙️] Applying voice EQ and -14 LUFS Broadcast Normalization...")
    tmp_pre_eq = input_wav_path.replace(".wav", "_pre_eq.wav")
    # FLOAT not PCM_16 — loudnorm still applies gain after this write
    sf.write(tmp_pre_eq, processed.T, sr_orig, subtype='FLOAT')

    eq_filter = (
        "equalizer=f=150:t=h:w=150:g=-3,"   # extra cut: fan/AC drone band, beyond what the highpass alone catches
        "equalizer=f=3500:t=h:w=1000:g=3,"
        "equalizer=f=8000:t=h:w=2000:g=2"
    )

    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", tmp_pre_eq,
                "-af", f"{eq_filter},loudnorm=I=-14:TP=-1:LRA=11",
                "-c:a", "pcm_s16le",
                output_wav_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print("[❌] ffmpeg failed:\n", e.stderr)
        raise
    finally:
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
         "-show_entries", "stream=width,height,r_frame_rate", "-of", "json", video_path],
        capture_output=True, text=True
    )
    info = json.loads(probe.stdout)["streams"][0]
    W, H = int(info["width"]), int(info["height"])
    fps_str = info.get("r_frame_rate", "30/1")
    try:
        num, den = fps_str.split('/')
        fps = int(num) / int(den)
    except Exception:
        fps = 30.0
    
    zoom_speed = 0.08 / fps

    filter_lines = []
    concat_v = ""
    concat_a = ""

    for i, (start_ms, end_ms) in enumerate(nonsilent_chunks):
        start_sec = max(0, (start_ms - 150) / 1000.0)
        end_sec = (end_ms + 100) / 1000.0
        dur = end_sec - start_sec

        v_base = f"[0:v]trim=start={start_sec:.3f}:end={end_sec:.3f},setpts=PTS-STARTPTS"
        if i % 2 == 1:
            z_expr = f"min(pzoom+{zoom_speed:.5f},1.15)"
            x_expr = f"({W}-({W}/zoom))/2"
            y_expr = f"({H}-({H}/zoom))/2"
            v_filter = f"{v_base},zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d=1:s={W}x{H}:fps={fps},setsar=1[v{i}];"
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
# 4. PRO MAX CINEMATIC COLOR ENGINE (UPDATED)
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
    # --- NEW "POTH RAKKE GRADING" STYLE ---
    elif grade_style == "poth-rakke":
        print("      ↳ Mode: Poth Rakke (Vibrant Tropical Yellow)")
        # This pushes towards a bright, saturated look with a specific yellowish-orange wash.
        filter_chain = "colorbalance=rs=0.10:gs=0.05:bs=-0.15:rm=0.10:bm=-0.15,eq=contrast=1.15:saturation=1.22:gamma=0.90,unsharp=5:5:0.8:3:3:0.0"
    elif grade_style == "studio-blue":
        print("      ↳ Mode: Studio Blue Backdrop (Skin-Safe)")
        # Cools the shadows/background while explicitly preserving/warming the midtones for skin-safe grading
        filter_chain = "colorbalance=rs=0.0:gs=0.0:bs=0.15:rm=0.05:bm=0.0:bh=0.05,eq=contrast=1.10:saturation=1.12:gamma=0.95,unsharp=5:5:0.8:3:3:0.0"
    elif grade_style == "m22-to-iphone-4k":
        print("      ↳ Mode: M22 Rescue (Denoise + Smart 4K Upscale + Smart HDR)")
        # 1. hqdn3d: Kills the nasty budget-sensor grain.
        # 2. scale: Dynamically checks if video is vertical or horizontal. 
        #    - If horizontal (iw>ih): Sets width to 3840, auto-calculates height (-2 keeps it even).
        #    - If vertical (ih>iw): Sets height to 3840, auto-calculates width.
        # 3. eq: Lifts the shadows slightly and boosts contrast to mimic Apple's Smart HDR.
        # 4. unsharp: Crisps up the edges after the upscale.
        filter_chain = (
            "hqdn3d=3.0:2.0:4.0:3.0,"
            "eq=contrast=1.08:saturation=1.15:gamma=1.05,"
            "unsharp=5:5:1.0:3:3:0.0,"
            "scale='if(gt(iw,ih),1920,-2)':'if(gt(iw,ih),-2,1920)':flags=bicubic"
        )
    else:
        print("      ↳ Mode: iPhone Pro Max (Smart HDR)")
        # Gamma > 1 lifts shadows (Smart HDR effect), preventing dark hair from crushing into the background
        filter_chain = "eq=contrast=1.05:saturation=1.15:gamma=1.10,unsharp=5:5:0.8:3:3:0.0"

    try:
        subprocess.run([
            "ffmpeg", "-i", video_path,
            "-vf", filter_chain,
            "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "18", "-b:v", "0",
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
    import re
    base_dir   = os.path.dirname(os.path.abspath(video_path))
    output_vid = os.path.splitext(video_path)[0] + "_captioned.mp4"
    ovr_dir    = os.path.join(base_dir, "_cap_overlays")
    os.makedirs(ovr_dir, exist_ok=True)

    font_family = cap_options.get("captionFont", "Montserrat")
    p_class     = cap_options.get("captionPrimaryStyle", "p-clean-white")
    s_class     = cap_options.get("captionSecondaryStyle", "s-electric-teal")
    cap_bottom_pct = float(cap_options.get("captionBottomPercent", 22)) / 100.0
    cap_scale      = float(cap_options.get("captionScale", 100)) / 100.0
    mixed_style = cap_options.get("captionMixedStyle", False)

    is_manual = cap_options.get("captionLanguage") == "manual_srt"
    word_events = []
    
    if is_manual:
        print("[⚙️] Parsing Manual Subtitles (Word-Level and Standard SRT)...")
        srt_text = cap_options.get("manualSrtText", "")
        lines = srt_text.strip().split('\n')
        current_segment_start = 0.0
        current_segment_end = 0.0
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.isdigit():
                continue
                
            if '-->' in line:
                parts = line.split('-->')
                if len(parts) == 2:
                    start_str = parts[0].strip()
                    end_str = parts[1].strip()
                    try:
                        h, m, s_ms = start_str.split(':')
                        s, ms = s_ms.split(',')
                        current_segment_start = int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000.0
                        
                        h, m, s_ms = end_str.split(':')
                        s, ms = s_ms.split(',')
                        current_segment_end = int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000.0
                    except:
                        pass
                continue
                
            if '<' in line and '>' in line:
                matches = re.finditer(r'<(\d{2}:\d{2}:\d{2},\d{3})>([^<]+)', line)
                for m in matches:
                    time_str = m.group(1)
                    word = m.group(2).strip()
                    if word:
                        try:
                            h, m_part, s_ms = time_str.split(':')
                            s, ms = s_ms.split(',')
                            start_sec = int(h)*3600 + int(m_part)*60 + int(s) + int(ms)/1000.0
                            word_events.append({
                                "word": word,
                                "start": start_sec,
                                "end": current_segment_end
                            })
                        except:
                            pass
            else:
                words = line.split()
                if not words:
                    continue
                duration = max(0, current_segment_end - current_segment_start)
                time_per_word = duration / len(words)
                
                for i, word in enumerate(words):
                    w_start = current_segment_start + i * time_per_word
                    w_end = w_start + time_per_word
                    word_events.append({
                        "word": word.strip(),
                        "start": w_start,
                        "end": w_end
                    })

        for i in range(len(word_events)):
            if i < len(word_events) - 1:
                next_start = word_events[i+1]["start"]
                if next_start > word_events[i]["start"]:
                    word_events[i]["end"] = next_start
            else:
                word_events[i]["end"] = max(word_events[i]["start"] + 0.5, word_events[i]["end"])
    else:
        print("[⚙️] Loading Whisper model...")
        model = whisper.load_model("large")
        temp_audio = os.path.join(base_dir, "_whisper_audio.wav")
        subprocess.run(
            ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
             "-ar", "16000", "-ac", "1", temp_audio, "-y"],
            check=True, capture_output=True
        )
        print("[⚙️] Transcribing with Whisper...")
        result = model.transcribe(temp_audio, word_timestamps=True, verbose=False)
    
        for seg in result.get("segments", []):
            for w in seg.get("words", []):
                word_events.append({
                    "word":  w["word"].strip(),
                    "start": w["start"],
                    "end":   w["end"]
                })

    hook_pri_text = cap_options.get("hookPrimaryText", "").strip()
    hook_sec_text = cap_options.get("hookSecondaryText", "").strip()
    if cap_options.get("hookEngine") and (hook_pri_text or hook_sec_text):
        hook_dur = float(cap_options.get("hookDuration", 1.5))
        word_events = [w for w in word_events if w["start"] >= hook_dur]

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
  @import url('https://fonts.cdnfonts.com/css/proxima-nova-2');
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
        
        # ── DYNAMIC SVG ICON LIBRARY ──
        svg_map = {
            "instagram": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%; height:100%;"><rect x="2" y="2" width="20" height="20" rx="5" ry="5"></rect><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path><line x1="17.5" y1="6.5" x2="17.51" y2="6.5"></line></svg>',
            "youtube": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%; height:100%;"><path d="M2.5 17a24.12 24.12 0 0 1 0-10 2 2 0 0 1 1.4-1.4 49.56 49.56 0 0 1 16.2 0A2 2 0 0 1 21.5 7a24.12 24.12 0 0 1 0 10 2 2 0 0 1-1.4 1.4 49.55 49.55 0 0 1-16.2 0A2 2 0 0 1 2.5 17"></path><path d="M10 15l5-3-5-3v6z"></path></svg>',
            "tiktok": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%; height:100%;"><path d="M9 12a4 4 0 1 0 4 4V4a5 5 0 0 0 5 5"></path></svg>',
            "money": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%; height:100%;"><rect x="2" y="6" width="20" height="12" rx="2"></rect><circle cx="12" cy="12" r="2"></circle><path d="M6 12h.01M18 12h.01"></path></svg>',
            "fire": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%; height:100%;"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"></path></svg>',
            "ai": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%; height:100%;"><path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"></path></svg>',
            "law": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%; height:100%;"><path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"></path><path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"></path><path d="M7 21h10"></path><path d="M12 3v18"></path><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"></path></svg>',
            "time": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%; height:100%;"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>',
            "code": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%; height:100%;"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg>',
            "lightning": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%; height:100%;"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>',
            "document": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%; height:100%;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>',
            "star": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%; height:100%;"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>',
            "heart": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%; height:100%;"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>',
            "camera": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%; height:100%;"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path><circle cx="12" cy="13" r="4"></circle></svg>',
            "music": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%; height:100%;"><path d="M9 18V5l12-2v13"></path><circle cx="6" cy="18" r="3"></circle><circle cx="18" cy="16" r="3"></circle></svg>',
            "globe": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%; height:100%;"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>',
            "check": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="width:100%; height:100%;"><polyline points="20 6 9 17 4 12"></polyline></svg>',
            "cross": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="width:100%; height:100%;"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>',
            "chart": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%; height:100%;"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"></polyline><polyline points="17 6 23 6 23 12"></polyline></svg>',
            "lightbulb": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%; height:100%;"><path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1.3.5 2.6 1.5 3.5.8.8 1.3 1.5 1.5 2.5"></path><path d="M9 18h6"></path><path d="M10 22h4"></path></svg>',
            "shield": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%; height:100%;"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>',
            "lock": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%; height:100%;"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>'
        }
        
        for t_s, t_e, png_path, phrase_words, active_idx, phrase_start in segments:
            key = (phrase_words, active_idx)
            if key in rendered_done: continue
            
            # 🚀 UPGRADED: Smart Row Line-Breaking Logic with Background SVGs
            page.evaluate("""
                (args) => {
                    const wrapEl = document.getElementById('wrap');
                    wrapEl.innerHTML = ''; 
                    
                    const isHeavy = (word) => word.replace(/[^a-zA-Z0-9]/g, '').length > 4;
                    
                    // 1. Start with a slightly smaller base size overall, multiplied by user scale
                    let baseSize = args.H * 0.045 * args.scale; 
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
                            
                            if (index === args.active_index && args.s_class !== 'none') {
                                span.className = 'base-cap ' + args.s_class;
                                span.style.transform = 'scale(1.05)';
                                span.style.display = 'inline-block';
                                span.style.transition = 'transform 0.1s ease-out';
                            } else {
                                span.className = 'base-cap ' + args.p_class;
                            }
                        }
                        
                        if (index > args.active_index) {
                            span.style.visibility = 'hidden'; 
                        }
                        
                        currentRow.appendChild(span);
                        wordsInRow++;
                        charsInRow += word.length;
                    });
                    
                    // 5. SVG Backdrop Injection (Dynamic Color & Animation)
                    let foundIcon = null;
                    let triggerIndex = -1;
                    const aliases = {
                        'instagram': 'instagram', 'ig': 'instagram', 'insta': 'instagram',
                        'youtube': 'youtube', 'yt': 'youtube', 'channel': 'youtube',
                        'tiktok': 'tiktok', 'tt': 'tiktok',
                        'money': 'money', 'cash': 'money', 'dollars': 'money', 'profit': 'money', 'rich': 'money', 'paid': 'money',
                        'fire': 'fire', 'burn': 'fire', 'hot': 'fire',
                        'ai': 'ai', 'chatgpt': 'ai', 'artificial': 'ai', 'software': 'ai', 'robot': 'ai',
                        'law': 'law', 'firm': 'law', 'lawyer': 'law', 'attorney': 'law', 'legal': 'law',
                        'time': 'time', 'clock': 'time', 'days': 'time', 'months': 'time', 'weeks': 'time', 'hours': 'time',
                        'code': 'code', 'app': 'code', 'api': 'code', 'developer': 'code',
                        'lightning': 'lightning', 'speed': 'lightning', 'fast': 'lightning', 'quick': 'lightning',
                        'document': 'document', 'blueprint': 'document', 'file': 'document', 'paper': 'document',
                        
                        'star': 'star', 'premium': 'star', 'best': 'star', 'top': 'star', 'quality': 'star',
                        'heart': 'heart', 'love': 'heart', 'like': 'heart', 'favorite': 'heart',
                        'camera': 'camera', 'video': 'camera', 'record': 'camera', 'film': 'camera', 'shot': 'camera', 'photo': 'camera',
                        'music': 'music', 'audio': 'music', 'sound': 'music', 'song': 'music', 'beat': 'music', 'track': 'music',
                        'globe': 'globe', 'world': 'globe', 'global': 'globe', 'online': 'globe', 'internet': 'globe', 'earth': 'globe',
                        'check': 'check', 'yes': 'check', 'correct': 'check', 'right': 'check', 'true': 'check', 'done': 'check', 'complete': 'check',
                        'cross': 'cross', 'no': 'cross', 'wrong': 'cross', 'false': 'cross', 'stop': 'cross', 'error': 'cross', 'fail': 'cross',
                        'chart': 'chart', 'growth': 'chart', 'analytics': 'chart', 'numbers': 'chart', 'data': 'chart', 'scale': 'chart', 'trending': 'chart',
                        'lightbulb': 'lightbulb', 'idea': 'lightbulb', 'smart': 'lightbulb', 'genius': 'lightbulb', 'mind': 'lightbulb', 'learn': 'lightbulb', 'think': 'lightbulb',
                        'shield': 'shield', 'secure': 'shield', 'safe': 'shield', 'protect': 'shield', 'trust': 'shield', 'privacy': 'shield',
                        'lock': 'lock', 'secret': 'lock', 'locked': 'lock', 'password': 'lock', 'private': 'lock'
                    };
                    const cleanWords = args.words.map(w => w.replace(/[^a-zA-Z]/g, '').toLowerCase());
                    for (let i = 0; i < cleanWords.length; i++) {
                        let w = cleanWords[i];
                        if (aliases[w] && args.svg_map[aliases[w]]) {
                            foundIcon = args.svg_map[aliases[w]];
                            triggerIndex = i;
                            break;
                        }
                    }
                    // Inject a dynamic silver metallic gradient definition if it doesn't exist yet
                    if (!document.getElementById('silver-grad-def')) {
                        const defDiv = document.createElement('div');
                        defDiv.innerHTML = `
                            <svg width="0" height="0" id="silver-grad-def" style="position:absolute;">
                                <defs>
                                    <linearGradient id="premiumSilver" x1="0%" y1="0%" x2="100%" y2="100%">
                                        <stop offset="0%" stop-color="#ffffff"/>
                                        <stop offset="30%" stop-color="#dceaff"/>
                                        <stop offset="50%" stop-color="#9fc4ff"/>
                                        <stop offset="70%" stop-color="#dceaff"/>
                                        <stop offset="100%" stop-color="#ffffff"/>
                                    </linearGradient>
                                </defs>
                            </svg>
                        `;
                        wrapEl.appendChild(defDiv);
                    }

                    if (foundIcon) {
                        const iconDiv = document.createElement('div');
                        // Replace 'currentColor' with our premium silver metallic gradient URL
                        iconDiv.innerHTML = foundIcon.replace(/stroke="currentColor"/g, 'stroke="url(#premiumSilver)"');
                        
                        // Intense stacked drop-shadow for the ultimate glowing effect
                        iconDiv.style.cssText = 'filter: drop-shadow(0 0 25px rgba(160, 200, 255, 0.95)) drop-shadow(0 0 10px rgba(255, 255, 255, 1));';
                        
                        iconDiv.style.position = 'absolute';
                        iconDiv.style.top = '40%';
                        iconDiv.style.left = '50%';
                        iconDiv.style.zIndex = '-1';
                        
                        // Size the SVG
                        const iconSize = baseSize * 3.5; 
                        iconDiv.style.width = iconSize + 'px';
                        iconDiv.style.height = iconSize + 'px';
                        
                        // ✨ ICON ANIMATION LOGIC ✨
                        // Glow brightly at full opacity when triggered, otherwise subtle background glow
                        if (args.active_index === triggerIndex) {
                            iconDiv.style.opacity = '1.0';
                            iconDiv.style.transform = 'translate(-50%, -50%) scale(1.15)';
                            iconDiv.style.transition = 'transform 0.1s ease-out, opacity 0.1s ease-out';
                        } else {
                            iconDiv.style.opacity = '0.35';
                            iconDiv.style.transform = 'translate(-50%, -50%) scale(0.9)';
                        }
                        
                        wrapEl.appendChild(iconDiv);
                    }
                }
            """, {
                "words": list(phrase_words),
                "active_index": active_idx,
                "H": H,
                "font_family": font_family,
                "p_class": p_class,
                "s_class": s_class,
                "mixed_style": mixed_style,
                "scale": cap_scale,
                "svg_map": svg_map
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
    if 'temp_audio' in locals() and os.path.exists(temp_audio):
        os.remove(temp_audio)

    print(f"[✅] Perfect Kinetic staggered phrases burned with '{anim_style}' animation: {output_vid}")
    return output_vid


# ─────────────────────────────────────────────────────────────────────────────
# 6. SINHALA TRANSCRIPT via GEMINI
# ─────────────────────────────────────────────────────────────────────────────

def get_perfect_sinhala_transcript(audio_path: str, api_key_opt: str = None, whisper_words: list = None) -> list:
    from google import genai
    from google.genai import types
    import time
    import json
    import os
 
    raw_keys = []
    if api_key_opt: raw_keys.append(("UI_PROVIDED_KEY", api_key_opt))
    primary_key = os.getenv("GEMINI_API_KEY")
    if primary_key: raw_keys.append(("GEMINI_API_KEY", primary_key))
    bypass_key = os.getenv("GEMINI_API_KEY_BYPASS")
    if bypass_key: raw_keys.append(("GEMINI_API_KEY_BYPASS", bypass_key))
    autopass_key = os.getenv("GEMINI_API_KEY_AUTOPASS")
    if autopass_key: raw_keys.append(("GEMINI_API_KEY_AUTOPASS", autopass_key))

    keys_to_try = []
    seen = set()
    for name, k in raw_keys:
        if k and k != "YOUR_FREE_API_KEY" and k not in seen:
            seen.add(k)
            keys_to_try.append((name, k))
    
    if not keys_to_try:
        print("[⚠️] No valid GEMINI_API_KEY found. Proceeding without forced alignment.")
        return []
    
    print(f"[⚙️] Will try {len(keys_to_try)} API key(s)...")

    import subprocess
    try:
        probe_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
        dur_out = subprocess.check_output(probe_cmd, text=True).strip()
        audio_dur = float(dur_out)
        duration_text = f"The total length of this audio is exactly {audio_dur:.2f} seconds. Your timestamps MUST NOT exceed this duration."
    except Exception:
        duration_text = "Pay close attention to the length of the audio."

    prompt = f"""
    Listen to this audio. It is a mix of Sinhala and English (Singlish).
    Write down EXACTLY what is said, verbatim.
    
    IMPORTANT CONTEXT: {duration_text}
    
    CRITICAL RULES: 
    1. DO NOT add words. DO NOT guess words. DO NOT fix broken sentences. If the audio mumbles, transcribe the mumble. Strictly stick to the voice.
    2. Break the text into short, logical phrases of exactly 3 to 5 words each.
    3. TRANSLITERATE ENGLISH: If an English technical word is spoken, type it in English letters (e.g., "AC", "pipe", "commission" , "Grab Me"). 
    4. NUMBER FORMATTING: Convert all spoken numbers into actual digits (e.g., "රුපියල් 5000").
    5. SLANG CORRECTION: Fix casual Singlish slang ONLY IF it matches the audio timing (e.g., keep "direct වැඩගන්න", "බාස්" , "වැඩ").
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

    models_to_try = ['gemini-flash-latest', 'gemini-2.5-pro', 'gemini-2.5-flash']

    for m_idx, model_name in enumerate(models_to_try):
        for attempt, (key_name, api_key) in enumerate(keys_to_try):
            if m_idx > 0 or attempt > 0:
                print(f"\n[⚠️] Retrying with Model '{model_name}' and API Key '{key_name}' (Model {m_idx+1}/{len(models_to_try)}, Key {attempt+1}/{len(keys_to_try)})...")
            
            print(f"[⚙️] Uploading audio to Gemini API using key '{key_name}'...")
            
            try:
                client = genai.Client(api_key=api_key)
                # 1. Upload the extracted .wav file to Gemini
                audio_file = client.files.upload(file=audio_path)
                
                # 2. Wait for processing (required for audio)
                while getattr(audio_file.state, "name", audio_file.state) == "PROCESSING":
                    print(".", end="", flush=True)
                    time.sleep(2)
                    audio_file = client.files.get(name=audio_file.name)
                print("\n[✅] Audio processed by Gemini.")
        
                # 4. Generate content
                import threading
                import sys
                
                done = False
                def print_progress():
                    while not done:
                        sys.stdout.write(".")
                        sys.stdout.flush()
                        time.sleep(2)
                        
                print(f"[⚙️] Generating 99% accurate transcript with {model_name} (this can take 20-60s)", end="")
                t = threading.Thread(target=print_progress)
                t.start()
                
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[prompt, audio_file],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json"
                        )
                    )
                finally:
                    done = True
                    t.join()
                    print()
                
                # Clean up the file from Google's servers
                client.files.delete(name=audio_file.name)
                
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
                print(f"[❌] Gemini API Error with model {model_name} and key {api_key[:6]}...: {e}")
                try:
                    if 'audio_file' in locals() and hasattr(audio_file, 'name'):
                        client.files.delete(name=audio_file.name)
                except:
                    pass
                
                # If we exhausted all keys for all models, give up
                if m_idx == len(models_to_try) - 1 and attempt == len(keys_to_try) - 1:
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

def align_phrases_to_whisper(gemini_phrases: list, whisper_words: list, from_manual: bool = False) -> list:
    """
    SMART ALIGNMENT ENGINE
    - If from_manual=True: timestamps are already accurate, only apply gap-fill smoothing.
    - If from_manual=False: apply Dynamic Time Warping (Elastic Projection) to fix
      Gemini's hallucinated timestamps using Whisper anchors.
    """
    phrases = [p for p in gemini_phrases if p.get("phrase", "").strip()]
    if not phrases:
        return []

    # ── MANUAL JSON PATH: Trust the timestamps, just smooth the gaps ──────────
    if from_manual or not whisper_words:
        print("[⚙️] Manual JSON mode: trusting timestamps, applying gap-fill only...")
        aligned = []
        MIN_DUR = 0.40

        for i, p in enumerate(phrases):
            start = float(p.get("start", 0))
            end   = float(p.get("end", start + 0.8))

            # Enforce minimum duration
            if end - start < MIN_DUR:
                end = start + MIN_DUR

            aligned.append({
                "phrase": p["phrase"],
                "start":  start,
                "end":    end
            })

        # Gap-fill: stretch each caption to fill small silences before the next phrase
        for i in range(len(aligned) - 1):
            gap = aligned[i + 1]["start"] - aligned[i]["end"]
            if 0 < gap <= 0.80:
                aligned[i]["end"] += gap * 0.85

        print(f"[✅] Manual alignment: {len(aligned)} phrases passed through with gap-fill.")
        return aligned

    # ── AUTO GEMINI PATH: Full Elastic Projection ─────────────────────────────
    anchors = sorted(whisper_words, key=lambda x: x["start"])

    g_starts = [float(p.get("start", 0)) for p in phrases]
    g_min, g_max = min(g_starts), max(g_starts)
    if g_max == g_min:
        g_max = g_min + 1.0

    w_starts = [float(a["start"]) for a in anchors]
    w_min, w_max = min(w_starts), max(w_starts)
    if w_max == w_min:
        w_max = w_min + 1.0

    aligned = []
    last_end = 0.0
    MIN_DUR  = 0.40

    for i, p in enumerate(phrases):
        g_time   = float(p.get("start", 0))
        progress = (g_time - g_min) / (g_max - g_min)
        projected_w_time = w_min + progress * (w_max - w_min)

        valid_anchors = [a for a in anchors if a["start"] >= last_end - 0.1]
        if valid_anchors:
            best_anchor  = min(valid_anchors, key=lambda a: abs(a["start"] - projected_w_time))
            actual_start = best_anchor["start"]
        else:
            actual_start = max(last_end, projected_w_time)

        actual_start = max(actual_start, last_end)

        if i + 1 < len(phrases):
            next_g_time  = float(phrases[i + 1].get("start", g_time + 1.0))
            next_prog    = (next_g_time - g_min) / (g_max - g_min)
            next_proj_w  = w_min + next_prog * (w_max - w_min)
            valid_next   = [a for a in anchors if a["start"] > actual_start]
            if valid_next:
                next_anchor = min(valid_next, key=lambda a: abs(a["start"] - next_proj_w))
                actual_end  = next_anchor["start"] - 0.05
            else:
                actual_end  = next_proj_w - 0.05
        else:
            actual_end = anchors[-1]["end"] if anchors[-1]["end"] > actual_start else actual_start + 1.0

        if actual_end - actual_start < MIN_DUR:
            actual_end = actual_start + MIN_DUR

        aligned.append({
            "phrase": p["phrase"],
            "start":  actual_start,
            "end":    actual_end
        })
        last_end = actual_end

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
    cap_bottom_pct = float(cap_options.get("captionBottomPercent", 22)) / 100.0
    cap_scale      = float(cap_options.get("captionScale", 100)) / 100.0

    # 1. Extract Audio
    temp_audio = os.path.join(base_dir, "_gemini_audio.wav")
    subprocess.run(
        ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
         "-ar", "16000", "-ac", "1", temp_audio, "-y"],
        check=True, capture_output=True
    )

    # 2. Get Timestamps via Whisper (Run FIRST so we can feed it to Gemini!)
    manual_gemini_json = cap_options.get("manualGeminiJson", "").strip()
    is_manual_gemini = cap_options.get("useManualGemini", False) and bool(manual_gemini_json)
    
    whisper_words = []
    if is_manual_gemini:
        print("[⚙️] Bypassing Whisper entirely for Manual JSON...")
    else:
        print("[⚙️] Running Whisper (base) — SEGMENT-ANCHOR mode for Sinhala...")
        try:
            from faster_whisper import WhisperModel
            import importlib.util
            if os.name == 'nt':
                try:
                    for pkg in ["nvidia.cublas", "nvidia.cudnn", "nvidia.cufft", "nvidia.curand", "nvidia.cusolver", "nvidia.cusparse", "nvidia.nvtx", "nvidia.nccl"]:
                        spec = importlib.util.find_spec(pkg)
                        if spec and spec.submodule_search_locations:
                            bin_path = os.path.join(spec.submodule_search_locations[0], "bin")
                            if os.path.exists(bin_path):
                                os.environ["PATH"] = bin_path + os.pathsep + os.environ.get("PATH", "")
                except Exception:
                    pass

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

            if len(word_anchors) > 0:
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
                print(f"[⚙️] Using {len(whisper_words)} segment-level anchors.")

        except Exception as e:
            print(f"[⚠️] Whisper failed ({e}). Falling back to Gemini timestamps without hints.")
            whisper_words = []

    # 3. Get Perfect Phrases from Gemini (using Whisper hints if available)
    if is_manual_gemini:
        print("[⚙️] Manual Gemini JSON detected! Bypassing API call entirely.")
        try:
            gemini_phrases = json.loads(manual_gemini_json)
        except Exception as e:
            print(f"[❌] FATAL: Invalid manual JSON: {e}")
            gemini_phrases = []
    else:
        gemini_phrases = get_perfect_sinhala_transcript(temp_audio, cap_options.get("geminiApiKey"), whisper_words)

    if not gemini_phrases:
        print("[❌] FATAL: Gemini failed. Cannot render captions.")
        if os.path.exists(temp_audio): os.remove(temp_audio)
        return video_path

    print(f"[⚙️] Extracted {len(gemini_phrases)} Singlish phrases from Gemini.")

    # ── STEP 3: Drift-corrected alignment ────────────────────────────────────
    if is_manual_gemini:
        segments_data = align_phrases_to_whisper(gemini_phrases, [], from_manual=True)
        print(f"[✅] Manual alignment done — {len(segments_data)} synced phrases.")
    elif whisper_words:
        segments_data = align_phrases_to_whisper(gemini_phrases, whisper_words, from_manual=False)
        print(f"[✅] Alignment done — {len(segments_data)} synced phrases.")
    else:
        print("[⚠️] Using Gemini timestamps with +0.10s offset as fallback.")
        segments_data = [
            {"phrase": p["phrase"],
             "start":  p["start"] + 0.10,
             "end":    p["end"]   + 0.10}
            for p in gemini_phrases
        ]

    hook_pri_text = cap_options.get("hookPrimaryText", "").strip()
    hook_sec_text = cap_options.get("hookSecondaryText", "").strip()
    if cap_options.get("hookEngine") and (hook_pri_text or hook_sec_text):
        hook_dur = float(cap_options.get("hookDuration", 1.5))
        segments_data = [s for s in segments_data if float(s["start"]) >= hook_dur]

    # ── NEW: Extract your Full-Stops for the Transition Engine ──
    flash_times = []
    for i, item in enumerate(segments_data):
        phrase_text = str(item.get("phrase", ""))
        # If the AI marked this phrase with a director's cut pipe symbol "|"
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
  .si-font-pri {{ font-family: 'Montserrat', 'Gemunu Libre', sans-serif; font-weight: 900; letter-spacing: -0.5px; }}
  .si-font-sec {{ font-family: 'Montserrat', 'Gemunu Libre', sans-serif; font-weight: 900; letter-spacing: -1px; }}

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

    # Point Playwright to the system-installed browsers since PyInstaller Temp doesn't bundle them
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "ms-playwright")
    
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
            if   char_count <= 15: font_size = int(H * 0.055 * cap_scale)
            elif char_count <= 25: font_size = int(H * 0.045 * cap_scale)
            else:                  font_size = int(H * 0.038 * cap_scale)

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
    import cv2
    import numpy as np
    
    base_dir    = os.path.dirname(os.path.abspath(video_path))
    output_vid  = os.path.splitext(video_path)[0] + "_glow.mp4"
    overlay_png = os.path.join(base_dir, "_bottom_glow.png")

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", video_path],
        capture_output=True, text=True
    )
    try:
        info = json.loads(probe.stdout)["streams"][0]
        W, H = int(info["width"]), int(info["height"])
    except Exception:
        W, H = 1080, 1920

    color_hex = color_hex.lstrip('#')
    if len(color_hex) != 6:
        color_hex = "000000"
    r, g, b = tuple(int(color_hex[i:i+2], 16) for i in (0, 2, 4))

    glow_h = int(H * 0.45)
    glow_img = np.zeros((glow_h, W, 4), dtype=np.uint8)
    for y in range(glow_h):
        alpha = int((y / glow_h) ** 2 * 230)
        glow_img[y, :, 0] = b
        glow_img[y, :, 1] = g
        glow_img[y, :, 2] = r
        glow_img[y, :, 3] = alpha
        
    cv2.imwrite(overlay_png, glow_img)
    
    filter_complex = f"[1:v]format=rgba[glow];[0:v][glow]overlay=x=0:y={H - glow_h}:format=auto[outv]"
    try:
        subprocess.run(["ffmpeg", "-f", "lavfi", "-i", "nullsrc", "-c:v", "h264_nvenc", "-t", "1", "-f", "null", "-"], check=True, capture_output=True)
        cvcodec = "h264_nvenc"
        preset = "p6"
        cq_args = ["-cq", "18"]
    except:
        cvcodec = "libx264"
        preset = "superfast"
        cq_args = ["-crf", "18"]

    cmd = [
        "ffmpeg", "-hwaccel", "auto", "-i", video_path, "-i", overlay_png,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "0:a?",
        "-c:v", cvcodec, "-preset", preset
    ] + cq_args + [
        "-pix_fmt", "yuv420p", "-c:a", "copy",
        output_vid, "-y"
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        if os.path.exists(overlay_png): os.remove(overlay_png)
        print(f"[✅] Cinematic Bottom Glow applied: {output_vid}")
        return output_vid
    except subprocess.CalledProcessError:
        print(f"[⚠️] Bottom Glow failed. Skipping.")
        if os.path.exists(overlay_png): os.remove(overlay_png)
        return video_path

# ─────────────────────────────────────────────
# 10.5 CINEMATIC BEAUTY FILTER ENGINE
# ─────────────────────────────────────────────

def stage_beauty_filter(video_path: str, options: dict) -> str:
    import cv2
    import numpy as np
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision
    
    print("[⚙️] Booting AI Face Mesh Beauty Engine (MediaPipe Tasks + OpenCV)...")
    base_dir    = os.path.dirname(os.path.abspath(video_path))
    output_vid  = os.path.splitext(video_path)[0] + "_beauty.mp4"
    
    engine_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(engine_dir, "pretrained_models", "face_landmarker.task")
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    if not os.path.exists(model_path):
        print("[⚙️] Downloading MediaPipe Face Landmarker model...")
        import urllib.request
        urllib.request.urlretrieve(
            "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task",
            model_path
        )
        
    base_options = mp_python.BaseOptions(model_asset_path=model_path)
    task_options = vision.FaceLandmarkerOptions(
        base_options=base_options,
        output_face_blendshapes=False,
        output_facial_transformation_matrixes=False,
        num_faces=1
    )
    
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps != fps: fps = 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    cmd = [
        "ffmpeg", "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{width}x{height}", "-pix_fmt", "bgr24", "-r", str(fps), "-i", "-",
        "-i", video_path, "-map", "0:v:0", "-map", "1:a:0?",
        "-vf", "scale=iw:ih*1.03,crop=iw:ih",
        "-c:v", "h264_nvenc", "-preset", "p4", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "copy", output_vid
    ]
    
    try:
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    except Exception as e:
        print(f"[❌] Failed to open FFmpeg pipe: {e}")
        return video_path
    
    LEFT_EYE = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]
    RIGHT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
    LIPS = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40]
    FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]

    with vision.FaceLandmarker.create_from_options(task_options) as landmarker:
        while True:
            ret, frame = cap.read()
            if not ret: break
            
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
            detection_result = landmarker.detect(mp_image)
            
            if detection_result.face_landmarks:
                for face_landmarks in detection_result.face_landmarks:
                    h, w, _ = frame.shape
                    
                    mask = np.zeros((h, w), dtype=np.uint8)
                    oval_pts = np.array([[int(face_landmarks[i].x * w), int(face_landmarks[i].y * h)] for i in FACE_OVAL], np.int32)
                    cv2.fillPoly(mask, [cv2.convexHull(oval_pts)], 255)
                    
                    for feature in [LEFT_EYE, RIGHT_EYE, LIPS]:
                        pts = np.array([[int(face_landmarks[i].x * w), int(face_landmarks[i].y * h)] for i in feature], np.int32)
                        cv2.fillPoly(mask, [cv2.convexHull(pts)], 0)
                    
                    mask = cv2.GaussianBlur(mask, (21, 21), 0)
                    mask_3d = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR) / 255.0
                    
                    smoothed = cv2.bilateralFilter(frame, 15, 75, 75)
                    
                    hsv = cv2.cvtColor(smoothed, cv2.COLOR_BGR2HSV).astype(np.float32)
                    hsv[:, :, 1] *= 1.10
                    hsv[:, :, 2] *= 1.08
                    hsv = np.clip(hsv, 0, 255).astype(np.uint8)
                    glowing_skin = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
                    
                    frame = (frame * (1 - mask_3d) + glowing_skin * mask_3d).astype(np.uint8)
                    break
                    
            process.stdin.write(frame.tobytes())
            
    cap.release()
    process.stdin.close()
    process.wait()
    
    print(f"[✅] AI Beauty Engine complete: {output_vid}")
    return output_vid


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

    mode          = bg_options.get("bgMode", "blur")
    hex_color     = bg_options.get("bgColor", "#09090b").lstrip('#')
    bg_image_path = bg_options.get("bgImagePath", "")
    keying_mode   = bg_options.get("keyingMode", "ai")
    
    bg_scale      = int(bg_options.get("bgScale", 100))
    sub_scale     = int(bg_options.get("subjectScale", 100))
    sub_y         = int(bg_options.get("subjectY", 0))

    print(f"[⚙️] Background FX Engine — mode: {mode} | keying: {keying_mode}")

    base_dir   = os.path.dirname(os.path.abspath(video_path))
    temp_vid   = os.path.join(base_dir, "_temp_bg_fx.mp4")
    output_vid = os.path.splitext(video_path)[0] + "_bgfx.mp4"
    temp_audio = os.path.join(base_dir, "_temp_audio.wav")

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

    # ── Chroma Key Path (FFmpeg Hardware Accelerated) ─────────────────────
    if keying_mode == "chroma":
        print("[🟩] Green Screen chroma-key active — using FFmpeg hardware math.")
        cap.release()
        out.release()
        if os.path.exists(temp_vid): os.remove(temp_vid)

        # ── TRUE 9:16 VERTICAL ARCHITECTURE ─────────────────────────────────
        # Final output canvas is ALWAYS 1080x1920 regardless of source dimensions.
        # All coordinates map to out_w / out_h, not source w/h.
        out_w, out_h = 1080, 1920

        # Handle Timeline Scenes & Sandwich Text
        timeline_scenes = bg_options.get("timelineScenes", [])
        if not timeline_scenes:
            timeline_scenes = [{
                "timestamp": 0.0,
                "bgImagePath": bg_image_path if mode == "image" else "",
                "bgScale": bg_scale,
                "subjectScale": sub_scale,
                "subjectY": sub_y,
                "textBehind": bg_options.get("textBehind", ""),
                "textY": bg_options.get("textY", 50),
                "textSize": bg_options.get("textSize", 100),
            }]

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True
        )
        try:
            video_duration = float(probe.stdout.strip())
        except:
            video_duration = 9999.0

        inputs = ["-i", video_path]
        num_inputs = 1
        filter_complex = ""
        valid_scene_count = 0

        for i, scene in enumerate(timeline_scenes):
            start_t = float(scene.get("timestamp", 0))
            end_t = float(timeline_scenes[i+1].get("timestamp")) if i+1 < len(timeline_scenes) else video_duration
            dur = end_t - start_t
            if dur <= 0: continue

            valid_scene_count += 1

            # 1. Background Source — always scale to 1080x1920
            scene_bg_img = scene.get("bgImagePath", "")
            scene_bg_scale = int(scene.get("bgScale", 100))
            if scene_bg_img and os.path.exists(scene_bg_img):
                inputs.extend(["-loop", "1", "-i", scene_bg_img])
                idx = num_inputs
                num_inputs += 1
                # base_scale = max(out_w/src_w, out_h/src_h) ensures full coverage
                # Then we apply the user bgScale zoom on top, centred crop to 1080x1920
                zoom_pct = scene_bg_scale / 100.0
                filter_complex += (
                    f"[{idx}:v]trim=duration={dur},setpts=PTS-STARTPTS,"
                    f"scale=iw*max({out_w}/iw\\,{out_h}/ih)*{zoom_pct:.4f}:"
                    f"ih*max({out_w}/iw\\,{out_h}/ih)*{zoom_pct:.4f},"
                    f"crop={out_w}:{out_h}[bg_raw{i}];"
                )
            else:
                scene_hex = hex_color if len(hex_color) == 6 else "09090b"
                filter_complex += f"color=c=#{scene_hex}:s={out_w}x{out_h}:d={dur}[bg_raw{i}];"

            # 2. Sandwich Text — coordinates mapped to out_h / out_w
            text = scene.get("textBehind", "").strip()
            if text:
                text_y_pct = int(scene.get("textY", 50))
                text_size = int(scene.get("textSize", 100))
                # Font size relative to output height, scaled by textSize %
                fs = int(out_h * 0.07 * (text_size / 100.0))
                fs = max(fs, 24)
                esc_text = text.replace("'", "\\\'").replace(":", "\\:")
                # text_y anchored to out_h — text slides from 25% lower than marker (chest level)
                base_y = int(out_h * text_y_pct / 100)
                start_y = min(base_y + int(out_h * 0.25), out_h - fs - 10)
                text_x = f"({out_w}-text_w)/2"
                text_cmd = (
                    f"drawtext=text='{esc_text}':fontcolor=white:fontsize={fs}"
                    f":x={text_x}:y={base_y}"
                    f":fontfile=/Windows/Fonts/impact.ttf"
                    f":shadowcolor=black:shadowx=3:shadowy=3"
                )
                filter_complex += f"[bg_raw{i}]{text_cmd}[bg{i}];"
            else:
                filter_complex += f"[bg_raw{i}]copy[bg{i}];"

            # 3. Subject — chroma key, scale to 1080x1920, compose on bg
            scene_sub_scale = int(scene.get("subjectScale", 100))
            scene_sub_y = int(scene.get("subjectY", 0))

            # Scale source video to 9:16 canvas first, then apply subject scale
            final_scale = scene_sub_scale / 100.0
            sub_canvas_w = int(out_w * final_scale)
            sub_canvas_h = int(out_h * final_scale)
            sub_canvas_w += sub_canvas_w % 2
            sub_canvas_h += sub_canvas_h % 2

            # y_offset: positive = down, negative = up — maps to out_h
            y_px_offset = int(out_h * scene_sub_y / 100)
            overlay_y = f"H-h+{y_px_offset}" if y_px_offset >= 0 else f"H-h{y_px_offset}"

            chroma_filter = "chromakey=0x1A9535:0.11:0.02,despill=green"
            filter_complex += (
                f"[0:v]trim=start={start_t}:duration={dur},setpts=PTS-STARTPTS,"
                f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
                f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2,"
                f"{chroma_filter},"
                f"scale={sub_canvas_w}:{sub_canvas_h}[fg{i}];"
            )
            filter_complex += f"[bg{i}][fg{i}]overlay=(W-w)/2:{overlay_y}:shortest=1[seg{i}];"

        # Concat all valid segments
        seg_labels = "".join([f"[seg{i}]" for i, scene in enumerate(timeline_scenes)
                              if (float(timeline_scenes[i+1].get('timestamp') if i+1 < len(timeline_scenes) else video_duration) - float(scene.get('timestamp', 0))) > 0])
        n_segs = valid_scene_count
        if n_segs > 1:
            filter_complex += f"{seg_labels}concat=n={n_segs}:v=1:a=0,format=yuv420p[outv]"
        elif n_segs == 1:
            # find the one valid seg label
            first_valid = next(
                i for i, scene in enumerate(timeline_scenes)
                if (float(timeline_scenes[i+1].get('timestamp') if i+1 < len(timeline_scenes) else video_duration) - float(scene.get('timestamp', 0))) > 0
            )
            filter_complex += f"[seg{first_valid}]format=yuv420p[outv]"
        else:
            print("[❌] No valid scenes found. Skipping background FX.")
            for f in [temp_audio]:
                if os.path.exists(f): os.remove(f)
            return video_path

        # Standard Swoosh for Text Slide Up Sandwich
        engine_dir = os.path.dirname(os.path.abspath(__file__))
        swoosh_sfx = os.path.join(engine_dir, "assets", "Standard Swoosh.wav")
        swoosh_times = []
        for scene in timeline_scenes:
            if scene.get("textBehind", "").strip():
                swoosh_times.append(float(scene.get("timestamp", 0.0)))

        audio_idx = num_inputs
        inputs.extend(["-i", temp_audio])
        num_inputs += 1
        
        audio_map = f"{audio_idx}:a?"
        
        if os.path.exists(swoosh_sfx) and swoosh_times:
            swoosh_idx = num_inputs
            inputs.extend(["-i", swoosh_sfx])
            num_inputs += 1
            
            filter_complex += f"[{audio_idx}:a]volume=1.0[main_a];"
            mix_inputs = "[main_a]"
            for i, t in enumerate(swoosh_times):
                delay_ms = int(max(0, t) * 1000)
                filter_complex += f"[{swoosh_idx}:a]adelay={delay_ms}|{delay_ms}[swoosh_{i}];"
                mix_inputs += f"[swoosh_{i}]"
            total_audios = len(swoosh_times) + 1
            filter_complex += f"{mix_inputs}amix=inputs={total_audios}:duration=first:dropout_transition=2:normalize=0[mixed_a];"
            audio_map = "[mixed_a]"

        print(f"[⚙️] Running ultra-fast FFmpeg render pipeline (Multi-Scene + Sandwich) → {out_w}x{out_h}...")
        cmd = [
            "ffmpeg", *inputs,
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", audio_map,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", output_vid, "-y"
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
            print(f"[❌] FFmpeg Engine Failed:\n{err_msg}")
            raise

        for f in [temp_audio]:
            if os.path.exists(f): os.remove(f)

        print(f"[✅] Background FX applied ({out_w}x{out_h} 9:16 vertical): {output_vid}")
        return output_vid


    # ── WebGL GPU Soft Key Path (Playwright) ──────────────────────────────
    elif keying_mode == "webgl":
        print("[🌐] Booting WebGL Browser Engine for Cinematic Soft Keying...")
        from playwright.sync_api import sync_playwright
        import pathlib
        import json
        
        cap.release()
        out.release()
        if os.path.exists(temp_vid): os.remove(temp_vid)
        
        # Convert paths to file URIs for browser
        vid_uri = pathlib.Path(video_path).as_uri()
        bg_uri = ""
        if mode == "image" and bg_image_path and os.path.exists(bg_image_path):
            bg_uri = pathlib.Path(bg_image_path).as_uri()
        
        bg_hex = hex_color if mode == "color" else "09090b"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ margin: 0; background: #{bg_hex}; overflow: hidden; }}
                canvas {{ width: 100vw; height: 100vh; }}
            </style>
        </head>
        <body>
            <video id="vid" src="{vid_uri}" muted style="display:none;"></video>
            <img id="bg" src="{bg_uri}" style="display:none;" crossorigin="anonymous">
            <canvas id="glcanvas" width="{w}" height="{h}"></canvas>
            <script>
                const vid = document.getElementById('vid');
                const bg = document.getElementById('bg');
                const canvas = document.getElementById('glcanvas');
                const gl = canvas.getContext('webgl');
                
                const vsSource = `
                    attribute vec4 aVertexPosition;
                    attribute vec2 aTextureCoord;
                    varying highp vec2 vTextureCoord;
                    void main(void) {{
                        gl_Position = aVertexPosition;
                        vTextureCoord = aTextureCoord;
                    }}
                `;
                
                // Cinematic Soft Key Shader
                const fsSource = `
                    precision highp float;
                    varying highp vec2 vTextureCoord;
                    uniform sampler2D uSampler;
                    uniform sampler2D uBgSampler;
                    uniform int uUseBgImage;
                    
                    void main(void) {{
                        vec4 color = texture2D(uSampler, vTextureCoord);
                        vec4 bg = uUseBgImage == 1 ? texture2D(uBgSampler, vTextureCoord) : vec4(0.0, 0.0, 0.0, 0.0);
                        
                        // Robust Green Screen Math: measures how much stronger Green is than Red and Blue
                        float maxRB = max(color.r, color.b);
                        float gDiff = color.g - maxRB;
                        
                        // The higher gDiff, the greener the pixel.
                        // If it's barely green (< 0.03), it's opaque foreground.
                        // If it's clearly green (> 0.12), it's transparent background.
                        float alpha = 1.0 - smoothstep(0.03, 0.12, gDiff);
                        
                        // Despill: neutralize green fringe on the edges
                        if (color.g > maxRB) {{
                            // Pull green down to the level of Red/Blue smoothly based on how "green" the pixel was
                            float despillFactor = clamp(gDiff / 0.15, 0.0, 1.0);
                            color.g = mix(color.g, maxRB, despillFactor);
                        }}
                        
                        vec4 finalColor = vec4(color.rgb, alpha);
                        if (uUseBgImage == 1) {{
                            // premultiply alpha for mix
                            gl_FragColor = mix(bg, vec4(color.rgb, 1.0), alpha);
                        }} else {{
                            gl_FragColor = vec4(color.rgb * alpha, alpha);
                        }}
                    }}
                `;
                
                function loadShader(gl, type, source) {{
                    const shader = gl.createShader(type);
                    gl.shaderSource(shader, source);
                    gl.compileShader(shader);
                    return shader;
                }}
                
                const shaderProgram = gl.createProgram();
                gl.attachShader(shaderProgram, loadShader(gl, gl.VERTEX_SHADER, vsSource));
                gl.attachShader(shaderProgram, loadShader(gl, gl.FRAGMENT_SHADER, fsSource));
                gl.linkProgram(shaderProgram);
                gl.useProgram(shaderProgram);
                
                const positions = new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]);
                const texCoords = new Float32Array([0, 1, 1, 1, 0, 0, 1, 0]);
                
                const posBuf = gl.createBuffer();
                gl.bindBuffer(gl.ARRAY_BUFFER, posBuf);
                gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW);
                const posAttr = gl.getAttribLocation(shaderProgram, 'aVertexPosition');
                gl.vertexAttribPointer(posAttr, 2, gl.FLOAT, false, 0, 0);
                gl.enableVertexAttribArray(posAttr);
                
                const texBuf = gl.createBuffer();
                gl.bindBuffer(gl.ARRAY_BUFFER, texBuf);
                gl.bufferData(gl.ARRAY_BUFFER, texCoords, gl.STATIC_DRAW);
                const texAttr = gl.getAttribLocation(shaderProgram, 'aTextureCoord');
                gl.vertexAttribPointer(texAttr, 2, gl.FLOAT, false, 0, 0);
                gl.enableVertexAttribArray(texAttr);
                
                const vidTexture = gl.createTexture();
                gl.bindTexture(gl.TEXTURE_2D, vidTexture);
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
                
                const bgTexture = gl.createTexture();
                gl.bindTexture(gl.TEXTURE_2D, bgTexture);
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
                
                const uSampler = gl.getUniformLocation(shaderProgram, 'uSampler');
                const uBgSampler = gl.getUniformLocation(shaderProgram, 'uBgSampler');
                const uUseBgImage = gl.getUniformLocation(shaderProgram, 'uUseBgImage');
                
                gl.uniform1i(uSampler, 0);
                gl.uniform1i(uBgSampler, 1);
                
                gl.viewport(0, 0, canvas.width, canvas.height);
                
                let bgLoaded = !bg.src || bg.src.endsWith('null') || bg.src === '';
                if (!bgLoaded) {{
                    bg.onload = () => {{
                        gl.activeTexture(gl.TEXTURE1);
                        gl.bindTexture(gl.TEXTURE_2D, bgTexture);
                        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, bg);
                        bgLoaded = true;
                        startProcessing();
                    }};
                }} else {{
                    gl.uniform1i(uUseBgImage, 0);
                    startProcessing();
                }}
                
                let mediaRecorder;
                let chunks = [];
                
                function startProcessing() {{
                    if (!bgLoaded) return;
                    if (bg.src && bg.src !== window.location.href && !bg.src.endsWith('null') && bg.src !== '') {{
                        gl.uniform1i(uUseBgImage, 1);
                    }}
                    
                    vid.play().then(() => {{
                        const stream = canvas.captureStream(60);
                        mediaRecorder = new MediaRecorder(stream, {{ mimeType: 'video/webm;codecs=vp9', videoBitsPerSecond: 16000000 }});
                        mediaRecorder.ondataavailable = e => chunks.push(e.data);
                        mediaRecorder.onstop = () => {{
                            const blob = new Blob(chunks, {{ type: 'video/webm' }});
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = 'webgl_render.webm';
                            a.click();
                            window.renderComplete = true;
                        }};
                        mediaRecorder.start();
                        renderLoop();
                    }});
                }}
                
                function renderLoop() {{
                    if (vid.paused || vid.ended) {{
                        if (mediaRecorder.state === 'recording') mediaRecorder.stop();
                        return;
                    }}
                    gl.activeTexture(gl.TEXTURE0);
                    gl.bindTexture(gl.TEXTURE_2D, vidTexture);
                    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, vid);
                    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
                    requestAnimationFrame(renderLoop);
                }}
                
                vid.onended = () => {{
                    if (mediaRecorder && mediaRecorder.state === 'recording') mediaRecorder.stop();
                }};
            </script>
        </body>
        </html>
        """
        
        webgl_html_path = os.path.join(base_dir, "_webgl_keyer.html")
        webgl_webm_path = os.path.join(base_dir, "_webgl_render.webm")
        with open(webgl_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        print("[⚙️] Running headless WebGL compositor via GPU...")
        
        # We must use specific flags to force hardware GPU rendering in headless mode
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "ms-playwright")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                channel="chrome",
                headless=True,
                args=[
                    "--use-gl=desktop",
                    "--enable-webgl",
                    "--ignore-gpu-blocklist",
                    "--autoplay-policy=no-user-gesture-required",
                    "--disable-web-security",
                    "--allow-file-access-from-files"
                ]
            )
            page = browser.new_page(
                viewport={"width": w, "height": h},
                device_scale_factor=1,
                accept_downloads=True
            )
            
            # Setup download intercept
            with page.expect_download(timeout=300000) as download_info:
                page.goto(pathlib.Path(webgl_html_path).as_uri())
                # Wait for the recording to finish and trigger download
                page.wait_for_function("window.renderComplete === true", timeout=300000)
                
            download = download_info.value
            download.save_as(webgl_webm_path)
            browser.close()
            
        print("[⚙️] Remuxing WebGL WebM with original audio...")
        subprocess.run([
            "ffmpeg", "-i", webgl_webm_path, "-i", temp_audio,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-map", "0:v:0", "-map", "1:a:0",
            "-shortest", output_vid, "-y"
        ], check=True, capture_output=True)
        
        for f in [webgl_html_path, webgl_webm_path, temp_audio]:
            if os.path.exists(f): os.remove(f)
            
        print(f"[✅] Background FX applied (WebGL): {output_vid}")
        return output_vid

    # ── MediaPipe AI Segmentation Path ───────────────────────────────────
    else:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        print("[🧠] Booting MediaPipe AI Selfie Segmenter...")
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

        base_mp_options = mp_python.BaseOptions(model_asset_path=model_path)
        seg_options     = vision.ImageSegmenterOptions(base_options=base_mp_options, output_confidence_masks=True)

        with vision.ImageSegmenter.create_from_options(seg_options) as segmenter:
            while cap.isOpened():
                success, frame = cap.read()
                if not success: break

                if mode == "blur":
                    bg_frame = cv2.GaussianBlur(frame, (99, 99), 0)
                    bg_frame = cv2.addWeighted(bg_frame, 0.7, np.zeros_like(bg_frame), 0.3, 0)
                elif mode == "image" and custom_bg_img is not None:
                    bg_frame = custom_bg_img
                else:
                    bg_frame = np.full(frame.shape, bgr_color, dtype=np.uint8)

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

def stage_scene_transitions(video_path: str, options: dict) -> str:
    import os
    import json
    import subprocess
    
    print("[⚙️] Injecting 0.3s Elastic Slide & Flash Transitions...")
    base_dir   = os.path.dirname(os.path.abspath(video_path))
    output_vid = os.path.splitext(video_path)[0] + "_transitions.mp4"
    json_path  = os.path.join(base_dir, "_flash_times.json")

    flash_times = []
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            flash_times = json.load(f)
        os.remove(json_path)

    if not flash_times:
        print("[⚙️] No cuts detected. Skipping transitions.")
        return video_path

    print(f"[🎬] Found {len(flash_times)} cuts. Rendering REAL FFmpeg Engine for Elastic Snap & Flash...")

    # We will split the video at cut times, apply the transition math to the incoming scene, 
    # and then concat them back together.
    
    filter_complex = f"[0:v]split={len(flash_times)+1}"
    for i in range(len(flash_times)+1):
        filter_complex += f"[v{i}]"
    filter_complex += ";\\n"
    
    last_t = 0.0
    for i, t in enumerate(flash_times):
        filter_complex += f"[v{i}]trim=start={last_t}:end={t},setpts=PTS-STARTPTS[seg{i}];\\n"
        last_t = t
    filter_complex += f"[v{len(flash_times)}]trim=start={last_t},setpts=PTS-STARTPTS[seg{len(flash_times)}];\\n"

    # Now apply the transition math to every incoming segment (seg 1 to n)
    concat_inputs = "[seg0]"
    
    for i in range(1, len(flash_times)+1):
        elastic_x_expr = "w * exp(-7*(t/0.3)) * cos(15*(t/0.3))"
        blur_expr = "boxblur=lr=if(lte(t,0.3), 20*(1-(t/0.3)), 0):lp=0"
        flash_expr = "eq=brightness='if(lte(t,0.3), 0.8 * (1 - (t/0.3)), 0)'"
        
        filter_complex += f"color=c=black:s=1080x1920:d=10[bg{i}];\\n"
        overlay_cmd = f"overlay=x='{elastic_x_expr}':y=0:shortest=1"
        filter_complex += f"[bg{i}][seg{i}]{overlay_cmd},{blur_expr},{flash_expr}[trans{i}];\\n"
        
        concat_inputs += f"[trans{i}]"
    
    filter_complex += f"{concat_inputs}concat=n={len(flash_times)+1}:v=1:a=0[outv]"
    
    # We must replace \\n with actual \n before executing since we escaped them to avoid string literal errors
    filter_complex = filter_complex.replace("\\\\n", "\\n")
    
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "0:a?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        output_vid
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"[✅] Elastic Slide & Flash transition rendered successfully: {output_vid}")
        return output_vid
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        print(f"[❌] Transitions failed: {err_msg}")
        return video_path

def stage_hardcode_flash(video_path: str, options: dict) -> str:
    print("[⚙️] Loading AI Director timestamps for Camera Flashes...")
    base_dir   = os.path.dirname(os.path.abspath(video_path))
    output_vid = os.path.splitext(video_path)[0] + "_flashes.mp4"
    json_path  = os.path.join(base_dir, "_flash_times.json")

    engine_dir = os.path.dirname(os.path.abspath(__file__))
    sfx_audio  = os.path.join(engine_dir, "assets", "fast woosh.mp3")

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
        print("[⚠️] fast woosh.mp3 missing. Visual flash only.")

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
# 14.5 AUDIO MERGER ENGINE
# ─────────────────────────────────────────────

def stage_merge_audio(video_path: str, options: dict) -> str:
    audio_path = options.get("mergeAudioPath", "").strip()
    if not audio_path or not os.path.exists(audio_path):
        print(f"[⚠️] Audio Merger skipped: No valid audio file provided.")
        return video_path
        
    print(f"[⚙️] Booting Audio Merger Engine... Merging {os.path.basename(audio_path)}")
    
    base_dir = os.path.dirname(os.path.abspath(video_path))
    output_vid = os.path.splitext(video_path)[0] + "_merged.mp4"
    
    # We re-encode the video (using hardware acceleration if possible) to completely rebuild the PTS 
    # starting from zero. This prevents massive desyncs when later applying caption overlays.
    try:
        import subprocess
        subprocess.run(["ffmpeg", "-f", "lavfi", "-i", "nullsrc", "-c:v", "h264_nvenc", "-t", "1", "-f", "null", "-"], check=True, capture_output=True)
        cvcodec = "h264_nvenc"
        preset = "p6"
        cq_args = ["-cq", "18"]
    except:
        cvcodec = "libx264"
        preset = "superfast"
        cq_args = ["-crf", "18"]

    cmd = [
        "ffmpeg", "-hwaccel", "auto", "-y", "-i", video_path, "-i", audio_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", cvcodec, "-preset", preset
    ] + cq_args + [
        "-c:a", "aac", "-b:a", "256k",
        "-filter:a", "volume=4dB",
        "-shortest",
        output_vid
    ]
    
    try:
        import subprocess
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"[✅] Audio merged successfully: {output_vid}")
        return output_vid
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        print(f"[❌] Audio merger failed: {err_msg}")
        return video_path
    except Exception as e:
        print(f"[❌] Audio merger failed: {e}")
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


# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# 17. CINEMATIC GRADE ENGINE — "The Pro Look"
#     Replicates: BG replace · S-curve grade · skin warmth · vignette · sharpen
#     Drop this BEFORE stage_starting_hook() in your pipeline
# ─────────────────────────────────────────────────────────────────────────────
def stage_cinematic_grade(video_path: str, options: dict) -> str:
    import cv2
    import numpy as np
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision
    import os, subprocess

    grade_style = options.get("cinematicGrade", "none")
    if grade_style == "none":
        return video_path

    print(f"[🎨] Cinematic Grade Engine — style: {grade_style}")

    base_dir   = os.path.dirname(os.path.abspath(video_path))
    output_vid = os.path.splitext(video_path)[0] + "_graded.mp4"
    engine_dir = os.path.dirname(os.path.abspath(__file__))

    # ── Style presets ─────────────────────────────────────────────────────
    # Each preset defines:
    #   bg_color  : (B, G, R) — solid studio backdrop
    #   bg_blur   : blur radius on bg plate (0 = solid color, >0 = blurred real bg)
    #   lift      : shadow lift amount (0.0–0.3)
    #   saturation: color saturation multiplier
    #   warmth    : red/yellow push on midtones (0.0–1.0)
    #   contrast  : S-curve strength (0.0–1.0)
    #   sharpen   : unsharp mask strength (0.0–1.0)
    #   vignette  : vignette strength (0.0–1.0)

    PRESETS = {
        "capcut_studio": {
            "bg_color":   (20, 38, 38),   # Deep teal — exactly what the CapCut vid used
            "bg_blur":     0,
            "lift":        0.06,
            "saturation":  1.25,
            "warmth":      0.18,
            "contrast":    0.55,
            "sharpen":     0.7,
            "vignette":    0.55,
        },
        "cinematic_cold": {
            "bg_color":   (28, 22, 18),   # Near-black, slight cool
            "bg_blur":     0,
            "lift":        0.04,
            "saturation":  0.95,
            "warmth":     -0.10,          # Negative = cooler push
            "contrast":    0.65,
            "sharpen":     0.5,
            "vignette":    0.7,
        },
        "warm_podcast": {
            "bg_color":   (20, 30, 50),   # Warm dark navy
            "bg_blur":     0,
            "lift":        0.08,
            "saturation":  1.15,
            "warmth":      0.25,
            "contrast":    0.45,
            "sharpen":     0.6,
            "vignette":    0.45,
        },
        "blurred_bg": {
            "bg_color":   None,           # Keep real bg — just blur it heavily
            "bg_blur":     55,
            "lift":        0.05,
            "saturation":  1.2,
            "warmth":      0.15,
            "contrast":    0.5,
            "sharpen":     0.65,
            "vignette":    0.5,
        },
    }

    p = PRESETS.get(grade_style, PRESETS["capcut_studio"])

    # ── Load MediaPipe segmenter ──────────────────────────────────────────
    model_path = os.path.join(engine_dir, "pretrained_models", "selfie_segmenter.tflite")
    if not os.path.exists(model_path):
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        import urllib.request
        urllib.request.urlretrieve(
            "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite",
            model_path)

    base_options = mp_python.BaseOptions(model_asset_path=model_path)
    seg_options  = vision.ImageSegmenterOptions(
        base_options=base_options, output_confidence_masks=True)

    # ── Build LUT helpers ─────────────────────────────────────────────────
    def build_s_curve_lut(strength: float) -> np.ndarray:
        x = np.arange(256, dtype=np.float32)
        t = (x - 128.0) / 128.0
        s = t / (1.0 + strength * (np.abs(t) - t * t))
        out = np.clip((s * 128.0 + 128.0), 0, 255).astype(np.uint8)
        return out

    def build_lift_lut(lift: float) -> np.ndarray:
        x = np.arange(256, dtype=np.float32)
        out = np.clip(x + lift * 255.0, 0, 255).astype(np.uint8)
        return out

    def apply_lut(img: np.ndarray, lut: np.ndarray) -> np.ndarray:
        return lut[img]

    # ── Skin-tone aware warmth ────────────────────────────────────────────
    def push_warmth(img_bgr: np.ndarray, amount: float) -> np.ndarray:
        if abs(amount) < 0.01:
            return img_bgr

        ycbcr = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2YCrCb)
        Y, Cr, Cb = cv2.split(ycbcr)

        skin_mask = (
            (Y  > 60)  & (Y  < 240) &
            (Cr > 128) & (Cr < 175) &
            (Cb > 85)  & (Cb < 135)
        ).astype(np.float32)

        skin_mask = cv2.GaussianBlur(skin_mask, (21, 21), 7)

        result = img_bgr.astype(np.float32)
        if amount > 0:
            result[:, :, 2] += skin_mask * amount * 30
            result[:, :, 1] += skin_mask * amount * 10
            result[:, :, 0] -= skin_mask * amount * 10
        else:
            result[:, :, 0] += skin_mask * abs(amount) * 25
            result[:, :, 2] -= skin_mask * abs(amount) * 15

        return np.clip(result, 0, 255).astype(np.uint8)

    # ── Vignette ──────────────────────────────────────────────────────────
    def make_vignette(h: int, w: int, strength: float) -> np.ndarray:
        cx, cy = w / 2.0, h / 2.0
        Y, X = np.ogrid[:h, :w]
        dist = np.sqrt(((X - cx) / cx) ** 2 + ((Y - cy) / cy) ** 2)
        vig = 1.0 - strength * np.clip(dist, 0.0, 1.0) ** 1.5
        return vig.astype(np.float32)

    # ── Unsharp mask ──────────────────────────────────────────────────────
    def unsharp_mask(img: np.ndarray, strength: float) -> np.ndarray:
        blur = cv2.GaussianBlur(img, (0, 0), 3.0)
        return cv2.addWeighted(img, 1.0 + strength, blur, -strength, 0)

    # ── Per-frame grade function ──────────────────────────────────────────
    s_lut   = build_s_curve_lut(p["contrast"])
    lift_lut = build_lift_lut(p["lift"])

    def grade_frame(frame: np.ndarray, mask_confidence: np.ndarray) -> np.ndarray:
        h, w = frame.shape[:2]
        
        hard_mask  = (mask_confidence > 0.5).astype(np.uint8)
        soft_mask  = cv2.GaussianBlur(
            (mask_confidence > 0.35).astype(np.float32), (21, 21), 7
        )[:, :, np.newaxis]

        if p["bg_color"] is not None:
            bg = np.full_like(frame, p["bg_color"], dtype=np.uint8)
        else:
            bg = cv2.GaussianBlur(frame, (p["bg_blur"] | 1, p["bg_blur"] | 1), 0)

        composite = (frame.astype(np.float32) * soft_mask
                     + bg.astype(np.float32) * (1.0 - soft_mask))
        composite = np.clip(composite, 0, 255).astype(np.uint8)

        if abs(p["saturation"] - 1.0) > 0.01:
            hsv = cv2.cvtColor(composite, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * p["saturation"], 0, 255)
            composite = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

        sm1 = soft_mask[:, :, 0]
        warmed_subject = push_warmth(composite, p["warmth"])
        composite = (warmed_subject.astype(np.float32) * sm1[:, :, np.newaxis]
                     + composite.astype(np.float32) * (1 - sm1[:, :, np.newaxis]))
        composite = np.clip(composite, 0, 255).astype(np.uint8)

        composite = apply_lut(composite, s_lut)
        composite = apply_lut(composite, lift_lut)

        if p["sharpen"] > 0.01:
            sharpened = unsharp_mask(composite, p["sharpen"])
            composite = (sharpened.astype(np.float32) * sm1[:, :, np.newaxis]
                         + composite.astype(np.float32) * (1 - sm1[:, :, np.newaxis]))
            composite = np.clip(composite, 0, 255).astype(np.uint8)

        if p["vignette"] > 0.01:
            vig = make_vignette(h, w, p["vignette"])[:, :, np.newaxis]
            composite = np.clip(
                composite.astype(np.float32) * vig, 0, 255
            ).astype(np.uint8)

        return composite

    cap    = cv2.VideoCapture(video_path)
    fps    = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    temp_no_audio = os.path.splitext(video_path)[0] + "_grade_temp.mp4"
    try:
        subprocess.run(["ffmpeg", "-f", "lavfi", "-i", "nullsrc", "-c:v", "h264_nvenc", "-t", "1", "-f", "null", "-"], check=True, capture_output=True)
        cvcodec = "h264_nvenc"
        preset = "p6"
        cq_args = ["-cq", "18"]
    except:
        cvcodec = "libx264"
        preset = "superfast"
        cq_args = ["-crf", "17"]

    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{width}x{height}",
        "-pix_fmt", "bgr24",
        "-r", str(fps),
        "-i", "-",
        "-c:v", cvcodec,
        "-preset", preset
    ] + cq_args + [
        "-pix_fmt", "yuv420p",
        temp_no_audio
    ]
    writer = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    with vision.ImageSegmenter.create_from_options(seg_options) as segmenter:
        import gc
        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            res    = segmenter.segment(mp_img)

            if res.confidence_masks:
                mask = np.squeeze(res.confidence_masks[0].numpy_view()).copy()
                graded = grade_frame(frame, mask)
            else:
                graded = unsharp_mask(frame, p["sharpen"] * 0.5)
                
            del res
            del mp_img

            writer.stdin.write(graded.tobytes())
            frame_idx += 1
            if frame_idx % 30 == 0:
                print(f"  [🎨] {frame_idx}/{total} frames graded...")
                gc.collect()

    cap.release()
    writer.stdin.close()
    writer.wait()

    print("[🎨] Re-muxing audio...")
    subprocess.run([
        "ffmpeg",
        "-i", temp_no_audio,
        "-i", video_path,
        "-c:v", "copy",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        output_vid, "-y"
    ], check=True, capture_output=True)

    os.remove(temp_no_audio)
    print(f"[✅] Cinematic grade done → {output_vid}")
    return output_vid


# ─────────────────────────────────────────────────────────────────────────────
# 15.5 TEXT PATTERN INTERRUPT HOOK ENGINE
# ─────────────────────────────────────────────────────────────────────────────
def stage_visual_hook(video_path: str, options: dict) -> str:
    import json
    import os
    import subprocess
    from playwright.sync_api import sync_playwright

    hook_pri_text = options.get("hookPrimaryText", "").strip()
    hook_sec_text = options.get("hookSecondaryText", "").strip()
    if not hook_pri_text and not hook_sec_text:
        return video_path
        
    print(f"[⚙️] Booting Visual Text Hook Engine (Pattern Interrupt)...")
    
    base_dir = os.path.dirname(os.path.abspath(video_path))
    output_vid = os.path.splitext(video_path)[0] + "_texthook.mp4"
    png_path = os.path.join(base_dir, "_hook_overlay.png")
    
    hook_dur = float(options.get("hookDuration", 1.5))
    hook_y = float(options.get("hookYPercent", 40))
    hook_size = float(options.get("hookSizePercent", 100))
    pri_style = options.get("hookPrimaryStyle", "s-electric-teal")
    sec_style = options.get("hookSecondaryStyle", "s-crimson-red")
    hook_bg_color = options.get("hookBgColor", "transparent")
    
    # Backward compatibility if frontend wasn't refreshed
    style_map = {
        "style-yellow-gradient": "s-hormozi-yellow",
        "style-red-gradient": "s-crimson-red",
        "style-neon-cyan": "s-electric-teal",
        "style-glass-silver": "p-glass-silver",
        "style-white-stroke": "p-clean-white",
        "style-black-box": "p-heavy-stroke"
    }
    pri_style = style_map.get(pri_style, pri_style)
    sec_style = style_map.get(sec_style, sec_style)
    
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", video_path],
        capture_output=True, text=True
    )
    try:
        info = json.loads(probe.stdout)["streams"][0]
        W, H = int(info["width"]), int(info["height"])
    except:
        W, H = 1080, 1920
        
    safe_pri = hook_pri_text.replace("'", "\\'").replace('"', '\\"').replace('\n', ' ')
    safe_sec = hook_sec_text.replace("'", "\\'").replace('"', '\\"').replace('\n', ' ')
    
    size_mult = hook_size / 100.0
    
    # Smart Auto-Sizing: Calculate max chars to prevent screen bleed
    pri_len = len(hook_pri_text) if hook_pri_text else 0
    sec_len = len(hook_sec_text) if hook_sec_text else 0
    max_len = max(pri_len, sec_len, 1)
    
    # Montserrat 900 char width is approx 75% of its height.
    # We want max width to be 90% of video width (W * 0.90)
    # font_size * max_len * 0.75 = W * 0.90  => font_size = W * 1.2 / max_len
    calc_size = int((W * 1.2) / max_len)
    
    # Cap the maximum size so short words (e.g. "HI") don't look comically huge
    base_dim = min(W, H)
    max_allowed = int(base_dim * 0.16)
    
    base_font = min(calc_size, max_allowed)
    huge_font = int(base_font * size_mult)
    
    glass_css = ""
    if hook_bg_color == "dark-blue-glow":
        glass_css = (
            "background: rgba(0, 20, 60, 0.6);\n"
            "            border: 2px solid rgba(0, 150, 255, 0.4);\n"
            "            border-radius: 30px;\n"
            "            padding: 40px 60px;\n"
            "            box-shadow: 0 0 50px rgba(0, 100, 255, 0.8), inset 0 1px 0 rgba(255,255,255,0.2);"
        )
    elif hook_bg_color == "silver-glow":
        glass_css = (
            "background: rgba(255, 255, 255, 0.1);\n"
            "            border: 2px solid rgba(255, 255, 255, 0.6);\n"
            "            border-radius: 30px;\n"
            "            padding: 40px 60px;\n"
            "            box-shadow: 0 0 40px rgba(200, 220, 255, 0.7), inset 0 1px 0 rgba(255,255,255,0.5);"
        )
    elif hook_bg_color and hook_bg_color.lower() != "transparent":
        glass_css = (
            f"background: {hook_bg_color};\n"
            f"            border: 2px solid rgba(255, 255, 255, 0.15);\n"
            f"            border-radius: 30px;\n"
            f"            padding: 40px 60px;\n"
            f"            box-shadow: 0 15px 35px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255,255,255,0.2);"
        )
    
    html_content = f"""<!DOCTYPE html>
    <html>
    <head>
    <meta charset="UTF-8">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Anton&family=Bangers&family=Gemunu+Libre:wght@800&family=Great+Vibes&family=Montserrat:wght@800;900&family=Oswald:wght@700&family=Poppins:wght@800;900&display=swap');
        @import url('https://fonts.cdnfonts.com/css/proxima-nova-2');
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ width: {W}px; height: {H}px; background: transparent; overflow: hidden; position: relative; }}
        
        .hook-container {{
            position: absolute;
            max-width: 90%;
            left: 50%;
            top: {hook_y}%;
            transform: translate(-50%, -50%);
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            text-align: center;
            {glass_css}
        }}
        
        .text-line {{
            font-family: 'Montserrat', 'Gemunu Libre', sans-serif;
            font-style: normal;
            font-size: {huge_font}px;
            font-weight: 900;
            line-height: 0.95;
            letter-spacing: -2px;
            text-transform: uppercase;
            white-space: nowrap;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text; color: transparent;
            margin-bottom: 5px;
        }}
        
        .p-glass-silver {{ background-image: linear-gradient(160deg, #fff 0%, #d2e8ff 30%, #b4d7ff 55%, #ebf6ff 75%, #fff 100%); filter: drop-shadow(0 0 10px rgba(140,185,255,0.50)) drop-shadow(0 1px 3px rgba(60,100,200,0.35)); }}
        .p-clean-white  {{ background-image: linear-gradient(to bottom, #ffffff 0%, #e0e0e0 100%); filter: drop-shadow(0 3px 6px rgba(0,0,0,0.8)); }}
        .p-heavy-stroke {{ background-image: linear-gradient(to bottom, #ffffff, #ffffff); filter: drop-shadow(2px 0 0 #000) drop-shadow(-2px 0 0 #000) drop-shadow(0 2px 0 #000) drop-shadow(0 -2px 0 #000) drop-shadow(0 5px 12px rgba(0,0,0,0.9)); }}
        .p-soft-yellow  {{ background-image: linear-gradient(to bottom, #FFFDE7 0%, #FFF176 100%); filter: drop-shadow(0 2px 4px rgba(0,0,0,0.7)); }}
        .p-neon-base    {{ background-image: linear-gradient(to bottom, #ffffff 0%, #e0f7fa 100%); filter: drop-shadow(0 0 10px rgba(0,255,255,0.4)) drop-shadow(0 2px 2px rgba(0,0,0,0.8)); }}
        .p-silver-translucent {{ background-image: linear-gradient(160deg, rgba(255,255,255,0.9) 0%, rgba(200,225,255,0.6) 100%); filter: drop-shadow(0 0 10px rgba(180,200,255,0.4)) drop-shadow(0 1px 2px rgba(0,0,0,0.8)); }}
        .p-sunset-glow  {{ background-image: linear-gradient(160deg, #ff7e5f 0%, #feb47b 100%); filter: drop-shadow(0 0 12px rgba(255,126,95,0.6)) drop-shadow(0 2px 4px rgba(0,0,0,0.9)); }}
      
        .s-electric-teal  {{ background-image: linear-gradient(to right, #00dcc8 0%, #00c3d2 50%, #00aadc 100%); filter: drop-shadow(0 0 15px rgba(0,210,200,0.75)) drop-shadow(0 2px 6px rgba(0,150,180,0.9)); }}
        .s-hormozi-yellow {{ background-image: linear-gradient(to bottom, #FFE81F 0%, #FF8A00 100%); filter: drop-shadow(0 0 15px rgba(255,165,0,0.6)) drop-shadow(0 3px 6px rgba(0,0,0,0.9)); }}
        .s-crimson-red    {{ background-image: linear-gradient(to bottom, #ff4b4b 0%, #b30000 100%); filter: drop-shadow(0 0 15px rgba(255,0,0,0.8)) drop-shadow(0 3px 5px rgba(0,0,0,0.9)); }}
        .s-cyber-purple   {{ background-image: linear-gradient(to right, #d500f9 0%, #651fff 100%); filter: drop-shadow(0 0 15px rgba(213,0,249,0.7)) drop-shadow(0 2px 4px rgba(0,0,0,0.8)); }}
        
    </style>
    </head>
    <body>
        <div class="hook-container" id="hook-text">
        </div>
        <script>
            const priText = "{safe_pri}";
            const secText = "{safe_sec}";
            const priStyle = "{pri_style}";
            const secStyle = "{sec_style}";
            
            let html = '';
            if (priText) {{
                html += `<div class="text-line ${{priStyle}}">${{priText}}</div>`;
            }}
            if (secText) {{
                html += `<div class="text-line ${{secStyle}}">${{secText}}</div>`;
            }}
            
            document.getElementById('hook-text').innerHTML = html;
        </script>
    </body>
    </html>
    """
    
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "ms-playwright")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1)
        page = context.new_page()
        page.set_content(html_content, wait_until="networkidle")
        page.screenshot(path=png_path, omit_background=True)
        browser.close()
        
    print("[⚙️] Compositing Snap-Zoom Pattern Interrupt with FFmpeg...")
    
    # Fast punchy camera flash at start, plus glitchy shake for 0.15s
    # (Flash removed so it doesn't overwrite the Visual SFX Hook underneath)
    shake_x = "if(lte(t,0.15), (random(1)-0.5)*15, 0)"
    shake_y = "if(lte(t,0.15), (random(1)-0.5)*15, 0)"
    
    cmd = [
        "ffmpeg", "-hwaccel", "auto", "-i", video_path, "-i", png_path,
        "-filter_complex",
        f"[0:v][1:v]overlay=x='{shake_x}':y='{shake_y}':enable='between(t,0,{hook_dur})'[outv]",
        "-map", "[outv]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "17",
        "-c:a", "copy",
        output_vid, "-y"
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        if os.path.exists(png_path): os.remove(png_path)
        print(f"[✅] Visual Text Hook applied: {output_vid}")
        return output_vid
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        print(f"[❌] Visual Text Hook failed: {err_msg}")
        if os.path.exists(png_path): os.remove(png_path)
        return video_path


# 16. HEADLESS CSS VISUAL HOOK ENGINE (Playwright + Web Animations)
#     "The Subject Arrives" — AE/TikTok Grade via HTML DOM Compositing
# ─────────────────────────────────────────────────────────────────────────────
def stage_starting_hook(video_path: str, options: dict) -> str:
    import cv2
    import numpy as np
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision
    from playwright.sync_api import sync_playwright
    import os, subprocess, base64

    hook_type = options.get("startingHook", "none")
    if hook_type == "none":
        return video_path

    print(f"[⚙️] Booting CSS Headless Hook Engine — {hook_type}")
    base_dir   = os.path.dirname(os.path.abspath(video_path))
    temp_vid   = os.path.join(base_dir, "_temp_hook.mp4")
    output_vid = os.path.splitext(video_path)[0] + "_hook.mp4"
    frames_dir = os.path.join(base_dir, "_hook_frames")
    engine_dir = os.path.dirname(os.path.abspath(__file__))

    os.makedirs(frames_dir, exist_ok=True)

    # ── 1. MediaPipe: Extract Background & Subject ────────────────────────
    model_path = os.path.join(engine_dir, "pretrained_models", "selfie_segmenter.tflite")
    if not os.path.exists(model_path):
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        import urllib.request
        urllib.request.urlretrieve(
            "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite",
            model_path)

    base_options = mp_python.BaseOptions(model_asset_path=model_path)
    seg_options  = vision.ImageSegmenterOptions(base_options=base_options, output_confidence_masks=True)

    cap    = cv2.VideoCapture(video_path)
    fps    = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    dur    = 0.35  # 350ms snappy cinematic intro
    if hook_type == 'blur_zoom':
        dur = 0.45  # Reduced from 0.85 to 0.45 so it doesn't feel 'stuck' on a frozen frame

    hook_frames = int(fps * dur)
    actual_dur = hook_frames / fps

    # Grab the first non-black frame
    first_frame = None
    for _ in range(30):
        ret, frame = cap.read()
        if not ret: break
        if np.mean(frame) > 5.0:
            first_frame = frame
            break

    if first_frame is None:
        cap.release(); return video_path

    with vision.ImageSegmenter.create_from_options(seg_options) as segmenter:
        rgb    = cv2.cvtColor(first_frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        res    = segmenter.segment(mp_img)

        if not res.confidence_masks:
            cap.release(); return video_path

        raw_mask   = np.squeeze(res.confidence_masks[0].numpy_view())
        hard_mask  = (raw_mask > 0.5).astype(np.uint8) * 255
        
        # Feather the mask slightly for clean CSS compositing
        soft_mask = cv2.GaussianBlur(hard_mask.astype(np.float32), (15, 15), 5) / 255.0
        
        # Create transparent PNG of the subject
        subject_rgba = np.zeros((height, width, 4), dtype=np.uint8)
        subject_rgba[:, :, :3] = first_frame
        subject_rgba[:, :, 3] = (soft_mask * 255).astype(np.uint8)
        
        # --- PRO AE TRICK: Clean Plate ---
        kernel = np.ones((15, 15), np.uint8)
        inpaint_mask = cv2.dilate(hard_mask, kernel, iterations=1)
        bg_clean = cv2.inpaint(first_frame, inpaint_mask, 3, cv2.INPAINT_TELEA)
        
        # We do NOT blur or darken the background. The background remains untouched.
        
        # Encode to Base64 to inject directly into HTML DOM
        _, sub_buf = cv2.imencode('.png', subject_rgba)
        sub_b64 = base64.b64encode(sub_buf).decode('utf-8')
        
        _, bg_buf = cv2.imencode('.jpg', bg_clean, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        bg_b64 = base64.b64encode(bg_buf).decode('utf-8')

    # ── 2. The HTML/CSS Render Engine ─────────────────────────────────────
    html_template = f"""<!DOCTYPE html>
    <html>
    <head>
    <meta charset="UTF-8">
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      body {{ width: {width}px; height: {height}px; background: #000; overflow: hidden; position: relative; }}
      
      .layer {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; transform-origin: center center; }}
      
      /* Background enhancements */
      #bg {{ z-index: 1; will-change: transform, filter; }}
      #bg-overlay {{
          position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 2;
          background: radial-gradient(circle at center, transparent 20%, rgba(0,0,0,0.85) 100%);
          mix-blend-mode: multiply;
      }}
      
      #subject-container {{ z-index: 10; position: absolute; top: 0; left: 0; width: 100%; height: 100%; perspective: 1500px; }}
      
      /* The base subject */
      #subject {{ width: 100%; height: 100%; object-fit: cover; will-change: transform, filter; transform-style: preserve-3d; }}
      
      /* The Echo and Glitch Clones */
      .glitch-clone {{ 
         position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; 
         opacity: 0; will-change: transform, filter, opacity; 
      }}
      
      /* Frame 1: The X-Ray Invert Layer */
      #xray-layer {{
          position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover;
          mix-blend-mode: exclusion; /* Forces the raw CapCut negative look */
          filter: invert(1) contrast(3.5) saturate(0) brightness(1.8);
          opacity: 0; z-index: 15;
      }}
      
      #cinematic-flash {{ 
         position: absolute; top: 0; left: 0; width: 100%; height: 100%; 
         background: radial-gradient(circle at 50% 30%, rgba(255, 255, 255, 1) 0%, rgba(255,255,255,0) 80%);
         mix-blend-mode: overlay; opacity: 0; z-index: 20; pointer-events: none;
      }}
    </style>
    </head>
    <body>
      <img id="bg" class="layer" src="data:image/jpeg;base64,{bg_b64}">
      <div id="bg-overlay"></div>
      <div id="cinematic-flash"></div>
      
      <div id="subject-container">
        <img id="clone1" class="glitch-clone" src="data:image/png;base64,{sub_b64}">
        <img id="clone2" class="glitch-clone" src="data:image/png;base64,{sub_b64}">
        <img id="clone3" class="glitch-clone" src="data:image/png;base64,{sub_b64}">
        
        <img id="rgb-red" class="glitch-clone" style="mix-blend-mode: screen;" src="data:image/png;base64,{sub_b64}">
        <img id="rgb-cyan" class="glitch-clone" style="mix-blend-mode: screen;" src="data:image/png;base64,{sub_b64}">
        
        <img id="xray-layer" src="data:image/png;base64,{sub_b64}">
        
        <img id="subject" src="data:image/png;base64,{sub_b64}">
      </div>

      <script>
        function renderFrame(progress, hookType) {{
            const bg = document.getElementById('bg');
            const sub = document.getElementById('subject');
            const c1 = document.getElementById('clone1');
            const c2 = document.getElementById('clone2');
            const c3 = document.getElementById('clone3');
            const rRed = document.getElementById('rgb-red');
            const rCyan = document.getElementById('rgb-cyan');
            const xray = document.getElementById('xray-layer');
            const cflash = document.getElementById('cinematic-flash');

            const easeOutExpo = t => t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
            const easeOutQuint = t => 1 - Math.pow(1 - t, 5);
            
            // ── AFTER EFFECTS PARALLAX BACKGROUND ──
            // Creates a cinematic Z-space push-in while pulling focus, blending back to normal
            let blendOut = easeOutQuint(Math.max(0, (progress - 0.5) * 2)); // Fades from 0 to 1 in the second half
            let bgScale = 1.05 + ((1 - blendOut) * 0.05); // Smooth subtle zoom
            let bgBlur = (1 - easeOutQuint(progress)) * 12; // Focus pull from blurry to sharp
            bg.style.transform = `scale(${{bgScale}})`;
            bg.style.filter = `blur(${{bgBlur}}px) brightness(${{0.6 + progress * 0.4}})`;
            
            // ── PREMIUM SUBJECT BASE STYLE ──
            // The shadow tightens and fades as the subject lands, perfectly stitching into the main video
            let shadowSpread = (1 - blendOut) * 60;
            let shadowOpacity = (1 - blendOut) * 0.9;
            let rimOpacity = (1 - blendOut) * 0.15;
            let contrastBoost = 1.0 + (1 - blendOut) * 0.05;
            let premiumSubjectShadow = `drop-shadow(0px 30px ${{shadowSpread}}px rgba(0, 0, 0, ${{shadowOpacity}})) drop-shadow(0px 0px 15px rgba(255, 255, 255, ${{rimOpacity}})) contrast(${{contrastBoost}})`;

            if (hookType === 'capcut_drop') {{
                if (progress < 0.15) {{
                    let noiseX = (Math.random() - 0.5) * 50;
                    let noiseY = (Math.random() - 0.5) * 20;
                    
                    sub.style.opacity = 0; 
                    
                    xray.style.opacity = 0.9;
                    xray.style.transform = `scale(1.12) translate(${{noiseX}}px, ${{noiseY}}px)`;
                    
                    rRed.style.opacity = 0.9;
                    rRed.style.transform = `scale(1.15) translateX(35px) translateY(-10px)`;
                    rRed.style.filter = `drop-shadow(25px 0 0 red) hue-rotate(-45deg) contrast(1.2)`;
                    
                    rCyan.style.opacity = 0.9;
                    rCyan.style.transform = `scale(1.15) translateX(-35px) translateY(10px)`;
                    rCyan.style.filter = `drop-shadow(-25px 0 0 cyan) hue-rotate(45deg) contrast(1.2)`;
                    
                    cflash.style.opacity = 0.4;
                }}
                else if (progress >= 0.15 && progress < 0.50) {{
                    let dropP = (progress - 0.15) / 0.35; 
                    let e = easeOutExpo(dropP);
                    let yOff = (1 - e) * -900; 
                    let scaleBoost = 1.0 + (1 - e) * 0.2;
                    
                    xray.style.opacity = 0; rRed.style.opacity = 0; rCyan.style.opacity = 0;
                    
                    sub.style.opacity = 1;
                    sub.style.transform = `translateY(${{yOff}}px) scale(${{scaleBoost}})`;
                    sub.style.filter = `${{premiumSubjectShadow}} brightness(${{1.0 + (1-e)*0.5}})`;
                    
                    c1.style.opacity = (1 - e) * 0.7;
                    c1.style.transform = `translateY(${{yOff - 120}}px) scaleY(${{1.1 + (1-e)*0.2}}) scaleX(${{scaleBoost}})`;
                    c1.style.filter = `blur(10px) opacity(0.8) brightness(1.4) drop-shadow(0 20px 20px cyan)`;
                    
                    c2.style.opacity = (1 - e) * 0.4;
                    c2.style.transform = `translateY(${{yOff - 250}}px) scaleY(${{1.2 + (1-e)*0.3}}) scaleX(${{scaleBoost}})`;
                    c2.style.filter = `blur(20px) opacity(0.5) brightness(1.2) drop-shadow(0 20px 20px magenta)`;
                    
                    cflash.style.opacity = 0;
                }}
                else {{
                    sub.style.opacity = 1;
                    sub.style.transform = `translateY(0) scale(1)`; 
                    // Preserve the premium look after the drop
                    sub.style.filter = premiumSubjectShadow; 
                    
                    c1.style.opacity = 0; c2.style.opacity = 0;
                    rRed.style.opacity = 0; rCyan.style.opacity = 0; xray.style.opacity = 0;
                    cflash.style.opacity = 0;
                }}
            }}
            
            else if (hookType === 'drop_in') {{
                let decay = easeOutExpo(progress);
                let yOff = (1 - decay) * -1000; 
                let scaleY = 1.0 + ((1 - decay) * 0.8);
                let scaleX = 1.0 - ((1 - decay) * 0.1);
                let bloom = 1 - progress; 
                
                sub.style.transform = `translateY(${{yOff}}px) scale(${{scaleX}}, ${{scaleY}})`;
                sub.style.filter = `${{premiumSubjectShadow}} drop-shadow(0px 0px ${{40*bloom}}px rgba(255, 255, 255, ${{bloom*0.8}})) brightness(${{1 + bloom*0.4}})`;
                
                c1.style.opacity = (1 - decay) * 0.6;
                c1.style.transform = `translateY(${{yOff - 80}}px) scale(${{scaleX}}, ${{scaleY}})`;
                c1.style.filter = `blur(8px) brightness(1.5)`;

                c2.style.opacity = (1 - decay) * 0.3;
                c2.style.transform = `translateY(${{yOff - 160}}px) scale(${{scaleX}}, ${{scaleY}})`;
                c2.style.filter = `blur(12px) brightness(1.2)`;
                if(c3) c3.style.opacity = 0;
                cflash.style.opacity = bloom * 0.9;
            }}
            
            else if (hookType === 'flash_drop') {{
                let decay = easeOutExpo(progress);
                let zOff = (1 - decay) * 600; 
                let yOff = (1 - decay) * -200;
                let bloom = 1 - progress;
                
                sub.style.transform = `translateY(${{yOff}}px) translateZ(${{zOff}}px)`;
                sub.style.filter = `${{premiumSubjectShadow}} drop-shadow(0px 0px ${{50*bloom}}px rgba(255, 240, 200, ${{bloom}})) brightness(${{1 + bloom*0.5}})`;

                let burst = progress / 0.5;
                if (burst <= 1) {{
                    c1.style.opacity = 1 - burst;
                    c1.style.transform = `scale(${{1.0 + burst*0.2}})`;
                    c1.style.filter = `brightness(1.5) blur(4px)`;
                }} else {{
                    c1.style.opacity = 0;
                }}
                c2.style.opacity = 0; if(c3) c3.style.opacity = 0;
                cflash.style.opacity = bloom * 0.9;
            }}

            else if (hookType === 'flash') {{
                let decay = easeOutExpo(progress);
                let bloom = 1 - progress;
                
                let scale = 1.0 + (progress * 0.05); 
                sub.style.transform = `scale(${{scale}})`;
                
                sub.style.filter = `${{premiumSubjectShadow}} drop-shadow(0px 0px ${{60*bloom}}px rgba(255, 255, 255, ${{bloom*0.9}})) brightness(${{1 + bloom*0.6}})`;
                
                c1.style.opacity = 0; c2.style.opacity = 0; if(c3) c3.style.opacity = 0;
                cflash.style.opacity = bloom * 0.9;
            }}

            else if (hookType === 'glitch') {{
                let decay = 1 - progress; 
                let bloom = 1 - progress;
                
                if (decay > 0.05) {{
                    let isHard = Math.random() > 0.5;
                    let shift = 30 * decay;
                    
                    c1.style.opacity = 0.7 * decay;
                    c1.style.transform = `translateX(${{shift}}px)`;
                    c1.style.filter = `hue-rotate(-90deg) saturate(3) brightness(1.2)`;
                    c1.style.clipPath = `inset(${{Math.random()*80}}% 0 ${{Math.random()*80}}% 0)`;

                    c2.style.opacity = 0.7 * decay;
                    c2.style.transform = `translateX(${{-shift}}px)`;
                    c2.style.filter = `hue-rotate(90deg) saturate(3) brightness(1.2)`;
                    c2.style.clipPath = `inset(${{Math.random()*80}}% 0 ${{Math.random()*80}}% 0)`;

                    sub.style.opacity = 1;
                    sub.style.transform = `translate(${{(Math.random()-0.5)*15*decay}}px, 0px)`;
                    
                    if (isHard) sub.style.clipPath = `polygon(0 ${{Math.random()*15}}%, 100% ${{Math.random()*15}}%, 100% 100%, 0 100%)`;
                    else sub.style.clipPath = 'none';
                }} else {{
                    c1.style.opacity = 0; c2.style.opacity = 0;
                    sub.style.opacity = 1; sub.style.transform = 'none';
                    sub.style.clipPath = 'none';
                }}
                
                sub.style.filter = `${{premiumSubjectShadow}} drop-shadow(0px 0px ${{30*bloom}}px rgba(0, 255, 255, ${{bloom*0.5}})) brightness(${{1 + bloom*0.3}})`;
                if(c3) c3.style.opacity = 0;
                cflash.style.opacity = bloom * 0.9;
            }}

            else if (hookType === 'impact') {{
                let decay = 1 - easeOutExpo(progress);
                let bloom = 1 - progress;
                
                let scale = 1.0 + (decay * 0.2);
                let shakeX = (Math.random() - 0.5) * 30 * decay;
                let shakeY = (Math.random() - 0.5) * 30 * decay;
                
                sub.style.transform = `translate(${{shakeX}}px, ${{shakeY}}px) scale(${{scale}})`;
                sub.style.filter = `${{premiumSubjectShadow}} drop-shadow(0px 0px ${{50*bloom}}px rgba(255, 200, 200, ${{bloom*0.6}})) brightness(${{1 + bloom*0.4}})`;
                
                c1.style.opacity = decay * 0.6;
                c1.style.transform = `translate(${{shakeX - 15*decay}}px, ${{shakeY}}px) scale(${{scale}})`;
                c1.style.filter = `hue-rotate(-90deg) brightness(1.2)`;

                c2.style.opacity = decay * 0.6;
                c2.style.transform = `translate(${{shakeX + 15*decay}}px, ${{shakeY}}px) scale(${{scale}})`;
                c2.style.filter = `hue-rotate(90deg) brightness(1.2)`;
                
                if(c3) c3.style.opacity = 0;
                cflash.style.opacity = bloom * 0.9;
            }}

            else if (hookType === 'blur_zoom') {{
                // Use Quint instead of Expo for a slower, smoother, more cinematic glide
                let decay = easeOutQuint(progress);
                
                // Enhanced cinematic blur zoom: Starts at 1.5x scale, 30px blur, and 1.8x brightness
                let currentScale = 1.5 - (0.5 * decay);
                let currentBlur = 30 - (30 * decay);
                let currentBrightness = 1.0 + (0.8 * (1 - decay));
                
                sub.style.transform = `scale(${{currentScale}})`;
                sub.style.filter = `${{premiumSubjectShadow}} blur(${{currentBlur}}px) brightness(${{currentBrightness}})`;
                
                c1.style.opacity = 0; c2.style.opacity = 0; if(c3) c3.style.opacity = 0;
                cflash.style.opacity = 0;
            }}
        }}
      </script>
    </body>
    </html>"""
    # ── 3. Frame Rendering via Playwright ─────────────────────────────────
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "ms-playwright")
    
    print("[⚙️] Stepping CSS frames in headless Chrome...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
        page = context.new_page()
        page.set_content(html_template, wait_until="load")

        for i in range(hook_frames):
            progress = i / max(hook_frames - 1, 1)
            page.evaluate(f"renderFrame({progress}, '{hook_type}')")
            page.screenshot(path=os.path.join(frames_dir, f"frame_{i:04d}.png"), type="png")
            
        browser.close()

    # ── 4. FFmpeg Compositing ─────────────────────────────────────────────
    print("[⚙️] Re-compositing sequence with audio...")
    sfx_map   = {"flash":"flash_sfx.MP3","flash_drop":"flash_sfx.MP3", "drop_in":"impact_sfx.MP3","glitch":"glitch_sfx.MP3","impact":"impact_sfx.MP3", "capcut_drop":"glitch_sfx.MP3", "blur_zoom":"woosh with echo.MP3"}
    sfx_audio = os.path.join(engine_dir, "assets", sfx_map.get(hook_type, ""))
    has_sfx   = os.path.exists(sfx_audio)

    # Convert PNG sequence to temporary MP4
    subprocess.run([
        "ffmpeg", "-framerate", str(fps), "-i", os.path.join(frames_dir, "frame_%04d.png"),
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", temp_vid, "-y"
    ], check=True, capture_output=True)

    # Overlay temp video over main video for duration, mix SFX
    fc = (f"[0:v]tpad=start_duration={actual_dur:.4f}:start_mode=clone[v_main];"
          f"[v_main][1:v]overlay=eof_action=pass[v_out];"
          f"[0:a]adelay={int(actual_dur*1000)}:all=1[main_a]")
    
    if has_sfx:
        fc += f";[2:a]volume=1.5[sfx];[main_a][sfx]amix=inputs=2:duration=longest:dropout_transition=2:normalize=0[a_final]"
        amap = "[a_final]"
    else:
        amap = "[main_a]"

    shared = ["-filter_complex", fc, "-map", "[v_out]", "-map", amap, "-c:a", "aac", "-b:a", "192k", output_vid, "-y"]
    base_cmd = ["ffmpeg", "-i", video_path, "-i", temp_vid]
    if has_sfx: base_cmd += ["-i", sfx_audio]

    subprocess.run(base_cmd + ["-c:v", "libx264", "-preset", "fast", "-crf", "17"] + shared, check=True, capture_output=True)

    # Cleanup
    if os.path.exists(temp_vid): os.remove(temp_vid)
    import shutil
    shutil.rmtree(frames_dir, ignore_errors=True)
    cap.release()
    
    print(f"[✅] CSS Hook sequence rendered → {output_vid}")
    return output_vid

# ─────────────────────────────────────────────
# 18. LIGHTNING-FAST STABILIZATION ENGINE
# ─────────────────────────────────────────────

def _interpolate_nans(arr: np.ndarray) -> np.ndarray:
    """Linearly interpolate NaN gaps (dropped detections) instead of
    forward-filling. Forward-fill creates a flat plateau followed by a
    step-jump when detection resumes, which the gaussian filter reads
    as a spike and 'corrects' -> visible micro-jolt in output."""
    n = len(arr)
    valid = ~np.isnan(arr)
    if valid.sum() == 0:
        return arr
    if valid.sum() == n:
        return arr
    idx = np.arange(n)
    arr = arr.copy()
    arr[~valid] = np.interp(idx[~valid], idx[valid], arr[valid])
    return arr


def _soft_clip(arr: np.ndarray, limit: float) -> np.ndarray:
    """Tanh-based soft clip: stays linear (transparent) well under the
    limit, smoothly compresses anything beyond it. Avoids the hard
    discontinuity a plain np.clip would introduce frame-to-frame."""
    if limit <= 0:
        return arr
    return limit * np.tanh(arr / limit)


def stage_fast_stabilize(video_path: str, options: dict) -> str:
    import os
    import subprocess
    import cv2
    import numpy as np
    from scipy.ndimage import gaussian_filter1d, median_filter
    import urllib.request

    engine_backend = options.get('stabilizerBackend', 'cpu')
    if engine_backend == 'gpu':
        print("[⚙️] Booting AI Facial Anchor Stabilizer (PyTorch GPU Mode) v2...")
    else:
        print("[⚙️] Booting AI Facial Anchor Stabilizer (Micro-Shock Absorber CPU) v2...")

    base_dir = os.path.dirname(os.path.abspath(video_path))
    output_vid = os.path.splitext(video_path)[0] + "_stabilized.mp4"
    engine_dir = os.path.dirname(os.path.abspath(__file__))

    try:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        print(f"[⚙️] Pass 1: Extracting rigid facial trajectory (multi-point anchor using {engine_backend.upper()})...")
        raw_x, raw_y = [], []
        valid_frames = []

        if engine_backend == 'gpu':
            try:
                from facenet_pytorch import MTCNN
                import torch
                device = 'cuda' if torch.cuda.is_available() else 'cpu'
                # MTCNN takes RGB images
                mtcnn = MTCNN(keep_all=False, device=device)
                
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    
                    # MTCNN runs very fast on GPU even without downscaling, but we downscale slightly just in case
                    process_w = 640
                    scale_ratio = process_w / width
                    process_h = int(height * scale_ratio)
                    small_frame = cv2.resize(frame, (process_w, process_h), interpolation=cv2.INTER_LINEAR)
                    rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
                    
                    boxes, probs, landmarks = mtcnn.detect(rgb_frame, landmarks=True)
                    if landmarks is not None and len(landmarks) > 0:
                        # landmarks[0] contains 5 points: left eye, right eye, nose, left mouth, right mouth
                        lm = landmarks[0] 
                        xs = [p[0] / scale_ratio for p in lm]
                        ys = [p[1] / scale_ratio for p in lm]
                        raw_x.append(float(np.mean(xs)))
                        raw_y.append(float(np.mean(ys)))
                        valid_frames.append(True)
                    else:
                        raw_x.append(np.nan)
                        raw_y.append(np.nan)
                        valid_frames.append(False)
            except ImportError:
                print("[⚠️] facenet-pytorch not installed! Falling back to CPU...")
                engine_backend = 'cpu' # Fallthrough to CPU below...
                
        if engine_backend == 'cpu':
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
            
            # ─── Load MediaPipe Face Landmarker ───────────────────────────────────
            model_path = os.path.join(engine_dir, "pretrained_models", "face_landmarker.task")
            if not os.path.exists(model_path):
                print("[⚙️] Downloading MediaPipe Face Landmarker model...")
                os.makedirs(os.path.dirname(model_path), exist_ok=True)
                try:
                    urllib.request.urlretrieve(
                        "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task",
                        model_path
                    )
                except Exception as e:
                    print(f"[⚠️] Failed to download model: {e}. Using original video.")
                    return video_path
                    
            base_options = mp_python.BaseOptions(model_asset_path=model_path)
            task_options = vision.FaceLandmarkerOptions(
                base_options=base_options,
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=False,
                num_faces=1
            )
            ANCHOR_IDS = [4, 6, 168, 133, 362]
            with vision.FaceLandmarker.create_from_options(task_options) as landmarker:
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break

                    # 🔥 DOWN-SCALE FOR 10X FASTER CPU INFERENCE
                    process_w = 480
                    scale_ratio = process_w / width
                    process_h = int(height * scale_ratio)
                    
                    small_frame = cv2.resize(frame, (process_w, process_h), interpolation=cv2.INTER_LINEAR)
                    rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
                    
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                    detection = landmarker.detect(mp_image)

                    if detection.face_landmarks:
                        lm = detection.face_landmarks[0]
                        xs = [lm[i].x * width for i in ANCHOR_IDS]
                        ys = [lm[i].y * height for i in ANCHOR_IDS]
                        raw_x.append(float(np.mean(xs)))
                        raw_y.append(float(np.mean(ys)))
                        valid_frames.append(True)
                    else:
                        raw_x.append(np.nan)
                        raw_y.append(np.nan)
                        valid_frames.append(False)

        cap.release()

        if not any(valid_frames):
            print("[⚠️] No face detected. Cannot anchor-stabilize. Falling back to original.")
            return video_path

        trajectory_x = np.array(raw_x, dtype=np.float64)
        trajectory_y = np.array(raw_y, dtype=np.float64)

        print("[⚙️] Pass 1b: Interpolating dropped-detection gaps...")
        trajectory_x = _interpolate_nans(trajectory_x)
        trajectory_y = _interpolate_nans(trajectory_y)

        print("[⚙️] Pass 2: Median pre-filter to strip outlier spikes...")
        # A short median filter removes single/double-frame outliers (blinks,
        # partial occlusion, brief misdetection) WITHOUT smearing real motion,
        # unlike the gaussian which just blends outliers into the trajectory.
        median_k = int(options.get("medianKernel", 5))
        if median_k % 2 == 0:
            median_k += 1
        trajectory_x = median_filter(trajectory_x, size=median_k, mode="nearest")
        trajectory_y = median_filter(trajectory_y, size=median_k, mode="nearest")

        print("[⚙️] Pass 3: Applying low-pass filter to isolate real (slow) motion...")
        is_motion_tracking = options.get("motionTracking", False)
        
        sigma_val = float(options.get("vibrationFilterStrength", 8.0))
        if is_motion_tracking:
            sigma_val *= 4.0  # High-lag spring physics
            
        smoothed_x = gaussian_filter1d(trajectory_x, sigma=sigma_val, mode="nearest")
        smoothed_y = gaussian_filter1d(trajectory_y, sigma=sigma_val, mode="nearest")

        is_motion_tracking = options.get("motionTracking", False)
        
        if is_motion_tracking:
            print("[⚙️] Pass 3b: Calculating dynamic motion tracking trajectory...")
            # For motion tracking, camera chases the smoothed face
            initial_x = np.nanmedian(trajectory_x[:30]) if len(trajectory_x) > 30 else trajectory_x[0]
            initial_y = np.nanmedian(trajectory_y[:30]) if len(trajectory_y) > 30 else trajectory_y[0]
            
            shift_x = smoothed_x - initial_x
            shift_y = smoothed_y - initial_y
            
            # Allow larger shifts, but clamp smoothly
            max_shift_px = float(width * 0.25) # 25% of width Jump-Cut Protection
            shift_x = _soft_clip(shift_x, max_shift_px)
            shift_y = _soft_clip(shift_y, max_shift_px)
        else:
            print("[⚙️] Pass 3b: Clamping correction magnitude...")
            shift_x = trajectory_x - smoothed_x
            shift_y = trajectory_y - smoothed_y
            
            max_shift_px = float(options.get("maxCorrectionPx", 12.0))
            shift_x = _soft_clip(shift_x, max_shift_px)
            shift_y = _soft_clip(shift_y, max_shift_px)
        
        print("[⚙️] Pass 4: Rendering smooth frames via FFmpeg pipe...")
        cmd = [
            "ffmpeg", "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
            "-s", f"{width}x{height}", "-pix_fmt", "bgr24", "-r", str(fps), "-i", "-",
            "-i", video_path, "-map", "0:v:0", "-map", "1:a:0?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "copy", output_vid
        ]

        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cap = cv2.VideoCapture(video_path)

        zoom_scale = 1.12 if is_motion_tracking else float(options.get("zoomScale", 1.03))

        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            dx = shift_x[frame_idx]
            dy = shift_y[frame_idx]

            if is_motion_tracking:
                sway_x = np.sin(frame_idx * 0.04) * (width * 0.015)
                sway_y = np.cos(frame_idx * 0.033) * (height * 0.015)
                dx += sway_x
                dy += sway_y

            M = np.float32([
                [zoom_scale, 0, -dx + (width * (1 - zoom_scale) / 2)],
                [0, zoom_scale, -dy + (height * (1 - zoom_scale) / 2)]
            ])

            stabilized_frame = cv2.warpAffine(
                frame, M, (width, height),
                flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT
            )

            process.stdin.write(stabilized_frame.tobytes())
            frame_idx += 1

        cap.release()
        process.stdin.close()
        process.wait()

        print(f"[✅] AI Anchor Stabilization complete (multi-point, interpolated, no spikes): {output_vid}")
        return output_vid

    except Exception as e:
        err_msg = str(e)
        print(f"[❌] AI Anchor Stabilization failed: {err_msg}")
        # If it fails, return the original video path so the pipeline doesn't break
        return video_path

# ─────────────────────────────────────────────
# 19. MAIN PIPELINE ORCHESTRATOR
# ─────────────────────────────────────────────
def stage_global_motion_tracking(video_path: str, options: dict) -> str:
    # A lightweight wrapper that runs stage_fast_stabilize in motion_tracking mode
    # on the fully composited video to create a cinematic handheld feel.
    print("\n[🎥] Activating Global Handheld Motion Tracking...")
    mt_options = options.copy()
    mt_options["motionTracking"] = True
    mt_options["zoomScale"] = 1.12 # Zoom slightly to allow sway margin
    return stage_fast_stabilize(video_path, mt_options)

def run_pipeline(video_path: str, options_json: str) -> None:
    import json as _json
    options = _json.loads(options_json)
    print(f"\n[🎬] STARTING LOCAL RENDER ENGINE: {os.path.basename(video_path)}\n")

    if not os.path.exists(video_path):
        print(f"[❌] FATAL: Input file not found: {video_path}")
        print("Please re-select the file in the UI.")
        return

    if options.get("enhanceAiImage"):
        print("\n[🎬] RUNNING AI IMAGE ENHANCEMENT...")
        result = stage_enhance_ai_image(video_path)
        print(f"\n[🚀] PIPELINE COMPLETE. Final output: {result}")
        return

    if options.get("generatePromptOnly"):
        print("\n[🎬] GENERATING SMART PROMPT...")
        import subprocess as _sp
        base_dir = os.path.dirname(os.path.abspath(video_path))
        temp_audio = os.path.join(base_dir, "_gemini_audio.wav")
        _sp.run(["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", temp_audio, "-y"], check=True, capture_output=True)
        try:
            probe_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", temp_audio]
            dur_out = _sp.check_output(probe_cmd, text=True).strip()
            audio_dur = float(dur_out)
            duration_text = f"The total length of this audio is exactly {audio_dur:.2f} seconds. Your timestamps MUST NOT exceed this duration."
        except Exception:
            duration_text = "Pay close attention to the length of the audio."

        prompt = f"""Listen to this audio. It is a mix of Sinhala and English (Singlish).
Write down EXACTLY what is said, verbatim.

IMPORTANT CONTEXT: {duration_text}

CRITICAL RULES: 
1. DO NOT add words. DO NOT guess words. DO NOT fix broken sentences. If the audio mumbles, transcribe the mumble. Strictly stick to the voice.
2. Break the text into short, logical phrases of exactly 3 to 5 words each.
3. TRANSLITERATE ENGLISH: If an English technical word is spoken, type it in English letters (e.g., "AC", "pipe", "commission" , "Grab Me"). 
4. NUMBER FORMATTING: Convert all spoken numbers into actual digits (e.g., "රුපියලෙ 5000").
5. SLANG CORRECTION: Fix casual Singlish slang ONLY IF it matches the audio timing.
6. KEYWORDS: Professional field engineer, commission, field engineer, direct, scam, skill, follow, comment, බාස්.
7. NO GRAMMAR/PUNCTUATION (CRITICAL): Do absolutely NOT use periods (.), commas (,), or question marks (?) anywhere in your text.
8. THE DIRECTOR'S CUT (CRITICAL): Place a pipe symbol "|" at the end of a phrase ONLY at key narrative beats.
   DO NOT exceed 8 pipes in total.

You must provide the approximate start and end times for each phrase in seconds.
Output strictly as a JSON array.
Do not include any markdown formatting. Just the raw JSON array."""

        print("[PROMPT_START]")
        print(prompt)
        print("[PROMPT_END]")
        if os.path.exists(temp_audio): os.remove(temp_audio)
        return

    # ─── MAIN PIPELINE SEQUENCE ───────────────────────────────────────────────
    current_video = video_path

    # 1. Stabilize (Rigid Anchor on RAW)
    if options.get("stabilizerEngine"):
        current_video = stage_fast_stabilize(current_video, options)

    # 2. Merge Studio Audio
    if options.get("mergeEngine"):
        current_video = stage_merge_audio(current_video, options)

    # 3. Background FX + Sandwich Text (Based on UI Timeline)
    if options.get("blurBackground"):
        current_video = stage_background_fx(current_video, options)

    # 4. Remove Dead Air / Jump Cuts (Chops the composited video!)
    if options.get("removeSilence"):
        current_video = stage_remove_silence(current_video, options)

    # 5. Semantic Smart Zoom
    if options.get("autoZoom"):
        current_video = stage_semantic_zoom(current_video, options)
        
    # 6. Hook Engine
    if options.get("hookEngine"):
        if options.get("startingHook") and options.get("startingHook") != "none":
            current_video = stage_starting_hook(current_video, options)
        if options.get("hookPrimaryText") or options.get("hookSecondaryText"):
            current_video = stage_visual_hook(current_video, options)

    # 7. AI B-Roll
    if options.get("aiBroll"):
        current_video = stage_ai_broll(current_video, options)

    # 8. Studio Audio Enhancement
    if options.get("studioAudio"):
        current_video = stage_studio_audio(current_video)

    if options.get("extractMp3"):
        current_video = stage_mp4_to_mp3(current_video, options)

    # 9. Beauty Filter
    if options.get("applyBeautyFilter"):
        current_video = stage_beauty_filter(current_video, options)

    # 10. Captions (Transcribes the ALREADY chopped video, meaning timestamps map perfectly!)
    if options.get("burnCaptions"):
        if options.get("captionLanguage") == "si":
            current_video = stage_burn_sinhala_captions(current_video, options)
        else:
            current_video = stage_burn_captions(current_video, options)
            
    # 11. Auto Transitions (Elastic Stretch & Flash based on perfectly mapped _flash_times.json)
    if options.get("autoTransitions"):
        current_video = stage_scene_transitions(current_video, options)

    # 12. Global Handheld Motion Tracking (Simulates a human operator on the whole scene)
    if options.get("motionTracking"):
        current_video = stage_global_motion_tracking(current_video, options)

    # 13. Cinematic Color Grade & M22 Rescue
    if options.get("cinematicColor"):
        current_video = stage_cinematic_color(current_video, options)
    if options.get("cinematicGrade") and options.get("cinematicGrade") != "none":
        current_video = stage_cinematic_grade(current_video, options)

    # 14. Bottom Glow
    if options.get("bottomGlow"):
        color = options.get("glowColor", "#000000")
        current_video = stage_bottom_glow(current_video, color)

    print(f"\\n[🚀] PIPELINE COMPLETE. Final output: {current_video}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("[X] Usage: python pipeline.py <video_path> <options_json>")
        sys.exit(1)

    video_path_arg   = sys.argv[1]
    options_json_arg = sys.argv[2]

    try:
        run_pipeline(video_path_arg, options_json_arg)
    except Exception as e:
        import traceback
        print(f"[X] PIPELINE CRASHED: {e}")
        traceback.print_exc()
        sys.exit(1)
