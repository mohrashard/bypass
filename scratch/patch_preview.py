import os
import re

preview_path = r"C:\Projects\capcut-bypass\ai_engine\preview_engine.py"
with open(preview_path, 'r', encoding='utf-8') as f:
    content = f.read()

webgl_preview_code = """
    elif keying_mode == "webgl":
        log("WebGL Mode selected, rendering preview via Playwright.")
        from playwright.sync_api import sync_playwright
        import urllib.parse
        
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
                        
                        vec3 keyColor = vec3(26.0/255.0, 149.0/255.0, 53.0/255.0);
                        float diff = distance(color.rgb, keyColor);
                        float alpha = smoothstep(0.10, 0.25, diff);
                        
                        if (color.g > color.r && color.g > color.b) {{
                            color.g = max(color.r, color.b);
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
                
                vid.currentTime = 2.0; // Seek to 2 seconds for preview
                
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
                    if (vid.readyState >= 1) {{ vid.currentTime = 2.0; }} // ensure seek
                }}
            </script>
        </body>
        </html>
        \"\"\"
        
        webgl_html_path = os.path.join(base_dir, "_webgl_preview.html")
        with open(webgl_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
            
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
                device_scale_factor=1
            )
            
            page.goto("file:///" + urllib.parse.quote(webgl_html_path.replace("\\\\", "/")))
            page.wait_for_function("window.renderComplete === true", timeout=30000)
            
            # Screenshot the canvas
            page.locator("canvas").screenshot(path=preview_img)
            browser.close()
            
        if os.path.exists(webgl_html_path): os.remove(webgl_html_path)
        print(f"[PREVIEW_READY] {preview_img}")
"""

if "elif keying_mode == \"webgl\":" not in content:
    content = content.replace("    else:\n        log(\"AI Mode selected, returning un-keyed frame.\")", webgl_preview_code + "\n    else:\n        log(\"AI Mode selected, returning un-keyed frame.\")")
    with open(preview_path, 'w', encoding='utf-8') as f:
        f.write(content)
