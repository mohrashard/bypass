with open('temp_pipeline_old.py', 'r', encoding='utf-16le', errors='replace') as f:
    content = f.read()

content = content.replace('ΓÜÖ∩╕Å', '⚙️').replace('ΓÜá∩╕Å', '⚠️').replace('Γ£à', '✅').replace('Γ¥î', '❌')
import re
content = re.sub(r'ΓöÇ+', '─', content)

with open(r'ai_engine\pipeline.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Pipeline recovered!")
