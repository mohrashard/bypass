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
    
    print(f"[PREVIEW_DBG] keying={keying_mode} mode={mode} bg_img={bg_image_path}")
    log(f"Keying Mode: {keying_mode}, BG Mode: {mode}, BG Path: {bg_image_path}")
    
    if keying_mode in ("chroma", "chroma-dark"):
        if keying_mode == "chroma-dark":
            chroma_filter = "chromakey=0x18742B:0.09:0.08,despill=green"
        else:
            chroma_filter = "chromakey=0x1A9535:0.11:0.02,despill=green"
        sub_w = int(w * sub_scale / 100)
        sub_h = int(h * sub_scale / 100)
        sub_w = sub_w if sub_w % 2 == 0 else sub_w + 1
        sub_h = sub_h if sub_h % 2 == 0 else sub_h + 1
        
        fg_filter = f"[0:v]{chroma_filter}[fg];[fg]scale={sub_w}:{sub_h}[fg_scaled]"
        y_offset = f"+(H*{sub_y}/100)" if sub_y != 0 else ""
        overlay_cmd = f"overlay=(W-w)/2:H-h{y_offset}:shortest=1,format=yuv420p"

        if mode == "blur":
            # split [0:v] into two streams: one for blurred bg, one for fg chroma key
            fg_filter_blur = f"[src1]{chroma_filter}[fg];[fg]scale={sub_w}:{sub_h}[fg_scaled]"
            filter_complex = f"[0:v]split=2[src0][src1];[src0]boxblur=25:25,colorchannelmixer=rr=0.7:gg=0.7:bb=0.7[bg];{fg_filter_blur};[bg][fg_scaled]{overlay_cmd}[outv]"
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

    elif keying_mode == "webgl":
        log("WebGL Mode selected, rendering preview via Playwright.")
        from playwright.sync_api import sync_playwright
        import pathlib
        
        vid_uri = pathlib.Path(video_path).as_uri()
        bg_uri = ""
        if mode == "image" and bg_image_path and os.path.exists(bg_image_path):
            bg_uri = pathlib.Path(bg_image_path).as_uri()
        
        bg_hex = hex_color if mode == "color" else "09090b"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ margin: 0; background: #{bg_hex}; overflow: hidden; }}
                canvas {{ width: 100vw; height: 100vh; }}
            </style>
        </head>
        <body>
            <video id="vid" src="{vid_uri}" muted style="display:none;"></video>
            <img id="bg" src="{bg_uri}" style="display:none;" crossorigin="anonymous">
            <canvas id="glcanvas" width="{w}" height="{h}"></canvas>
            <script>
                const vid = document.getElementById('vid');
                const bg = document.getElementById('bg');
                const canvas = document.getElementById('glcanvas');
                const gl = canvas.getContext('webgl', {{ preserveDrawingBuffer: true }});
                
                const vsSource = `
                    attribute vec4 aVertexPosition;
                    attribute vec2 aTextureCoord;
                    varying highp vec2 vTextureCoord;
                    void main(void) {{
                        gl_Position = aVertexPosition;
                        vTextureCoord = aTextureCoord;
                    }}
                `;
                
                // Cinematic Soft Key Shader
                const fsSource = `
                    precision highp float;
                    varying highp vec2 vTextureCoord;
                    uniform sampler2D uSampler;
                    uniform sampler2D uBgSampler;
                    uniform int uUseBgImage;
                    
                    void main(void) {{
                        vec4 color = texture2D(uSampler, vTextureCoord);
                        vec4 bg = uUseBgImage == 1 ? texture2D(uBgSampler, vTextureCoord) : vec4(0.0, 0.0, 0.0, 0.0);
                        
                        // Robust Green Screen Math: measures how much stronger Green is than Red and Blue
                        float maxRB = max(color.r, color.b);
                        float gDiff = color.g - maxRB;
                        
                        // The higher gDiff, the greener the pixel.
                        // If it's barely green (< 0.03), it's opaque foreground.
                        // If it's clearly green (> 0.12), it's transparent background.
                        float alpha = 1.0 - smoothstep(0.03, 0.12, gDiff);
                        
                        // Despill: neutralize green fringe on the edges
                        if (color.g > maxRB) {{
                            // Pull green down to the level of Red/Blue smoothly based on how "green" the pixel was
                            float despillFactor = clamp(gDiff / 0.15, 0.0, 1.0);
                            color.g = mix(color.g, maxRB, despillFactor);
                        }}
                        
                        vec4 finalColor = vec4(color.rgb, alpha);
                        if (uUseBgImage == 1) {{
                            gl_FragColor = mix(bg, vec4(color.rgb, 1.0), alpha);
                        }} else {{
                            gl_FragColor = vec4(color.rgb * alpha, alpha);
                        }}
                    }}
                `;
                
                function loadShader(gl, type, source) {{
                    const shader = gl.createShader(type);
                    gl.shaderSource(shader, source);
                    gl.compileShader(shader);
                    return shader;
                }}
                
                const shaderProgram = gl.createProgram();
                gl.attachShader(shaderProgram, loadShader(gl, gl.VERTEX_SHADER, vsSource));
                gl.attachShader(shaderProgram, loadShader(gl, gl.FRAGMENT_SHADER, fsSource));
                gl.linkProgram(shaderProgram);
                gl.useProgram(shaderProgram);
                
                const positions = new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]);
                const texCoords = new Float32Array([0, 1, 1, 1, 0, 0, 1, 0]);
                
                const posBuf = gl.createBuffer();
                gl.bindBuffer(gl.ARRAY_BUFFER, posBuf);
                gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW);
                const posAttr = gl.getAttribLocation(shaderProgram, 'aVertexPosition');
                gl.vertexAttribPointer(posAttr, 2, gl.FLOAT, false, 0, 0);
                gl.enableVertexAttribArray(posAttr);
                
                const texBuf = gl.createBuffer();
                gl.bindBuffer(gl.ARRAY_BUFFER, texBuf);
                gl.bufferData(gl.ARRAY_BUFFER, texCoords, gl.STATIC_DRAW);
                const texAttr = gl.getAttribLocation(shaderProgram, 'aTextureCoord');
                gl.vertexAttribPointer(texAttr, 2, gl.FLOAT, false, 0, 0);
                gl.enableVertexAttribArray(texAttr);
                
                const vidTexture = gl.createTexture();
                gl.bindTexture(gl.TEXTURE_2D, vidTexture);
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
                
                const bgTexture = gl.createTexture();
                gl.bindTexture(gl.TEXTURE_2D, bgTexture);
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
                gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
                
                const uSampler = gl.getUniformLocation(shaderProgram, 'uSampler');
                const uBgSampler = gl.getUniformLocation(shaderProgram, 'uBgSampler');
                const uUseBgImage = gl.getUniformLocation(shaderProgram, 'uUseBgImage');
                
                gl.uniform1i(uSampler, 0);
                gl.uniform1i(uBgSampler, 1);
                
                gl.viewport(0, 0, canvas.width, canvas.height);
                
                let bgLoaded = !bg.src || bg.src.endsWith('null') || bg.src === '';
                if (!bgLoaded) {{
                    bg.onload = () => {{
                        gl.activeTexture(gl.TEXTURE1);
                        gl.bindTexture(gl.TEXTURE_2D, bgTexture);
                        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, bg);
                        bgLoaded = true;
                        startProcessing();
                    }};
                }} else {{
                    gl.uniform1i(uUseBgImage, 0);
                    startProcessing();
                }}
                
                function startProcessing() {{
                    vid.onseeked = () => {{
                        gl.activeTexture(gl.TEXTURE0);
                        gl.bindTexture(gl.TEXTURE_2D, vidTexture);
                        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, vid);
                        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
                        window.renderComplete = true;
                    }};
                    
                    if (vid.readyState >= 1) {{ 
                        vid.currentTime = 2.0; 
                    }} else {{
                        vid.onloadedmetadata = () => {{
                            vid.currentTime = 2.0;
                        }};
                    }}
                }}
            </script>
        </body>
        </html>
        """
        
        webgl_html_path = os.path.join(base_dir, "_webgl_preview.html")
        with open(webgl_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "ms-playwright")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                channel="chrome",
                headless=True,
                args=[
                    "--use-gl=desktop",
                    "--enable-webgl",
                    "--ignore-gpu-blocklist",
                    "--autoplay-policy=no-user-gesture-required",
                    "--disable-web-security",
                    "--allow-file-access-from-files"
                ]
            )
            page = browser.new_page(
                viewport={"width": w, "height": h},
                device_scale_factor=1
            )
            
            page.goto(pathlib.Path(webgl_html_path).as_uri())
            page.wait_for_function("window.renderComplete === true", timeout=30000)
            
            # Screenshot the canvas
            page.locator("canvas").screenshot(path=preview_img)
            browser.close()
            
        if os.path.exists(webgl_html_path): os.remove(webgl_html_path)
        print(f"[PREVIEW_READY] {preview_img}")

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