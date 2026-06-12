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
      
      #bg {{ z-index: 1; }}
      #subject-container {{ z-index: 10; position: absolute; top: 0; left: 0; width: 100%; height: 100%; perspective: 1000px; }}
      
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
          filter: invert(1) contrast(3) saturate(0) brightness(1.5);
          opacity: 0; z-index: 15;
      }}
      
      #cinematic-flash {{ 
         position: absolute; top: 0; left: 0; width: 100%; height: 100%; 
         background: rgba(255, 255, 255, 1);
         mix-blend-mode: overlay; opacity: 0; z-index: 20; pointer-events: none;
      }}
    </style>
    </head>
    <body>
      <img id="bg" class="layer" src="data:image/jpeg;base64,{bg_b64}">
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
            
            // Background is strictly untouched to keep focus on the speaker
            bg.style.transform = 'none';
            bg.style.filter = 'none';
            
            // ─────────────────────────────────────────────────────────────
            // THE CAPCUT HOLOGRAM DROP (Matches your 3 uploaded frames)
            // ─────────────────────────────────────────────────────────────
            if (hookType === 'capcut_drop') {{
                // PHASE 1: FRAME 1 - The X-Ray Glitch (0% to 15% of the animation)
                if (progress < 0.15) {{
                    let noiseX = (Math.random() - 0.5) * 40;
                    
                    sub.style.opacity = 0; // Hide the clean plate entirely
                    
                    // Trigger the aggressive negative inversion look
                    xray.style.opacity = 0.8;
                    xray.style.transform = `scale(1.1) translateX(${{noiseX}}px)`;
                    
                    // Heavy RGB split snapping randomly
                    rRed.style.opacity = 0.9;
                    rRed.style.transform = `scale(1.15) translateX(30px)`;
                    rRed.style.filter = `drop-shadow(20px 0 0 red) hue-rotate(-45deg)`;
                    
                    rCyan.style.opacity = 0.9;
                    rCyan.style.transform = `scale(1.15) translateX(-30px)`;
                    rCyan.style.filter = `drop-shadow(-20px 0 0 cyan) hue-rotate(45deg)`;
                    
                    cflash.style.opacity = 0.3; // Slight ambient flash
                }}
                
                // PHASE 2: FRAME 2 - The Vertical Echo Drop (15% to 50%)
                else if (progress >= 0.15 && progress < 0.50) {{
                    // Normalize progress for this specific window
                    let dropP = (progress - 0.15) / 0.35; 
                    let e = easeOutExpo(dropP);
                    let yOff = (1 - e) * -800; // Falling from above the frame
                    
                    // Turn off the X-Ray/Glitch layers immediately
                    xray.style.opacity = 0;
                    rRed.style.opacity = 0;
                    rCyan.style.opacity = 0;
                    
                    // Main subject falling in
                    sub.style.opacity = 1;
                    sub.style.transform = `translateY(${{yOff}}px) scale(1)`;
                    sub.style.filter = `brightness(1.1)`;
                    
                    // Echo Clones trailing behind (creates the motion blur ghosting from Image 2)
                    c1.style.opacity = (1 - e) * 0.6;
                    c1.style.transform = `translateY(${{yOff - 100}}px) scaleY(1.1)`;
                    c1.style.filter = `blur(8px) opacity(0.7)`;
                    
                    c2.style.opacity = (1 - e) * 0.3;
                    c2.style.transform = `translateY(${{yOff - 220}}px) scaleY(1.2)`;
                    c2.style.filter = `blur(15px) opacity(0.4)`;
                    
                    cflash.style.opacity = 0;
                }}
                
                // PHASE 3: FRAME 3 - The Hard Settle (50% to 100%)
                else {{
                    sub.style.opacity = 1;
                    sub.style.transform = `translateY(0) scale(1)`; // Snapped to baseline
                    sub.style.filter = `none`; // Perfectly clean plate
                    
                    // Kill all clones and effects
                    c1.style.opacity = 0;
                    c2.style.opacity = 0;
                    rRed.style.opacity = 0;
                    rCyan.style.opacity = 0;
                    xray.style.opacity = 0;
                    cflash.style.opacity = 0;
                }}
            }}
            
            else if (hookType === 'drop_in') {{
                // Cinematic "Dropped from Sky"
                let decay = easeOutExpo(progress);
                let yOff = (1 - decay) * -1000; 
                let scaleY = 1.0 + ((1 - decay) * 0.8);
                let scaleX = 1.0 - ((1 - decay) * 0.1);
                let bloom = 1 - progress; 
                
                sub.style.transform = `translateY(${{yOff}}px) scale(${{scaleX}}, ${{scaleY}})`;
                sub.style.filter = `drop-shadow(0px 30px 40px rgba(0, 0, 0, 0.8)) drop-shadow(0px 0px ${{40*bloom}}px rgba(255, 255, 255, ${{bloom*0.8}})) brightness(${{1 + bloom*0.4}})`;
                
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
                let zOff = (1 - decay) * 600; // Deep 3D perspective 
                let yOff = (1 - decay) * -200;
                let bloom = 1 - progress;
                
                sub.style.transform = `translateY(${{yOff}}px) translateZ(${{zOff}}px)`;
                sub.style.filter = `drop-shadow(0px 20px 40px rgba(0,0,0,0.7)) drop-shadow(0px 0px ${{50*bloom}}px rgba(255, 240, 200, ${{bloom}})) brightness(${{1 + bloom*0.5}})`;

                // Impact burst ring
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
                
                let scale = 1.0 + (progress * 0.05); // Cinematic push-in
                sub.style.transform = `scale(${{scale}})`;
                
                // Heavenly rim light and drop shadow
                sub.style.filter = `drop-shadow(0px 10px 30px rgba(0,0,0,0.5)) drop-shadow(0px 0px ${{60*bloom}}px rgba(255, 255, 255, ${{bloom*0.9}})) brightness(${{1 + bloom*0.6}})`;
                
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
                
                sub.style.filter = `drop-shadow(0px 0px ${{30*bloom}}px rgba(0, 255, 255, ${{bloom*0.5}})) brightness(${{1 + bloom*0.3}})`;
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
                sub.style.filter = `drop-shadow(0px 20px 40px rgba(0,0,0,0.7)) drop-shadow(0px 0px ${{50*bloom}}px rgba(255, 200, 200, ${{bloom*0.6}})) brightness(${{1 + bloom*0.4}})`;
                
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
