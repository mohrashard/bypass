import re

file_path = r"c:\Projects\capcut-bypass\ai_engine\pipeline.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

pattern = r"            if \(hookType === 'drop_in'\) \{\{.*?        \}\}\n      </script>"
match = re.search(pattern, content, flags=re.DOTALL)

if match:
    block = match.group(0)
    # Fix ${var} to ${{var}} to escape Python f-string
    fixed_block = re.sub(r'\$\{([^\{\}]+)\}', r'${{\1}}', block)
    
    new_content = content[:match.start()] + fixed_block + content[match.end():]
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("SUCCESS")
else:
    print("FAILED")
