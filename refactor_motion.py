with open(r'ai_engine\pipeline.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Remove is_motion_tracking block from stage_fast_stabilize
start_tracking = content.find('        is_motion_tracking = options.get("motionTracking", False)')
end_tracking = content.find('            zoom_scale = float(options.get("zoomScale", 1.03))') + len('            zoom_scale = float(options.get("zoomScale", 1.03))')

if start_tracking != -1 and end_tracking != -1:
    old_tracking_code = content[start_tracking:end_tracking]
    replacement = '''        shift_x = trajectory_x - smoothed_x
        shift_y = trajectory_y - smoothed_y
        
        max_shift_px = float(options.get("maxCorrectionPx", 12.0))
        shift_x = _soft_clip(shift_x, max_shift_px)
        shift_y = _soft_clip(shift_y, max_shift_px)
        zoom_scale = float(options.get("zoomScale", 1.03))'''
    content = content.replace(old_tracking_code, replacement)

# 2. Add stage_camera_motion
new_stage = '''
def stage_camera_motion(video_path: str, options: dict) -> str:
    print("[⚙️] Applying cinematic handheld camera motion to composite...")
    import cv2
    import numpy as np
    import os
    import subprocess
    
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    output_vid = os.path.splitext(video_path)[0] + "_motion.mp4"
    
    cmd = [
        "ffmpeg", "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{width}x{height}", "-pix_fmt", "bgr24", "-r", str(fps), "-i", "-",
        "-i", video_path, "-map", "0:v:0", "-map", "1:a:0?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "copy", output_vid
    ]
    
    process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    zoom_scale = 1.05
    frame_idx = 0
    
    while True:
        ret, frame = cap.read()
        if not ret: break
        
        sway_x = np.sin(frame_idx * 0.04) * (width * 0.015)
        sway_y = np.cos(frame_idx * 0.033) * (height * 0.015)
        
        M = np.float32([
            [zoom_scale, 0, -sway_x + (width * (1 - zoom_scale) / 2)],
            [0, zoom_scale, -sway_y + (height * (1 - zoom_scale) / 2)]
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
    return output_vid
'''

insert_point = content.find('def stage_composite_sandwich')
if insert_point != -1:
    content = content[:insert_point] + new_stage + content[insert_point:]

# 3. Add to orchestration
orchestration_insert = content.find('    if options.get("cinematicColor"):')
if orchestration_insert != -1:
    orchestration_logic = '''    if options.get("motionTracking"):
        current_video = stage_camera_motion(current_video, options)

'''
    content = content[:orchestration_insert] + orchestration_logic + content[orchestration_insert:]

with open(r'ai_engine\pipeline.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Pipeline modified!")
