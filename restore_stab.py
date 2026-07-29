import re

with open(r'old_stab_full.txt', 'r', encoding='utf-8') as f:
    old_code = f.read()
    
# Clean up the weird console encoding characters from old_stab_full.txt
old_code = old_code.replace('ΓÜÖ∩╕Å', '⚙️').replace('ΓÜá∩╕Å', '⚠️').replace('Γ£à', '✅').replace('Γ¥î', '❌')
old_code = re.sub(r'ΓöÇ+', '─', old_code)

# We want to insert is_motion_tracking support right after smoothed_y = gaussian_filter1d(...)
insert_target = '''        smoothed_y = gaussian_filter1d(trajectory_y, sigma=sigma_val, mode="nearest")

        shift_x = trajectory_x - smoothed_x
        shift_y = trajectory_y - smoothed_y'''

new_tracking_block = '''        smoothed_y = gaussian_filter1d(trajectory_y, sigma=sigma_val, mode="nearest")

        is_motion_tracking = options.get("motionTracking", False)
        if is_motion_tracking:
            print("[⚙️] Pass 3b: Calculating dynamic motion tracking trajectory...")
            lag_sigma = 45.0
            tracking_x = gaussian_filter1d(trajectory_x, sigma=lag_sigma, mode="nearest")
            tracking_y = gaussian_filter1d(trajectory_y, sigma=lag_sigma, mode="nearest")
            
            initial_x = np.nanmedian(trajectory_x[:30]) if len(trajectory_x) > 30 else trajectory_x[0]
            initial_y = np.nanmedian(trajectory_y[:30]) if len(trajectory_y) > 30 else trajectory_y[0]
            
            t = np.arange(len(trajectory_x))
            sway_x = np.sin(t * 0.04) * (width * 0.015)
            sway_y = np.cos(t * 0.033) * (height * 0.015)
            
            shift_x = tracking_x - initial_x + sway_x
            shift_y = tracking_y - initial_y + sway_y
            
            zoom_scale = 1.16
        else:
            shift_x = trajectory_x - smoothed_x
            shift_y = trajectory_y - smoothed_y
            zoom_scale = float(options.get("zoomScale", 1.03))'''

old_code = old_code.replace(insert_target, new_tracking_block)

# Also remove the hardcoded zoom_scale = float(options.get("zoomScale", 1.03)) further down
old_code = old_code.replace('        zoom_scale = float(options.get("zoomScale", 1.03))\n', '')

# Remove the bottom separation blocks carefully so we don't truncate the function
old_code = old_code.split('# AI IMAGE ENHANCER')[0]
# Clean up lines before AI IMAGE ENHANCER
lines = old_code.split('\n')
clean_lines = []
for line in lines:
    if line.startswith('# ──') and len(line) > 10 and 'Load MediaPipe' not in line:
        continue
    clean_lines.append(line)
old_code = '\n'.join(clean_lines).strip() + '\n\n'

with open(r'ai_engine\pipeline.py', 'r', encoding='utf-8') as f:
    pipeline = f.read()

start_idx = pipeline.find('def stage_fast_stabilize')
end_idx = pipeline.find('def stage_enhance_ai_image', start_idx)

if start_idx != -1 and end_idx != -1:
    pipeline = pipeline[:start_idx] + old_code + pipeline[end_idx:]
    with open(r'ai_engine\pipeline.py', 'w', encoding='utf-8') as f:
        f.write(pipeline)
    print("Successfully restored old stabilizer and injected motion tracking!")
else:
    print("Could not find insertion points")
