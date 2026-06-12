import re

file_path = r"c:\Projects\capcut-bypass\ai_engine\pipeline.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Add CSS for cinematic-flash
css_to_add = """      .glitch-clone {{ 
         position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; 
         mix-blend-mode: screen; opacity: 0; will-change: transform, filter, opacity; transform-style: preserve-3d;
      }}
      #cinematic-flash {{ 
         position: absolute; top: 0; left: 0; width: 100%; height: 100%; 
         background: radial-gradient(circle at 50% 50%, rgba(255, 250, 230, 0.9) 0%, rgba(255, 200, 150, 0.4) 40%, rgba(0,0,0,0) 80%);
         mix-blend-mode: screen; opacity: 0; z-index: 20; pointer-events: none; will-change: opacity, transform;
      }}"""
content = re.sub(r'      \.glitch-clone \{\{.*?      \}\}', css_to_add, content, flags=re.DOTALL)

# Add HTML for cinematic-flash
html_to_add = """      <img id="bg" class="layer" src="data:image/jpeg;base64,{bg_b64}">
      <div id="cinematic-flash"></div>"""
content = content.replace('      <img id="bg" class="layer" src="data:image/jpeg;base64,{bg_b64}">', html_to_add)

# Add JS element
js_elem = """            const c3 = document.getElementById('clone3');
            const cflash = document.getElementById('cinematic-flash');"""
content = content.replace("            const c3 = document.getElementById('clone3');", js_elem)

# Add opacity to drop_in
content = content.replace("c3.style.opacity = 0;\n            }}", "c3.style.opacity = 0;\n                cflash.style.opacity = bloom * 0.9;\n            }}")

# Add opacity to flash_drop
content = content.replace("c2.style.opacity = 0; c3.style.opacity = 0;\n            }}", "c2.style.opacity = 0; c3.style.opacity = 0;\n                cflash.style.opacity = bloom * 0.95;\n            }}")

# Add opacity to flash
content = content.replace("c1.style.opacity = 0; c2.style.opacity = 0; c3.style.opacity = 0;\n            }}", "c1.style.opacity = 0; c2.style.opacity = 0; c3.style.opacity = 0;\n                cflash.style.opacity = bloom * 1.0;\n            }}")

# Add opacity to glitch
content = content.replace("c3.style.opacity = 0;\n            }}", "c3.style.opacity = 0;\n                cflash.style.opacity = bloom * 0.5;\n            }}")

# Add opacity to impact
content = content.replace("c3.style.opacity = 0;\n            }}", "c3.style.opacity = 0;\n                cflash.style.opacity = bloom * 0.85;\n            }}")


with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("SUCCESS")
