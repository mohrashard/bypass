import os

with open('c:/Projects/capcut-bypass/ai_engine/pipeline.py', 'r', encoding='utf-8') as f:
    code = f.read()

find_str = '''        audio_idx = num_inputs
        inputs.extend(["-i", temp_audio])

        print(f"[⚙️] Running ultra-fast FFmpeg render pipeline (Multi-Scene + Sandwich) → {out_w}x{out_h}...")
        cmd = [
            "ffmpeg", *inputs,
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", f"{audio_idx}:a?",'''

replace_str = '''        # Standard Swoosh for Text Slide Up Sandwich
        engine_dir = os.path.dirname(os.path.abspath(__file__))
        swoosh_sfx = os.path.join(engine_dir, "assets", "Standard Swoosh.wav")
        swoosh_times = []
        for scene in timeline_scenes:
            if scene.get("textBehind", "").strip():
                swoosh_times.append(float(scene.get("timestamp", 0.0)))

        audio_idx = num_inputs
        inputs.extend(["-i", temp_audio])
        num_inputs += 1
        
        audio_map = f"{audio_idx}:a?"
        
        if os.path.exists(swoosh_sfx) and swoosh_times:
            swoosh_idx = num_inputs
            inputs.extend(["-i", swoosh_sfx])
            num_inputs += 1
            
            filter_complex += f"[{audio_idx}:a]volume=1.0[main_a];"
            mix_inputs = "[main_a]"
            for i, t in enumerate(swoosh_times):
                delay_ms = int(max(0, t) * 1000)
                filter_complex += f"[{swoosh_idx}:a]adelay={delay_ms}|{delay_ms}[swoosh_{i}];"
                mix_inputs += f"[swoosh_{i}]"
            total_audios = len(swoosh_times) + 1
            filter_complex += f"{mix_inputs}amix=inputs={total_audios}:duration=first:dropout_transition=2:normalize=0[mixed_a];"
            audio_map = "[mixed_a]"

        print(f"[⚙️] Running ultra-fast FFmpeg render pipeline (Multi-Scene + Sandwich) → {out_w}x{out_h}...")
        cmd = [
            "ffmpeg", *inputs,
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", audio_map,'''

if find_str in code:
    code = code.replace(find_str, replace_str)
    with open('c:/Projects/capcut-bypass/ai_engine/pipeline.py', 'w', encoding='utf-8') as f:
        f.write(code)
    print('SUCCESS')
else:
    print('COULD NOT FIND STRING')
