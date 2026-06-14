import json, re, os, urllib.request, urllib.error
from pathlib import Path

api_key = Path(r'C:\Users\张林子翔\Desktop\学习助手\api_key.txt').read_text().strip()
print(f"API Key: ***{api_key[-4:]}")

def call(prompt, max_t=3000):
    data = {
        'model': 'deepseek-chat',
        'messages': [{'role': 'system', 'content': '你是护理考试命题专家。'}, {'role': 'user', 'content': prompt}],
        'temperature': 0.7, 'max_tokens': max_t, 'stream': False
    }
    req = urllib.request.Request(
        'https://api.deepseek.com/chat/completions',
        data=json.dumps(data).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'}
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())['choices'][0]['message']['content']

# Find test file
desktop = Path.home() / 'Desktop'
raw = None
fname = ""
for root, dirs, files in os.walk(str(desktop)):
    for f in files:
        if '循环' in f and f.endswith('.txt'):
            fp = os.path.join(root, f)
            raw = Path(fp).read_text(encoding='utf-8', errors='replace')
            fname = f
            break
    if raw:
        break

print(f"File: {fname}, {len(raw)} chars")

# Step 1: Group
print("\n--- Grouping ---")
resp = call(f'识别以下护理知识点中的所有疾病。输出JSON: {{"diseases":[{{"name":"病名","entry_count":数}}]}}\n\n{raw[:8000]}', 2000)
m = re.search(r'\{.*\}', resp, re.DOTALL)
diseases = json.loads(m.group(0))['diseases'] if m else [{'name': '测试'}]
print(f"Found {len(diseases)} diseases")

# Step 2: Generate with paired questions
d = diseases[0]
print(f"\n--- Generating: {d['name']} ---")

prompt = f'''为"{d['name']}"生成阶段五末尾的配对题（6组）。
每组：左列案例选择题（病例题干+ABCD选项+每个选项的完整解析），右列对应考点的高难度填空题（挖关键数值/机制/禁忌词）。
两列表格，一一配对，覆盖"{d['name']}"的主要考点。
知识点原文：{raw[:12000]}
输出Markdown。'''
result = call(prompt, 6000)
print(f"Generated {len(result)} chars")
print(result[:3000])
print("...\n--- PASS ---")
