import os, sys, json, subprocess, shutil
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageChops

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

