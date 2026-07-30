import os
import re

with open('c:/Projects/capcut-bypass/ai_engine/pipeline.py', 'r', encoding='utf-8') as f:
    code = f.read()

new_transitions = '''def stage_scene_transitions(video_path: str, options: dict) -> str:
    import os
    import json
    import subprocess
    
    print("[⚙️] Injecting 0.3s Elastic Slide & Flash Transitions...")
    base_dir   = os.path.dirname(os.path.abspath(video_path))
    output_vid = os.path.splitext(video_path)[0] + "_transitions.mp4"
    json_path  = os.path.join(base_dir, "_flash_times.json")

    flash_times = []
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            flash_times = json.load(f)
        os.remove(json_path)

    if not flash_times:
        print("[⚙️] No cuts detected. Skipping transitions.")
        return video_path

    print(f"[🎬] Found {len(flash_times)} cuts. Rendering REAL FFmpeg Engine for Elastic Snap & Flash...")

    # We will split the video at cut times, apply the transition math to the incoming scene, 
    # and then concat them back together.
    
    filter_complex = f"[0:v]split={len(flash_times)+1}"
    for i in range(len(flash_times)+1):
        filter_complex += f"[v{i}]"
    filter_complex += ";\\n"
    
    last_t = 0.0
    for i, t in enumerate(flash_times):
        filter_complex += f"[v{i}]trim=start={last_t}:end={t},setpts=PTS-STARTPTS[seg{i}];\\n"
        last_t = t
    filter_complex += f"[v{len(flash_times)}]trim=start={last_t},setpts=PTS-STARTPTS[seg{len(flash_times)}];\\n"

    # Now apply the transition math to every incoming segment (seg 1 to n)
    concat_inputs = "[seg0]"
    
    for i in range(1, len(flash_times)+1):
        elastic_x_expr = "w * exp(-7*(t/0.3)) * cos(15*(t/0.3))"
        blur_expr = "boxblur=lr=if(lte(t,0.3), 20*(1-(t/0.3)), 0):lp=0"
        flash_expr = "eq=brightness='if(lte(t,0.3), 0.8 * (1 - (t/0.3)), 0)'"
        
        filter_complex += f"color=c=black:s=1080x1920:d=10[bg{i}];\\n"
        overlay_cmd = f"overlay=x='{elastic_x_expr}':y=0:shortest=1"
        filter_complex += f"[bg{i}][seg{i}]{overlay_cmd},{blur_expr},{flash_expr}[trans{i}];\\n"
        
        concat_inputs += f"[trans{i}]"
    
    filter_complex += f"{concat_inputs}concat=n={len(flash_times)+1}:v=1:a=0[outv]"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "0:a?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        output_vid
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"[✅] Elastic Slide & Flash transition rendered successfully: {output_vid}")
        return output_vid
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        print(f"[❌] Transitions failed: {err_msg}")
        return video_path

'''

# We need to replace everything from "def stage_scene_transitions" down to just before "def stage_hardcode_flash"
pattern = r"def stage_scene_transitions\(video_path: str, options: dict\) -> str:.*?def stage_hardcode_flash"
# By using lookahead, we don't consume stage_hardcode_flash
pattern = r"def stage_scene_transitions\(video_path: str, options: dict\) -> str:.*?(?=def stage_hardcode_flash)"

code = re.sub(pattern, new_transitions, code, flags=re.DOTALL)

with open('c:/Projects/capcut-bypass/ai_engine/pipeline.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('SUCCESS')
