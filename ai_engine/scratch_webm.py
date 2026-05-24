import os

target = r"c:\Projects\capcut-bypass\ai_engine\pipeline.py"
with open(target, "r", encoding="utf-8") as f:
    content = f.read()

# REPLACE ENGLISH EXPORT
content = content.replace(
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
        chunk_out = os.path.join(base_dir, f"_ovr_chunk_{chunk_start:04d}.mp4")""",
"""    # Start from a fully transparent black video using fast VP9 (WebM)
    transparent_base = os.path.join(base_dir, "_transparent_base.webm")
    subprocess.run([
        "ffmpeg",
        "-f", "lavfi", "-i", f"color=c=black@0.0:size={W}x{H}:rate={fps}:duration={duration}",
        "-c:v", "libvpx-vp9", "-row-mt", "1", "-cpu-used", "4", "-crf", "25", "-b:v", "0",
        "-pix_fmt", "yuva420p", "-auto-alt-ref", "0",
        transparent_base, "-y"
    ], check=True, capture_output=True)

    current_video = transparent_base
    for chunk_start in range(0, len(segments), CHUNK):
        chunk     = segments[chunk_start: chunk_start + CHUNK]
        chunk_out = os.path.join(base_dir, f"_ovr_chunk_{chunk_start:04d}.webm")"""
)

content = content.replace(
"""        cmd = inputs + [
            "-filter_complex", ";".join(filter_parts),
            "-map", f"[v{len(chunk)}]",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p",
            chunk_out, "-y"
        ]""",
"""        cmd = inputs + [
            "-filter_complex", ";".join(filter_parts),
            "-map", f"[v{len(chunk)}]",
            "-c:v", "libvpx-vp9", "-row-mt", "1", "-cpu-used", "4", "-crf", "25", "-b:v", "0",
            "-pix_fmt", "yuva420p", "-auto-alt-ref", "0",
            chunk_out, "-y"
        ]"""
)

content = content.replace(
"""    output_vid = os.path.splitext(video_path)[0] + "_captions_overlay_en.mp4\"""",
"""    output_vid = os.path.splitext(video_path)[0] + "_captions_overlay_en.webm\""""
)

content = content.replace(
"""    print(f"[📋] Drag '{os.path.basename(output_vid)}' to CapCut -> Remove BG -> Chroma Key the Green color.")""",
"""    print(f"[📋] Drag '{os.path.basename(output_vid)}' onto your CapCut timeline above your footage.")"""
)


# REPLACE SINHALA EXPORT
content = content.replace(
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
        chunk_out = os.path.join(base_dir, f"_ovr_si_chunk_{chunk_start:04d}.mp4")""",
"""    transparent_base = os.path.join(base_dir, "_transparent_base_si.webm")
    subprocess.run([
        "ffmpeg",
        "-f", "lavfi", "-i", f"color=c=black@0.0:size={W}x{H}:rate={fps}:duration={duration}",
        "-c:v", "libvpx-vp9", "-row-mt", "1", "-cpu-used", "4", "-crf", "25", "-b:v", "0",
        "-pix_fmt", "yuva420p", "-auto-alt-ref", "0",
        transparent_base, "-y"
    ], check=True, capture_output=True)

    current_video = transparent_base
    for chunk_start in range(0, len(segments_arr), CHUNK):
        chunk     = segments_arr[chunk_start: chunk_start + CHUNK]
        chunk_out = os.path.join(base_dir, f"_ovr_si_chunk_{chunk_start:04d}.webm")"""
)

content = content.replace(
"""    output_vid = os.path.splitext(video_path)[0] + "_captions_overlay_si.mp4\"""",
"""    output_vid = os.path.splitext(video_path)[0] + "_captions_overlay_si.webm\""""
)

with open(target, "w", encoding="utf-8") as f:
    f.write(content)

print("Done replacing.")
