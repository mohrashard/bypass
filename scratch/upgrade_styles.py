import os
import re

file_path = r"c:\Projects\capcut-bypass\ai_engine\pipeline.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Pattern to find the JS block inside html_template
pattern = r"            if \(hookType === 'drop_in'\) \{\{.*?            \}\}\n        \}\}"

replacement = r"""            if (hookType === 'drop_in') {{
                // Cinematic "Dropped from Sky"
                let decay = easeOutExpo(progress);
                let yOff = (1 - decay) * -1000; 
                let scaleY = 1.0 + ((1 - decay) * 0.8);
                let scaleX = 1.0 - ((1 - decay) * 0.1);
                let bloom = 1 - progress; 
                
                sub.style.transform = `translateY(${yOff}px) scale(${scaleX}, ${scaleY})`;
                sub.style.filter = `drop-shadow(0px 30px 40px rgba(0, 0, 0, 0.8)) drop-shadow(0px 0px ${40*bloom}px rgba(255, 255, 255, ${bloom*0.8})) brightness(${1 + bloom*0.4})`;
                
                c1.style.opacity = (1 - decay) * 0.6;
                c1.style.transform = `translateY(${yOff - 80}px) scale(${scaleX}, ${scaleY})`;
                c1.style.filter = `blur(8px) brightness(1.5)`;

                c2.style.opacity = (1 - decay) * 0.3;
                c2.style.transform = `translateY(${yOff - 160}px) scale(${scaleX}, ${scaleY})`;
                c2.style.filter = `blur(12px) brightness(1.2)`;
                c3.style.opacity = 0;
            }}
            
            else if (hookType === 'flash_drop') {{
                let decay = easeOutExpo(progress);
                let zOff = (1 - decay) * 600; // Deep 3D perspective 
                let yOff = (1 - decay) * -200;
                let bloom = 1 - progress;
                
                sub.style.transform = `translateY(${yOff}px) translateZ(${zOff}px)`;
                sub.style.filter = `drop-shadow(0px 20px 40px rgba(0,0,0,0.7)) drop-shadow(0px 0px ${50*bloom}px rgba(255, 240, 200, ${bloom})) brightness(${1 + bloom*0.5})`;

                // Impact burst ring
                let burst = progress / 0.5;
                if (burst <= 1) {{
                    c1.style.opacity = 1 - burst;
                    c1.style.transform = `scale(${1.0 + burst*0.2})`;
                    c1.style.filter = `brightness(1.5) blur(4px)`;
                }} else {{
                    c1.style.opacity = 0;
                }}
                c2.style.opacity = 0; c3.style.opacity = 0;
            }}

            else if (hookType === 'flash') {{
                let decay = easeOutExpo(progress);
                let bloom = 1 - progress;
                
                let scale = 1.0 + (progress * 0.05); // Cinematic push-in
                sub.style.transform = `scale(${scale})`;
                
                // Heavenly rim light and drop shadow
                sub.style.filter = `drop-shadow(0px 10px 30px rgba(0,0,0,0.5)) drop-shadow(0px 0px ${60*bloom}px rgba(255, 255, 255, ${bloom*0.9})) brightness(${1 + bloom*0.6})`;
                
                c1.style.opacity = 0; c2.style.opacity = 0; c3.style.opacity = 0;
            }}

            else if (hookType === 'glitch') {{
                let decay = 1 - progress; 
                let bloom = 1 - progress;
                
                if (decay > 0.05) {{
                    let isHard = Math.random() > 0.5;
                    let shift = 30 * decay;
                    
                    c1.style.opacity = 0.7 * decay;
                    c1.style.transform = `translateX(${shift}px)`;
                    c1.style.filter = `hue-rotate(-90deg) saturate(3) brightness(1.2)`;
                    c1.style.clipPath = `inset(${Math.random()*80}% 0 ${Math.random()*80}% 0)`;

                    c2.style.opacity = 0.7 * decay;
                    c2.style.transform = `translateX(${-shift}px)`;
                    c2.style.filter = `hue-rotate(90deg) saturate(3) brightness(1.2)`;
                    c2.style.clipPath = `inset(${Math.random()*80}% 0 ${Math.random()*80}% 0)`;

                    sub.style.opacity = 1;
                    sub.style.transform = `translate(${(Math.random()-0.5)*15*decay}px, 0px)`;
                    
                    if (isHard) sub.style.clipPath = `polygon(0 ${Math.random()*15}%, 100% ${Math.random()*15}%, 100% 100%, 0 100%)`;
                    else sub.style.clipPath = 'none';
                }} else {{
                    c1.style.opacity = 0; c2.style.opacity = 0;
                    sub.style.opacity = 1; sub.style.transform = 'none';
                    sub.style.clipPath = 'none';
                }}
                
                sub.style.filter = `drop-shadow(0px 0px ${30*bloom}px rgba(0, 255, 255, ${bloom*0.5})) brightness(${1 + bloom*0.3})`;
                c3.style.opacity = 0;
            }}

            else if (hookType === 'impact') {{
                let decay = 1 - easeOutExpo(progress);
                let bloom = 1 - progress;
                
                let scale = 1.0 + (decay * 0.2);
                let shakeX = (Math.random() - 0.5) * 30 * decay;
                let shakeY = (Math.random() - 0.5) * 30 * decay;
                
                sub.style.transform = `translate(${shakeX}px, ${shakeY}px) scale(${scale})`;
                sub.style.filter = `drop-shadow(0px 20px 40px rgba(0,0,0,0.7)) drop-shadow(0px 0px ${50*bloom}px rgba(255, 200, 200, ${bloom*0.6})) brightness(${1 + bloom*0.4})`;
                
                c1.style.opacity = decay * 0.6;
                c1.style.transform = `translate(${shakeX - 15*decay}px, ${shakeY}px) scale(${scale})`;
                c1.style.filter = `hue-rotate(-90deg) brightness(1.2)`;

                c2.style.opacity = decay * 0.6;
                c2.style.transform = `translate(${shakeX + 15*decay}px, ${shakeY}px) scale(${scale})`;
                c2.style.filter = `hue-rotate(90deg) brightness(1.2)`;
                
                c3.style.opacity = 0;
            }}
        }}"""

new_content, count = re.subn(pattern, replacement, content, flags=re.DOTALL)

if count > 0:
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("SUCCESS")
else:
    print("FAILED TO MATCH")
