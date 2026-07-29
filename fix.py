import re
with open(r'ai_engine\pipeline.py', 'r', encoding='utf-8') as f:
    content = f.read()

start_idx = content.find('def stage_dynamic_background_fx(video_path: str, options: dict) -> str:')
end_idx = content.find('def stage_composite_sandwich', start_idx)

original_func = content[start_idx:end_idx]

# We need to change w, h to out_w, out_h
new_func = original_func.replace(
'''    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))''',
'''    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # Nexus Engine always outputs 9:16 vertical for Shorts/TikTok
    out_w, out_h = 1080, 1920
    base_scale = max(out_w / w, out_h / h)
    options['_base_preview_scale'] = base_scale # Save for compositing stage''')

new_func = new_func.replace(
'''                img = cv2.imread(p)
                bg_images.append(cv2.resize(img, (int(w * 1.1), int(h * 1.1))))''',
'''                img = cv2.imread(p)
                if img is not None:
                    bg_images.append(img)''')

new_func = new_func.replace(
'''            bg_images = [np.zeros((int(h * 1.1), int(w * 1.1), 3), dtype=np.uint8)]''',
'''            bg_images = [np.zeros((out_h, out_w, 3), dtype=np.uint8)]''')

new_func = new_func.replace(
'''                scene_texts.append({
                "text": s.get("textBehind", ""),
                "y": float(s.get("textY", 50.0)),
                "size": float(s.get("textSize", 100.0))
            })''',
'''                scene_texts.append({
                "text": s.get("textBehind", ""),
                "y": float(s.get("textY", 50.0)),
                "size": float(s.get("textSize", 100.0)),
                "bgScale": float(s.get("bgScale", 100.0))
            })''')

new_func = new_func.replace(
'''        if not scene_texts:
            scene_texts = [{"text": "", "y": 50.0, "size": 100.0}] * len(bg_images)''',
'''        if not scene_texts:
            scene_texts = [{"text": "", "y": 50.0, "size": 100.0, "bgScale": 100.0}] * len(bg_images)''')

new_func = new_func.replace(
'''    bg_out = cv2.VideoWriter(output_vid, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))''',
'''    bg_out = cv2.VideoWriter(output_vid, cv2.VideoWriter_fourcc(*'mp4v'), fps, (out_w, out_h))''')

new_func = new_func.replace(
'''        base_img = bg_images[bg_idx]
        if drift:
            bg_frame = apply_parallax_drift(base_img, scene_progress, scale_dir=-1, pan_dir=-1)
        else:
            bg_frame = cv2.resize(base_img, (w, h))''',
'''        base_img = bg_images[bg_idx]
        bg_scale = scene_texts[bg_idx]["bgScale"] / 100.0 if bg_idx < len(scene_texts) else 1.0
        
        # Scale to cover target out_w, out_h
        img_h, img_w = base_img.shape[:2]
        scale = max(out_w / img_w, out_h / img_h) * bg_scale
        new_w, new_h = max(out_w, int(img_w * scale)), max(out_h, int(img_h * scale))
        resized = cv2.resize(base_img, (new_w, new_h))
        
        # Center crop
        start_y = (new_h - out_h) // 2
        start_x = (new_w - out_w) // 2
        bg_frame = resized[start_y:start_y+out_h, start_x:start_x+out_w]''')

new_func = new_func.replace(
'''            base_y = int(h * (text_cfg["y"] / 100.0))
            # Slide from off-screen bottom up to the target position
            y_pos = base_y + int((h - base_y + 300) * (1.0 - ease))''',
'''            base_y = int(out_h * (text_cfg["y"] / 100.0))
            y_pos = base_y + int((out_h - base_y + 300) * (1.0 - ease))''')

new_func = new_func.replace(
'''            text_img = Image.new('RGBA', (w, h), (0, 0, 0, 0))''',
'''            text_img = Image.new('RGBA', (out_w, out_h), (0, 0, 0, 0))''')

new_func = new_func.replace(
'''            text_x = (w - text_w) // 2''',
'''            text_x = (out_w - text_w) // 2''')

# Now stage_composite_sandwich
start_idx_sandwich = end_idx
end_idx_sandwich = content.find('def stage_scene_transitions', start_idx_sandwich)
orig_sandwich = content[start_idx_sandwich:end_idx_sandwich]

new_sandwich = orig_sandwich.replace(
'''    fg_filter = f"[1:v]{chroma_filter}[fg_scaled]"
    overlay_cmd = "overlay=(W-w)/2:H-h:shortest=1,format=yuv420p"
    
    filter_complex = f"[0:v]scale=iw:ih[bg];{fg_filter};[bg][fg_scaled]{overlay_cmd}[outv]"''',
'''    sub_scale = 100.0
    sub_y = 0.0
    if options.get("timelineScenes") and len(options.get("timelineScenes")) > 0:
        sub_scale = float(options["timelineScenes"][0].get("subjectScale", 100.0))
        sub_y = float(options["timelineScenes"][0].get("subjectY", 0.0))
    else:
        sub_scale = float(options.get("subjectScale", 100.0))
        sub_y = float(options.get("subjectY", 0.0))
        
    base_scale = options.get('_base_preview_scale', 1.0)
    final_scale = base_scale * (sub_scale / 100.0)
    
    fg_filter = f"[1:v]{chroma_filter}[fg_keyed];[fg_keyed]scale=iw*{final_scale}:ih*{final_scale}[fg_scaled]"
    
    y_offset = f"+(H*{sub_y}/100)" if sub_y != 0 else ""
    overlay_cmd = f"overlay=(W-w)/2:H-h{y_offset}:shortest=1,format=yuv420p"
    
    filter_complex = f"[0:v]scale=iw:ih[bg];{fg_filter};[bg][fg_scaled]{overlay_cmd}[outv]"''')

new_sandwich = new_sandwich.replace(
'''    fg_filter = f"[0:v]{chroma_filter}[fg_scaled]"
    overlay_cmd = "overlay=(W-w)/2:H-h:shortest=1,format=yuv420p"''',
'''    sub_scale = 100.0
    sub_y = 0.0
    if options.get("timelineScenes") and len(options.get("timelineScenes")) > 0:
        sub_scale = float(options["timelineScenes"][0].get("subjectScale", 100.0))
        sub_y = float(options["timelineScenes"][0].get("subjectY", 0.0))
    else:
        sub_scale = float(options.get("subjectScale", 100.0))
        sub_y = float(options.get("subjectY", 0.0))
        
    base_scale = options.get('_base_preview_scale', 1.0)
    final_scale = base_scale * (sub_scale / 100.0)
    
    fg_filter = f"[0:v]{chroma_filter}[fg_keyed];[fg_keyed]scale=iw*{final_scale}:ih*{final_scale}[fg_scaled]"
    
    y_offset = f"+(H*{sub_y}/100)" if sub_y != 0 else ""
    overlay_cmd = f"overlay=(W-w)/2:H-h{y_offset}:shortest=1,format=yuv420p"''')

content = content[:start_idx] + new_func + new_sandwich + content[end_idx_sandwich:]

with open(r'ai_engine\pipeline.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Success!')
