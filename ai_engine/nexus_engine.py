"""
NEXUS ENGINE — HTML → MP4 Renderer (Windows-compatible fixed)
"""

import sys
import json
import os
import subprocess
import asyncio
import io
import tempfile

# ─── PyInstaller App Compilation Fixes ─────────────
if hasattr(sys, '_MEIPASS'):
    exe_dir = os.path.dirname(sys.executable)
    os.environ["PATH"] = sys._MEIPASS + os.pathsep + exe_dir + os.pathsep + os.environ.get("PATH", "")
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(exe_dir, "pw-browsers")

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

async def extract_html_audio(browser, html_source, duration):
    audio_injector = """
    <script>
    (function() {
        window.__audioStream = null;
        window.__audioChunks = [];
        
        const _AudioContext = window.AudioContext || window.webkitAudioContext;
        if(!_AudioContext) return;
        
        window.AudioContext = class extends _AudioContext {
            constructor(opts) {
                super(opts);
                if (!window.__sharedAudioContext) {
                    window.__sharedAudioContext = this;
                    this.__mediaStreamDestination = this.createMediaStreamDestination();
                    window.__audioStream = this.__mediaStreamDestination.stream;
                    
                    try {
                        window.__mediaRecorder = new MediaRecorder(window.__audioStream);
                        window.__mediaRecorder.ondataavailable = e => {
                            if (e.data.size > 0) window.__audioChunks.push(e.data);
                        };
                        window.__mediaRecorder.start();
                    } catch(e) {
                        console.error(e);
                    }
                } else {
                    this.__mediaStreamDestination = window.__sharedAudioContext.__mediaStreamDestination;
                }
            }
        };

        const _connect = AudioNode.prototype.connect;
        AudioNode.prototype.connect = function() {
            var destination = arguments[0];
            if (destination && destination.toString() === "[object AudioDestinationNode]") {
                if (this.context && this.context.__mediaStreamDestination) {
                    _connect.call(this, this.context.__mediaStreamDestination);
                }
            }
            return _connect.apply(this, arguments);
        };

        const _play = HTMLMediaElement.prototype.play;
        HTMLMediaElement.prototype.play = function() {
            if (!this.__routed) {
                this.__routed = true;
                try {
                    const ctx = window.__sharedAudioContext || new window.AudioContext();
                    const source = ctx.createMediaElementSource(this);
                    source.connect(ctx.destination);
                } catch(e) {}
            }
            return _play.apply(this, arguments);
        };

        window.__stopAndGetAudio = async function() {
            return new Promise(resolve => {
                if (!window.__mediaRecorder || window.__mediaRecorder.state === "inactive") {
                    resolve(""); return;
                }
                window.__mediaRecorder.onstop = async () => {
                    const blob = new Blob(window.__audioChunks, { type: "audio/webm" });
                    const reader = new FileReader();
                    reader.onloadend = () => {
                        let base64data = reader.result;
                        resolve(base64data.split(',')[1]);
                    };
                    reader.readAsDataURL(blob);
                };
                window.__mediaRecorder.stop();
            });
        };
    })();
    </script>
    """
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as tmp:
        head_lower = html_source.lower()
        if "<head>" in head_lower:
            idx = head_lower.index("<head>") + len("<head>")
            tmp.write(html_source[:idx] + audio_injector + html_source[idx:])
        else:
            tmp.write(audio_injector + html_source)
        tmp_path = tmp.name

    page = await browser.new_page()
    try:
        await page.goto(f"file:///{tmp_path.replace(os.sep, '/')}", wait_until="domcontentloaded")
        await asyncio.sleep(duration + 0.5)
        base64_audio = await page.evaluate("window.__stopAndGetAudio()")
    except Exception as e:
        print(f"[⚠️] Audio extraction error: {e}")
        base64_audio = ""
    
    await page.close()
    os.unlink(tmp_path)
    return base64_audio



async def render_html_to_mp4(
    html_source: str,
    output_path: str,
    duration: float = 5.0,
    fps: int = 60,
    width: int = 1920,
    height: int = 1080,
    bg_color: str = "#000000",
    audio_path: str = None,
    transparent: bool = False,
) -> str:
    from playwright.async_api import async_playwright

    total_frames = int(duration * fps)
    spf = 1.0 / fps

    print(f"[⚙️] Nexus Engine initializing...")
    print(f"[⚙️] Resolution: {width}x{height} | {fps}fps | {duration}s | {total_frames} frames")

    # ── Write HTML to temp file ─────────────────────────────────────────────
    # FIX 1: Don't use setTimeout in the injector at all.
    # FIX 2: Don't rely on window.onload — CDN scripts can block it in headless.
    # Instead: set __nexusReady after DOMContentLoaded + one real rAF tick.
    # We use a real setTimeout here BEFORE overriding it (stored as _realSetTimeout).
    nexus_injector = f"""
<script>
(function() {{
    var _nexusTime = 0;
    var _rafCallbacks = new Map();
    var _rafId = 0;

    // ── Save real natives BEFORE overriding anything ──────────────────────
    var _realRAF      = window.requestAnimationFrame.bind(window);
    var _realSetTimeout = window.setTimeout.bind(window);   // save REAL setTimeout
    var _realPerfNow  = performance.now.bind(performance);

    // ── Override Date.now ─────────────────────────────────────────────────
    var _OrigDate = Date;
    function NexusDate() {{
        if (arguments.length === 0) return new _OrigDate(_nexusTime);
        return new (Function.prototype.bind.apply(_OrigDate, [null].concat(Array.from(arguments))))();
    }}
    NexusDate.now = function() {{ return _nexusTime; }};
    NexusDate.parse = _OrigDate.parse;
    NexusDate.UTC   = _OrigDate.UTC;
    NexusDate.prototype = _OrigDate.prototype;
    window.Date = NexusDate;

    // ── Override performance.now ──────────────────────────────────────────
    performance.now = function() {{ return _nexusTime; }};

    // ── Override rAF ──────────────────────────────────────────────────────
    window.requestAnimationFrame = function(cb) {{
        var id = ++_rafId;
        _rafCallbacks.set(id, cb);
        return id;
    }};
    window.cancelAnimationFrame = function(id) {{
        _rafCallbacks.delete(id);
    }};

    // ── __nexusSeek: advance to a specific time in ms ─────────────────────
    window.__nexusSeek = function(timeMs) {{
        _nexusTime = timeMs;
        var cbs = new Map(_rafCallbacks);
        _rafCallbacks.clear();
        cbs.forEach(function(cb) {{
            try {{ cb(timeMs); }} catch(e) {{ console.error('rAF cb error:', e); }}
        }});
        document.documentElement.style.setProperty('--nexus-t', timeMs + 'ms');
    }};

    window.__nexusReady = false;

    // ── Ready detection: DOMContentLoaded + real rAF tick ────────────────
    // Using _realSetTimeout (saved before override) so it actually fires.
    // DOMContentLoaded is reliable even when CDN scripts are loading/failing.
    document.addEventListener('DOMContentLoaded', function() {{
        // Global volume reduction for all headless renders
        if (window.Tone && window.Tone.Destination) {{
            window.Tone.Destination.volume.value = -15;
        }}
        document.querySelectorAll('audio, video').forEach(function(media) {{
            media.volume = 0.15;
        }});

        // Fire rAF tick 0 so GSAP/anime.js initialize their internals
        window.__nexusSeek(0);
        // Use the REAL setTimeout (not our overridden one) to wait 200ms
        // for any sync script initialization after DOMContentLoaded
        _realSetTimeout(function() {{
            window.__nexusSeek(0); // fire again after scripts ran
            window.__nexusReady = true;
        }}, 200);
    }});
}})();
</script>
"""

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8"
    ) as tmp:
        injected_html = html_source
        head_lower = html_source.lower()
        if "<head>" in head_lower:
            idx = head_lower.index("<head>") + len("<head>")
            injected_html = html_source[:idx] + nexus_injector + html_source[idx:]
        elif "<html>" in head_lower:
            idx = head_lower.index("<html>") + len("<html>")
            injected_html = html_source[:idx] + nexus_injector + html_source[idx:]
        else:
            injected_html = nexus_injector + html_source

        tmp.write(injected_html)
        tmp_path = tmp.name

    print(f"[⚙️] Launching headless Chromium...")

    # ── FIX 3: Windows-safe Chromium args (no --use-gl=egl which is Linux-only)
    is_windows = os.name == 'nt'
    chromium_args = [
        "--disable-web-security",
        "--allow-file-access-from-files",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--font-render-hinting=none",
        "--force-color-profile=srgb",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-backgrounding-occluded-windows",
        "--run-all-compositor-stages-before-draw",
        "--disable-features=IsolateOrigins,site-per-process",
        "--enable-accelerated-2d-canvas",
        "--hide-scrollbars",
        "--autoplay-policy=no-user-gesture-required",
    ]
    if not is_windows:
        # EGL/GPU accel — Linux only
        chromium_args += ["--use-gl=egl", "--enable-gpu"]
    else:
        # Windows: Enable GPU for massive speedup in DOM/Canvas rendering
        chromium_args += ["--enable-gpu"]

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="msedge",
            headless=True,
            args=chromium_args,
        )

        page = await browser.new_page(
            viewport={"width": width, "height": height},
            device_scale_factor=1,
        )

        # Navigate with a generous timeout; network issues shouldn't abort us
        await page.goto(
            f"file:///{tmp_path.replace(os.sep, '/')}",
            wait_until="domcontentloaded",   # FIX 4: don't wait for network (CDN)
            timeout=30000,
        )

        # FIX 5: Poll for __nexusReady with a longer timeout + helpful error
        print(f"[⚙️] Waiting for animation to initialize...")
        try:
            await page.wait_for_function(
                "window.__nexusReady === true",
                timeout=20000,
                polling=100,   # check every 100ms
            )
        except Exception:
            # Debug: check what's actually on the page
            ready_val = await page.evaluate("typeof window.__nexusReady + ' = ' + window.__nexusReady")
            console_errors = await page.evaluate("""
                window.__nexusErrors || 'none'
            """)
            print(f"[❌] __nexusReady timed out. Value: {ready_val}")
            print(f"[❌] Check your HTML for script errors. Trying to proceed anyway...")
            # Force-set ready and continue rather than hard crash
            await page.evaluate("window.__nexusReady = true; window.__nexusSeek(0);")

        audio_task = None
        if not audio_path:
            print(f"[⚙️] Starting concurrent audio extraction pass...")
            audio_task = asyncio.create_task(extract_html_audio(browser, html_source, duration))

        print(f"[✅] Animation initialized. Starting frame capture...")

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-f", "image2pipe",
            "-vcodec", "png" if transparent else "mjpeg",
            "-framerate", str(fps),
            "-thread_queue_size", "512",
            "-i", "pipe:0"
        ]
        
        if audio_path and os.path.exists(audio_path):
            ffmpeg_cmd.extend(["-i", audio_path])
            
        if transparent:
            # Lossless Apple Animation codec (supports alpha perfectly, very fast)
            ffmpeg_cmd.extend([
                "-c:v", "qtrle",
                "-pix_fmt", "argb"
            ])
        else:
            ffmpeg_cmd.extend([
                "-c:v", "h264_nvenc",
                "-preset", "p4",
                "-cq", "18",
                "-pix_fmt", "yuv420p"
            ])
        
        if audio_path and os.path.exists(audio_path):
            ffmpeg_cmd.extend([
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest"
            ])
            
        ffmpeg_cmd.extend([
            "-movflags", "+faststart",
            output_path,
        ])

        print(f"[⚙️] Opening FFmpeg pipe → {os.path.basename(output_path)}")
        ffmpeg_proc = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        print(f"[🎬] Rendering {total_frames} frames...")

        import base64
        client = await page.context.new_cdp_session(page)

        errors = 0
        for frame_idx in range(total_frames):
            time_ms = frame_idx * spf * 1000.0

            await page.evaluate(f"window.__nexusSeek({time_ms:.4f})")

            try:
                # Fast CDP screenshot
                if transparent:
                    res = await client.send("Page.captureScreenshot", {
                        "format": "png",
                        "omitBackground": True
                    })
                else:
                    res = await client.send("Page.captureScreenshot", {
                        "format": "jpeg",
                        "quality": 100
                    })
                jpeg_bytes = base64.b64decode(res["data"])
                
                ffmpeg_proc.stdin.write(jpeg_bytes)
                await ffmpeg_proc.stdin.drain()
            except Exception as e:
                errors += 1
                print(f"[⚠️] Frame {frame_idx} screenshot failed: {e}")
                if errors > 10:
                    print(f"[❌] Too many frame errors. Aborting.")
                    break

            if frame_idx % max(1, total_frames // 20) == 0:
                pct = int(frame_idx / total_frames * 100)
                bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                print(f"[⚙️] [{bar}] {pct}% — frame {frame_idx}/{total_frames}")

        print(f"[⚙️] All frames sent. Finalizing MP4...")
        ffmpeg_proc.stdin.close()
        await ffmpeg_proc.stdin.wait_closed()
        
        _, stderr = await ffmpeg_proc.communicate()

        if ffmpeg_proc.returncode != 0:
            raise RuntimeError(f"FFmpeg failed:\n{stderr.decode()}")
            
        if audio_task:
            print(f"[⚙️] Finalizing audio extraction...")
            base64_audio = await audio_task
            if base64_audio:
                print(f"[⚙️] Audio captured. Muxing with video...")
                import base64
                audio_bytes = base64.b64decode(base64_audio)
                with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as a_tmp:
                    a_tmp.write(audio_bytes)
                    a_tmp_path = a_tmp.name
                
                _, ext = os.path.splitext(output_path)
                final_tmp = output_path + f".tmp{ext}"
                mux_cmd = [
                    "ffmpeg", "-y",
                    "-i", output_path,
                    "-i", a_tmp_path,
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k",
                    "-shortest",
                    final_tmp
                ]
                subprocess.run(mux_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                os.replace(final_tmp, output_path)
                os.unlink(a_tmp_path)
            else:
                print(f"[⚙️] No audio detected in HTML.")

        await browser.close()

    os.unlink(tmp_path)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"[✅] Nexus render complete → {output_path} ({size_mb:.1f} MB)")
    return output_path


def main():
    if len(sys.argv) < 3:
        print("Usage: nexus_engine.py <options_json> <output_path>")
        sys.exit(1)

    options_arg = sys.argv[1]
    output_path = sys.argv[2]
    
    if options_arg.endswith('.json') and os.path.exists(options_arg):
        with open(options_arg, 'r', encoding='utf-8') as f:
            options_arg = f.read()

    options = json.loads(options_arg)
    output_path = sys.argv[2]

    html_source = options.get("html", "")
    duration    = float(options.get("duration", 5.0))
    fps         = int(options.get("fps", 60))
    width       = int(options.get("width", 1920))
    height      = int(options.get("height", 1080))
    bg_color    = options.get("bgColor", "#000000")
    audio_path  = options.get("audioPath", None)
    transparent = options.get("transparent", False)

    if not html_source:
        print("[❌] No HTML provided.")
        sys.exit(1)

    asyncio.run(render_html_to_mp4(
        html_source=html_source,
        output_path=output_path,
        duration=duration,
        fps=fps,
        width=width,
        height=height,
        bg_color=bg_color,
        audio_path=audio_path,
        transparent=transparent,
    ))


if __name__ == "__main__":
    main()