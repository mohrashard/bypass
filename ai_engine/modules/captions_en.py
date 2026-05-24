import os, sys, json, subprocess, shutil
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageChops

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

