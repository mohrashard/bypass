import sys
import json
import os
import tempfile
import asyncio
from typing import List, Optional
from pydantic import BaseModel
from playwright.async_api import async_playwright

class Element(BaseModel):
    id: str
    type: str
    content: str
    font: str = "Mate"
    size: int = 40
    color: str = "#F8FAFC"
    x: int = 50
    y: int = 50
    
    bg_color: str = "transparent"
    bg_padding: int = 15
    bg_radius: int = 0
    stroke_color: str = "transparent"
    stroke_width: int = 0
    shadow_color: str = "transparent"
    shadow_blur: int = 0
    shadow_x: int = 0
    shadow_y: int = 0

class SlideContext(BaseModel):
    id: str
    elements: List[Element]

class CarouselConfig(BaseModel):
    slides: List[SlideContext]
    theme_bg: str = "#0F172A"
    ratio: str = "1:1"
    show_swipe: bool = True
    show_dots: bool = True
    ui_color: str = "#3B82F6"
    preview_idx: int = 0

def get_dimensions(ratio: str):
    if ratio == "1:1": return 1080, 1080
    elif ratio == "4:5": return 1080, 1350
    elif ratio == "16:9": return 1920, 1080
    return 1080, 1080

def get_font_family(font_name: str):
    font_family_map = {
        "Mate": "'Mate', serif",
        "Proxima Nova": "'Montserrat', sans-serif",
        "Cursive": "'Pacifico', cursive",
        "Gemunu Libre": "'Gemunu Libre', sans-serif"
    }
    return font_family_map.get(font_name, "'Inter', sans-serif")

def render_elements(slide: SlideContext):
    import base64
    import mimetypes
    html = ""
    for elem in slide.elements:
        if elem.type == "text":
            font = get_font_family(elem.font)
            css_styles = f"position: absolute; left: {elem.x}%; top: {elem.y}%; transform: translate(-50%, -50%); font-family: {font}; font-size: {elem.size}px; color: {elem.color}; white-space: pre-wrap; text-align: center; line-height: 1.2; width: max-content; max-width: 90%; z-index: 10;"
            if elem.bg_color and elem.bg_color != "transparent":
                css_styles += f" background-color: {elem.bg_color}; padding: {elem.bg_padding}px; border-radius: {elem.bg_radius}px;"
            if elem.stroke_color and elem.stroke_color != "transparent" and elem.stroke_width > 0:
                css_styles += f" -webkit-text-stroke: {elem.stroke_width}px {elem.stroke_color};"
            if elem.shadow_color and elem.shadow_color != "transparent" and (elem.shadow_blur > 0 or elem.shadow_x != 0 or elem.shadow_y != 0):
                css_styles += f" text-shadow: {elem.shadow_x}px {elem.shadow_y}px {elem.shadow_blur}px {elem.shadow_color};"
            html += f'<div style="{css_styles}">{elem.content}</div>'
        elif elem.type == "image":
            try:
                if os.path.exists(elem.content):
                    mime_type, _ = mimetypes.guess_type(elem.content)
                    if not mime_type: mime_type = "image/jpeg"
                    with open(elem.content, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode('utf-8')
                    src = f"data:{mime_type};base64,{b64}"
                else:
                    src = elem.content
            except Exception as e:
                src = elem.content
            html += f'<img src="{src}" style="position: absolute; left: 0; top: 0; width: 100%; height: 100%; object-fit: cover; z-index: 0;" />'
    return html

def render_retention_ui(config: CarouselConfig, is_last_slide: bool = False, current_idx: int = 0, total_slides: int = 1):
    html = ""
    if config.show_dots and total_slides > 1:
        dots = ""
        for i in range(total_slides):
            opacity = "1.0" if i == current_idx else "0.3"
            dots += f'<div style="width: 8px; height: 8px; border-radius: 50%; background: {config.ui_color}; opacity: {opacity}; margin: 0 4px;"></div>'
        html += f'<div style="position: absolute; bottom: 5%; left: 50%; transform: translateX(-50%); display: flex;">{dots}</div>'
    if config.show_swipe and not is_last_slide:
        html += f'<div style="position: absolute; right: 5%; top: 50%; transform: translateY(-50%); color: {config.ui_color}; font-size: 32px; font-weight: bold; opacity: 0.8; font-family: sans-serif;">›</div>'
    return html

def generate_html_single(slide: SlideContext, config: CarouselConfig, current_idx: int, total_slides: int):
    elements_html = render_elements(slide)
    ui_html = render_retention_ui(config, current_idx == total_slides - 1, current_idx, total_slides)
    return f"""
    <!DOCTYPE html><html><head>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Gemunu+Libre:wght@400;700&family=Mate:ital,wght@0,400;0,400i;1,400;1,400i&family=Montserrat:wght@400;700&family=Pacifico&family=Inter:wght@400;700&display=swap" rel="stylesheet">
        <style>body {{ margin: 0; padding: 0; background-color: {config.theme_bg}; height: 100vh; width: 100vw; overflow: hidden; position: relative; }}</style>
    </head><body>{elements_html}{ui_html}</body></html>
    """

async def run_preview(config: CarouselConfig):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-web-security", "--allow-file-access-from-files"])
        w, h = get_dimensions(config.ratio)
        page = await browser.new_page(viewport={"width": w, "height": h})
        if len(config.slides) == 0:
            print("[ERROR] No slides provided")
            sys.exit(1)
            
        idx = config.preview_idx if config.preview_idx < len(config.slides) else 0
        html = generate_html_single(config.slides[idx], config, idx, len(config.slides))
        await page.set_content(html, wait_until="load")
        
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        
        await page.screenshot(path=path, type="png")
        await page.close()
        await browser.close()
        print(f"[PREVIEW_READY] {path}")

async def run_render(config: CarouselConfig):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-web-security", "--allow-file-access-from-files"])
        w, h = get_dimensions(config.ratio)
        page = await browser.new_page(viewport={"width": w, "height": h})
        
        multi_html = "<!DOCTYPE html><html><head><style>"
        multi_html += "@page { size: " + f"{w}px {h}px" + "; margin: 0; }"
        multi_html += "body { margin: 0; padding: 0; }"
        multi_html += ".slide { width: " + f"{w}px; height: {h}px;" + " page-break-after: always; position: relative; overflow: hidden; background-color: " + config.theme_bg + "; }"
        multi_html += "</style>"
        multi_html += '<link href="https://fonts.googleapis.com/css2?family=Gemunu+Libre:wght@400;700&family=Mate:ital,wght@0,400;0,400i;1,400;1,400i&family=Montserrat:wght@400;700&family=Pacifico&family=Inter:wght@400;700&display=swap" rel="stylesheet"></head><body>'
        
        for idx, slide in enumerate(config.slides):
            elements_html = render_elements(slide)
            ui_html = render_retention_ui(config, idx == len(config.slides) - 1, idx, len(config.slides))
            multi_html += f'<div class="slide">{elements_html}{ui_html}</div>'
            
        multi_html += "</body></html>"
        
        await page.set_content(multi_html, wait_until="load")
        
        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        
        await page.pdf(path=path, print_background=True, width=f"{w}px", height=f"{h}px")
        await page.close()
        await browser.close()
        print(f"[RENDER_READY] {path}")

def main():
    log_file = os.path.join(tempfile.gettempdir(), "carousel_engine_debug.log")
    with open(log_file, "a", encoding="utf-8") as lf:
        lf.write(f"\\n--- STARTING CAROUSEL ENGINE ---\\n")
        lf.write(f"ARGS: {sys.argv}\\n")
    
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
    if len(sys.argv) < 3:
        with open(log_file, "a", encoding="utf-8") as lf:
            lf.write("ERROR: Not enough args\\n")
        print("Usage: python carousel_engine.py <action: preview|render> <config_json>")
        sys.exit(1)
        
    action = sys.argv[1]
    options_json = sys.argv[2]
    
    # Allow passing file path if JSON is too large for argv
    if options_json.endswith('.json') and os.path.exists(options_json):
        with open(options_json, 'r', encoding='utf-8') as f:
            options_json = f.read()
            
    try:
        data = json.loads(options_json)
        config = CarouselConfig(**data)
    except Exception as e:
        with open(log_file, "a", encoding="utf-8") as lf:
            lf.write(f"JSON PARSE ERROR: {e}\\n")
            lf.write(f"RAW JSON: {options_json}\\n")
        print(f"[ERROR] Failed to parse JSON: {e}")
        sys.exit(1)
        
    try:
        if action == "preview":
            asyncio.run(run_preview(config))
        elif action == "render":
            asyncio.run(run_render(config))
        else:
            with open(log_file, "a", encoding="utf-8") as lf:
                lf.write(f"ERROR: Unknown action: {action}\\n")
            print(f"[ERROR] Unknown action: {action}")
            sys.exit(1)
        with open(log_file, "a", encoding="utf-8") as lf:
            lf.write(f"SUCCESS: Completed action {action}\\n")
    except Exception as e:
        import traceback
        with open(log_file, "a", encoding="utf-8") as lf:
            lf.write(f"FATAL EXCEPTION in run: {e}\\n{traceback.format_exc()}\\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
