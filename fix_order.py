with open(r'ai_engine\pipeline.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
sandwich_lines = []
in_sandwich = False

for line in lines:
    if line.strip() == 'if options.get("textBehindSubject") and options.get("_sandwich_fg"):':
        in_sandwich = True
        sandwich_lines.append(line)
    elif in_sandwich:
        sandwich_lines.append(line)
        if line.strip() == '': # End of block or we can just capture the next line
            pass
        if 'current_video = stage_composite_sandwich' in line:
            in_sandwich = False
    else:
        new_lines.append(line)

# Now find where to insert the sandwich_lines
insert_idx = -1
for i, line in enumerate(new_lines):
    if line.strip() == 'if options.get("cinematicColor"):':
        insert_idx = i
        break

if insert_idx != -1 and sandwich_lines:
    final_lines = new_lines[:insert_idx] + sandwich_lines + ['\n'] + new_lines[insert_idx:]
    with open(r'ai_engine\pipeline.py', 'w', encoding='utf-8') as f:
        f.writelines(final_lines)
    print("Orchestration order fixed!")
else:
    print("Could not find insertion point or sandwich lines!")
