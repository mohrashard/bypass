import os, sys, json, subprocess, shutil
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageChops

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
    green_screen = options.get("greenScreenOverlay", False)
    if green_screen:
        print("[⚙️] [OVERLAY EXPORT] Compositing onto Green Screen (.mp4)...")
    else:
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
    if green_screen:
        output_vid = os.path.splitext(video_path)[0] + "_captions_overlay_en.mp4"
    else:
        output_vid = os.path.splitext(video_path)[0] + "_captions_overlay_en.mov"

    for chunk_start in range(0, len(segments), CHUNK):
        chunk     = segments[chunk_start: chunk_start + CHUNK]
        ext = ".mp4" if green_screen else ".mov"
        chunk_out = os.path.join(base_dir, f"_ovr_en_chunk_{chunk_start:04d}{ext}")
        chunk_files.append(chunk_out)

        if current_base is None:
            if green_screen:
                inputs_cmd = [
                    "ffmpeg", "-f", "lavfi", "-i",
                    f"color=c=#00FF00:size={W}x{H}:rate={fps}:duration={duration}" 
                ]
            else:
                # Force RGBA directly on the lavfi generation to guarantee a transparent background
                inputs_cmd = [
                    "ffmpeg",
                    "-f", "lavfi", "-i",
                    f"color=c=black@0.0:size={W}x{H}:rate={fps}:duration={duration},format=rgba"
                ]
        else:
            if green_screen:
                inputs_cmd = ["ffmpeg", "-i", current_base]
            else:
                # Tell FFmpeg to decode the previous chunk preserving alpha
                inputs_cmd = ["ffmpeg", "-vcodec", "qtrle", "-i", current_base]

        for _, _, path, _, _ in chunk:
            inputs_cmd += ["-i", path]

        filter_parts = _build_overlay_filter(chunk, anim_style, dur)

        if green_screen:
            cmd = inputs_cmd + [
                "-filter_complex", ";".join(filter_parts),
                "-map", f"[v{len(chunk)}]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18", 
                "-pix_fmt", "yuv420p",
                chunk_out, "-y"
            ]
        else:
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
    green_screen = options.get("greenScreenOverlay", False)
    if green_screen:
        print("[⚙️] [OVERLAY EXPORT] Compositing Sinhala captions onto Green Screen (.mp4)...")
    else:
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
    if green_screen:
        output_vid = os.path.splitext(video_path)[0] + "_captions_overlay_si.mp4"
    else:
        output_vid = os.path.splitext(video_path)[0] + "_captions_overlay_si.mov"

    for chunk_start in range(0, len(segments_arr), CHUNK):
        chunk     = segments_arr[chunk_start: chunk_start + CHUNK]
        ext = ".mp4" if green_screen else ".mov"
        chunk_out = os.path.join(base_dir, f"_ovr_si_chunk_{chunk_start:04d}{ext}")
        chunk_files.append(chunk_out)

        if current_base is None:
            if green_screen:
                inputs_cmd = [
                    "ffmpeg", "-f", "lavfi", "-i",
                    f"color=c=#00FF00:size={W}x{H}:rate={fps}:duration={duration}" 
                ]
            else:
                # Force RGBA directly on the lavfi generation
                inputs_cmd = [
                    "ffmpeg",
                    "-f", "lavfi", "-i",
                    f"color=c=black@0.0:size={W}x{H}:rate={fps}:duration={duration},format=rgba"
                ]
        else:
            if green_screen:
                inputs_cmd = ["ffmpeg", "-i", current_base]
            else:
                # Tell FFmpeg to decode the previous chunk preserving alpha
                inputs_cmd = ["ffmpeg", "-vcodec", "qtrle", "-i", current_base]

        for _, _, path, _, _ in chunk:
            inputs_cmd += ["-i", path]

        filter_parts = _build_si_filter(chunk, anim_style, dur)

        if green_screen:
            cmd = inputs_cmd + [
                "-filter_complex", ";".join(filter_parts),
                "-map", f"[v{len(chunk)}]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18", 
                "-pix_fmt", "yuv420p",
                chunk_out, "-y"
            ]
        else:
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


