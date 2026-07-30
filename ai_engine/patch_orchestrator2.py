import os
import re

with open('c:/Projects/capcut-bypass/ai_engine/pipeline.py', 'r', encoding='utf-8') as f:
    code = f.read()

run_pipeline_code = '''def run_pipeline(video_path: str, options_json: str) -> None:
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

        prompt = f"""Listen to this audio. It is a mix of Sinhala and English (Singlish).\\nWrite down EXACTLY what is said, verbatim.\\n\\nIMPORTANT CONTEXT: {duration_text}\\n\\nCRITICAL RULES: \\n1. DO NOT add words. DO NOT guess words. DO NOT fix broken sentences. If the audio mumbles, transcribe the mumble. Strictly stick to the voice.\\n2. Break the text into short, logical phrases of exactly 3 to 5 words each.\\n3. TRANSLITERATE ENGLISH: If an English technical word is spoken, type it in English letters (e.g., "AC", "pipe", "commission" , "Grab Me"). \\n4. NUMBER FORMATTING: Convert all spoken numbers into actual digits (e.g., "රුපියලෙ 5000").\\n5. SLANG CORRECTION: Fix casual Singlish slang ONLY IF it matches the audio timing.\\n6. KEYWORDS: Professional field engineer, commission, field engineer, direct, scam, skill, follow, comment, බාස්.\\n7. NO GRAMMAR/PUNCTUATION (CRITICAL): Do absolutely NOT use periods (.), commas (,), or question marks (?) anywhere in your text.\\n8. THE DIRECTOR'S CUT (CRITICAL): Place a pipe symbol "|" at the end of a phrase ONLY at key narrative beats.\\n   DO NOT exceed 8 pipes in total.\\n\\nYou must provide the approximate start and end times for each phrase in seconds.\\nOutput strictly as a JSON array.\\nDo not include any markdown formatting. Just the raw JSON array."""

        print("[PROMPT_START]")
        print(prompt)
        print("[PROMPT_END]")
        if os.path.exists(temp_audio): os.remove(temp_audio)
        return

    # ─── MAIN PIPELINE SEQUENCE ───────────────────────────────────────────────
    current_video = video_path

    # 1. Stabilize (Rigid Anchor on RAW)
    if options.get("stabilizerEngine"):
        current_video = stage_fast_stabilize(current_video, options)

    # 2. Merge Studio Audio
    if options.get("mergeEngine"):
        current_video = stage_merge_audio(current_video, options)

    # 3. Background FX + Sandwich Text (Based on UI Timeline)
    if options.get("blurBackground"):
        current_video = stage_background_fx(current_video, options)

    # 4. Remove Dead Air / Jump Cuts (Chops the composited video!)
    if options.get("removeSilence"):
        current_video = stage_remove_silence(current_video, options)

    # 5. Semantic Smart Zoom
    if options.get("autoZoom"):
        current_video = stage_semantic_zoom(current_video, options)
        
    # 6. Hook Engine
    if options.get("hookEngine"):
        if options.get("startingHook") and options.get("startingHook") != "none":
            current_video = stage_starting_hook(current_video, options)
        if options.get("hookPrimaryText") or options.get("hookSecondaryText"):
            current_video = stage_visual_hook(current_video, options)

    # 7. AI B-Roll
    if options.get("aiBroll"):
        current_video = stage_ai_broll(current_video, options)

    # 8. Studio Audio Enhancement
    if options.get("studioAudio"):
        current_video = stage_studio_audio(current_video)

    if options.get("extractMp3"):
        current_video = stage_mp4_to_mp3(current_video, options)

    # 9. Beauty Filter
    if options.get("applyBeautyFilter"):
        current_video = stage_beauty_filter(current_video, options)

    # 10. Captions (Transcribes the ALREADY chopped video, meaning timestamps map perfectly!)
    if options.get("burnCaptions"):
        if options.get("captionLanguage") == "si":
            current_video = stage_burn_sinhala_captions(current_video, options)
        else:
            current_video = stage_burn_captions(current_video, options)
            
    # 11. Auto Transitions (Elastic Stretch & Flash based on perfectly mapped _flash_times.json)
    if options.get("autoTransitions"):
        current_video = stage_scene_transitions(current_video, options)

    # 12. Global Handheld Motion Tracking (Simulates a human operator on the whole scene)
    if options.get("motionTracking"):
        current_video = stage_global_motion_tracking(current_video, options)

    # 13. Cinematic Color Grade & M22 Rescue
    if options.get("cinematicColor"):
        current_video = stage_cinematic_color(current_video, options)
    if options.get("cinematicGrade") and options.get("cinematicGrade") != "none":
        current_video = stage_cinematic_grade(current_video, options)

    # 14. Bottom Glow
    if options.get("bottomGlow"):
        color = options.get("glowColor", "#000000")
        current_video = stage_bottom_glow(current_video, color)

    print(f"\\n[🚀] PIPELINE COMPLETE. Final output: {current_video}")
'''

# Replace everything from "def run_pipeline" to the end of the file
pattern = r"def run_pipeline\(video_path: str, options_json: str\) -> None:.*"
code = re.sub(pattern, run_pipeline_code, code, flags=re.DOTALL)

global_mt_code = '''def stage_global_motion_tracking(video_path: str, options: dict) -> str:
    # A lightweight wrapper that runs stage_fast_stabilize in motion_tracking mode
    # on the fully composited video to create a cinematic handheld feel.
    print("\\n[🎥] Activating Global Handheld Motion Tracking...")
    mt_options = options.copy()
    mt_options["motionTracking"] = True
    mt_options["zoomScale"] = 1.12 # Zoom slightly to allow sway margin
    return stage_fast_stabilize(video_path, mt_options)

'''
code = code.replace("def run_pipeline(", global_mt_code + "def run_pipeline(")

main_block = '''

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("[X] Usage: python pipeline.py <video_path> <options_json>")
        sys.exit(1)

    video_path_arg   = sys.argv[1]
    options_json_arg = sys.argv[2]

    try:
        run_pipeline(video_path_arg, options_json_arg)
    except Exception as e:
        import traceback
        print(f"[X] PIPELINE CRASHED: {e}")
        traceback.print_exc()
        sys.exit(1)
'''
code += main_block

with open('c:/Projects/capcut-bypass/ai_engine/pipeline.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('SUCCESS')
