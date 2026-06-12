import re

file_path = r"c:\Projects\capcut-bypass\ai_engine\pipeline.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Insert stage_cinematic_grade
cinematic_grade_code = """# ─────────────────────────────────────────────────────────────────────────────
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
    writer = cv2.VideoWriter(
        temp_no_audio,
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height)
    )

    with vision.ImageSegmenter.create_from_options(seg_options) as segmenter:
        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            res    = segmenter.segment(mp_img)

            if res.confidence_masks:
                mask = np.squeeze(res.confidence_masks[0].numpy_view())
                graded = grade_frame(frame, mask)
            else:
                graded = unsharp_mask(frame, p["sharpen"] * 0.5)

            writer.write(graded)
            frame_idx += 1
            if frame_idx % 30 == 0:
                print(f"  [🎨] {frame_idx}/{total} frames graded...")

    cap.release()
    writer.release()

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

"""

content = re.sub(
    r"(# 16\. HEADLESS CSS VISUAL HOOK ENGINE \(Playwright \+ Web Animations\))",
    cinematic_grade_code + r"\n\1",
    content
)

# 2. Add to run_pipeline
call_code = """
    if options.get("cinematicGrade") and options.get("cinematicGrade") != "none":
        current_video = stage_cinematic_grade(current_video, options)
"""

content = re.sub(
    r"(if options\.get\(\"startingHook\"\) and options\.get\(\"startingHook\"\) != \"none\":\n\s+current_video = stage_starting_hook\(current_video, options\))",
    call_code.strip() + r"\n\n    \1",
    content
)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("SUCCESS")
