import sys
content = open('c:\\Projects\\capcut-bypass\\ai_engine\\pipeline.py', 'r', encoding='utf-8').read()

idx = content.find('            print("[⚠️] N    # ─── MAIN PIPELINE SEQUENCE ───────────────────────────────────────────────')

if idx != -1:
    top = content[:idx]
    
    missing_code = '''            print("[⚠️] No face detected. Cannot anchor-stabilize. Falling back to original.")
            return video_path

        trajectory_x = np.array(raw_x, dtype=np.float64)
        trajectory_y = np.array(raw_y, dtype=np.float64)

        print("[⚙️] Pass 1b: Interpolating dropped-detection gaps...")
        trajectory_x = _interpolate_nans(trajectory_x)
        trajectory_y = _interpolate_nans(trajectory_y)

        print("[⚙️] Pass 2: Median pre-filter to strip outlier spikes...")
        # A short median filter removes single/double-frame outliers (blinks,
        # partial occlusion, brief misdetection) WITHOUT smearing real motion,
        # unlike the gaussian which just blends outliers into the trajectory.
        median_k = int(options.get("medianKernel", 5))
        if median_k % 2 == 0:
            median_k += 1
        trajectory_x = median_filter(trajectory_x, size=median_k, mode="nearest")
        trajectory_y = median_filter(trajectory_y, size=median_k, mode="nearest")

        print("[⚙️] Pass 3: Applying low-pass filter to isolate real (slow) motion...")
        sigma_val = float(options.get("vibrationFilterStrength", 8.0))
        smoothed_x = gaussian_filter1d(trajectory_x, sigma=sigma_val, mode="nearest")
        smoothed_y = gaussian_filter1d(trajectory_y, sigma=sigma_val, mode="nearest")

        shift_x = trajectory_x - smoothed_x
        shift_y = trajectory_y - smoothed_y

        print("[⚙️] Pass 3b: Clamping correction magnitude...")
        # If a correction is asking for a huge shift, it's not "shake" -
        # it's either a genuine fast head movement or a leftover detection
        # glitch. Either way, over-correcting it is what produces the
        # "too much shake" feeling. Clamp + soft-taper instead of hard cut,
        # so we don't introduce a new discontinuity.
        max_shift_px = float(options.get("maxCorrectionPx", 12.0)) # Reduced to 3.0 to prevent tugging
        shift_x = _soft_clip(shift_x, max_shift_px)
        shift_y = _soft_clip(shift_y, max_shift_px)
        
        print("[⚙️] Pass 4: Rendering smooth frames via FFmpeg pipe...")
        cmd = [
            "ffmpeg", "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
            "-s", f"{width}x{height}", "-pix_fmt", "bgr24", "-r", str(fps), "-i", "-",
            "-i", video_path, "-map", "0:v:0", "-map", "1:a:0?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "copy", output_vid
        ]

        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cap = cv2.VideoCapture(video_path)

        zoom_scale = float(options.get("zoomScale", 1.03))

        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            dx = shift_x[frame_idx]
            dy = shift_y[frame_idx]

            M = np.float32([
                [zoom_scale, 0, -dx + (width * (1 - zoom_scale) / 2)],
                [0, zoom_scale, -dy + (height * (1 - zoom_scale) / 2)]
            ])

            stabilized_frame = cv2.warpAffine(
                frame, M, (width, height),
                flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT
            )

            process.stdin.write(stabilized_frame.tobytes())
            frame_idx += 1

        cap.release()
        process.stdin.close()
        process.wait()

        print(f"[✅] AI Anchor Stabilization complete (multi-point, interpolated, no spikes): {output_vid}")
        return output_vid

    except Exception as e:
        err_msg = str(e)
        print(f"[❌] AI Anchor Stabilization failed: {err_msg}")
        # If it fails, return the original video path so the pipeline doesn't break
        return video_path

# ─────────────────────────────────────────────
# 19. MAIN PIPELINE ORCHESTRATOR
# ─────────────────────────────────────────────
def stage_global_motion_tracking(video_path: str, options: dict) -> str:
    # FUNCTION REMOVED AS PER LEGACY REQUEST
    return video_path

def run_pipeline(video_path: str, options_json: str) -> None:
    import json as _json
    options = _json.loads(options_json)
    print(f"\\n[🎬] STARTING LOCAL RENDER ENGINE: {os.path.basename(video_path)}\\n")

    if not os.path.exists(video_path):
        print(f"[❌] FATAL: Input file not found: {video_path}")
        print("Please re-select the file in the UI.")
        return

    if options.get("enhanceAiImage"):
        print("\\n[🎬] RUNNING AI IMAGE ENHANCEMENT...")
        result = stage_enhance_ai_image(video_path)
        print(f"\\n[🚀] PIPELINE COMPLETE. Final output: {result}")
        return

    if options.get("generatePromptOnly"):
        print("\\n[🎬] GENERATING SMART PROMPT...")
        import subprocess as _sp
        base_dir = os.path.dirname(os.path.abspath(video_path))
        temp_audio = os.path.join(base_dir, "_gemini_audio.wav")
        _sp.run(["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", temp_audio, "-y"], check=True, capture_output=True)
        try:
            probe_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", temp_audio]
            dur_out = _sp.check_output(probe_cmd, text=True).strip()
            audio_dur = float(dur_out)
            duration_text = f"The total length of this audio is exactly {audio_dur:.2f} seconds. Your timestamps MUST NOT exceed this duration."
        except Exception:
            duration_text = "Pay close attention to the length of the audio."

        prompt = f"""Listen to this audio. It is a mix of Sinhala and English (Singlish).
Write down EXACTLY what is said, verbatim.

IMPORTANT CONTEXT: {duration_text}

CRITICAL RULES: 
1. DO NOT add words. DO NOT guess words. DO NOT fix broken sentences. If the audio mumbles, transcribe the mumble. Strictly stick to the voice.
2. Break the text into short, logical phrases of exactly 3 to 5 words each.
3. TRANSLITERATE ENGLISH: If an English technical word is spoken, type it in English letters (e.g., "AC", "pipe", "commission" , "Grab Me"). 
4. NUMBER FORMATTING: Convert all spoken numbers into actual digits (e.g., "රුපියලෙ 5000").
5. SLANG CORRECTION: Fix casual Singlish slang ONLY IF it matches the audio timing.
6. KEYWORDS: Professional field engineer, commission, field engineer, direct, scam, skill, follow, comment, බාස්.
7. NO GRAMMAR/PUNCTUATION (CRITICAL): Do absolutely NOT use periods (.), commas (,), or question marks (?) anywhere in your text.
8. THE DIRECTOR'S CUT (CRITICAL - DO NOT IGNORE): You MUST place a literal pipe symbol "|" at the end of specific phrases where a visual scene change should occur. 
   - Example: "This is why you need AI automation |"
   - The video editor software literally searches for the "|" character to know when to jump-cut. If you omit it, the video will break. 
   - DO NOT exceed 8 pipes in total.

You must provide the approximate start and end times for each phrase in seconds.
Output strictly as a JSON array.
Do not include any markdown formatting. Just the raw JSON array."""

        print("[PROMPT_START]")
        print(prompt)
        print("[PROMPT_END]")
        if os.path.exists(temp_audio): os.remove(temp_audio)
        return

    # ─── MAIN PIPELINE SEQUENCE ───────────────────────────────────────────────
'''
    
    # We find where the `current_video = video_path` starts to append the rest
    bottom_idx = content.find('    current_video = video_path', idx)
    
    if bottom_idx != -1:
        final_content = top + missing_code + content[bottom_idx:]
        open('c:\\Projects\\capcut-bypass\\ai_engine\\pipeline.py', 'w', encoding='utf-8').write(final_content)
        print('Pipeline repaired successfully.')
    else:
        print('Could not find bottom.')
else:
    print('Could not find corruption.')
