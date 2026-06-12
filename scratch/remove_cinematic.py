import re

file_path = r"c:\Projects\capcut-bypass\ai_engine\pipeline.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Pattern to remove the entire stage_cinematic_grade block
# Starts with the # 17. CINEMATIC GRADE ENGINE header
# Ends right before # 16. HEADLESS CSS VISUAL HOOK ENGINE
pattern = r"# ─────────────────────────────────────────────────────────────────────────────\n# 17\. CINEMATIC GRADE ENGINE — \"The Pro Look\".*?(?=# 16\. HEADLESS CSS VISUAL HOOK ENGINE)"

new_content = re.sub(pattern, "", content, flags=re.DOTALL)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(new_content)
    
print("SUCCESS")
