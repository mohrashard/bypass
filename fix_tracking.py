with open(r'ai_engine\pipeline.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: M22 4K Rescue optimization
old_m22 = '''        filter_chain = (
            "hqdn3d=4.0:3.0:6.0:4.5,"
            "eq=contrast=1.08:saturation=1.15:gamma=1.05,"
            "unsharp=5:5:1.2:3:3:0.0,"
            "scale='if(gt(iw,ih),3840,-2)':'if(gt(iw,ih),-2,3840)':flags=lanczos"
        )'''
new_m22 = '''        filter_chain = (
            "hqdn3d=3.0:2.0:4.0:3.0,"
            "eq=contrast=1.08:saturation=1.15:gamma=1.05,"
            "unsharp=5:5:1.0:3:3:0.0,"
            "scale='if(gt(iw,ih),1920,-2)':'if(gt(iw,ih),-2,1920)':flags=bicubic"
        )'''
content = content.replace(old_m22, new_m22)

# Fix NVENC usage in stage_cinematic_grade
old_ffmpeg_grade = '''        subprocess.run([
            "ffmpeg", "-i", video_path,
            "-vf", filter_chain,
            "-c:v", "libx264", "-preset", "fast", "-crf", "16",'''
new_ffmpeg_grade = '''        subprocess.run([
            "ffmpeg", "-i", video_path,
            "-vf", filter_chain,
            "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "18", "-b:v", "0",'''
content = content.replace(old_ffmpeg_grade, new_ffmpeg_grade)


# Fix 2: Motion Tracking in stage_fast_stabilize
import numpy as np

start_idx = content.find('shift_x = trajectory_x - smoothed_x')
end_idx = content.find('print("[⚙️] Pass 4: Rendering smooth frames via FFmpeg pipe...")', start_idx)

original_shift = content[start_idx:end_idx]

new_shift = '''        is_motion_tracking = options.get("motionTracking", False)
        
        if is_motion_tracking:
            print("[⚙️] Pass 3b: Calculating dynamic motion tracking trajectory...")
            # For motion tracking, camera chases the smoothed face
            initial_x = np.nanmedian(trajectory_x[:30]) if len(trajectory_x) > 30 else trajectory_x[0]
            initial_y = np.nanmedian(trajectory_y[:30]) if len(trajectory_y) > 30 else trajectory_y[0]
            
            shift_x = smoothed_x - initial_x
            shift_y = smoothed_y - initial_y
            
            # Allow larger shifts, but clamp smoothly
            max_shift_px = float(width * 0.08) # 8% of width
            shift_x = _soft_clip(shift_x, max_shift_px)
            shift_y = _soft_clip(shift_y, max_shift_px)
        else:
            print("[⚙️] Pass 3b: Clamping correction magnitude...")
            shift_x = trajectory_x - smoothed_x
            shift_y = trajectory_y - smoothed_y
            
            max_shift_px = float(options.get("maxCorrectionPx", 12.0))
            shift_x = _soft_clip(shift_x, max_shift_px)
            shift_y = _soft_clip(shift_y, max_shift_px)
        
'''
content = content[:start_idx] + new_shift + content[end_idx:]

# Ensure zoom scale is larger for motion tracking
zoom_start = content.find('zoom_scale = float(options.get("zoomScale", 1.03))')
zoom_end = zoom_start + len('zoom_scale = float(options.get("zoomScale", 1.03))')
content = content[:zoom_start] + 'zoom_scale = 1.12 if is_motion_tracking else float(options.get("zoomScale", 1.03))' + content[zoom_end:]

# Use nvenc for stabilization to be faster too
stab_ff_start = content.find('''            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",''')
stab_ff_end = stab_ff_start + len('''            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",''')
if stab_ff_start != -1:
    content = content[:stab_ff_start] + '''            "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "18", "-b:v", "0", "-pix_fmt", "yuv420p",''' + content[stab_ff_end:]

with open(r'ai_engine\pipeline.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Success!')
