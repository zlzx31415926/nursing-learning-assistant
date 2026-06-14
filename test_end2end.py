"""端到端测试：读文件 → AI分组 → 生成学习环"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 直接导入核心函数，绕过 streamlit
import importlib.util
spec = importlib.util.spec_from_file_location("helper", "学习助手.py")
# 不能直接导入整个文件（因为streamlit.set_page_config必须在streamlit run下）
# 所以手动提取需要的函数

import json, re, urllib.request, urllib.error
from pathlib import Path
from docx import Document

API_KEY_FILE = Path("api_key.txt")
api_key = API_KEY_FILE.read_text().strip() if API_KEY_FILE.exists() else ""
print(f"API Key: {'***' + api_key[-4:] if api_key else 'NOT SET'}")

def call_api(prompt, system="", max_tokens=4000):
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system or "你是护理考试命题专家。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": max_tokens,
        "stream": False
    }
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        return result["choices"][0]["message"]["content"]

# 1. 测试文件解析
print("\n=== 测试1: 读文件 ===")
txt_path = Path("..") / "大项目学习" / "[完整版]第3章 循环系统疾病病人的护理（1）.txt"
# 找文件
found = None
for root, dirs, files in os.walk(Path.home() / "Desktop"):
    for f in files:
        if "循环系统" in f and f.endswith('.txt'):
            found = Path(root) / f
            break
    if found:
        break

if not found:
    print("未找到循环系统文件，跳过")
    sys.exit(1)

raw = found.read_text(encoding='utf-8', errors='replace')
print(f"文件: {found.name}, {len(raw)} 字符")

# 2. 测试 AI 分组
if not api_key:
    print("\n跳过AI测试（无API Key）")
    sys.exit(0)

print("\n=== 测试2: AI 疾病分组 ===")
sample = raw[:8000]
prompt = f"""以下是护理学知识点原始资料。识别所有疾病主题，输出JSON。

资料：
{sample}

输出JSON格式：{{"diseases":[{{"name":"疾病名","entry_count":数量}}]}}
"""
try:
    resp = call_api(prompt, max_tokens=2000)
    json_match = re.search(r'```json\s*(.*?)\s*```', resp, re.DOTALL)
    if json_match:
        data = json.loads(json_match.group(1))
    else:
        data = json.loads(resp)
    diseases = data.get("diseases", [])
    print(f"识别到 {len(diseases)} 个疾病:")
    for d in diseases[:5]:
        print(f"  - {d['name']} ({d.get('entry_count','?')}条)")
except Exception as e:
    print(f"分组失败: {e}")

# 3. 测试生成一个学习环
if diseases:
    print(f"\n=== 测试3: 生成 {diseases[0]['name']} 学习环 ===")
    dname = diseases[0]['name']
    tier = 3 if diseases[0].get('entry_count', 0) >= 6 else 2
    gen_prompt = f"""请为"{dname}"生成一份护理考试学习材料（简化测试版，只生成阶段一和阶段二）。

【要求】：基于以下原始知识点，填空用______①______格式。

知识点原文：
{raw[:8000]}

请输出Markdown。"""
    try:
        result = call_api(gen_prompt, max_tokens=3000)
        print(f"生成成功！{len(result)} 字符")
        print(result[:800])
        print("...")
    except Exception as e:
        print(f"生成失败: {e}")

print("\n=== 全部测试完成 ===")
