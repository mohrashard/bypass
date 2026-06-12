import sys

file_path = r"c:\Projects\capcut-bypass\ai_engine\pipeline.py"

with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if line.startswith("def stage_starting_hook(video_path: str, options: dict) -> str:"):
        start_idx = i
    elif line.strip().startswith("# ── 3. Frame Rendering via Playwright") and start_idx != -1:
        end_idx = i
        break

if start_idx == -1 or end_idx == -1:
    print("Could not find block")
    sys.exit(1)

new_code = """def stage_starting_hook(video_path: str, options: dict) -> str:
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
    </style>
    </head>
    <body>
      <img id="bg" class="layer" src="data:image/jpeg;base64,{bg_b64}">
      
      <div id="subject-container">
        <img id="clone1" class="glitch-clone" src="data:image/png;base64,{sub_b64}">
        <img id="clone2" class="glitch-clone" src="data:image/png;base64,{sub_b64}">
        <img id="clone3" class="glitch-clone" src="data:image/png;base64,{sub_b64}">
        <img id="subject" src="data:image/png;base64,{sub_b64}">
      </div>

      <script>
        function renderFrame(progress, hookType) {{
            const bg = document.getElementById('bg');
            const sub = document.getElementById('subject');
            const c1 = document.getElementById('clone1');
            const c2 = document.getElementById('clone2');
            const c3 = document.getElementById('clone3');

            const easeOutExpo = t => t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
            
            // Background is strictly untouched to keep focus on the speaker
            bg.style.transform = 'none';
            bg.style.filter = 'none';
            
            if (hookType === 'drop_in') {{
                // Crisp drop in from slightly above
                let decay = easeOutExpo(progress);
                let yOff = (1 - decay) * -150; 
                let scale = 1.0 + ((1 - decay) * 0.3);
                
                sub.style.transform = `translateY(${{yOff}}px) scale(${{scale}})`;
                sub.style.filter = `drop-shadow(0px 30px 40px rgba(0, 0, 0, 0.6)) brightness(${{1 + (1-decay)*0.3}})`;
                
                // Subtle light trail
                c1.style.opacity = (1 - decay) * 0.5;
                c1.style.transform = `translateY(${{yOff - 40}}px) scale(${{scale}})`;
                c1.style.filter = `blur(4px) brightness(1.2)`;
                
                c2.style.opacity = 0; c3.style.opacity = 0;
            }}
            
            else if (hookType === 'flash_drop') {{
                // Crisp drop in scaling down
                let decay = easeOutExpo(progress);
                let scale = 1.0 + ((1 - decay) * 0.4);
                
                sub.style.transform = `scale(${{scale}})`;
                sub.style.filter = `brightness(${{1.0 + (1-decay)*0.5}}) drop-shadow(0px 20px 30px rgba(0,0,0,0.5))`;

                // Impact burst ring
                let burst = progress / 0.5;
                if (burst <= 1) {{
                    c1.style.opacity = 1 - burst;
                    c1.style.transform = `scale(${{1.0 + burst*0.2}})`;
                    c1.style.filter = `brightness(1.5) blur(2px)`;
                }} else {{
                    c1.style.opacity = 0;
                }}
                c2.style.opacity = 0; c3.style.opacity = 0;
            }}

            else if (hookType === 'flash') {{
                // Simple bright flash exclusively on the subject
                let decay = easeOutExpo(progress);
                
                let scale = 1.0 + (progress * 0.02); // very slow subtle push
                sub.style.transform = `scale(${{scale}})`;
                sub.style.filter = `brightness(${{1.0 + decay*0.6}}) drop-shadow(0px 0px ${{40*decay}}px rgba(255, 255, 255, ${{decay*0.8}}))`;
                
                c1.style.opacity = 0; c2.style.opacity = 0; c3.style.opacity = 0;
            }}

            else if (hookType === 'glitch') {{
                // Sharp cyber glitch
                let decay = 1 - progress; 
                
                if (decay > 0.05) {{
                    let isHard = Math.random() > 0.5;
                    let shift = 20 * decay;
                    
                    c1.style.opacity = 0.7 * decay;
                    c1.style.transform = `translateX(${{shift}}px)`;
                    c1.style.filter = `hue-rotate(-90deg) saturate(2)`;
                    c1.style.clipPath = `inset(${{Math.random()*80}}% 0 ${{Math.random()*80}}% 0)`;

                    c2.style.opacity = 0.7 * decay;
                    c2.style.transform = `translateX(${{-shift}}px)`;
                    c2.style.filter = `hue-rotate(90deg) saturate(2)`;
                    c2.style.clipPath = `inset(${{Math.random()*80}}% 0 ${{Math.random()*80}}% 0)`;

                    sub.style.opacity = 1;
                    sub.style.transform = `translate(${{(Math.random()-0.5)*10*decay}}px, 0px)`;
                    
                    if (isHard) sub.style.clipPath = `polygon(0 ${{Math.random()*10}}%, 100% ${{Math.random()*10}}%, 100% 100%, 0 100%)`;
                    else sub.style.clipPath = 'none';
                }} else {{
                    c1.style.opacity = 0; c2.style.opacity = 0;
                    sub.style.opacity = 1; sub.style.transform = 'none';
                    sub.style.clipPath = 'none';
                }}
                c3.style.opacity = 0;
            }}

            else if (hookType === 'impact') {{
                // Fast bass hit punch
                let decay = 1 - easeOutExpo(progress);
                
                let scale = 1.0 + (decay * 0.15);
                let shakeX = (Math.random() - 0.5) * 20 * decay;
                let shakeY = (Math.random() - 0.5) * 20 * decay;
                
                sub.style.transform = `translate(${{shakeX}}px, ${{shakeY}}px) scale(${{scale}})`;
                sub.style.filter = `brightness(${{1 + decay*0.3}}) drop-shadow(0px 10px 20px rgba(0,0,0,0.5))`;
                
                // Tight chromatic aberration
                c1.style.opacity = decay * 0.6;
                c1.style.transform = `translate(${{shakeX - 10*decay}}px, ${{shakeY}}px) scale(${{scale}})`;
                c1.style.filter = `hue-rotate(-90deg)`;

                c2.style.opacity = decay * 0.6;
                c2.style.transform = `translate(${{shakeX + 10*decay}}px, ${{shakeY}}px) scale(${{scale}})`;
                c2.style.filter = `hue-rotate(90deg)`;
                
                c3.style.opacity = 0;
            }}
        }}
      </script>
    </body>
    </html>
    \"\"\"
"""

final_lines = lines[:start_idx] + [new_code] + lines[end_idx:]
with open(file_path, "w", encoding="utf-8") as f:
    f.writelines(final_lines)

print("SUCCESS")
