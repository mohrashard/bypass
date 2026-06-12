import re

file_path = r"c:\Projects\capcut-bypass\ai_engine\pipeline.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Replace VideoWriter initialization
old_init = """    temp_no_audio = os.path.splitext(video_path)[0] + "_grade_temp.mp4"
    writer = cv2.VideoWriter(
        temp_no_audio,
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height)
    )"""

new_init = """    temp_no_audio = os.path.splitext(video_path)[0] + "_grade_temp.mp4"
    try:
        subprocess.run(["ffmpeg", "-f", "lavfi", "-i", "nullsrc", "-c:v", "h264_nvenc", "-t", "1", "-f", "null", "-"], check=True, capture_output=True)
        cvcodec = "h264_nvenc"
        preset = "p6"
        cq_args = ["-cq", "18"]
    except:
        cvcodec = "libx264"
        preset = "superfast"
        cq_args = ["-crf", "17"]

    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{width}x{height}",
        "-pix_fmt", "bgr24",
        "-r", str(fps),
        "-i", "-",
        "-c:v", cvcodec,
        "-preset", preset
    ] + cq_args + [
        "-pix_fmt", "yuv420p",
        temp_no_audio
    ]
    writer = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)"""

content = content.replace(old_init, new_init)

# 2. Replace writing
content = content.replace("writer.write(graded)", "writer.stdin.write(graded.tobytes())")

# 3. Replace release
content = content.replace("writer.release()", "writer.stdin.close()\n    writer.wait()")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("SUCCESS")
