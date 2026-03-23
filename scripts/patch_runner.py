import re

with open("app/services/automation_runner.py", "r") as f:
    original = f.read()

with open("scripts/new_runner.py", "r") as f:
    new_func = f.read()

# Find the start of run_automation_once
start_idx = original.find("def run_automation_once(db: Session, automation_id: int)")

if start_idx != -1:
    patched = original[:start_idx] + new_func
    with open("app/services/automation_runner.py", "w") as f:
        f.write(patched)
    print("Patched successfully")
else:
    print("Could not find function signature")
