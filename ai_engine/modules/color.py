import os, sys, json, subprocess, shutil
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageChops

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

