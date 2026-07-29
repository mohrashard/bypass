import re
with open(r'ai_engine\pipeline.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove the engine backend string matching
start_idx = content.find("    engine_backend = options.get('stabilizerBackend', 'cpu')")
end_idx = content.find("    # Fix OMP error when using PyTorch + OpenCV")

if start_idx != -1 and end_idx != -1:
    new_header = '''    print("[⚙️] Booting AI Facial Anchor Stabilizer (Micro-Shock Absorber CPU) v2...")\n'''
    content = content[:start_idx] + new_header + content[end_idx:]

# Remove the GPU branching logic entirely
gpu_branch_start = content.find("        if engine_backend == 'gpu':")
cpu_branch_start = content.find("        if engine_backend == 'cpu':")
cpu_branch_end = content.find("            import mediapipe as mp")

if gpu_branch_start != -1 and cpu_branch_start != -1:
    # Just remove the if-else and un-indent the mediapipe code? No, I can just replace the if statements
    # with a single block that has no `if` check, but wait, it's easier to just strip the gpu block.
    
    # We want to replace from `if engine_backend == 'gpu':` all the way to `if engine_backend == 'cpu':`
    # with nothing.
    content = content[:gpu_branch_start] + content[cpu_branch_end:]
    
    # Then we have `            import mediapipe as mp` which has 12 spaces.
    # It used to be inside `if engine_backend == 'cpu':`
    # Let's just leave it indented, it doesn't hurt syntax to have an extra indented block if we put it inside a dummy if, or we can just un-indent it.
    # Actually, Python requires correct indentation. We should un-indent the mediapipe block.
    
    # But wait, it's easier to use a regex to un-indent the mediapipe block.
    # Let's just do:
    # Find the mediapipe block
    mp_start = content.find("            import mediapipe as mp")
    mp_end = content.find("        cap.release()", mp_start)
    
    mp_block = content[mp_start:mp_end]
    # Un-indent by 4 spaces
    mp_block_unindented = "\n".join([line[4:] if line.startswith("    ") else line for line in mp_block.split("\n")])
    
    content = content[:mp_start] + mp_block_unindented + content[mp_end:]

with open(r'ai_engine\pipeline.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Removed slow PyTorch tracker!")
