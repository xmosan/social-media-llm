import re

with open('app/routes/ui_assets.py', 'r') as f:
    text = f.read()

# Extract STUDIO_SCRIPTS_JS contents
match = re.search(r'STUDIO_SCRIPTS_JS = """\n<script>\n(.*?)\n</script>\n"""', text, re.DOTALL)
if match:
    js = match.group(1)
    
    # Check balanced braces
    stack = []
    for i, char in enumerate(js):
        if char == '{':
            stack.append(('{', i))
        elif char == '}':
            if not stack:
                print(f"Error: Unexpected '}}' at index {i}")
            else:
                stack.pop()
    
    if stack:
        for s in stack:
            print(f"Error: Unclosed '{s[0]}' at index {s[1]}")
            # Show context
            start = max(0, s[1] - 50)
            end = min(len(js), s[1] + 50)
            print(f"Context: ... {js[start:end]} ...")
    else:
        print("Braces are balanced in JS.")
else:
    print("Could not find STUDIO_SCRIPTS_JS")
