import os, sys, json, subprocess, shutil
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageChops

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

