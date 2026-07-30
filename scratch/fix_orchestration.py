with open('ai_engine/pipeline.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Find the broken run_pipeline orchestration area
# It starts at the garbled comment around line 3672 and goes to if __name__
garbled_start = content.find('\n# ???????????????????????????????????????????????????    current_video = video_path')
if garbled_start == -1:
    garbled_start = content.find('\n    current_video = video_path\n\n    # 1. Fast Stabilize')
    if garbled_start == -1:
        print("ERROR: Could not find corruption marker. Searching differently...")
        idx = content.find('stage_dynamic_background_fx')
        if idx != -1:
            garbled_start = content.rfind('\n', 0, idx - 300)
            print(f"Found via stage_dynamic_background_fx, start at char {garbled_start}")

garbled_end = content.find('\nif __name__')

print(f"Replacing chars {garbled_start} to {garbled_end}")

# The correct orchestration to inject
correct_orchestration = '''
def run_pipeline(video_path: str, options_json: str) -> None:
    import json as _json
    options = _json.loads(options_json)
    print(f"\\n[\\U0001f3ac] STARTING LOCAL RENDER ENGINE: {os.path.basename(video_path)}\\n")

    if not os.path.exists(video_path):
        print(f"[\\u274c] FATAL: Input file not found: {video_path}")
        print("Please re-select the file in the UI.")
        return

    if options.get("enhanceAiImage"):
        print("\\n[\\U0001f3ac] RUNNING AI IMAGE ENHANCEMENT...")
        result = stage_enhance_ai_image(video_path)
        print(f"\\n[\\U0001f680] PIPELINE COMPLETE. Final output: {result}")
        return

    if options.get("generatePromptOnly"):
        print("\\n[\\U0001f3ac] GENERATING SMART PROMPT...")
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
4. NUMBER FORMATTING: Convert all spoken numbers into actual digits (e.g., "\\u0dbb\\u0dd4\\u0db4\\u0dd2\\u0dba\\u0dbd\\u0ec0 5000").
5. SLANG CORRECTION: Fix casual Singlish slang ONLY IF it matches the audio timing.
6. KEYWORDS: Professional field engineer, commission, field engineer, direct, scam, skill, follow, comment, \\u0db6\\u0dcf\\u0dc3\\u0dca.
7. NO GRAMMAR/PUNCTUATION (CRITICAL): Do absolutely NOT use periods (.), commas (,), or question marks (?) anywhere in your text.
8. THE DIRECTOR\'S CUT (CRITICAL): Place a pipe symbol "|" at the end of a phrase ONLY at key narrative beats.
   DO NOT exceed 8 pipes in total.

You must provide the approximate start and end times for each phrase in seconds.
Output strictly as a JSON array.
Do not include any markdown formatting. Just the raw JSON array."""

        print("[PROMPT_START]")
        print(prompt)
        print("[PROMPT_END]")
        if os.path.exists(temp_audio): os.remove(temp_audio)
        return

    # ─── MAIN PIPELINE SEQUENCE ───────────────────────────────────────────────
    # Stage order is CRITICAL. Do not change without understanding dependencies.
    current_video = video_path

    # STEP 1: Stabilize FIRST on raw footage (before cuts/audio changes)
    if options.get("stabilizerEngine") or options.get("motionTracking"):
        current_video = stage_fast_stabilize(current_video, options)

    # STEP 2: Merge Studio Audio
    if options.get("mergeEngine"):
        current_video = stage_merge_audio(current_video, options)

    # STEP 3: Remove Dead Air / Jump Cuts
    if options.get("removeSilence"):
        current_video = stage_remove_silence(current_video, options)

    # STEP 4: Background FX (green screen key, background image, sandwich text)
    if options.get("blurBackground"):
        current_video = stage_background_fx(current_video, options)

    # STEP 5: Semantic Smart Zoom
    if options.get("autoZoom"):
        current_video = stage_semantic_zoom(current_video, options)

    # STEP 6: Color Grading (applies globally to composited shot)
    if options.get("cinematicColor"):
        current_video = stage_cinematic_color(current_video, options)

    if options.get("cinematicGrade") and options.get("cinematicGrade") != "none":
        current_video = stage_cinematic_grade(current_video, options)

    # STEP 7: Bottom Glow (after grade, so it blends seamlessly)
    if options.get("bottomGlow"):
        color = options.get("glowColor", "#000000")
        current_video = stage_bottom_glow(current_video, color)

    # STEP 8: Hook Engine (text interrupts, starting hook)
    if options.get("hookEngine"):
        if options.get("startingHook") and options.get("startingHook") != "none":
            current_video = stage_starting_hook(current_video, options)
        if options.get("hookPrimaryText") or options.get("hookSecondaryText"):
            current_video = stage_visual_hook(current_video, options)

    # STEP 9: AI B-Roll
    if options.get("aiBroll"):
        current_video = stage_ai_broll(current_video, options)

    # STEP 10: Studio Audio Enhancement / MP3 Export
    if options.get("studioAudio"):
        current_video = stage_studio_audio(current_video)

    if options.get("extractMp3"):
        current_video = stage_mp4_to_mp3(current_video, options)

    # STEP 11: Beauty Filter
    if options.get("applyBeautyFilter"):
        current_video = stage_beauty_filter(current_video, options)

    # STEP 12: Captions
    if options.get("burnCaptions"):
        if options.get("captionLanguage") == "si":
            current_video = stage_burn_sinhala_captions(current_video, options)
        else:
            current_video = stage_burn_captions(current_video, options)

    # STEP 13: Auto Transitions / Camera Flashes
    if options.get("autoTransitions"):
        current_video = stage_hardcode_flash(current_video, options)

    # STEP 14: Export Caption Overlay JSON
    if options.get("exportCaptionOverlay"):
        lang = options.get("captionLanguage", "en")
        if lang == "si":
            export_captions_overlay_si(current_video, options)
        else:
            export_captions_overlay_en(current_video, options)

    print(f"\\n[\\U0001f680] PIPELINE COMPLETE. Final output: {current_video}")

'''

before = content[:garbled_start]
fixed = before + correct_orchestration

with open('ai_engine/pipeline.py', 'w', encoding='utf-8') as f:
    f.write(fixed)

print(f"Done. New length: {len(fixed)} chars")
