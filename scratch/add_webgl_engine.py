import os
import re

pipeline_path = r"C:\Projects\capcut-bypass\ai_engine\pipeline.py"
with open(pipeline_path, 'r', encoding='utf-8') as f:
    content = f.read()

webgl_code = """
    # ── WebGL GPU Soft Key Path (Playwright) ──────────────────────────────
    elif keying_mode == "webgl":
        print("[🌐] Booting WebGL Browser Engine for Cinematic Soft Keying...")
        from playwright.sync_api import sync_playwright
        import urllib.parse
        import json
        
        cap.release()
        out.release()
        if os.path.exists(temp_vid): os.remove(temp_vid)
        
        # Convert paths to file URIs for browser
        vid_uri = "file:///" + urllib.parse.quote(video_path.replace("\\\\", "/"))
        bg_uri = ""
        if mode == "image" and bg_image_path and os.path.exists(bg_image_path):
            bg_uri = "file:///" + urllib.parse.quote(bg_image_path.replace("\\\\", "/"))
        
        bg_hex = hex_color if mode == "color" else "09090b"
        
        html_content = f\"\"\"
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
                const gl = canvas.getContext('webgl');
                
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
                        
                        // Distance to green screen color (0x1A9535 -> 26, 149, 53)
                        vec3 keyColor = vec3(26.0/255.0, 149.0/255.0, 53.0/255.0);
                        float diff = distance(color.rgb, keyColor);
                        
                        // Soft alpha ramp
                        float alpha = smoothstep(0.10, 0.25, diff);
                        
                        // Despill: limit green to max of red and blue
                        if (color.g > color.r && color.g > color.b) {{
                            color.g = max(color.r, color.b);
                        }}
                        
                        vec4 finalColor = vec4(color.rgb, alpha);
                        if (uUseBgImage == 1) {{
                            // premultiply alpha for mix
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
                
                let mediaRecorder;
                let chunks = [];
                
                function startProcessing() {{
                    if (!bgLoaded) return;
                    if (bg.src && bg.src !== window.location.href && !bg.src.endsWith('null') && bg.src !== '') {{
                        gl.uniform1i(uUseBgImage, 1);
                    }}
                    
                    vid.play().then(() => {{
                        const stream = canvas.captureStream(60);
                        mediaRecorder = new MediaRecorder(stream, {{ mimeType: 'video/webm;codecs=vp9', videoBitsPerSecond: 16000000 }});
                        mediaRecorder.ondataavailable = e => chunks.push(e.data);
                        mediaRecorder.onstop = () => {{
                            const blob = new Blob(chunks, {{ type: 'video/webm' }});
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = 'webgl_render.webm';
                            a.click();
                            window.renderComplete = true;
                        }};
                        mediaRecorder.start();
                        renderLoop();
                    }});
                }}
                
                function renderLoop() {{
                    if (vid.paused || vid.ended) {{
                        if (mediaRecorder.state === 'recording') mediaRecorder.stop();
                        return;
                    }}
                    gl.activeTexture(gl.TEXTURE0);
                    gl.bindTexture(gl.TEXTURE_2D, vidTexture);
                    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, vid);
                    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
                    requestAnimationFrame(renderLoop);
                }}
                
                vid.onended = () => {{
                    if (mediaRecorder && mediaRecorder.state === 'recording') mediaRecorder.stop();
                }};
            </script>
        </body>
        </html>
        \"\"\"
        
        webgl_html_path = os.path.join(base_dir, "_webgl_keyer.html")
        webgl_webm_path = os.path.join(base_dir, "_webgl_render.webm")
        with open(webgl_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        print("[⚙️] Running headless WebGL compositor via GPU...")
        
        # We must use specific flags to force hardware GPU rendering in headless mode
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "ms-playwright")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--use-gl=desktop",
                    "--enable-webgl",
                    "--ignore-gpu-blocklist",
                    "--autoplay-policy=no-user-gesture-required",
                    "--disable-web-security"
                ]
            )
            page = browser.new_page(
                viewport={"width": w, "height": h},
                device_scale_factor=1,
                accept_downloads=True
            )
            
            # Setup download intercept
            with page.expect_download(timeout=300000) as download_info:
                page.goto("file:///" + urllib.parse.quote(webgl_html_path.replace("\\\\", "/")))
                # Wait for the recording to finish and trigger download
                page.wait_for_function("window.renderComplete === true", timeout=300000)
                
            download = download_info.value
            download.save_as(webgl_webm_path)
            browser.close()
            
        print("[⚙️] Remuxing WebGL WebM with original audio...")
        subprocess.run([
            "ffmpeg", "-i", webgl_webm_path, "-i", temp_audio,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-map", "0:v:0", "-map", "1:a:0",
            "-shortest", output_vid, "-y"
        ], check=True, capture_output=True)
        
        for f in [webgl_html_path, webgl_webm_path, temp_audio]:
            if os.path.exists(f): os.remove(f)
            
        print(f"[✅] Background FX applied (WebGL): {output_vid}")
        return output_vid
"""

if webgl_code not in content:
    content = content.replace("    # ── MediaPipe AI Segmentation Path ───────────────────────────────────", webgl_code + "\n    # ── MediaPipe AI Segmentation Path ───────────────────────────────────")
    with open(pipeline_path, 'w', encoding='utf-8') as f:
        f.write(content)
