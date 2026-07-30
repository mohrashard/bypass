import sys
content = open('c:\\Projects\\capcut-bypass\\ai_engine\\pipeline.py', 'r', encoding='utf-8').read()

if '    # ─── MAIN PIPELINE SEQUENCE ───────────────────────────────────────────────' in content:
    idx = content.find('    # ─── MAIN PIPELINE SEQUENCE ───────────────────────────────────────────────')
    top = content[:idx]
    
    new_pipeline = '''    # ─── MAIN PIPELINE SEQUENCE ───────────────────────────────────────────────
    current_video = video_path

    # PHASE 1: MERGE, CLEAN, AND STABILIZE
    if options.get("stabilizerEngine"):
        current_video = stage_fast_stabilize(current_video, options)

    if options.get("mergeEngine"):
        current_video = stage_merge_audio(current_video, options)

    # PHASE 2: APPLY BG, SANDWICH TEXTS ETC. (Output to timeline)
    if options.get("blurBackground"):
        current_video = stage_background_fx(current_video, options)

    if options.get("hookEngine"):
        if options.get("startingHook") and options.get("startingHook") != "none":
            current_video = stage_starting_hook(current_video, options)
        if options.get("hookPrimaryText") or options.get("hookSecondaryText"):
            current_video = stage_visual_hook(current_video, options)

    if options.get("aiBroll"):
        current_video = stage_ai_broll(current_video, options)

    if options.get("applyBeautyFilter"):
        current_video = stage_beauty_filter(current_video, options)

    if options.get("studioAudio"):
        current_video = stage_studio_audio(current_video)

    if options.get("extractMp3"):
        current_video = stage_mp4_to_mp3(current_video, options)

    # PHASE 3: COLOR GRADE & BOTTOM GLOW
    if options.get("cinematicColor"):
        current_video = stage_cinematic_color(current_video, options)
    if options.get("cinematicGrade") and options.get("cinematicGrade") != "none":
        current_video = stage_cinematic_grade(current_video, options)

    if options.get("bottomGlow"):
        color = options.get("glowColor", "#000000")
        current_video = stage_bottom_glow(current_video, color)

    # PHASE 4: CHOP -> THEN TRANSCRIBE AND APPLY CAPTION
    if options.get("removeSilence"):
        current_video = stage_remove_silence(current_video, options)

    if options.get("burnCaptions"):
        if options.get("captionLanguage") == "si":
            current_video = stage_burn_sinhala_captions(current_video, options)
        else:
            current_video = stage_burn_captions(current_video, options)

    # PHASE 5: TRANSITIONS
    if options.get("autoTransitions"):
        current_video = stage_scene_transitions(current_video, options)

    if options.get("motionTracking"):
        current_video = stage_global_motion_tracking(current_video, options)

    print(f"\\n[🚀] PIPELINE COMPLETE. Final output: {current_video}")
    return current_video

'''
    
    bottom_idx = content.find('if __name__ == "__main__":', idx)
    
    if bottom_idx != -1:
        final_content = top + new_pipeline + content[bottom_idx:]
        open('c:\\Projects\\capcut-bypass\\ai_engine\\pipeline.py', 'w', encoding='utf-8').write(final_content)
        print('Pipeline reordered successfully.')
    else:
        print('Could not find main block.')
else:
    print('Could not find pipeline sequence.')
