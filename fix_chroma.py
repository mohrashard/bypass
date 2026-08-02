"""Replace the broken multi-scene chroma block with the clean simple version."""
import sys

with open('ai_engine/pipeline.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find start and end by line number (confirmed: 1852 and 2072)
lines = content.split('\n')
start_line = 1851  # 0-indexed = line 1852
end_line   = 2071  # 0-indexed = line 2072

before = '\n'.join(lines[:start_line])
after  = '\n'.join(lines[end_line:])

new_block = """    # \u2500\u2500 Chroma Key Path (FFmpeg Hardware Accelerated) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    if keying_mode in ("chroma", "chroma-dark"):
        print("[\\U0001f7e9] Green Screen chroma-key active \\u2014 using FFmpeg hardware math.")
        cap.release()
        out.release()
        if os.path.exists(temp_vid): os.remove(temp_vid)

        # Output canvas \u2014 respects user dropdown selection
        output_ratio = bg_options.get("outputRatio", "source")
        if output_ratio == "9:16":
            out_w, out_h = 1080, 1920
        elif output_ratio == "16:9":
            out_w, out_h = 1920, 1080
        else:
            out_w, out_h = w, h

        # Chroma filter
        if keying_mode == "chroma-dark":
            chroma_filter = "chromakey=0x18742B:0.09:0.08,despill=green"
        else:
            chroma_filter = "chromakey=0x1A9535:0.11:0.02,despill=green"

        # Subject dimensions (must be even for libx264)
        sub_w = int(out_w * sub_scale / 100)
        sub_h = int(out_h * sub_scale / 100)
        sub_w = sub_w if sub_w % 2 == 0 else sub_w + 1
        sub_h = sub_h if sub_h % 2 == 0 else sub_h + 1

        y_offset = f"+(H*{sub_y}/100)" if sub_y != 0 else ""
        overlay_cmd = f"overlay=(W-w)/2:H-h{y_offset}:shortest=1,format=yuv420p"

        # fg_chain: scale source to canvas, apply chroma key, scale to subject size
        fg_chain = (
            f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
            f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2,"
            f"{chroma_filter}[fg];[fg]scale={sub_w}:{sub_h}[fg_scaled]"
        )

        audio_idx = 1
        if mode == "blur":
            # Split [0:v] so blur-bg and fg each get their own stream
            filter_complex = (
                f"[0:v]split=2[raw0][raw1];"
                f"[raw0]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
                f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2,"
                f"boxblur=25:25,colorchannelmixer=rr=0.7:gg=0.7:bb=0.7[bg];"
                f"[raw1]{fg_chain};"
                f"[bg][fg_scaled]{overlay_cmd}[outv]"
            )
            inputs = ["-i", video_path]

        elif mode == "image" and bg_image_path and os.path.exists(bg_image_path):
            bg_w = int(out_w * (bg_scale / 100.0))
            bg_h = int(out_h * (bg_scale / 100.0))
            filter_complex = (
                f"[1:v]scale={bg_w}:{bg_h}:force_original_aspect_ratio=increase,"
                f"crop={out_w}:{out_h}[bg];"
                f"[0:v]{fg_chain};"
                f"[bg][fg_scaled]{overlay_cmd}[outv]"
            )
            inputs = ["-i", video_path, "-loop", "1", "-i", bg_image_path]
            audio_idx = 2

        else:
            ff_color = hex_color if len(hex_color) == 6 else "09090b"
            filter_complex = (
                f"color=c=#{ff_color}:s={out_w}x{out_h}:d=9999[bg];"
                f"[0:v]{fg_chain};"
                f"[bg][fg_scaled]{overlay_cmd}[outv]"
            )
            inputs = ["-i", video_path]

        print(f"[\\u2699\\ufe0f] Running FFmpeg render \\u2192 {out_w}x{out_h}...")
        cmd = [
            "ffmpeg", *inputs, "-i", temp_audio,
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", f"{audio_idx}:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", output_vid, "-y"
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.decode("utf-8", errors="ignore") if e.stderr else str(e)
            print(f"[\\u274c] FFmpeg Engine Failed:\\n{err_msg}")
            raise

        for f in [temp_audio]:
            if os.path.exists(f): os.remove(f)

        print(f"[\\u2705] Background FX applied ({out_w}x{out_h}): {output_vid}")
        return output_vid

"""

new_content = before + '\n' + new_block + after

with open('ai_engine/pipeline.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print('Done! Clean chroma block written.')
