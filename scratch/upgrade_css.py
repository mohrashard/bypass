import re

file_path = r"c:\Projects\capcut-bypass\ai_engine\pipeline.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

pattern = r"html_template = f\"\"\"<!DOCTYPE html>.*?</html>\"\"\""

new_html = """html_template = f\"\"\"<!DOCTYPE html>
    <html>
    <head>
    <meta charset="UTF-8">
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      body {{ width: {width}px; height: {height}px; background: #000; overflow: hidden; position: relative; }}
      
      .layer {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; transform-origin: center center; }}
      
      /* Background enhancements */
      #bg {{ z-index: 1; will-change: transform, filter; }}
      #bg-overlay {{
          position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 2;
          background: radial-gradient(circle at center, transparent 20%, rgba(0,0,0,0.85) 100%);
          mix-blend-mode: multiply;
      }}
      
      #subject-container {{ z-index: 10; position: absolute; top: 0; left: 0; width: 100%; height: 100%; perspective: 1500px; }}
      
      /* The base subject */
      #subject {{ width: 100%; height: 100%; object-fit: cover; will-change: transform, filter; transform-style: preserve-3d; }}
      
      /* The Echo and Glitch Clones */
      .glitch-clone {{ 
         position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; 
         opacity: 0; will-change: transform, filter, opacity; 
      }}
      
      /* Frame 1: The X-Ray Invert Layer */
      #xray-layer {{
          position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover;
          mix-blend-mode: exclusion; /* Forces the raw CapCut negative look */
          filter: invert(1) contrast(3.5) saturate(0) brightness(1.8);
          opacity: 0; z-index: 15;
      }}
      
      #cinematic-flash {{ 
         position: absolute; top: 0; left: 0; width: 100%; height: 100%; 
         background: radial-gradient(circle at 50% 30%, rgba(255, 255, 255, 1) 0%, rgba(255,255,255,0) 80%);
         mix-blend-mode: overlay; opacity: 0; z-index: 20; pointer-events: none;
      }}
    </style>
    </head>
    <body>
      <img id="bg" class="layer" src="data:image/jpeg;base64,{bg_b64}">
      <div id="bg-overlay"></div>
      <div id="cinematic-flash"></div>
      
      <div id="subject-container">
        <img id="clone1" class="glitch-clone" src="data:image/png;base64,{sub_b64}">
        <img id="clone2" class="glitch-clone" src="data:image/png;base64,{sub_b64}">
        <img id="clone3" class="glitch-clone" src="data:image/png;base64,{sub_b64}">
        
        <img id="rgb-red" class="glitch-clone" style="mix-blend-mode: screen;" src="data:image/png;base64,{sub_b64}">
        <img id="rgb-cyan" class="glitch-clone" style="mix-blend-mode: screen;" src="data:image/png;base64,{sub_b64}">
        
        <img id="xray-layer" src="data:image/png;base64,{sub_b64}">
        
        <img id="subject" src="data:image/png;base64,{sub_b64}">
      </div>

      <script>
        function renderFrame(progress, hookType) {{
            const bg = document.getElementById('bg');
            const sub = document.getElementById('subject');
            const c1 = document.getElementById('clone1');
            const c2 = document.getElementById('clone2');
            const c3 = document.getElementById('clone3');
            const rRed = document.getElementById('rgb-red');
            const rCyan = document.getElementById('rgb-cyan');
            const xray = document.getElementById('xray-layer');
            const cflash = document.getElementById('cinematic-flash');

            const easeOutExpo = t => t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
            const easeOutQuint = t => 1 - Math.pow(1 - t, 5);
            
            // ── AFTER EFFECTS PARALLAX BACKGROUND ──
            // Creates a cinematic Z-space push-in while pulling focus
            let bgScale = 1.05 + (progress * 0.05); // Smooth subtle zoom
            let bgBlur = (1 - easeOutQuint(progress)) * 12; // Focus pull from blurry to sharp
            bg.style.transform = `scale(${{bgScale}})`;
            bg.style.filter = `blur(${{bgBlur}}px) brightness(${{0.6 + progress * 0.4}})`;
            
            // ── PREMIUM SUBJECT BASE STYLE ──
            // Gives the speaker a 3D pop off the background + high-end contrast
            let premiumSubjectShadow = `drop-shadow(0px 30px 60px rgba(0, 0, 0, 0.9)) drop-shadow(0px 0px 15px rgba(255, 255, 255, 0.15)) contrast(1.05) saturate(1.1)`;

            if (hookType === 'capcut_drop') {{
                if (progress < 0.15) {{
                    let noiseX = (Math.random() - 0.5) * 50;
                    let noiseY = (Math.random() - 0.5) * 20;
                    
                    sub.style.opacity = 0; 
                    
                    xray.style.opacity = 0.9;
                    xray.style.transform = `scale(1.12) translate(${{noiseX}}px, ${{noiseY}}px)`;
                    
                    rRed.style.opacity = 0.9;
                    rRed.style.transform = `scale(1.15) translateX(35px) translateY(-10px)`;
                    rRed.style.filter = `drop-shadow(25px 0 0 red) hue-rotate(-45deg) contrast(1.2)`;
                    
                    rCyan.style.opacity = 0.9;
                    rCyan.style.transform = `scale(1.15) translateX(-35px) translateY(10px)`;
                    rCyan.style.filter = `drop-shadow(-25px 0 0 cyan) hue-rotate(45deg) contrast(1.2)`;
                    
                    cflash.style.opacity = 0.4;
                }}
                else if (progress >= 0.15 && progress < 0.50) {{
                    let dropP = (progress - 0.15) / 0.35; 
                    let e = easeOutExpo(dropP);
                    let yOff = (1 - e) * -900; 
                    let scaleBoost = 1.0 + (1 - e) * 0.2;
                    
                    xray.style.opacity = 0; rRed.style.opacity = 0; rCyan.style.opacity = 0;
                    
                    sub.style.opacity = 1;
                    sub.style.transform = `translateY(${{yOff}}px) scale(${{scaleBoost}})`;
                    sub.style.filter = `${{premiumSubjectShadow}} brightness(${{1.0 + (1-e)*0.5}})`;
                    
                    c1.style.opacity = (1 - e) * 0.7;
                    c1.style.transform = `translateY(${{yOff - 120}}px) scaleY(${{1.1 + (1-e)*0.2}}) scaleX(${{scaleBoost}})`;
                    c1.style.filter = `blur(10px) opacity(0.8) brightness(1.4) drop-shadow(0 20px 20px cyan)`;
                    
                    c2.style.opacity = (1 - e) * 0.4;
                    c2.style.transform = `translateY(${{yOff - 250}}px) scaleY(${{1.2 + (1-e)*0.3}}) scaleX(${{scaleBoost}})`;
                    c2.style.filter = `blur(20px) opacity(0.5) brightness(1.2) drop-shadow(0 20px 20px magenta)`;
                    
                    cflash.style.opacity = 0;
                }}
                else {{
                    sub.style.opacity = 1;
                    sub.style.transform = `translateY(0) scale(1)`; 
                    // Preserve the premium look after the drop
                    sub.style.filter = premiumSubjectShadow; 
                    
                    c1.style.opacity = 0; c2.style.opacity = 0;
                    rRed.style.opacity = 0; rCyan.style.opacity = 0; xray.style.opacity = 0;
                    cflash.style.opacity = 0;
                }}
            }}
            
            else if (hookType === 'drop_in') {{
                let decay = easeOutExpo(progress);
                let yOff = (1 - decay) * -1000; 
                let scaleY = 1.0 + ((1 - decay) * 0.8);
                let scaleX = 1.0 - ((1 - decay) * 0.1);
                let bloom = 1 - progress; 
                
                sub.style.transform = `translateY(${{yOff}}px) scale(${{scaleX}}, ${{scaleY}})`;
                sub.style.filter = `${{premiumSubjectShadow}} drop-shadow(0px 0px ${{40*bloom}}px rgba(255, 255, 255, ${{bloom*0.8}})) brightness(${{1 + bloom*0.4}})`;
                
                c1.style.opacity = (1 - decay) * 0.6;
                c1.style.transform = `translateY(${{yOff - 80}}px) scale(${{scaleX}}, ${{scaleY}})`;
                c1.style.filter = `blur(8px) brightness(1.5)`;

                c2.style.opacity = (1 - decay) * 0.3;
                c2.style.transform = `translateY(${{yOff - 160}}px) scale(${{scaleX}}, ${{scaleY}})`;
                c2.style.filter = `blur(12px) brightness(1.2)`;
                if(c3) c3.style.opacity = 0;
                cflash.style.opacity = bloom * 0.9;
            }}
            
            else if (hookType === 'flash_drop') {{
                let decay = easeOutExpo(progress);
                let zOff = (1 - decay) * 600; 
                let yOff = (1 - decay) * -200;
                let bloom = 1 - progress;
                
                sub.style.transform = `translateY(${{yOff}}px) translateZ(${{zOff}}px)`;
                sub.style.filter = `${{premiumSubjectShadow}} drop-shadow(0px 0px ${{50*bloom}}px rgba(255, 240, 200, ${{bloom}})) brightness(${{1 + bloom*0.5}})`;

                let burst = progress / 0.5;
                if (burst <= 1) {{
                    c1.style.opacity = 1 - burst;
                    c1.style.transform = `scale(${{1.0 + burst*0.2}})`;
                    c1.style.filter = `brightness(1.5) blur(4px)`;
                }} else {{
                    c1.style.opacity = 0;
                }}
                c2.style.opacity = 0; if(c3) c3.style.opacity = 0;
                cflash.style.opacity = bloom * 0.9;
            }}

            else if (hookType === 'flash') {{
                let decay = easeOutExpo(progress);
                let bloom = 1 - progress;
                
                let scale = 1.0 + (progress * 0.05); 
                sub.style.transform = `scale(${{scale}})`;
                
                sub.style.filter = `${{premiumSubjectShadow}} drop-shadow(0px 0px ${{60*bloom}}px rgba(255, 255, 255, ${{bloom*0.9}})) brightness(${{1 + bloom*0.6}})`;
                
                c1.style.opacity = 0; c2.style.opacity = 0; if(c3) c3.style.opacity = 0;
                cflash.style.opacity = bloom * 0.9;
            }}

            else if (hookType === 'glitch') {{
                let decay = 1 - progress; 
                let bloom = 1 - progress;
                
                if (decay > 0.05) {{
                    let isHard = Math.random() > 0.5;
                    let shift = 30 * decay;
                    
                    c1.style.opacity = 0.7 * decay;
                    c1.style.transform = `translateX(${{shift}}px)`;
                    c1.style.filter = `hue-rotate(-90deg) saturate(3) brightness(1.2)`;
                    c1.style.clipPath = `inset(${{Math.random()*80}}% 0 ${{Math.random()*80}}% 0)`;

                    c2.style.opacity = 0.7 * decay;
                    c2.style.transform = `translateX(${{-shift}}px)`;
                    c2.style.filter = `hue-rotate(90deg) saturate(3) brightness(1.2)`;
                    c2.style.clipPath = `inset(${{Math.random()*80}}% 0 ${{Math.random()*80}}% 0)`;

                    sub.style.opacity = 1;
                    sub.style.transform = `translate(${{(Math.random()-0.5)*15*decay}}px, 0px)`;
                    
                    if (isHard) sub.style.clipPath = `polygon(0 ${{Math.random()*15}}%, 100% ${{Math.random()*15}}%, 100% 100%, 0 100%)`;
                    else sub.style.clipPath = 'none';
                }} else {{
                    c1.style.opacity = 0; c2.style.opacity = 0;
                    sub.style.opacity = 1; sub.style.transform = 'none';
                    sub.style.clipPath = 'none';
                }}
                
                sub.style.filter = `${{premiumSubjectShadow}} drop-shadow(0px 0px ${{30*bloom}}px rgba(0, 255, 255, ${{bloom*0.5}})) brightness(${{1 + bloom*0.3}})`;
                if(c3) c3.style.opacity = 0;
                cflash.style.opacity = bloom * 0.9;
            }}

            else if (hookType === 'impact') {{
                let decay = 1 - easeOutExpo(progress);
                let bloom = 1 - progress;
                
                let scale = 1.0 + (decay * 0.2);
                let shakeX = (Math.random() - 0.5) * 30 * decay;
                let shakeY = (Math.random() - 0.5) * 30 * decay;
                
                sub.style.transform = `translate(${{shakeX}}px, ${{shakeY}}px) scale(${{scale}})`;
                sub.style.filter = `${{premiumSubjectShadow}} drop-shadow(0px 0px ${{50*bloom}}px rgba(255, 200, 200, ${{bloom*0.6}})) brightness(${{1 + bloom*0.4}})`;
                
                c1.style.opacity = decay * 0.6;
                c1.style.transform = `translate(${{shakeX - 15*decay}}px, ${{shakeY}}px) scale(${{scale}})`;
                c1.style.filter = `hue-rotate(-90deg) brightness(1.2)`;

                c2.style.opacity = decay * 0.6;
                c2.style.transform = `translate(${{shakeX + 15*decay}}px, ${{shakeY}}px) scale(${{scale}})`;
                c2.style.filter = `hue-rotate(90deg) brightness(1.2)`;
                
                if(c3) c3.style.opacity = 0;
                cflash.style.opacity = bloom * 0.9;
            }}
        }}
      </script>
    </body>
    </html>\"\"\""""

new_content = re.sub(pattern, new_html, content, flags=re.DOTALL)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(new_content)

print("SUCCESS")
