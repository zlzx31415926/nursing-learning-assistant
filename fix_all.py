lines = open(r'C:\Users\张林子翔\Desktop\学习助手\学习助手.py', encoding='utf-8').readlines()

# Keep lines 0-424, replace 425-472 with clean code, keep 473+
clean_block = [
    '请输出完整的 Markdown 格式学习材料。"""\n',
    '    return call_deepseek(prompt, SYSTEM_PROMPT, max_tokens=8000, progress_placeholder=progress_placeholder)\n',
    '\n',
    '\n',
]

new_lines = lines[:425] + clean_block + lines[473:]
with open(r'C:\Users\张林子翔\Desktop\学习助手\学习助手.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f'Lines: {len(lines)} -> {len(new_lines)}')
