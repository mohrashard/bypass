import cv2
import numpy as np
import subprocess
import re
import os

def generate_dynamic_background(video_path, bg_paths, w, h, fps):
    print("Detecting scenes...")
    cmd = ["ffmpeg", "-i", video_path, "-filter:v", "select='gt(scene,0.4)',showinfo", "-f", "null", "-"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    scene_cuts = [float(m) for m in re.findall(r'pts_time:([0-9.]+)', res.stderr)]
    print(f"Detected scenes at: {scene_cuts}")
    
    bg_images = []
    for p in bg_paths:
        img = cv2.imread(p)
        if img is not None:
            bg_images.append(cv2.resize(img, (w, h)))
    
    if not bg_images:
        bg_images = [np.zeros((h, w, 3), dtype=np.uint8)]
        
    unified_bg = "_temp_unified_bg.mp4"
    bg_out = cv2.VideoWriter(unified_bg, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))
    cap_bg = cv2.VideoCapture(video_path)
    
    transition_dur = 0.5
    
    while cap_bg.isOpened():
        ret, _ = cap_bg.read()
        if not ret: break
        
        t = cap_bg.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        
        bg_idx = 0
        active_cut = -1
        
        for cut in scene_cuts:
            if t > cut:
                bg_idx += 1
                active_cut = cut
                
        bg_idx = min(bg_idx, len(bg_images) - 1)
        
        # Check transition
        if active_cut != -1 and (t - active_cut) < transition_dur and bg_idx > 0:
            progress = (t - active_cut) / transition_dur
            img_old = bg_images[bg_idx - 1]
            img_new = bg_images[bg_idx]
            
            frame_composite = np.zeros((h, w, 3), dtype=np.uint8)
            x_offset = int(progress * w)
            if x_offset < w:
                frame_composite[:, 0:(w-x_offset)] = img_old[:, x_offset:w]
                if x_offset > 0:
                    frame_composite[:, (w-x_offset):w] = img_new[:, 0:x_offset]
            else:
                frame_composite = img_new.copy()
                
            pix_factor = 1.0 - abs(progress - 0.5) * 2
            if pix_factor > 0.05:
                block_size = int(pix_factor * 40) + 1
                small = cv2.resize(frame_composite, (w // block_size, h // block_size), interpolation=cv2.INTER_LINEAR)
                frame_composite = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
                
            bg_frame = frame_composite
        else:
            bg_frame = bg_images[bg_idx]
            
        bg_out.write(bg_frame)
        
    cap_bg.release()
    bg_out.release()
    print("Done generating background")

# generate_dynamic_background("test_out.mp4", ["test.jpg", "test_format.jpg"], 1080, 1920, 30.0)
