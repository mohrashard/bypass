import re

file_path = r"c:\Projects\capcut-bypass\ai_engine\pipeline.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

funcs = re.findall(r"def stage_\w+\(", content)
print(funcs)
