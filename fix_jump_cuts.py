with open(r'ai_engine\pipeline.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the block where filtering happens
start_str = '        print("[⚙️] Pass 3: Applying low-pass filter to isolate real (slow) motion...")'
end_str = '        is_motion_tracking = options.get("motionTracking", False)'

if start_str in content and end_str in content:
    start_idx = content.find(start_str)
    end_idx = content.find(end_str)
    
    new_filtering = '''        print("[⚙️] Pass 3: Applying smart segment-aware low-pass filter to isolate real motion...")
        sigma_val = float(options.get("vibrationFilterStrength", 8.0))
        
        def smart_filter(traj, sigma, threshold):
            diffs = np.abs(np.diff(traj))
            cut_indices = np.where(diffs > threshold)[0] + 1
            if len(cut_indices) == 0:
                return gaussian_filter1d(traj, sigma=sigma, mode="nearest")
            segments = np.split(traj, cut_indices)
            return np.concatenate([gaussian_filter1d(seg, sigma=sigma, mode="nearest") for seg in segments if len(seg) > 0])
            
        jump_threshold_x = width * 0.05
        jump_threshold_y = height * 0.05
        
        smoothed_x = smart_filter(trajectory_x, sigma_val, jump_threshold_x)
        smoothed_y = smart_filter(trajectory_y, sigma_val, jump_threshold_y)

'''
    content = content[:start_idx] + new_filtering + content[end_idx:]
    
    # Also fix dynamic motion tracking filtering
    mt_start_str = '            tracking_x = gaussian_filter1d(trajectory_x, sigma=lag_sigma, mode="nearest")'
    mt_end_str = '            initial_x = np.nanmedian(trajectory_x[:30])'
    mt_start_idx = content.find(mt_start_str)
    mt_end_idx = content.find(mt_end_str)
    
    if mt_start_idx != -1 and mt_end_idx != -1:
        new_mt_filtering = '''            tracking_x = smart_filter(trajectory_x, lag_sigma, jump_threshold_x)
            tracking_y = smart_filter(trajectory_y, lag_sigma, jump_threshold_y)
            
'''
        content = content[:mt_start_idx] + new_mt_filtering + content[mt_end_idx:]
        
    with open(r'ai_engine\pipeline.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Jump cut robustness added!")
else:
    print("Could not find blocks")
