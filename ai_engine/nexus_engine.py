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

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)


async def render_html_to_mp4(
    html_source: str,
    output_path: str,
    duration: float = 5.0,
    fps: int = 60,
    width: int = 1920,
    height: int = 1080,
    bg_color: str = "#000000",
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
    ]
    if not is_windows:
        # EGL/GPU accel — Linux only
        chromium_args += ["--use-gl=egl", "--enable-gpu"]
    else:
        # Windows: software renderer is more reliable in headless
        chromium_args += ["--disable-gpu"]

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

        print(f"[✅] Animation initialized. Starting frame capture...")

        # ── FFmpeg pipe ───────────────────────────────────────────────────
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-f", "image2pipe",
            "-vcodec", "png",
            "-framerate", str(fps),
            "-i", "pipe:0",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "14",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-vf", f"scale={width}:{height}:flags=lanczos",
            output_path,
        ]

        print(f"[⚙️] Opening FFmpeg pipe → {os.path.basename(output_path)}")
        ffmpeg_proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        print(f"[🎬] Rendering {total_frames} frames...")

        errors = 0
        for frame_idx in range(total_frames):
            time_ms = frame_idx * spf * 1000.0

            await page.evaluate(f"window.__nexusSeek({time_ms:.4f})")

            try:
                png_bytes = await page.screenshot(
                    type="png",
                    clip={"x": 0, "y": 0, "width": width, "height": height},
                    animations="disabled",
                )
                ffmpeg_proc.stdin.write(png_bytes)
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
        _, stderr = ffmpeg_proc.communicate()

        if ffmpeg_proc.returncode != 0:
            raise RuntimeError(f"FFmpeg failed:\n{stderr.decode()}")

        await browser.close()

    os.unlink(tmp_path)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"[✅] Nexus render complete → {output_path} ({size_mb:.1f} MB)")
    return output_path


def main():
    if len(sys.argv) < 3:
        print("Usage: nexus_engine.py <options_json> <output_path>")
        sys.exit(1)

    options = json.loads(sys.argv[1])
    output_path = sys.argv[2]

    html_source = options.get("html", "")
    duration    = float(options.get("duration", 5.0))
    fps         = int(options.get("fps", 60))
    width       = int(options.get("width", 1920))
    height      = int(options.get("height", 1080))
    bg_color    = options.get("bgColor", "#000000")

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
    ))


if __name__ == "__main__":
    main()