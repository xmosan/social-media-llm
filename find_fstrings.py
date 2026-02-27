import ast
import os

def check_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        source = f.read()
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as e:
        print(f"SyntaxError in {filepath}: {e}")
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for value in node.values:
                if isinstance(value, ast.FormattedValue):
                    expr_source = ast.get_source_segment(source, value.value)
                    if expr_source and '\\' in expr_source:
                        print(f"File {filepath} line {value.lineno}: Backslash in f-string expression: {{{expr_source}}}")

for root, _, files in os.walk('app'):
    for file in files:
        if file.endswith('.py'):
            check_file(os.path.join(root, file))
