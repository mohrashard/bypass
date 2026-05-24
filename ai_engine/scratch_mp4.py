import os
import re

target = r"c:\Projects\capcut-bypass\ai_engine\pipeline.py"
with open(target, "r", encoding="utf-8") as f:
    content = f.read()

# REPLACE ENGLISH EXPORT
content = content.replace(
"""    # Start from a fully transparent black video (no source footage)
    transparent_base = os.path.join(base_dir, "_transparent_base.mov")
    subprocess.run([
        "ffmpeg",
        "-f", "lavfi", "-i", f"color=c=black@0.0:size={W}x{H}:rate={fps}:duration={duration}",
        "-c:v", "prores_ks", "-profile:v", "4",  # ProRes 4444 — lossless alpha, works in CapCut/Premiere/DaVinci
        "-pix_fmt", "yuva444p10le",
        transparent_base, "-y"
    ], check=True, capture_output=True)

    current_video = transparent_base
    for chunk_start in range(0, len(segments), CHUNK):
        chunk     = segments[chunk_start: chunk_start + CHUNK]
        chunk_out = os.path.join(base_dir, f"_ovr_chunk_{chunk_start:04d}.mov")""",
"""    # Start from a solid Green Screen video for Chroma Keying (100x faster than ProRes)
    transparent_base = os.path.join(base_dir, "_transparent_base.mp4")
    subprocess.run([
        "ffmpeg",
        "-f", "lavfi", "-i", f"color=c=#00FF00:size={W}x{H}:rate={fps}:duration={duration}",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        transparent_base, "-y"
    ], check=True, capture_output=True)

    current_video = transparent_base
    for chunk_start in range(0, len(segments), CHUNK):
        chunk     = segments[chunk_start: chunk_start + CHUNK]
        chunk_out = os.path.join(base_dir, f"_ovr_chunk_{chunk_start:04d}.mp4")"""
)

content = content.replace(
"""        cmd = inputs + [
            "-filter_complex", ";".join(filter_parts),
            "-map", f"[v{len(chunk)}]",
            "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le",
            chunk_out, "-y"
        ]""",
"""        cmd = inputs + [
            "-filter_complex", ";".join(filter_parts),
            "-map", f"[v{len(chunk)}]",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p",
            chunk_out, "-y"
        ]"""
)

content = content.replace(
"""    output_vid = os.path.splitext(video_path)[0] + "_captions_overlay_en.mov\"""",
"""    output_vid = os.path.splitext(video_path)[0] + "_captions_overlay_en.mp4\""""
)

content = content.replace(
"""    print(f"[📋] Drag '{os.path.basename(output_vid)}' onto your CapCut timeline above your footage.")""",
"""    print(f"[📋] Drag '{os.path.basename(output_vid)}' to CapCut -> Remove BG -> Chroma Key the Green color.")"""
)

# REPLACE SINHALA EXPORT
content = content.replace(
"""    transparent_base = os.path.join(base_dir, "_transparent_base_si.mov")
    subprocess.run([
        "ffmpeg",
        "-f", "lavfi", "-i", f"color=c=black@0.0:size={W}x{H}:rate={fps}:duration={duration}",
        "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le",
        transparent_base, "-y"
    ], check=True, capture_output=True)

    current_video = transparent_base
    for chunk_start in range(0, len(segments_arr), CHUNK):
        chunk     = segments_arr[chunk_start: chunk_start + CHUNK]
        chunk_out = os.path.join(base_dir, f"_ovr_si_chunk_{chunk_start:04d}.mov")""",
"""    transparent_base = os.path.join(base_dir, "_transparent_base_si.mp4")
    subprocess.run([
        "ffmpeg",
        "-f", "lavfi", "-i", f"color=c=#00FF00:size={W}x{H}:rate={fps}:duration={duration}",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p",
        transparent_base, "-y"
    ], check=True, capture_output=True)

    current_video = transparent_base
    for chunk_start in range(0, len(segments_arr), CHUNK):
        chunk     = segments_arr[chunk_start: chunk_start + CHUNK]
        chunk_out = os.path.join(base_dir, f"_ovr_si_chunk_{chunk_start:04d}.mp4")"""
)

content = content.replace(
"""    output_vid = os.path.splitext(video_path)[0] + "_captions_overlay_si.mov\"""",
"""    output_vid = os.path.splitext(video_path)[0] + "_captions_overlay_si.mp4\""""
)

with open(target, "w", encoding="utf-8") as f:
    f.write(content)

print("Done replacing.")
