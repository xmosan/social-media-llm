import re

def check_js_syntax(file_path):
    content = open(file_path).read()
    js_blocks = re.findall(r'<script>(.*?)</script>', content, re.DOTALL)
    
    for i, js in enumerate(js_blocks):
        print(f"Checking JS block {i}...")
        stack = []
        mapping = {')': '(', '}': '{', ']': '['}
        line_no = 1
        for char in js:
            if char == '\n':
                line_no += 1
            if char in '({[':
                stack.append((char, line_no))
            elif char in ')}]':
                if not stack:
                    print(f"Extra closing {char} at line {line_no}")
                    return False
                top, top_line = stack.pop()
                if mapping[char] != top:
                    print(f"Mismatched {char} at line {line_no} (expected {top} from line {top_line})")
                    return False
        if stack:
            # Check for strings/template literals which might contain brackets
            print("Warning: This simple checker doesn't handle strings. Checking for obvious leaks.")
            top, top_line = stack.pop()
            print(f"Unclosed {top} from line {top_line}")
            return False
    print("JS syntax (brackets) looks good!")
    return True

check_js_syntax('/Users/hamoodi/new code 2-6/Social Media LLM/app/routes/ui_assets.py')
