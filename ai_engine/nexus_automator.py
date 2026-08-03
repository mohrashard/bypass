import sys
import json
import os
import io

# Fix Windows console UTF-8 encoding issues for emojis
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
if sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

def generate_code(options):
    from dotenv import load_dotenv
    from groq import Groq

    # Load environment variables
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    groq_api_key = os.environ.get("GROQ_API_KEY")
    
    if not groq_api_key:
        print("[❌] GROQ_API_KEY not found in .env")
        sys.exit(1)

    print("\n[🤖] Booting Groq LLM (Llama 3 70B) for Code Generation...")
    client = Groq(api_key=groq_api_key)

    user_prompt = options.get("prompt", "")
    phrase = options.get("phrase", "")

    # Read the base system prompt from the markdown file
    prompt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "NEXUS_ENGINE_PROMPT.md")
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            base_prompt = f.read()
    except Exception as e:
        print(f"[❌] Could not read NEXUS_ENGINE_PROMPT.md: {e}")
        sys.exit(1)

    system_prompt = base_prompt + f"""

---
ADDITIONAL CONTEXT FOR THIS REQUEST:
The target phrase to animate is: "{phrase}". Ensure this exact text is prominent in your design.
Only output the raw HTML code. Do NOT wrap it in Markdown code blocks (no ```html ... ```). Output starting directly with <!DOCTYPE html>.
"""

    print(f"[⚙️] Sending prompt for phrase: '{phrase}'")
    
    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.2,
        )
        
        generated_html = response.choices[0].message.content.strip()
        
        # In case the model still outputs markdown blocks, strip them
        if generated_html.startswith("```html"):
            generated_html = generated_html[7:]
        if generated_html.startswith("```"):
            generated_html = generated_html[3:]
        if generated_html.endswith("```"):
            generated_html = generated_html[:-3]
            
        generated_html = generated_html.strip()

        print("\n[✅] Code Generation Complete!")
        # Use delimiters so the frontend can easily parse it from stdout
        print("__HTML_START__")
        print(generated_html)
        print("__HTML_END__")
        
    except Exception as e:
        print(f"[❌] Groq API failed: {e}")
        import traceback
        traceback.print_exc()

def render_pipeline(options):
    import subprocess
    import tempfile
    
    print("\n[🎬] Booting Batch Render Engine")
    video_path = options.get("videoPath")
    segments = options.get("segments", [])
    
    if not video_path or not os.path.exists(video_path):
        print(f"[❌] Base video not found: {video_path}")
        sys.exit(1)
        
    valid_segments = [s for s in segments if s.get("htmlCode")]
    if not valid_segments:
        print("[❌] No generated HTML found in any segment.")
        sys.exit(1)
        
    print(f"[⚙️] Found {len(valid_segments)} segments with HTML code.")
    
    temp_dir = tempfile.mkdtemp(prefix="nexus_automator_")
    segment_videos = []
    
    nexus_engine_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nexus_engine.py")
    python_exe = sys.executable

    def get_video_dims(path):
        try:
            cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", path]
            out = subprocess.check_output(cmd).decode().strip()
            w, h = out.split(",")
            return int(w), int(h)
        except Exception:
            return 1080, 1920
            
    def check_has_audio(path):
        try:
            cmd = ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", path]
            out = subprocess.check_output(cmd).decode().strip()
            return "audio" in out
        except Exception:
            return False

    base_w, base_h = get_video_dims(video_path)
    base_has_audio = check_has_audio(video_path)

    # Step 1: Render each segment to a transparent .mov
    for i, seg in enumerate(valid_segments):
        start_time = float(seg.get("start", 0))
        end_time = float(seg.get("end", 0))
        duration = end_time - start_time
        if duration <= 0:
            duration = 3.0 # Fallback
            
        out_mov = os.path.join(temp_dir, f"segment_{i}.mov")
        print(f"\n[🚀] Rendering Segment {i+1}/{len(valid_segments)} (Duration: {duration:.2f}s) -> {out_mov}")
        
        # We assume 1080x1920 (9:16) for now, standard for Nexus Engine shorts
        engine_options = {
            "html": seg["htmlCode"],
            "duration": duration,
            "fps": 60,
            "width": 1080,
            "height": 1920,
            "transparent": True
        }
        
        opt_fd, opt_path = tempfile.mkstemp(suffix=".json", prefix="engine_opt_")
        with os.fdopen(opt_fd, 'w', encoding='utf-8') as f:
            json.dump(engine_options, f)
            
        cmd = [
            python_exe,
            nexus_engine_script,
            opt_path,
            out_mov
        ]
        
        result = subprocess.run(cmd)
        
        try:
            os.unlink(opt_path)
        except:
            pass
        if result.returncode == 0 and os.path.exists(out_mov):
            segment_videos.append({
                "path": out_mov,
                "start": start_time,
                "end": end_time,
                "has_audio": check_has_audio(out_mov)
            })
        else:
            print(f"[⚠️] Failed to render segment {i+1}")

    if not segment_videos:
        print("[❌] All segment renders failed.")
        sys.exit(1)
        
    # Step 2: Composite over the base video
    base_name, ext = os.path.splitext(video_path)
    final_output = f"{base_name}_nexus_final{ext}"
    
    print(f"\n[🎬] Compositing {len(segment_videos)} overlays onto base video...")
    
    # Build FFmpeg complex filter
    ffmpeg_cmd = ["ffmpeg", "-y", "-i", video_path]
    for seg_vid in segment_videos:
        ffmpeg_cmd.extend(["-i", seg_vid["path"]])
        
    filter_complex = ""
    # Base video is [0:v]
    last_overlay = "[0:v]"
    
    for i, seg_vid in enumerate(segment_videos):
        input_idx = i + 1
        start_ms = int(seg_vid["start"] * 1000)
        # We need to setpts for the overlay video to delay it to the exact start time
        # Overlay the delayed stream over the current base
        next_overlay = f"[v{i+1}]"
        
        # 1. Scale to match base video, then delay the overlay's presentation timestamp
        filter_complex += f"[{input_idx}:v]scale={base_w}:{base_h},setpts=PTS-STARTPTS+{seg_vid['start']}/TB[delay{i}];"
        
        # 2. Composite it with `enable` to ensure it disappears exactly when the segment ends.
        # This prevents the final frame of the animation from freezing over the rest of the video.
        filter_complex += f"{last_overlay}[delay{i}]overlay=enable='between(t,{seg_vid['start']},{seg_vid['end']})'[v{i+1}];"
        last_overlay = next_overlay
        
    # --- AUDIO MIXING ---
    amix_inputs = []
    if base_has_audio:
        filter_complex += "[0:a]anull[a0];"
        amix_inputs.append("[a0]")
        
    for i, seg_vid in enumerate(segment_videos):
        if seg_vid.get("has_audio"):
            input_idx = i + 1
            start_ms = int(seg_vid["start"] * 1000)
            # adelay requires a delay for each channel. We provide two pipes to cover stereo.
            filter_complex += f"[{input_idx}:a]adelay={start_ms}|{start_ms}[a{input_idx}];"
            amix_inputs.append(f"[a{input_idx}]")
            
    if amix_inputs:
        if len(amix_inputs) > 1:
            mix_str = "".join(amix_inputs)
            filter_complex += f"{mix_str}amix=inputs={len(amix_inputs)}:duration=longest:normalize=0[aout];"
            last_audio = "[aout]"
        else:
            last_audio = amix_inputs[0]
    else:
        last_audio = None
        
    # Remove the trailing semicolon
    filter_complex = filter_complex.rstrip(";")
    
    ffmpeg_cmd.extend([
        "-filter_complex", filter_complex,
        "-map", last_overlay
    ])
    
    if last_audio:
        ffmpeg_cmd.extend(["-map", last_audio])
        
    ffmpeg_cmd.extend([
        "-c:v", "h264_nvenc",
        "-preset", "p4",
        "-cq", "18",
        "-c:a", "aac",
        "-b:a", "192k",
        final_output
    ])
    
    print(f"[⚙️] Running final FFmpeg merge...")
    try:
        subprocess.run(ffmpeg_cmd, check=True)
        print(f"\n[✅] Basic Batch Render Complete: {final_output}")
        
        # Step 3: Apply cinematic transitions if requested
        transitions = options.get("transitions", [])
        if transitions:
            try:
                print(f"[⚙️] Executing Cinematic 'Flash' Transitions...")
                from pipeline import stage_scene_transitions
                
                # Format transition times to match what pipeline.py expects: [{"timestamp": t}]
                # Note: stage_scene_transitions skips the 0.0 timestamp cut, so we prepend a dummy 0.0
                timelineScenes = [{"timestamp": 0.0}] + [{"timestamp": float(t)} for t in transitions]
                
                transition_options = {"timelineScenes": timelineScenes}
                
                # Apply the transitions directly onto the final output video
                final_output = stage_scene_transitions(final_output, transition_options)
                
            except Exception as e:
                print(f"[❌] Error applying cinematic transitions: {e}")
                
        print(f"\n[🚀] Final Video Available At: {final_output}")
    except subprocess.CalledProcessError as e:
        print(f"\n[❌] FFmpeg merge failed with error code {e.returncode}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("[❌] Missing options JSON")
        sys.exit(1)

    options_json_arg = sys.argv[1]
    
    if options_json_arg.endswith('.json') and os.path.exists(options_json_arg):
        with open(options_json_arg, 'r', encoding='utf-8') as f:
            options_json_arg = f.read()
    
    try:
        options = json.loads(options_json_arg)
    except json.JSONDecodeError:
        print("[❌] Invalid JSON provided")
        sys.exit(1)

    action = options.get("action", "generate")
    
    if action == "generate":
        generate_code(options)
    elif action == "render":
        render_pipeline(options)
    else:
        print(f"[❌] Unknown action: {action}")
        sys.exit(1)
