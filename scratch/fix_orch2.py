with open('ai_engine/pipeline.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Find the old leftover partial orchestration that sits between stage_fast_stabilize and def run_pipeline
# It starts with '\n\n    # 1. Fast Stabilize' (wrongly indented leftover)
old_partial_marker = '\n    # 1. Fast Stabilize\n'
run_pipeline_marker = '\ndef run_pipeline('

idx_partial = content.find(old_partial_marker)
idx_run_pipeline = content.find(run_pipeline_marker, idx_partial if idx_partial != -1 else 0)

print(f"Partial marker at: {idx_partial}")
print(f"run_pipeline def at: {idx_run_pipeline}")

if idx_partial != -1 and idx_run_pipeline != -1:
    # Cut out the junk between partial and def run_pipeline
    before = content[:idx_partial]
    after = content[idx_run_pipeline:]
    fixed = before + '\n\n' + after
    with open('ai_engine/pipeline.py', 'w', encoding='utf-8') as f:
        f.write(fixed)
    print(f"Fixed. New length: {len(fixed)}")
else:
    # Alternative: find by the indented if options block before def run_pipeline
    # The mangled block starts right after the except block of stage_fast_stabilize
    # which ends with 'return video_path\n\n'
    stab_end = content.rfind('        return video_path\n', 0, idx_run_pipeline)
    print(f"stab_end at: {stab_end}")
    if stab_end != -1:
        before = content[:stab_end + len('        return video_path\n')]
        after = content[idx_run_pipeline:]
        fixed = before + '\n\n' + after
        with open('ai_engine/pipeline.py', 'w', encoding='utf-8') as f:
            f.write(fixed)
        print(f"Fixed via stab_end. New length: {len(fixed)}")
    else:
        print("ERROR: Cannot find fix points")
