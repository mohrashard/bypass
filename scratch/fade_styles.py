import re

file_path = r"c:\Projects\capcut-bypass\ai_engine\pipeline.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# We want to replace the `premiumSubjectShadow` logic so it scales down with progress.
# Specifically in the drop-in effects.

replacement = """            // ── AFTER EFFECTS PARALLAX BACKGROUND ──
            // Creates a cinematic Z-space push-in while pulling focus, blending back to normal
            let blendOut = easeOutQuint(Math.max(0, (progress - 0.5) * 2)); // Fades from 0 to 1 in the second half
            let bgScale = 1.05 + ((1 - blendOut) * 0.05); // Smooth subtle zoom
            let bgBlur = (1 - easeOutQuint(progress)) * 12; // Focus pull from blurry to sharp
            bg.style.transform = `scale(${bgScale})`;
            bg.style.filter = `blur(${bgBlur}px) brightness(${0.6 + progress * 0.4})`;
            
            // ── PREMIUM SUBJECT BASE STYLE ──
            // The shadow tightens and fades as the subject lands, perfectly stitching into the main video
            let shadowSpread = (1 - blendOut) * 60;
            let shadowOpacity = (1 - blendOut) * 0.9;
            let rimOpacity = (1 - blendOut) * 0.15;
            let contrastBoost = 1.0 + (1 - blendOut) * 0.05;
            let premiumSubjectShadow = `drop-shadow(0px 30px ${shadowSpread}px rgba(0, 0, 0, ${shadowOpacity})) drop-shadow(0px 0px 15px rgba(255, 255, 255, ${rimOpacity})) contrast(${contrastBoost})`;"""

content = re.sub(
    r"// ── AFTER EFFECTS PARALLAX BACKGROUND ──.*?let premiumSubjectShadow = [^\n]+;",
    replacement,
    content,
    flags=re.DOTALL
)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("SUCCESS")
