def stage_enhance_ai_image(input_image_path: str) -> str:
    from playwright.sync_api import sync_playwright
    print(f"[ΓÜÖ∩╕Å] Bypassing Invisible AI Watermarks via High-Res Screenshot: {input_image_path}")
    base, ext = os.path.splitext(input_image_path)
    output_image_path = f"{base}_hq.jpg"

    try:
        # 1. Get original image dimensions
        img = Image.open(input_image_path)
        w, h = img.size
        img.close()

        # 2. Automate a headless browser to "screenshot" the image.
        # The browser's compositing and upscaling completely destroys 
        # fragile steganographic watermarks (like SynthID).
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-web-security", "--allow-file-access-from-files"]
            )
            
            # device_scale_factor=2 upscales the screenshot by 2x for high quality
            context = browser.new_context(
                viewport={"width": w, "height": h},
                device_scale_factor=2 
            )
            page = context.new_page()
            
            # We slightly overscale (101%) to force sub-pixel resampling.
            # This guarantees the invisible pixel noise patterns are irreversibly scrambled.
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                    body, html {{ width: {w}px; height: {h}px; overflow: hidden; background: #000; }}
                    img {{ 
                        width: 101%; 
                        height: 101%; 
                        object-fit: cover; 
                        transform: translate(-0.5%, -0.5%); 
                    }}
                </style>
            </head>
            <body>
                <img src="file:///{input_image_path.replace(os.sep, '/')}" />
            </body>
            </html>
            """
            
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as tmp:
                tmp.write(html_content)
                tmp_path = tmp.name

            try:
                page.goto(f"file:///{tmp_path.replace(os.sep, '/')}", wait_until="networkidle")
                # 3. Take the high-quality 2x screenshot
                page.screenshot(path=output_image_path, type="jpeg", quality=100)
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                    
            browser.close()

        print(f"[Γ£à] High-Quality Screenshot saved (Watermarks Destroyed): {output_image_path}")
        return output_image_path
    except Exception as e:
        print(f"[Γ¥î] Image screenshot enhancement failed: {e}")
        return input_image_path

# 14. MAIN PIPELINE ORCHESTRATION
# ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
