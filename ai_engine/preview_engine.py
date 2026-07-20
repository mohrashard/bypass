import sys
import json
import os
import subprocess
import cv2

def log(msg):
    pass

def generate_preview(video_path: str, options_json: str):
    log("=== RUNNING PREVIEW ENGINE ===")
    log(f"Options: {options_json}")
    try:
        options = json.loads(options_json)
    except Exception as e:
        log(f"JSON Parse Error: {e}")
        return
        
    bg_options = options
    mode = bg_options.get("bgMode", "blur")
    hex_color = bg_options.get("bgColor", "#09090b").lstrip('#')
    bg_image_path = bg_options.get("bgImagePath", "")
    keying_mode = bg_options.get("keyingMode", "ai")
    
    bg_scale = int(bg_options.get("bgScale", 100))
    sub_scale = int(bg_options.get("subjectScale", 100))
    sub_y = int(bg_options.get("subjectY", 0))

    base_dir = os.path.dirname(os.path.abspath(video_path))
    preview_img = os.path.join(base_dir, "_live_preview.jpg")

    cap = cv2.VideoCapture(video_path)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    
    if os.path.exists(preview_img): 
        os.remove(preview_img)
        log("Deleted old preview image.")
    
    log(f"Keying Mode: {keying_mode}, BG Mode: {mode}, BG Path: {bg_image_path}")
    
    if keying_mode == "chroma":
        chroma_filter = "chromakey=0x1A9535:0.11:0.02,despill=green"
        sub_w = int(w * sub_scale / 100)
        sub_h = int(h * sub_scale / 100)
        sub_w = sub_w if sub_w % 2 == 0 else sub_w + 1
        sub_h = sub_h if sub_h % 2 == 0 else sub_h + 1
        
        fg_filter = f"[0:v]{chroma_filter}[fg];[fg]scale={sub_w}:{sub_h}[fg_scaled]"
        y_offset = f"+(H*{sub_y}/100)" if sub_y != 0 else ""
        overlay_cmd = f"overlay=(W-w)/2:H-h{y_offset}:shortest=1,format=yuv420p"

        if mode == "blur":
            filter_complex = f"[0:v]boxblur=25:25,colorchannelmixer=rr=0.7:gg=0.7:bb=0.7[bg];{fg_filter};[bg][fg_scaled]{overlay_cmd}[outv]"
            inputs = ["-i", video_path]
        elif mode == "image" and bg_image_path and os.path.exists(bg_image_path):
            bg_w = int(w * (bg_scale / 100.0))
            bg_h = int(h * (bg_scale / 100.0))
            filter_complex = f"[1:v]scale={bg_w}:{bg_h}:force_original_aspect_ratio=increase,crop={w}:{h}[bg];{fg_filter};[bg][fg_scaled]{overlay_cmd}[outv]"
            inputs = ["-i", video_path, "-loop", "1", "-i", bg_image_path]
            log("Using custom image background filter_complex.")
        else:
            ff_color = hex_color if len(hex_color) == 6 else "09090b"
            filter_complex = f"color=c=#{ff_color}:s={w}x{h}:d=9999[bg];{fg_filter};[bg][fg_scaled]{overlay_cmd}[outv]"
            inputs = ["-i", video_path]
            log("Using solid color background filter_complex.")
            
        cmd = [
            "ffmpeg", "-ss", "00:00:02", *inputs, 
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-vframes", "1", preview_img, "-y", "-update", "1"
        ]
        log(f"FFmpeg CMD: {' '.join(cmd)}")
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            log("FFmpeg completed successfully.")
            print(f"[PREVIEW_READY] {preview_img}")
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
            log(f"FFmpeg Error: {err_msg}")
            print(f"[❌] Preview Generation Failed:\n{err_msg}")
    else:
        log("AI Mode selected, returning un-keyed frame.")
        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, 50)
        success, frame = cap.read()
        if success:
            cv2.imwrite(preview_img, frame)
            print(f"[PREVIEW_READY] {preview_img}")
            log("Saved un-keyed frame.")
        cap.release()

if __name__ == "__main__":
    if len(sys.argv) > 2:
        generate_preview(sys.argv[1], sys.argv[2])
