import os
import re

with open('c:/Projects/capcut-bypass/ai_engine/pipeline.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(r'print\(f"\n\[🎬\] STARTING LOCAL RENDER ENGINE: \{os\.path\.basename\(video_path\)\}\n"\)', r'print(f"\\n[🎬] STARTING LOCAL RENDER ENGINE: {os.path.basename(video_path)}\\n")', content)
content = re.sub(r'print\("\n\[🎬\] RUNNING AI IMAGE ENHANCEMENT\.\.\."\)', r'print("\\n[🎬] RUNNING AI IMAGE ENHANCEMENT...")', content)
content = re.sub(r'print\(f"\n\[🚀\] PIPELINE COMPLETE\. Final output: \{result\}"\)', r'print(f"\\n[🚀] PIPELINE COMPLETE. Final output: {result}")', content)
content = re.sub(r'print\("\n\[🎬\] GENERATING SMART PROMPT\.\.\."\)', r'print("\\n[🎬] GENERATING SMART PROMPT...")', content)

with open('c:/Projects/capcut-bypass/ai_engine/pipeline.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("SUCCESS")
