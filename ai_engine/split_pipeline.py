import os
import re

with open('pipeline.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

def get_line_index(pattern):
    for i, line in enumerate(lines):
        if re.search(pattern, line):
            return i
    return len(lines)

# Define section boundaries based on comments and function defs
sections = {
    "audio.py": ["def process_with_ai_stack", "def stage_cinematic_color"],
    "color.py": ["def stage_cinematic_color", "def stage_burn_captions"],
    "captions_en.py": ["def stage_burn_captions", "def get_perfect_sinhala_transcript"],
    "captions_si.py": ["def get_perfect_sinhala_transcript", "def stage_bottom_glow"],
    "fx.py": ["def stage_bottom_glow", "def export_captions_overlay_en"],
    "export.py": ["def export_captions_overlay_en", "def run_pipeline"]
}

os.makedirs('modules', exist_ok=True)

# Write core modules
for mod_name, bounds in sections.items():
    start_idx = get_line_index(bounds[0])
    end_idx = get_line_index(bounds[1])
    
    # Extract lines
    mod_lines = lines[start_idx:end_idx]
    
    # Prepend common imports
    header = "import os, sys, json, subprocess, shutil\nfrom PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageChops\n\n"
    
    with open(f"modules/{mod_name}", 'w', encoding='utf-8') as out:
        out.write(header + "".join(mod_lines))

# Write new pipeline.py
header_lines = lines[:get_line_index("def process_with_ai_stack")]
footer_lines = lines[get_line_index("def run_pipeline"):]

new_pipeline = "".join(header_lines) + """
from modules.audio import process_with_ai_stack, stage_remove_silence, extract_audio, mux_audio, stage_studio_audio
from modules.color import stage_cinematic_color
from modules.captions_en import stage_burn_captions
from modules.captions_si import get_perfect_sinhala_transcript, align_phrases_to_whisper, stage_burn_sinhala_captions
from modules.fx import stage_bottom_glow, stage_background_fx, stage_semantic_zoom
from modules.export import export_captions_overlay_en, export_captions_overlay_si
""" + "\n" + "".join(footer_lines)

with open('pipeline.py', 'w', encoding='utf-8') as out:
    out.write(new_pipeline)

print("Split completed successfully!")
