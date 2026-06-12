import re

file_path = r"c:\Projects\capcut-bypass\ai_engine\pipeline.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Pattern to remove the current AI BODY-SCAN VISUAL HOOK ENGINE
# Starts from # 16. AI BODY-SCAN VISUAL HOOK ENGINE
# Ends before # 14. MAIN PIPELINE ORCHESTRATION (actually # ─────────────────────────────────────────────)
pattern = r"# 16\. AI BODY-SCAN VISUAL HOOK ENGINE.*?def stage_starting_hook.*?(?=\n# ─────────────────────────────────────────────\n# 14\. MAIN PIPELINE ORCHESTRATION)"

# The Playwright CSS Engine code
new_engine_code = """# 16. HEADLESS CSS VISUAL HOOK ENGINE (Playwright + Web Animations)
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
    hook_frames = int(fps * dur)

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
    html_template = f\"\"\"<!DOCTYPE html>
    <html>
    <head>
    <meta charset="UTF-8">
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      body {{ width: {width}px; height: {height}px; background: #000; overflow: hidden; position: relative; }}
      
      .layer {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; transform-origin: center center; }}
      
      #bg {{ z-index: 1; }}
      #subject-container {{ z-index: 10; position: absolute; top: 0; left: 0; width: 100%; height: 100%; perspective: 1000px; }}
      #subject {{ width: 100%; height: 100%; object-fit: cover; will-change: transform, filter; transform-style: preserve-3d; }}
      
      .glitch-clone {{ 
         position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; 
         mix-blend-mode: screen; opacity: 0; will-change: transform, filter, opacity; transform-style: preserve-3d;
      }}
      #cinematic-flash {{ 
         position: absolute; top: 0; left: 0; width: 100%; height: 100%; 
         background: radial-gradient(circle at 50% 50%, rgba(255, 250, 230, 0.9) 0%, rgba(255, 200, 150, 0.4) 40%, rgba(0,0,0,0) 80%);
         mix-blend-mode: screen; opacity: 0; z-index: 20; pointer-events: none; will-change: opacity, transform;
      }}
    </style>
    </head>
    <body>
      <img id="bg" class="layer" src="data:image/jpeg;base64,{bg_b64}">
      <div id="cinematic-flash"></div>
      
      <div id="subject-container">
        <img id="clone1" class="glitch-clone" src="data:image/png;base64,{sub_b64}">
        <img id="clone2" class="glitch-clone" src="data:image/png;base64,{sub_b64}">
        <img id="clone3" class="glitch-clone" src="data:image/png;base64,{sub_b64}">
        
        <img id="rgb-red" class="glitch-clone" style="mix-blend-mode: screen;" src="data:image/png;base64,{sub_b64}">
        <img id="rgb-cyan" class="glitch-clone" style="mix-blend-mode: screen;" src="data:image/png;base64,{sub_b64}">
        <img id="xray-layer" class="glitch-clone" style="mix-blend-mode: exclusion; filter: invert(1) contrast(3) saturate(0) brightness(1.5);" src="data:image/png;base64,{sub_b64}">
        
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
            
            // Background is strictly untouched to keep focus on the speaker
            bg.style.transform = 'none';
            bg.style.filter = 'none';
            
            if (hookType === 'capcut_drop') {{
                // PHASE 1: FRAME 1 - The X-Ray Glitch (0% to 15% of the animation)
                if (progress < 0.15) {{
                    let noiseX = (Math.random() - 0.5) * 40;
                    
                    sub.style.opacity = 0; // Hide the clean plate entirely
                    
                    // Trigger the aggressive negative inversion look
                    xray.style.opacity = 0.8;
                    xray.style.transform = `scale(1.1) translateX(${{noiseX}}px)`;
                    
                    // Heavy RGB split snapping randomly
                    rRed.style.opacity = 0.9;
                    rRed.style.transform = `scale(1.15) translateX(30px)`;
                    rRed.style.filter = `drop-shadow(20px 0 0 red) hue-rotate(-45deg)`;
                    
                    rCyan.style.opacity = 0.9;
                    rCyan.style.transform = `scale(1.15) translateX(-30px)`;
                    rCyan.style.filter = `drop-shadow(-20px 0 0 cyan) hue-rotate(45deg)`;
                    
                    cflash.style.opacity = 0.3; // Slight ambient flash
                }}
                
                // PHASE 2: FRAME 2 - The Vertical Echo Drop (15% to 50%)
                else if (progress >= 0.15 && progress < 0.50) {{
                    // Normalize progress for this specific window
                    let dropP = (progress - 0.15) / 0.35; 
                    let e = easeOutExpo(dropP);
                    let yOff = (1 - e) * -800; // Falling from above the frame
                    
                    // Turn off the X-Ray/Glitch layers immediately
                    xray.style.opacity = 0;
                    rRed.style.opacity = 0;
                    rCyan.style.opacity = 0;
                    
                    // Main subject falling in
                    sub.style.opacity = 1;
                    sub.style.transform = `translateY(${{yOff}}px) scale(1)`;
                    sub.style.filter = `brightness(1.1)`;
                    
                    // Echo Clones trailing behind (creates the motion blur ghosting from Image 2)
                    c1.style.opacity = (1 - e) * 0.6;
                    c1.style.transform = `translateY(${{yOff - 100}}px) scaleY(1.1)`;
                    c1.style.filter = `blur(8px) opacity(0.7) brightness(1.5)`;
                    
                    c2.style.opacity = (1 - e) * 0.3;
                    c2.style.transform = `translateY(${{yOff - 220}}px) scaleY(1.2)`;
                    c2.style.filter = `blur(15px) opacity(0.4) brightness(1.2)`;
                    
                    cflash.style.opacity = 0;
                }}
                
                // PHASE 3: FRAME 3 - The Hard Settle (50% to 100%)
                else {{
                    sub.style.opacity = 1;
                    sub.style.transform = `translateY(0) scale(1)`; // Snapped to baseline
                    sub.style.filter = `none`; // Perfectly clean plate
                    
                    // Kill all clones and effects
                    c1.style.opacity = 0;
                    c2.style.opacity = 0;
                    rRed.style.opacity = 0;
                    rCyan.style.opacity = 0;
                    xray.style.opacity = 0;
                    cflash.style.opacity = 0;
                }}
            }}
            
            else if (hookType === 'drop_in') {{
                // Cinematic "Dropped from Sky"
                let decay = easeOutExpo(progress);
                let yOff = (1 - decay) * -1000; 
                let scaleY = 1.0 + ((1 - decay) * 0.8);
                let scaleX = 1.0 - ((1 - decay) * 0.1);
                let bloom = 1 - progress; 
                
                sub.style.transform = `translateY(${{yOff}}px) scale(${{scaleX}}, ${{scaleY}})`;
                sub.style.filter = `drop-shadow(0px 30px 40px rgba(0, 0, 0, 0.8)) drop-shadow(0px 0px ${{40*bloom}}px rgba(255, 255, 255, ${{bloom*0.8}})) brightness(${{1 + bloom*0.4}})`;
                
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
                let zOff = (1 - decay) * 600; // Deep 3D perspective 
                let yOff = (1 - decay) * -200;
                let bloom = 1 - progress;
                
                sub.style.transform = `translateY(${{yOff}}px) translateZ(${{zOff}}px)`;
                sub.style.filter = `drop-shadow(0px 20px 40px rgba(0,0,0,0.7)) drop-shadow(0px 0px ${{50*bloom}}px rgba(255, 240, 200, ${{bloom}})) brightness(${{1 + bloom*0.5}})`;

                // Impact burst ring
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
                
                let scale = 1.0 + (progress * 0.05); // Cinematic push-in
                sub.style.transform = `scale(${{scale}})`;
                
                // Heavenly rim light and drop shadow
                sub.style.filter = `drop-shadow(0px 10px 30px rgba(0,0,0,0.5)) drop-shadow(0px 0px ${{60*bloom}}px rgba(255, 255, 255, ${{bloom*0.9}})) brightness(${{1 + bloom*0.6}})`;
                
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
                
                sub.style.filter = `drop-shadow(0px 0px ${{30*bloom}}px rgba(0, 255, 255, ${{bloom*0.5}})) brightness(${{1 + bloom*0.3}})`;
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
                sub.style.filter = `drop-shadow(0px 20px 40px rgba(0,0,0,0.7)) drop-shadow(0px 0px ${{50*bloom}}px rgba(255, 200, 200, ${{bloom*0.6}})) brightness(${{1 + bloom*0.4}})`;
                
                c1.style.opacity = decay * 0.6;
                c1.style.transform = `translate(${{shakeX - 15*decay}}px, ${{shakeY}}px) scale(${{scale}})`;
                c1.style.filter = `hue-rotate(-90deg) brightness(1.2)`;

                c2.style.opacity = decay * 0.6;
                c2.style.transform = `translate(${{shakeX + 15*decay}}px, ${{shakeY}}px) scale(${{scale}})`;
                c2.style.filter = `hue-rotate(90deg) brightness(1.2)`;
                
                if(c3) c3.style.opacity = 0;
                cflash.style.opacity = bloom * 0.9;
            }}
        }}
      </script>
    </body>
    </html>\"\"\"
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
    sfx_map   = {"flash":"flash_sfx.MP3","flash_drop":"flash_sfx.MP3", "drop_in":"impact_sfx.MP3","glitch":"glitch_sfx.MP3","impact":"impact_sfx.MP3", "capcut_drop":"glitch_sfx.MP3"}
    sfx_audio = os.path.join(engine_dir, "assets", sfx_map.get(hook_type, ""))
    has_sfx   = os.path.exists(sfx_audio)

    # Convert PNG sequence to temporary MP4
    subprocess.run([
        "ffmpeg", "-framerate", str(fps), "-i", os.path.join(frames_dir, "frame_%04d.png"),
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", temp_vid, "-y"
    ], check=True, capture_output=True)

    # Overlay temp video over main video for duration, mix SFX
    fc = (f"[0:v]tpad=start_duration={dur}:start_mode=clone[v_main];"
          f"[v_main][1:v]overlay=eof_action=pass[v_out];"
          f"[0:a]adelay={int(dur*1000)}:all=1[main_a]")
    
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
"""

new_content = re.sub(pattern, new_engine_code, content, flags=re.DOTALL)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(new_content)

print("SUCCESS")
