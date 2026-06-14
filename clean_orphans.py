lines = open(r'C:\Users\张林子翔\Desktop\学习助手\学习助手.py', encoding='utf-8').readlines()

# Find all "请输出完整的 Markdown 格式学习材料。""" lines
new_lines = []
skip_until_python = False
for i, line in enumerate(lines):
    stripped = line.strip()

    # After a triple-quote that closes the prompt, check if next line is orphaned Chinese
    if skip_until_python:
        # Skip until we find a Python code line (starts with def, return, #, empty, or contains =)
        if stripped.startswith('def ') or stripped.startswith('return ') or stripped.startswith('#') or stripped == '' or 'call_deepseek' in stripped or 'SYSTEM_PROMPT' in stripped:
            skip_until_python = False
            new_lines.append(line)
        # else skip this orphaned line
        continue

    if stripped == '"""' and i > 0 and '学习材料' in lines[i-1]:
        new_lines.append(line)
        skip_until_python = True
        continue

    new_lines.append(line)

with open(r'C:\Users\张林子翔\Desktop\学习助手\学习助手.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f'Lines before: {len(lines)}, after: {len(new_lines)}')
print('Cleaned.')
