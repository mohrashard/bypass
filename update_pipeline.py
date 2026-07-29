import os

file_path = r'c:\Projects\capcut-bypass\ai_engine\pipeline.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# We want to replace the chroma key section inside stage_background_fx
import re

start_marker = r'if os\.path\.exists\(temp_vid\): os\.remove\(temp_vid\)'
end_marker = r'return output_vid'

match_start = re.search(start_marker, content)
match_end = re.search(end_marker, content[match_start.end():])

if not match_start or not match_end:
    print("Could not find markers")
    exit(1)
    
start_idx = match_start.end()
end_idx = match_start.end() + match_end.start() - 25 # backtrack a bit to keep the print statement before return

new_code = """
        # Handle Timeline Scenes & Sandwich Text
        timeline_scenes = bg_options.get("timelineScenes", [])
        if not timeline_scenes:
            timeline_scenes = [{
                "timestamp": 0.0,
                "bgImagePath": bg_image_path if mode == "image" else "",
                "bgScale": bg_scale,
                "subjectScale": sub_scale,
                "subjectY": sub_y,
                "textBehind": bg_options.get("textBehind", ""),
                "textY": bg_options.get("textY", 50),
                "textSize": bg_options.get("textSize", 100),
            }]

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True
        )
        try:
            video_duration = float(probe.stdout.strip())
        except:
            video_duration = 9999.0

        inputs = ["-i", video_path]
        num_inputs = 1
        filter_complex = ""
        bg_streams = []

        for i, scene in enumerate(timeline_scenes):
            start_t = float(scene.get("timestamp", 0))
            end_t = float(timeline_scenes[i+1].get("timestamp")) if i+1 < len(timeline_scenes) else video_duration
            dur = end_t - start_t
            if dur <= 0: continue

            # 1. Background Source
            scene_bg_img = scene.get("bgImagePath", "")
            if scene_bg_img and os.path.exists(scene_bg_img):
                inputs.extend(["-loop", "1", "-i", scene_bg_img])
                idx = num_inputs
                num_inputs += 1
                scene_bg_scale = int(scene.get("bgScale", 100))
                bg_w = int(w * (scene_bg_scale / 100.0))
                bg_h = int(h * (scene_bg_scale / 100.0))
                filter_complex += f"[{idx}:v]trim=duration={dur},scale={bg_w}:{bg_h}:force_original_aspect_ratio=increase,crop={w}:{h},setpts=PTS-STARTPTS[bg_raw{i}];"
            else:
                scene_hex = hex_color if len(hex_color) == 6 else "09090b"
                filter_complex += f"color=c=#{scene_hex}:s={w}x{h}:d={dur}[bg_raw{i}];"

            # 2. Sandwich Text
            text = scene.get("textBehind", "").strip()
            if text:
                text_y = int(scene.get("textY", 50))
                text_size = int(scene.get("textSize", 100))
                fs = int(text_size * 1.5)
                # Escape single quotes and colons for FFmpeg
                esc_text = text.replace("'", "\\\\\\'").replace(":", "\\\\:")
                text_cmd = f"drawtext=text='{esc_text}':fontcolor=white:fontsize={fs}:x=(w-text_w)/2:y=(h-text_h)*{text_y}/100"
                filter_complex += f"[bg_raw{i}]{text_cmd}[bg{i}];"
            else:
                filter_complex += f"[bg_raw{i}]copy[bg{i}];"

            bg_streams.append(f"[bg{i}]")

            # 3. Subject Overlay
            scene_sub_scale = int(scene.get("subjectScale", 100))
            scene_sub_y = int(scene.get("subjectY", 0))
            sub_w = int(w * scene_sub_scale / 100)
            sub_h = int(h * scene_sub_scale / 100)
            sub_w = sub_w if sub_w % 2 == 0 else sub_w + 1
            sub_h = sub_h if sub_h % 2 == 0 else sub_h + 1
            y_offset = f"+(H*{scene_sub_y}/100)" if scene_sub_y != 0 else ""

            chroma_filter = "chromakey=0x1A9535:0.11:0.02,despill=green"
            
            filter_complex += f"[0:v]trim=start={start_t}:duration={dur},setpts=PTS-STARTPTS,{chroma_filter},scale={sub_w}:{sub_h}[fg{i}];"
            filter_complex += f"{bg_streams[-1]}[fg{i}]overlay=(W-w)/2:H-h{y_offset}:shortest=1[seg{i}];"

        # Concat all segments
        concat_inputs = "".join([f"[seg{i}]" for i in range(len(timeline_scenes))])
        if len(timeline_scenes) > 1:
            filter_complex += f"{concat_inputs}concat=n={len(timeline_scenes)}:v=1:a=0,format=yuv420p[outv]"
        else:
            filter_complex += f"{concat_inputs}format=yuv420p[outv]"

        audio_idx = num_inputs
        inputs.extend(["-i", temp_audio])

        print("[⚙️] Running ultra-fast FFmpeg render pipeline (Multi-Scene + Sandwich)...")
        cmd = [
            "ffmpeg", *inputs,
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", f"{audio_idx}:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", output_vid, "-y"
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
            print(f"[❌] FFmpeg Engine Failed:\\n{err_msg}")
            raise

        for f in [temp_audio]:
            if os.path.exists(f): os.remove(f)

        print(f"[✅] Background FX applied: {output_vid}")
"""

final_content = content[:start_idx] + "\n" + new_code + "\n        " + content[end_idx:]

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(final_content)
    
print("Successfully replaced.")
