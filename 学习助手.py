"""
2303/205机密文件 · 六阶段交互式学习系统
=====================================
上传原始知识点文件 → 智能归组理顺 → 按档位生成学习环 → 交互式学习+错题追踪
"""

import streamlit as st
import json
import os
import re
import time
import uuid
import threading
from pathlib import Path
from datetime import datetime
from docx import Document
import urllib.request
import urllib.error

# ============================================================
# 配置
# ============================================================
BASE_DIR = Path(__file__).parent
KNOWLEDGE_BASE_DIR = BASE_DIR / "knowledge_base"
USER_MODEL_FILE = BASE_DIR / "user_model.json"
ERROR_LOG_FILE = BASE_DIR / "error_log.json"
API_KEY_FILE = BASE_DIR / "api_key.txt"

UPLOAD_DIR = BASE_DIR / "uploads"

for d in [KNOWLEDGE_BASE_DIR, UPLOAD_DIR]:
    d.mkdir(parents=True, exist_ok=True)

ERROR_TYPES = [
    "数值混淆", "对偶记反", "副作用张冠李戴", "禁忌忽略",
    "癌变/恶化漏判", "跨章节断裂", "优先级判断错误", "其他"
]

TIER_FORCE_KEYWORDS = [
    "禁用", "严禁", "绝对禁忌", "可致死", "最严重",
    "首选", "金标准", "最常见的并发症", "急救", "抢救", "立即"
]

# ============================================================
# 页面设置
# ============================================================
# set_page_config 已移至 app.py（解决 Streamlit Cloud 中文文件名问题）
# 本地直接运行时用默认配置
try:
    st.set_page_config(page_title="2303/205机密文件", page_icon="🩺", layout="wide", initial_sidebar_state="expanded")
except:
    pass  # app.py 已经调用过了

# 访问控制——从 app.py 进入时已验证，本地运行时跳过
if "authenticated" not in st.session_state:
    st.session_state.authenticated = True  # 本地直接运行无需密码

# 自定义样式
st.markdown("""
<style>
    /* 全局 */
    .stApp { background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%); }

    /* 侧边栏 */
    section[data-testid="stSidebar"] {
        background: #ffffff;
        border-right: 1px solid #e0e4e8;
    }
    section[data-testid="stSidebar"] h1 {
        color: #4A90D9;
        font-weight: 700;
    }

    /* 卡片 */
    div[data-testid="stMetric"] {
        background: white;
        padding: 12px;
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }

    /* 按钮 */
    .stButton > button {
        border-radius: 8px;
        border: none;
        font-weight: 500;
        transition: all 0.2s;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(74,144,217,0.2);
    }

    /* 展开器 */
    .streamlit-expanderHeader {
        border-radius: 8px;
        background: #f8f9fa;
    }

    /* 标签页 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 12px 20px;
        font-weight: 500;
    }

    /* 输入框 */
    input, textarea {
        border-radius: 8px !important;
        border: 1px solid #dce1e6 !important;
    }
    input:focus, textarea:focus {
        border-color: #4A90D9 !important;
        box-shadow: 0 0 0 2px rgba(74,144,217,0.15) !important;
    }

    /* 提示信息 */
    .stAlert {
        border-radius: 10px;
    }

    /* 滚动条 */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-thumb { background: #d0d5da; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 工具函数
# ============================================================
def load_api_key():
    """加载 API Key。"""
    if "api_key" in st.session_state and st.session_state.api_key:
        return st.session_state.api_key
    if API_KEY_FILE.exists():
        key = API_KEY_FILE.read_text().strip()
        if key:
            return key
    return os.environ.get("DEEPSEEK_API_KEY", "")


def call_deepseek(prompt: str, system_prompt: str = "", max_tokens: int = 4000, progress_placeholder=None) -> str:
    """调用 DeepSeek API（支持流式输出到 progress_placeholder）。"""
    api_key = st.session_state.get("api_key", "") or load_api_key()
    if not api_key:
        raise ValueError("请先设置 DeepSeek API Key")

    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt or "你是一位资深护理考试命题专家。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": max_tokens,
        "stream": True  # 开启流式
    }

    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            full_text = ""
            char_count = 0
            buffer = b""
            while True:
                chunk = resp.read(1024)
                if not chunk:
                    break
                buffer += chunk
                # 解析 SSE 数据
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line = line.strip()
                    if line.startswith(b"data: "):
                        data_str = line[6:].decode("utf-8", errors="replace")
                        if data_str == "[DONE]":
                            break
                        try:
                            delta = json.loads(data_str)
                            content = delta["choices"][0].get("delta", {}).get("content", "")
                            if content:
                                full_text += content
                                char_count += len(content)
                                # 每收到约200字更新一次进度
                                if progress_placeholder and char_count % 200 < len(content) + 5:
                                    progress_placeholder.markdown(
                                        f"🤖 正在生成...（已生成 {char_count} 字）\n\n{full_text[-500:]}"
                                    )
                        except:
                            pass
            return full_text
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        raise RuntimeError(f"API 调用失败 (HTTP {e.code}): {body[:500]}")


def parse_file(uploaded_file) -> str:
    """解析上传的文件，返回文本内容。"""
    if uploaded_file.name.endswith('.txt'):
        return uploaded_file.read().decode('utf-8', errors='replace')

    elif uploaded_file.name.endswith('.docx'):
        # 保存临时文件
        tmp_path = BASE_DIR / f"_tmp_{uuid.uuid4().hex}.docx"
        tmp_path.write_bytes(uploaded_file.read())
        try:
            doc = Document(str(tmp_path))
            lines = []
            for para in doc.paragraphs:
                text = para.text.strip()
                if text and len(text) > 5:
                    lines.append(text)
            return "\n".join(lines)
        finally:
            tmp_path.unlink(missing_ok=True)

    else:
        raise ValueError(f"不支持的文件格式: {uploaded_file.name}。请上传 .txt 或 .docx 文件。")


def load_user_model() -> dict:
    """加载用户模型。"""
    if USER_MODEL_FILE.exists():
        return json.loads(USER_MODEL_FILE.read_text(encoding='utf-8'))
    return {"mastery": {}, "error_log": [], "last_session": None}


def save_user_model(model: dict):
    """保存用户模型。"""
    USER_MODEL_FILE.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding='utf-8')


def log_error(disease: str, module: str, error_type: str, question: str, user_answer: str, correct_answer: str):
    """记录错题。"""
    model = load_user_model()
    model["error_log"].append({
        "timestamp": datetime.now().isoformat(),
        "disease": disease,
        "module": module,
        "error_type": error_type,
        "question": question[:200],
        "user_answer": user_answer[:200],
        "correct_answer": correct_answer[:200],
        "resolved": False
    })
    model["last_session"] = datetime.now().isoformat()
    save_user_model(model)


def get_error_stats(disease: str = None) -> dict:
    """获取错题统计。"""
    model = load_user_model()
    errors = model["error_log"]
    if disease:
        errors = [e for e in errors if e["disease"] == disease]

    stats = {}
    for et in ERROR_TYPES:
        count = len([e for e in errors if e.get("error_type") == et])
        if count > 0:
            stats[et] = count
    return stats


# ============================================================
# 智能引擎
# ============================================================
SYSTEM_PROMPT = """你是一位资深护理考试命题专家，同时也是临床带教护士。你的视角不是"老师讲解"，而是**护士推理**——学生拿到你的材料后，应该能训练出"看到病人→推出诊断→决定护理优先级"的临床思维。

⚠️ 六阶段同等重要、环环相扣。阶段一（理解）帮零基础学生搞懂机制本质，但不能厚此薄彼——阶段二（记忆）的精准性、阶段三（辨析）的鉴别力、阶段四（应用）的决策力、阶段五（检验）的实战力、阶段六（复盘）的提升力，同样关键。前一阶段是后一阶段的基石，缺一环整个学习链就断。

【核心设计哲学——三条铁律】：
1. **推理链必须延伸到护理决策**：不能推到"水肿形成"就停了。要继续推到：水肿→我看到什么体征→我判断什么性质→我决定查什么→我重点监测什么→最危险并发症是什么→我怎么预防。路径是：病理生理→临床表现→护理观察点→护理决策→风险预判。
2. **鉴别诊断用动态分叉，不用静态表格**：不要直接把"A vs B对比表"摊开给学生看。要从"共同症状"出发→列出分叉鉴别点→让学生自己推导出不同疾病。训练的是"凭什么区分"，不是"区分结果是什么"。
3. **送命题干扰项标注设计意图**：每个错误选项后面不只说"错"，要标注"为什么有人会选这个"——是成人思维干扰？数值互换？概念颠倒？药物张冠李戴？让学生学习干扰项的制造规律。

【阶段一·图解式推理链范例】（必须模仿此风格）：
推理链不是罗列A→B→C，而是每一步都要解释"因为什么"：
"HP进入胃内 → 穿透黏液层（因为鞭毛提供动力）→ 黏附于胃上皮 → 分泌尿素酶分解尿素→产生氨（氨像一层"防护罩"中和胃酸，让细菌在强酸中存活）→ 同时损伤上皮细胞膜 → 产生VacA毒素→上皮细胞空泡变性（像气球被扎破）→ 菌体胞壁作为抗原→诱发自身免疫→进一步损伤→胃黏膜屏障破坏（防御的城墙塌了）→ H⁺逆弥散→胃酸和胃蛋白酶向深层侵袭→自身消化→溃疡形成"
每一步括号里都解释"为什么"，关键概念用比喻（"防护罩""城墙塌了""气球被扎破"）。
**推理链末尾必须追加护理决策延伸**——格式：「🩺 护理行动：我看到___→我想到___→我决定___」

【机制反推导格式】（每条推理链配一道反推导题）：
正向推理练的是"为什么"，反向推理练的是"凭什么判断"——考试就是从表现反推机制。
格式：⭐⭐ 反推练习：患者出现[临床表现]，请回答：①这是哪个机制导致的？②如果机制相反会怎样？③排除了什么其他可能？
例如：⭐⭐ 反推练习：急性肾炎患儿眼睑浮肿，非凹陷性，血压偏高。请回答：①水肿为什么是非凹陷性而非凹陷性？②如果是凹陷性水肿，首先考虑什么病？③血压偏高提示什么风险？

【阶段一·关键概念解剖范例】：
### 关键概念：Oddi括约肌
- 是什么：胆总管和胰管在十二指肠开口处的环形平滑肌，像一个"阀门"
- 在哪：十二指肠乳头，胆管和胰管汇合处
- 干嘛的：①控制胆汁排入十二指肠 ②防止十二指肠内容物反流进胆管和胰管
- 比喻：厨房水槽的排水阀——打开=胆汁流入肠道帮助消化，关闭=防止肠道细菌反流
- 临床关联：吗啡使Oddi括约肌痉挛→阀门卡死→胆汁/胰液排不出→急性胰腺炎/胆绞痛

【审题关键词速查格式】"看到X→立刻锁定Y"的快速反应格式，两列："题目中出现"、"立刻锁定"。例如：
| 题目中出现 | 立刻锁定 |
|:--|:--|
| "搏动性跳痛" | 脓性指头炎 → 必须切开减压 |
| "空腹+右上腹痛+午夜痛" | 十二指肠溃疡 |

【命名陷阱格式】每个陷阱有标题+类型+干扰项+破题关键。例如：
🔥陷阱1：波动感的干扰（类型：切开指征混淆）
  → 选项里必混入"波动感"
  → 破题关键：指头炎不等到波动感才切——搏动性跳痛就是指征
🔥陷阱2：短效vs长效降糖药停药时机互换（类型：药物管理）
  → 出题人把短效和长效的停药时间互换
  → 破题关键：短效→术前1晚停；长效→术前2-3天停

【优先级排序题格式】（每个疾病至少1道）：
给出多项护理措施，让学生排序并解释为什么是这个顺序。格式：
"请将以下措施按优先级排列：A.___ B.___ C.___ D.___ E.___。排序：___。追问：为什么[某个]排在[另一个]前面？"
必须在答案中解释每项优先级的逻辑。

【集中坑点预警清单格式】（考前快速扫描用）：
表格，按类型分组（数值混淆/概念颠倒/药物张冠李戴/禁忌忽略/并发症互换），每行：坑点描述 | 为什么容易错 | 正确做法。至少6条。

【跨章节融合病例格式】（第二、三档使用）：
病例自带合并症（糖尿病/高血压/肾衰/肝病），药物选择考虑合并症×过敏史的交互。
例如："患者有糖尿病，空腹血糖11.5mmol/L。此时血糖高能否推迟切开？→不能，感染是紧急指征，血糖控制与手术同步进行。"
双病例对比题格式：患者A和患者B同时就诊，各自诊断？处理？谁更紧急？为什么？"""


def load_toc(subject: str) -> str:
    """加载对应科目的教材目录作为归类参考。"""
    toc_map = {
        "内科": "toc_内科.json",
        "外科": "toc_外科.json",
        "儿科": "toc_儿科.json",
        "妇产科": "toc_妇产科.json",
        "基础护理": "toc_基础护理.json",
    }
    toc_file = BASE_DIR / toc_map.get(subject, "")
    if toc_file.exists():
        toc_data = json.loads(toc_file.read_text(encoding='utf-8'))
        # 格式化为紧凑的目录参考文本
        lines = [f"【{toc_data['subject']}教材目录——归类必须严格对照此结构】"]
        for ch in toc_data.get("chapters", []):
            chapter = ch["chapter"]
            diseases = " | ".join(ch["diseases"])
            lines.append(f"  {chapter} → 包含：{diseases}")
        return "\n".join(lines)
    return ""


def ai_group_and_sort(raw_text: str, subject: str = "") -> dict:
    """智能归组：对照教材目录，从散乱原始资料中识别疾病并按逻辑排序。"""
    # 加载教材目录作为归类参照
    toc_ref = load_toc(subject)

    # 样本扩大到 15000 字符，减少遗漏
    sample = raw_text[:15000] if len(raw_text) > 15000 else raw_text

    if toc_ref:
        prompt = f"""你是一位护理教学专家。以下是一份护理学知识点的原始资料。

请从原始资料中识别出实际存在的疾病/考点，将它们归类排序。**只输出资料中实际出现的疾病**，资料没有的不要列。

提示：下面这份教材目录仅供你核对疾病名称是否规范——如果资料中的疾病名称与目录不一致，请用目录中的标准名称。

{toc_ref}

⚠️ 归类规则：

**规则1：合并章节的知识点要同时归到每个疾病**
如果原始资料把多个疾病合并论述（比如只有一个"疖和痈"章节，写了10条知识点），这10条知识点应**同时算到疖和痈两个疾病的条目中**。两个条目都标 confidence="low"，在 low_confidence_entries 中标注"条目与XX共享——原始资料未拆分"。

**规则2：禁止自创打包大类**
如果原始资料里出现了"非特异性感染"这种将多个疾病打包的类别，拆开分到各自对应的TOC疾病中去，不要自创条目。

**规则3：交叉知识点归属**
如果一条知识点涉及多个疾病，放在最主要的疾病下，并在 low_confidence_entries 中标注交叉关联。

**规则4：逻辑排序**
按 "病因→机制→临床表现→检查→治疗→护理→并发症" 的顺序排列。

**规则5：信心度打分**
≥3条且清晰→"high"，1-2条或模糊→"low"。

{toc_ref}

请输出 JSON 格式：
```json
{{
  "diseases": [
    {{
      "name": "疾病名称（必须取自教材目录）",
      "chapter": "所属章节",
      "confidence": "high",
      "entry_count": 18,
      "original_entries": ["条目66", "条目76", ...],
      "merged_entries": [["条目76", "条目87", "合并原因"]],
      "low_confidence_entries": ["条目226（可能属于心梗范畴）"],
      "summary": "该疾病的核心内容概要（50字以内）"
    }}
  ],
  "quality_self_assessment": "high"
}}
```

原始资料：
{sample}"""
    else:
        # 没有 TOC 时的兜底方案
        prompt = f"""以下是一份护理学知识点的原始资料（前15000字符样本）。资料中的知识点是散乱排列的，同一疾病分散在多处，不同疾病混杂在一起。

请完成以下任务：
1. 识别这份资料中涵盖的所有疾病/考点主题
2. 对每个疾病，列出属于它的原始条目编号或内容摘要
3. 按 "病因→机制→临床表现→检查→治疗→护理→并发症" 的逻辑顺序排列
4. 标注每个疾病的知识点数量
5. 对归类信心度打分：高信心度（边界清晰）或 低信心度（可能与其他疾病重叠）
6. 识别哪些条目可以在同一疾病内合并去重

⚠️ 注意：不要随意合并不同疾病。如果一个知识点讲的是两个病的对比，把它放在最主要的疾病下并在 low_confidence_entries 标注关联。

请输出 JSON 格式：
```json
{{
  "diseases": [
    {{
      "name": "疾病名称",
      "confidence": "high",
      "entry_count": 18,
      "original_entries": ["条目66", "条目76", ...],
      "merged_entries": [["条目76", "条目87", "合并原因"]],
      "low_confidence_entries": ["条目226（可能属于心梗范畴）"],
      "summary": "该疾病的核心内容概要（50字以内）"
    }}
  ],
  "quality_self_assessment": "high"
}}
```
原始资料：
{sample}"""
    response = call_deepseek(prompt, SYSTEM_PROMPT, max_tokens=4000)
    # 解析 JSON
    json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except Exception as e:
            return {"diseases": [], "quality_self_assessment": "low", "raw": response[:500], "parse_error": str(e)}
    # 尝试直接解析
    try:
        return json.loads(response)
    except:
        return {"diseases": [], "quality_self_assessment": "low", "raw": response[:500]}


def judge_tier(disease_info: dict) -> int:
    """判断档位。"""
    count = disease_info.get("entry_count", 0)
    summary = disease_info.get("summary", "")
    name = disease_info.get("name", "")

    # ≥6条 → 第三档
    if count >= 6:
        return 3
    # 含强制关键词 → 第三档
    for kw in TIER_FORCE_KEYWORDS:
        if kw in summary or kw in name:
            return 3
    # 3-5条 → 第二档
    if count >= 3:
        return 2
    # ≤2条 → 第一档
    return 1


def generate_learning_loop(disease_name: str, disease_points: str, tier: int, progress_placeholder=None) -> str:
    """生成六阶段学习环。第三档拆成两次API调用，总输出16000 tokens，杜绝截断。"""
    points_text = disease_points[:25000] if len(disease_points) > 25000 else disease_points

    # 基础提示词（不含阶段具体内容）
    base_prompt = f"""请为"{disease_name}"生成一份护理考试学习材料。你的视角是**护士推理**——不是"老师讲给你听"，而是训练学生"看到病人→推出诊断→决定护理优先级"。

⚠️ 六阶段同等重要，环环相扣——前一阶段是后一阶段的基石，缺一不可。

【输出格式——必须遵守的阶段标题】：
每个阶段必须使用以下格式作为一级标题：
# 阶段一：理解
# 阶段二：记忆
# 阶段三：辨析
# 阶段四：应用
# 阶段五：检验
# 阶段六：复盘

【阶段一·硬性要求】：
1. 「一句话机制速记」：150-200字，必须包含：疾病本质 + 关键病理机制 + 最核心鉴别点
2. 「图解式推理链」：至少4-5条，每条7-15步，每步用括号解释"为什么"
   格式：A→B（因为...）→C（导致...）→D
   每条链末尾必加「💡 关键追问：...」+「🩺 护理行动：我看到___→我想到___→我决定___」
3. 「机制反推导」：每条推理链配1道反推题
   格式：⭐⭐ 反推练习：患者出现[表现]，①机制是什么？②如果机制相反会怎样？③排除了什么诊断？
4. 「关键概念解剖」：挑3个核心名词，按"是什么→在哪→干嘛→比喻→临床关联"五步，各80-120字
5. 「机制→表现对应表」：两列 | 机制（为什么）| 临床表现（所以会怎样）| 重要性★ |

【输出质量铁律】：
1. 每道选择题必须有：完整病例题干（≥2行）+ 明确问题 + 4个完整选项 + 逐一解析 + 每个干扰项标注设计意图
2. 内容不得截断——字不够就少生成题，但不能把题写一半
3. 配对表左右两列都必须是完整内容

【阶段二至六·统一要求】：
- 每个知识点独立成段，不合并；末尾标重要性★和考查形式
- 鉴别诊断用**动态分叉推导**：从共同症状出发→分叉鉴别点→落到不同诊断
- 送命题每个干扰项标注**设计意图**：成人思维干扰/数值互换/概念颠倒/药物张冠李戴/并发症互换
- 优先级排序题**必须让学生动手排**，追问"为什么A在B前面"
- 坑点预警清单**集中按类型分组**，每行：坑点 | 为什么容易错 | 正确做法
- 不生成记忆口诀——用「机制反推导」替代
- 基础填空≥15空 | 案例选择≥6道（完整解析+干扰项设计意图）| 配对≥8组 | 坑点≥8条
- 不因考频低跳过任何知识点，一律平等对待

【知识点原文】：
{points_text}

⚠️ 上面的知识点原文是参考资料，不是唯一依据。你需要以它为起点，但**不能局限于它**：
- 如果知识点充足 → 基于原文展开深化
- 如果知识点很少或不完整 → 用你的专业知识补全所有缺失的考试重点、临床表现、护理要点
- 如果完全没有相关知识点 → 完全基于你的专业知识生成完整材料
核心原则：无论原文有多少内容，最终输出的六阶段材料必须覆盖该疾病的完整考试范围。"""

    # ========== 第三档：拆成两次，各8000 tokens专攻三阶段 ==========
    if tier == 3:
        config_1_3 = """请生成阶段一至阶段三：
阶段一：理解（⚠️机制地基）——「一句话速记」+「图解式推理链」至少4-5条（每条7-15步，每步解释"为什么"，末尾必加🩺护理行动延伸）+「机制反推导」每条推理链配1道反推题+「关键概念解剖」2-3个（通俗比喻）+「机制→表现对应表」（机制|表现|★）
阶段二：记忆 - 基础填空（至少15空，"因为A→所以B"配对）+ 对比速记表 + 图解记忆法 + 关键词提取矩阵 + 审题关键词速查
阶段三：辨析 - 鉴别诊断动态分叉推导 + 细节辨析（3-5个陷阱，标注干扰项设计意图）+ 命名陷阱预判（至少3个）+ 反向归类 + 机制反推导"""

        config_4_6 = """请继续生成阶段四至阶段六：
阶段四：应用 - 渐进决策模式（4步递进）+ 优先级排序（至少1道动手排序题，追问"为什么A在B前面"）+ 跨章节融合决策（引入合并症，药物选择×过敏史×合并症三角互动）
阶段五：检验 - 高仿真送命题（4-5子题含解析，干扰项标注设计意图）+ 跨章节变形题（2-3道）+ 跨考点串联矩阵 + 跨章节综合病例串（2-3个病例，自带合并症、双病例对比、命名陷阱）+ 案例选择题×高难填空题配对（至少8组）+ 集中坑点预警清单（按类型分组，至少8条）
阶段六：复盘 - 学习环总览 + 阶段自检清单（每个阶段一个核心问题）+ 错题画像 + 知识修补清单 + 考前救急方案"""

        # 第一次：生成阶段1-3（8000 tokens 专攻三阶段，不会截断）
        if progress_placeholder is not None:
            progress_placeholder.info("📝 正在生成阶段一至三（理解·记忆·辨析）...")
        content_1_3 = call_deepseek(
            base_prompt + f"\n\n【生成内容】：{config_1_3}\n\n请输出 Markdown 格式的阶段一至三。",
            SYSTEM_PROMPT, max_tokens=8000
        )

        # 第二次：生成阶段4-6，传入完整1-3做上下文确保连贯
        if progress_placeholder is not None:
            progress_placeholder.info("📝 正在生成阶段四至六（应用·检验·复盘）...")
        try:
            content_4_6 = call_deepseek(
                base_prompt + f"\n\n【前三个阶段已生成，请保持风格和内容一致】：\n{content_1_3}\n\n【生成内容】：{config_4_6}\n\n请接着输出 Markdown 格式的阶段四至六。注意：保持与前文的连贯性，不要出现矛盾。如果前文中提到了某个药物或机制，阶段四五引用时必须一致。",
                SYSTEM_PROMPT, max_tokens=8000
            )
        except Exception:
            content_4_6 = "\n\n---\n\n⚠️ 阶段四至六生成失败，请点「🔄 重新生成」重试。\n\n"
            content_4_6 += "# 阶段四：应用\n（内容缺失）\n\n# 阶段五：检验\n（内容缺失）\n\n# 阶段六：复盘\n（内容缺失）\n"

        return content_1_3 + "\n\n" + content_4_6

    # ========== 第一、二档：一次调用 ==========
    tier_config = {
        1: """第一档（快速过滤）：只生成以下内容：
- 一句话机制速记（50-80字核心机制）
- 机制反推导（2道：给出表现→反推机制→排除其他可能）
- 对比速记表（核心数值和概念对比）
- 审题关键词速查（"看到X→立刻锁定Y"快速反应格式）
- 集中坑点预警清单（6-8条，按类型分组：数值混淆/概念颠倒/药物张冠李戴）
- 关键词提取矩阵
不生成完整推理链、送命题、渐进决策。""",

        2: """第二档（深度拆解）：生成简化版：
- 一句话机制速记
- 核心推理链（1-2条，选最关键的，每条必须延伸到护理决策：病理→表现→护理观察点→护理行动→风险预判）
- 机制反推导（每条推理链配1道反推题：给表现→问机制→问排除→问如果相反）
- 基础填空 + GU/DU式对比速记表
- 审题关键词速查（"看到X→立刻锁定Y"格式）
- 细节辨析（2-3个高频陷阱，每个含"为什么错"解释和干扰项设计意图）
- 出题人陷阱预判（至少2个命名陷阱，标注陷阱类型）
- 优先级排序题（1道动手排序题，含解释）
- 渐进决策模式（分两部分：基础版4步递进 + 🔥跨章节融合版含1个合并症）
- 高仿真送命题（分两部分：标准版2-3子题 + 🔥DeepSeek融合版1个跨科病例含命名陷阱；每个干扰项标注设计意图）
- 1道跨章节变形题
- 集中坑点预警清单（按类型分组，考前可扫）
- 关键词提取矩阵""",
    }
    prompt = base_prompt + f"\n\n【生成结构】：{tier_config[tier]}\n\n请输出完整的 Markdown 格式学习材料。"
    return call_deepseek(prompt, SYSTEM_PROMPT, max_tokens=8000, progress_placeholder=progress_placeholder)


def glue_topics(disease_a: str, content_a: str, disease_b: str, content_b: str) -> str:
    """粘合两个考点——生成跨章节融汇卡片。"""
    prompt = f"""你是一位护理考试命题专家。请将以下两个考点/疾病"粘合"在一起，生成一份跨章节融汇卡片。

考点A：「{disease_a}」
考点B：「{disease_b}」

卡片内容要求：
1. **共同机制/关联**：两个疾病在病理生理上有什么关联？（比如：一个病会导致另一个、共享同一套机制、药物之间的相互影响）
2. **关键鉴别点**：如果考题中同时出现这两个疾病的症状，如何快速区分？（2-3个鉴别要点）
3. **联合出题预判**：出题人可能怎样把这两个考点融合进一道题？（给1个完整的跨章节病例题干样例）
4. **护理交叉注意**：如果患者同时有这两个疾病，护理上有什么需要特别注意的？（药物禁忌、生命体征监测、体位等）

考点A的参考内容：
{content_a}

考点B的参考内容：
{content_b}

请用 Markdown 格式输出，语言简练，300-500字即可。每个部分用小标题分隔。"""
    return call_deepseek(prompt, max_tokens=2000)


# ============================================================
# 访问控制——密码门禁（密码存在 Streamlit Cloud Secrets 中，不写入代码）
# ============================================================
APP_PASSWORD = None  # 部署时从 st.secrets 读取

def check_password():
    """密码验证界面。"""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    # 从 Streamlit Secrets 读取密码（云端），本地运行时用默认密码
    try:
        real_password = st.secrets["app_password"]
    except:
        real_password = "123456"  # 本地测试用

    # 未验证 → 显示登录界面
    st.title("🩺 2303/205机密文件")
    st.markdown("---")
    pwd = st.text_input("请输入访问密码", type="password", placeholder="输入密码后按回车")
    if pwd:
        if pwd == real_password:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("密码错误")
    st.stop()
    return False

# ============================================================
# 初始化 Session State
# ============================================================
def init_session():
    defaults = {
        "api_key": load_api_key(),
        "raw_text": "",
        "source_name": "",          # 当前上传的文件名
        "diseases": [],
        "selected_disease": None,
        "learning_loops": {},       # {disease_name: markdown_content}
        "grouping_report": "",      # 归组报告
        "processing": False,
        "fill_answers": {},         # {question_id: user_answer}
        "fill_results": {},         # {question_id: bool}
        "deep_dive_cache": {},      # {module_key: expanded_content}
        "glue_cache": {},           # {topic_pair: glue_content}
        "error_counts": {},         # {error_type: count}
        "current_stage": 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()

# ============================================================
# 侧边栏
# ============================================================
with st.sidebar:
    st.title("🩺 2303/205机密文件")

    # API Key
    st.subheader("🔑 API 设置")
    api_key = st.text_input(
        "DeepSeek API Key",
        value=st.session_state.api_key,
        type="password",
        placeholder="sk-...",
        help="在 https://platform.deepseek.com 免费获取"
    )
    if api_key != st.session_state.api_key:
        st.session_state.api_key = api_key
        API_KEY_FILE.write_text(api_key)

    st.divider()

    # ==================== 分科选择 ====================
    SUBJECTS = ["内科", "外科", "儿科", "妇产科", "基础护理", "其他"]
    if "current_subject" not in st.session_state:
        st.session_state.current_subject = "内科"

    st.subheader("📚 学科")
    selected_subject = st.selectbox("选择学科", SUBJECTS,
        index=SUBJECTS.index(st.session_state.current_subject) if st.session_state.current_subject in SUBJECTS else 0,
        key="subject_selector")
    if selected_subject != st.session_state.current_subject:
        st.session_state.current_subject = selected_subject
        # 切换学科时清空当前显示
        st.session_state.diseases = []
        st.session_state.selected_disease = None
        st.rerun()

    # 确保该学科的目录存在
    subject_upload_dir = UPLOAD_DIR / st.session_state.current_subject
    subject_kb_dir = KNOWLEDGE_BASE_DIR / st.session_state.current_subject
    subject_upload_dir.mkdir(parents=True, exist_ok=True)
    subject_kb_dir.mkdir(parents=True, exist_ok=True)

    # ========== 自动恢复上次进度（不花钱） ==========
    saved_groupings = sorted(subject_upload_dir.glob("*_grouping.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if saved_groupings and not st.session_state.get("diseases"):
        latest = saved_groupings[0]
        gd = json.loads(latest.read_text(encoding='utf-8'))
        gs = gd.get("source", latest.stem.replace("_grouping", ""))
        src = subject_upload_dir / f"{gs}.txt"
        if not src.exists(): src = subject_upload_dir / f"{gs}.docx"
        if src.exists():
            st.success(f"📂 已恢复：{gs}（{len(gd.get('diseases',[]))}个考点）")
            st.session_state.diseases = gd.get("diseases", [])
            st.session_state.source_name = gs
            st.session_state.raw_text = src.read_text(encoding='utf-8', errors='replace')

    st.divider()

    # ==================== 已保存的文件 ====================
    st.subheader("📂 已保存文件")
    saved_files = sorted(subject_upload_dir.glob("*.*"), key=lambda f: f.stat().st_mtime, reverse=True)
    saved_files = [f for f in saved_files if f.suffix.lower() in ['.txt', '.docx']]

    if saved_files:
        for sf in saved_files:
            fname = sf.name
            fsize = sf.stat().st_size / 1024
            cols = st.columns([3, 1])
            with cols[0]:
                if st.button(f"📄 {fname}（{fsize:.0f}KB）", key=f"load_{sf.stem}", use_container_width=True,
                             help=f"点击重新加载并分析此文件"):
                    raw_text = sf.read_text(encoding='utf-8', errors='replace')
                    source_name = sf.stem
                    st.session_state.raw_text = raw_text
                    st.session_state.source_name = source_name
                    st.session_state.diseases = []
                    st.session_state.learning_loops = {}
                    st.session_state.selected_disease = None
                    with st.spinner("🤖 正在识别疾病并归组..."):
                        try:
                            result = ai_group_and_sort(raw_text, st.session_state.current_subject)
                            diseases = result.get("diseases", [])
                            quality = result.get("quality_self_assessment", "unknown")
                            for d in diseases:
                                d["source"] = source_name
                                d["subject"] = st.session_state.current_subject
                            st.session_state.diseases = diseases
                            st.session_state.grouping_report = json.dumps(result, ensure_ascii=False, indent=2)
                            # 保存分组结果
                            gf = subject_upload_dir / f"{source_name}_grouping.json"
                            gf.write_text(json.dumps({"diseases": diseases, "quality": quality, "source": source_name}, ensure_ascii=False, indent=2), encoding='utf-8')
                            st.success(f"✅ 识别到 {len(diseases)} 个考点（已保存）")
                        except Exception as e:
                            st.error(f"归组失败: {e}")
                    st.rerun()
            with cols[1]:
                # 删除按钮
                if st.button("🗑️", key=f"del_{sf.stem}", help="删除此文件"):
                    sf.unlink()
                    st.rerun()

    # ==================== 上传新文件 ====================
    st.subheader("📤 上传新文件")
    uploaded_file = st.file_uploader(
        f"上传到「{st.session_state.current_subject}」",
        type=["txt", "docx"],
        key=f"upload_{st.session_state.current_subject}",
        help="上传后自动保存，下次无需重新上传"
    )

    if uploaded_file and st.button("🚀 上传并分析", use_container_width=True):
        # 保存文件
        save_path = subject_upload_dir / uploaded_file.name
        save_path.write_bytes(uploaded_file.read())
        source_name = uploaded_file.name.rsplit('.', 1)[0]

        # 解析并归组
        raw_text = save_path.read_text(encoding='utf-8', errors='replace')
        st.session_state.raw_text = raw_text
        st.session_state.source_name = source_name
        st.session_state.diseases = []
        st.session_state.learning_loops = {}
        st.session_state.selected_disease = None

        with st.spinner("🤖 正在识别疾病并归组..."):
            try:
                result = ai_group_and_sort(raw_text, st.session_state.current_subject)
                diseases = result.get("diseases", [])
                quality = result.get("quality_self_assessment", "unknown")
                for d in diseases:
                    d["source"] = source_name
                    d["subject"] = st.session_state.current_subject
                st.session_state.diseases = diseases
                st.session_state.grouping_report = json.dumps(result, ensure_ascii=False, indent=2)
                gf = subject_upload_dir / f"{source_name}_grouping.json"
                gf.write_text(json.dumps({"diseases": diseases, "quality": quality, "source": source_name}, ensure_ascii=False, indent=2), encoding='utf-8')
                st.success(f"✅ 识别到 {len(diseases)} 个考点（已保存，下次秒开）")
            except Exception as e:
                st.error(f"归组失败: {e}")
        st.rerun()

    st.divider()

    # ==================== 当前考点列表 ====================
    source_name = st.session_state.get("source_name", "")
    if source_name:
        st.subheader(f"📋 {source_name}")
    else:
        st.subheader("📋 考点板块")
    diseases = st.session_state.get("diseases", [])

    if diseases:
        # ---- 处理待生成的考点（不在按钮回调里调API，避免UI冻结） ----
        pending = st.session_state.get("_pending_gen")
        if pending:
            name = pending["name"]
            d = pending["d"]
            tier = pending["tier"]
            full_raw = st.session_state.raw_text
            with st.spinner(f"🤖 正在生成「{name}」（第{tier}档），正在全力写作中..."):
                loop_content = generate_learning_loop(name, full_raw, tier)
            safe_name = re.sub(r'[\\/:*?"<>|]', '-', name)
            (subject_kb_dir / f"{safe_name}_六阶段学习环.md").write_text(loop_content, encoding='utf-8')
            st.session_state.learning_loops[name] = loop_content
            st.session_state.selected_disease = d
            del st.session_state["_pending_gen"]
            st.rerun()

        for i, d in enumerate(diseases):
            name = d.get("name", f"考点{i+1}")
            count = d.get("entry_count", 0)
            tier = judge_tier(d)
            tier_emoji = {1: "🔵", 2: "🟠", 3: "🔴"}.get(tier, "⚪")
            confidence = d.get("confidence", "high")
            conf_mark = "⚠️" if confidence == "low" else ""

            btn_label = f"{tier_emoji} {name} ({count}条) {conf_mark}"
            if st.button(btn_label, key=f"disease_{i}", use_container_width=True):
                if name in st.session_state.learning_loops:
                    st.session_state.selected_disease = d
                    st.rerun()
                else:
                    # 不直接调API，只打标记，等下次渲染
                    st.session_state["_pending_gen"] = {"name": name, "d": d, "tier": tier}
                    st.rerun()
    else:
        st.info("👆 上传文件或从「已保存文件」中选择")

    st.divider()

    # ==================== 所有学科知识库 ====================
    st.subheader("💾 全部知识库")

    # 遍历所有学科
    all_kb_dirs = sorted(KNOWLEDGE_BASE_DIR.glob("*"), key=lambda d: d.stat().st_mtime if d.is_dir() else 0, reverse=True)
    for kb_dir in all_kb_dirs:
        if not kb_dir.is_dir():
            continue
        subject_name = kb_dir.name
        kb_files = sorted(kb_dir.glob("*六阶段学习环.md"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not kb_files:
            continue

        subject_emoji = {"内科": "🫀", "外科": "🔪", "儿科": "👶", "妇产科": "🤰", "基础护理": "💊"}.get(subject_name, "📚")
        with st.expander(f"{subject_emoji} {subject_name}（{len(kb_files)}个）", expanded=(subject_name == st.session_state.current_subject)):
            for f in kb_files:
                stem = f.stem.replace("_六阶段学习环", "").replace("-六阶段学习环", "")
                size_k = len(f.read_text(encoding='utf-8')) // 1000
                if st.button(f"📄 {stem}（{size_k}k字）", key=f"kb_{subject_name}_{stem}", use_container_width=True):
                    content = f.read_text(encoding='utf-8')
                    st.session_state.learning_loops[stem] = content
                    st.session_state.selected_disease = {"name": stem, "source": subject_name, "is_review": True}
                    st.rerun()

    st.divider()

    # 错题统计
    st.subheader("📊 错题画像")
    error_stats = get_error_stats()
    if error_stats:
        for et, count in sorted(error_stats.items(), key=lambda x: -x[1]):
            st.text(f"{et}: {count}次")
    else:
        st.text("暂无错题记录")

# ============================================================
# 主区域
# ============================================================
st.title("📖 六阶段学习环")

selected = st.session_state.get("selected_disease")
if not selected:
    st.info("👈 从左侧选择一个考点板块开始学习")
    st.markdown("---")
    st.markdown("### 使用流程")
    st.markdown("1. **上传**机构原始资料（.txt 或 .docx）")
    st.markdown("2. 点击**开始分析**，系统自动识别疾病并归组")
    st.markdown("3. 从左侧**选择考点**，自动生成六阶段学习环")
    st.markdown("4. **交互学习**——填空、推理、辨析、决策")
    st.markdown("5. 错题自动收集，考前精准补漏")
    st.stop()

name = selected.get("name", "未知考点")
tier = judge_tier(selected)
is_review = selected.get("is_review", False) or "entry_count" not in selected
loop_content = st.session_state.learning_loops.get(name, "")

# 如果是从知识库点击的，尝试从各学科子目录加载
if not loop_content:
    safe_name = re.sub(r'[\\/:*?"<>|]', '-', name)
    target_filename = f"{safe_name}_六阶段学习环.md"
    # 搜所有学科子目录
    for kb_dir in sorted(KNOWLEDGE_BASE_DIR.glob("*")):
        if kb_dir.is_dir():
            kb_file = kb_dir / target_filename
            if kb_file.exists():
                loop_content = kb_file.read_text(encoding='utf-8')
                st.session_state.learning_loops[name] = loop_content
                break

# 顶部信息栏
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    subject = selected.get("subject", st.session_state.get("current_subject", "-"))
    st.metric("学科", subject)
with col2:
    st.metric("考点", name)
with col3:
    if is_review:
        st.metric("模式", "📚 复习")
    else:
        st.metric("档位", {1: "🔵 1档", 2: "🟠 2档", 3: "🔴 3档"}.get(tier, "📚"))
with col4:
    st.metric("条目", selected.get("entry_count", "-"))
with col5:
    source = selected.get("source", st.session_state.get("source_name", "-"))
    st.metric("来源", source[:10] if len(source) > 10 else source)

if not loop_content:
    st.info("⏳ 内容加载中...")
    st.stop()

# 功能按钮栏
btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)
with btn_col1:
    if st.button("🤔 问老师", use_container_width=True,
                 help="对任何概念、名词、机制有疑问——直接问，老师给你讲解"):
        st.session_state.show_ask_teacher = True
with btn_col2:
    if st.button("🔗 粘合考点", use_container_width=True):
        st.session_state.show_glue = True
with btn_col3:
    if st.button("🔄 重新生成", use_container_width=True):
        if name in st.session_state.learning_loops:
            del st.session_state.learning_loops[name]
        st.rerun()
with btn_col4:
    safe_name_dl = re.sub(r'[\\/:*?"<>|]', '-', name)
    st.download_button(
        "📥 导出",
        loop_content,
        f"{safe_name_dl}_六阶段学习环.md",
        "text/markdown",
        use_container_width=True
    )

st.divider()

# 解析学习环内容，提取各阶段
def parse_stages(content: str) -> dict:
    """将 Markdown 内容按阶段标题拆分。匹配不到时显示原始内容而不是空壳。"""
    stages = {}
    # 用更宽松的正则：匹配 # 阶段X 或 ## 阶段X 或 ### 阶段X（X可以是中文数字或阿拉伯数字）
    pattern = r'(#{1,3}\s*阶段[一二三四五六1-6].*?)(?=#{1,3}\s*阶段[一二三四五六1-6]|$)'
    matches = list(re.finditer(pattern, content, re.DOTALL))
    stage_names = ["阶段一：理解", "阶段二：记忆", "阶段三：辨析", "阶段四：应用", "阶段五：检验", "阶段六：复盘"]

    if not matches:
        # 没有任何阶段标题匹配 → 整篇内容放到一个"全部内容"tab
        stages["📖 全部内容"] = content
        return stages

    for i, name in enumerate(stage_names):
        if i < len(matches):
            stages[name] = matches[i].group(1)
    return stages

stages = parse_stages(loop_content)
stage_names = list(stages.keys())

# 兜底：解析失败时直接用全部内容
if len(stage_names) == 1 and stage_names[0].startswith("📖"):
    st.markdown(stages[stage_names[0]])
    st.stop()

# 学习模式切换
col_mode, col_progress = st.columns([1, 3])
with col_mode:
    sequential = st.checkbox("🎓 逐阶递进", value=True, help="完成当前阶段后才能进入下一阶段")
with col_progress:
    if sequential:
        current = st.session_state.get("current_stage", 0)
        progress_text = " → ".join([f"{'✅' if j < current else '⬤' if j == current else '○'} {name}" for j, name in enumerate(stage_names)])
        st.caption(progress_text)

if sequential:
    # 逐阶模式：只展示当前阶段
    current = st.session_state.get("current_stage", 0)
    if current >= len(stage_names):
        current = 0
        st.session_state.current_stage = 0

    tab_name = stage_names[current]
    content = stages.get(tab_name, "")
    st.subheader(f"🎯 {tab_name}")

    # --- 阶段内容渲染（与自由模式共用下面的逻辑）---
    # 为简洁，这里用 if-elif 复用原始渲染逻辑
    i = current
    tabs = [None]  # dummy
else:
    # 自由模式：所有阶段以选项卡展示
    current = None
    tabs = st.tabs(stage_names)

for i, tab_name in enumerate(stage_names):
    if sequential:
        if i != current:
            continue
    else:
        tabs_i = tabs[i]

    content = stages.get(tab_name, "")

    # 兜底：如果内容没有被分阶段，直接展示原文
    if tab_name.startswith("📖"):
        st.markdown(content)
        continue

    # 打开阶段渲染上下文（自由模式用 tab，逐阶模式直接渲染）
    if not sequential:
        tabs_i.__enter__()
    try:
        # 阶段一：推理链交互
        if i == 0:
            # 查找填空标记
            blanks = list(re.finditer(r'______([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚㉛㉜㉝㉞㉟㊱㊲㊳㊴㊵㊶㊷]+)______', content))
            if blanks:
                st.markdown("#### ✏️ 推理链填空（逐个填写，填完再对答案）")
                for j, match in enumerate(blanks):
                    blank_id = f"{name}_stage0_{j}"
                    num = match.group(1)
                    # 获取上下文
                    start = max(0, match.start() - 80)
                    end = min(len(content), match.end() + 80)
                    context = content[start:end].replace(match.group(0), f"______**{num}**______")
                    st.markdown(f"*...{context}...*")

                    user_answer = st.text_input(f"空 {num}", key=f"fill_{blank_id}", placeholder="输入你的答案")
                    if user_answer:
                        st.session_state.fill_answers[blank_id] = user_answer

            # 答案区域
            answer_match = re.search(r'答案[：:](.*?)(?=\n\n|#|\Z)', content, re.DOTALL)
            if answer_match:
                with st.expander("📋 查看答案"):
                    st.markdown(answer_match.group(1))

            # 显示原始内容
            with st.expander("📄 完整阶段一内容"):
                st.markdown(content)

        # 阶段二：填空交互
        elif i == 1:
            blanks = list(re.finditer(r'______([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚㉛㉜㉝㉞㉟㊱㊲㊳㊴㊵㊶㊷㊸㊹㊺㊻㊼㊽㊾㊿]+)______', content))
            if blanks:
                st.markdown("#### ✏️ 基础填空（逐个填写后批改）")
                correct_count = 0
                total = len(blanks)

                for j, match in enumerate(blanks):
                    blank_id = f"{name}_stage1_{j}"
                    num = match.group(1)

                    # 尝试提取正确答案
                    answer_section = content[match.end():]
                    correct_answer = "（答案见下方）"

                    col_a, col_b = st.columns([3, 1])
                    with col_a:
                        start = max(0, match.start() - 120)
                        end = min(len(content), match.end() + 120)
                        context = content[start:end].replace(match.group(0), f"______**{num}**______")
                        st.markdown(f"{context}")

                    with col_b:
                        user_answer = st.text_input(f"答案 {num}", key=f"fill2_{blank_id}", placeholder="输入")
                        submit_key = f"submit_{blank_id}"
                        if st.button("✓", key=submit_key):
                            if user_answer.strip():
                                st.session_state.fill_answers[blank_id] = user_answer
                                st.session_state.fill_results[blank_id] = None  # 需要人工核对
                                st.success("已记录！")

            with st.expander("📋 查看所有答案"):
                answer_match = re.search(r'答案[：:](.*?)(?=\n\n#|\n\n阶段|\Z)', content, re.DOTALL)
                if answer_match:
                    st.markdown(answer_match.group(1))
                else:
                    st.markdown(content[-2000:])

            with st.expander("📄 完整阶段二内容"):
                st.markdown(content)

        # 阶段三：主动预判陷阱
        elif i == 2:
            trap_sections = re.findall(r'(陷阱[一二三四五六七八九十].*?)(?=陷阱[一二三四五六七八九十]|\n\n#|\Z)', content, re.DOTALL)
            if trap_sections:
                st.markdown("#### 🎯 主动预判陷阱")
                for j, trap in enumerate(trap_sections[:5]):
                    with st.expander(f"陷阱 {j+1}", expanded=(j == 0)):
                        # 先显示问题
                        question_match = re.search(r'(问题[：:].*?)(?=答案|$)', trap, re.DOTALL)
                        if question_match:
                            st.markdown("**问题：**")
                            st.markdown(question_match.group(1))

                            pre_judge_key = f"prejudge_{name}_{j}"
                            user_prejudge = st.text_area(
                                "你的预判（在看答案之前，先猜坑在哪里）：",
                                key=pre_judge_key,
                                placeholder="先自己想，再看答案..."
                            )

                            if st.button(f"查看答案对比", key=f"show_answer_{j}"):
                                answer_match = re.search(r'答案[：:](.*?)$', trap, re.DOTALL)
                                if answer_match:
                                    st.markdown("**正确答案：**")
                                    st.markdown(answer_match.group(1))
                                    if user_prejudge:
                                        st.info(f"你的预判：{user_prejudge}\n\n对比上面的答案，看你的思路对不对。")

            with st.expander("📄 完整阶段三内容"):
                st.markdown(content)

        # 阶段四：临床决策
        elif i == 3:
            question_sections = re.findall(r'(问题[①②③④⑤].*?)(?=问题[①②③④⑤]|\n\n#|\Z)', content, re.DOTALL)
            if question_sections:
                st.markdown("#### 🏥 渐进决策（逐题作答）")
                user_model = load_user_model()

                for j, q_section in enumerate(question_sections[:6]):
                    with st.expander(f"问题 {j+1}", expanded=(j == 0)):
                        st.markdown(q_section[:800])

                        # 用户作答区域
                        answer_key = f"decision_{name}_{j}"
                        user_decision = st.text_area(
                            "你的回答：",
                            key=answer_key,
                            placeholder="输入你的临床判断..."
                        )

                        if st.button(f"对答案", key=f"check_decision_{j}"):
                            answer_match = re.search(r'答案[：:](.*?)$', q_section, re.DOTALL)
                            if answer_match:
                                correct = answer_match.group(1)[:300]
                                st.markdown(f"**参考答案：** {correct}")

                            if user_decision.strip():
                                # 简单判断（基于长度和关键词）
                                error_type = st.selectbox(
                                    "这道题你做对了吗？",
                                    ["对了 ✓", "错了 - 选择错因"],
                                    key=f"error_select_{j}"
                                )
                                if "错了" in error_type:
                                    et = st.selectbox("错因类型", ERROR_TYPES, key=f"error_type_{j}")
                                    if st.button("记录错题", key=f"log_error_{j}"):
                                        log_error(name, "阶段四-临床决策", et, q_section[:200], user_decision, correct)
                                        st.success("✅ 错题已记录！")

            with st.expander("📄 完整阶段四内容"):
                st.markdown(content)

        # 阶段五：送命题测试
        elif i == 4:
            st.markdown("#### 🔥 高仿真送命题")

            # 提取子题
            sub_questions = re.findall(r'(子题\d+[：:].*?)(?=子题\d+[：:]|\n\n##|\Z)', content, re.DOTALL)
            if not sub_questions:
                sub_questions = [content]

            score = 0
            total_q = 0

            for j, sq in enumerate(sub_questions[:4]):
                with st.expander(f"子题 {j+1}", expanded=True):
                    # 显示题目
                    q_text = re.sub(r'解析[：:].*', '', sq, flags=re.DOTALL)
                    st.markdown(q_text[:1000])

                    # 提取选项
                    options = re.findall(r'([A-E])\s*[\.\、\s]+(.*?)(?=[A-E]\s*[\.\、\s]|\n\s*\n|\Z)', sq)
                    choice = st.radio(
                        f"选择你的答案",
                        [f"{o[0]}. {o[1][:100]}" for o in options],
                        key=f"quiz_{name}_{j}",
                        index=None
                    )

                    if st.button(f"提交答案", key=f"submit_quiz_{j}"):
                        if choice:
                            user_choice = choice[0]
                            # 查找正确答案
                            answer_match = re.search(r'✅\s*正确答案[：:]\s*\*?\*?([A-E])', sq)
                            if not answer_match:
                                answer_match = re.search(r'正确[的]*答案[是为]*[：:]\s*([A-E])', sq)

                            if answer_match:
                                correct = answer_match.group(1)
                                total_q += 1
                                if user_choice == correct:
                                    score += 1
                                    st.success(f"✅ 正确！答案选 {correct}")
                                else:
                                    st.error(f"❌ 错误。你的答案：{user_choice}，正确答案：{correct}")
                                    # 错题记录
                                    error_type = st.selectbox("错因类型", ERROR_TYPES, key=f"quiz_error_{j}")
                                    if st.button("记录此错题", key=f"log_quiz_{j}"):
                                        log_error(name, "阶段五-送命题", error_type, q_text[:200], user_choice, correct)
                                        st.success("✅ 已记录！")

                            # 显示解析
                            parse_match = re.search(r'解析[：:](.*?)$', sq, re.DOTALL)
                            if parse_match:
                                st.markdown("---")
                                st.markdown("**解析：**")
                                st.markdown(parse_match.group(1)[:1500])

            if total_q > 0:
                st.metric("得分", f"{score}/{total_q}")

            with st.expander("📄 完整阶段五内容"):
                st.markdown(content)

        # 阶段六：复盘
        else:
            st.markdown("#### 📊 你的错题画像")
            error_stats = get_error_stats(name)
            if error_stats:
                st.bar_chart(error_stats)
                for et, count in error_stats.items():
                    st.text(f"• {et}: {count} 次")
            else:
                st.info("🎉 暂无错题记录！")

            with st.expander("📄 完整阶段六内容"):
                st.markdown(content)
    finally:
        if not sequential:
            tabs_i.__exit__(None, None, None)

    # 逐阶递进：阶段完成按钮
    if sequential and current is not None and i == current:
        st.divider()
        if current < len(stage_names) - 1:
            if st.button(f"✅ 完成「{stage_names[current]}」，进入「{stage_names[current+1]}」→", use_container_width=True, key=f"next_stage_{current}"):
                st.session_state.current_stage = current + 1
                st.rerun()
        else:
            st.success("🎉 全部六个阶段已完成！")
            if st.button("🔄 重新学习", use_container_width=True):
                st.session_state.current_stage = 0
                st.rerun()

# ============================================================
# 问老师 —— 对任何概念/名词/机制提问
# ============================================================
if st.session_state.get("show_ask_teacher"):
    st.divider()
    st.subheader("🤔 问老师")

    # 加载历史问答
    qa_file = subject_kb_dir / f"{safe_name_dl}_问答记录.json"
    if qa_file.exists():
        try:
            qa_history = json.loads(qa_file.read_text(encoding='utf-8'))
            if qa_history:
                with st.expander(f"📝 历史问答（{len(qa_history)}条）"):
                    for qa in reversed(qa_history):
                        st.caption(f"🕐 {qa.get('time', '')}")
                        st.markdown(f"**❓ {qa.get('question', '')}**")
                        st.markdown(qa.get('answer', ''))
                        st.divider()
        except:
            pass

    # 快捷提问
    quick_q = st.radio(
        "想了解什么？",
        ["✍️ 自己输入问题", "🧠 解释一个医学名词/解剖结构", "🔬 用比喻帮我理解一个机制",
         "📋 分析当前内容中的某个病例", "🔄 帮我理清两个易混概念的区别"],
        horizontal=True,
        key="ask_mode"
    )

    user_question = ""
    if "自己输入" in quick_q:
        user_question = st.text_area(
            "把你的问题写在这里：",
            placeholder="比如：Na⁺-K⁺-ATP酶到底是什么？它在心肌细胞的哪个位置？为什么抑制它就能治疗心衰？",
            key="custom_q"
        )
    elif "名词" in quick_q:
        user_question = st.text_input("输入你想了解的名词：", placeholder="比如：Oddi括约肌、浦肯野纤维、窦房结...", key="term_q")
        if user_question:
            user_question = f"请解释医学名词「{user_question}」：①它是什么（定义）；②它在身体的哪个位置（解剖）；③它的生理功能是什么；④它和当前考点「{name}」有什么关系；⑤用一个生活中的比喻帮助我理解。"
    elif "比喻" in quick_q:
        user_question = st.text_input("输入你想理解的机制：", placeholder="比如：低钾为什么会诱发洋地黄中毒？", key="analogy_q")
        if user_question:
            user_question = f"请用通俗易懂的比喻帮我理解：「{user_question}」（这是护理考点「{name}」中的内容）。先用比喻讲清楚，再回到医学语境中解释。"
    elif "病例" in quick_q:
        user_question = "请从当前内容「{name}」中提取一个关键的病例或临床情景，然后：①分析这个病例为什么会出现这些表现（从病理生理角度）；②如果我作为护士遇到这个病人，我的思维过程应该是什么样的；③最容易在这个病例中犯的护理错误是什么。"
    elif "易混" in quick_q:
        concept_a = st.text_input("概念A：", placeholder="比如：洋地黄中毒的消化道症状", key="concept_a")
        concept_b = st.text_input("概念B：", placeholder="比如：心衰加重的消化道症状", key="concept_b")
        if concept_a and concept_b:
            user_question = f"请帮我理清两个容易混淆的概念的区别——「{concept_a}」vs「{concept_b}」。从定义、机制、关键鉴别点、临床表现、护理处理五个维度对比。这两个概念都属于护理考点「{name}」的范畴。"

    if user_question and st.button("💡 问老师", type="primary"):
        with st.spinner("老师正在思考..."):
            prompt = f"""你是一位耐心、善于用比喻讲解的护理学老师。

学生正在学习「{name}」这个考点。当前学习材料的摘要如下：
{loop_content[:2000]}

学生的问题是：
{user_question}

请你像一个好老师那样回答：
1. 先用最通俗的方式解释（可以用生活中的比喻）
2. 再回到医学语境中严谨地讲清楚
3. 最后说明这和「{name}」的学习有什么关系、考试会怎么考
4. 如果涉及解剖位置，描述具体位置（比如"在心脏的右上方，靠近..."）
"""
            try:
                answer = call_deepseek(prompt, max_tokens=2000)
                st.markdown("---")
                st.markdown("### 💡 老师讲解")
                st.markdown(answer)

                # 保存问答记录
                qa_file = subject_kb_dir / f"{safe_name_dl}_问答记录.json"
                qa_history = []
                if qa_file.exists():
                    try:
                        qa_history = json.loads(qa_file.read_text(encoding='utf-8'))
                    except:
                        qa_history = []
                qa_history.append({
                    "question": user_question[:500],
                    "answer": answer,
                    "time": datetime.now().strftime("%m/%d %H:%M")
                })
                qa_file.write_text(json.dumps(qa_history, ensure_ascii=False, indent=2), encoding='utf-8')

                # 追问
                st.text_input("还有不懂的？继续追问：", key=f"followup_{hash(user_question)}", placeholder="继续问...")
            except Exception as e:
                st.error(f"提问失败: {e}")

    if st.button("✕ 关闭", key="close_ask"):
        st.session_state.show_ask_teacher = False
        st.rerun()

# ============================================================
# 粘合弹窗
# ============================================================
if st.session_state.get("show_glue"):
    st.divider()
    st.subheader("🔗 跨考点粘合")
    other_diseases = [d.get("name") for d in diseases if d.get("name") != name]
    if other_diseases:
        target = st.selectbox("选择要粘合的考点", other_diseases)
        if st.button("生成粘合卡片", type="primary"):
            with st.spinner(f"🔗 正在粘合 {name} × {target}..."):
                try:
                    content_b = st.session_state.learning_loops.get(target, "")
                    if not content_b:
                        # 从知识库中找
                        kb_file = KNOWLEDGE_BASE_DIR / f"{target}_六阶段学习环.md"
                        if kb_file.exists():
                            content_b = kb_file.read_text(encoding='utf-8')
                        else:
                            content_b = target

                    result = glue_topics(name, loop_content[:1500], target, content_b[:1500])
                    st.markdown(result)
                    st.session_state.glue_cache[f"{name}_{target}"] = result
                except Exception as e:
                    st.error(f"粘合失败: {e}")
    else:
        st.info("知识库中还没有其他考点。请先生成更多考点再粘合。")

# ============================================================
# 页脚
# ============================================================
st.divider()
st.caption(f"💾 知识库: {len(list(KNOWLEDGE_BASE_DIR.glob('*.md')))} 个考点 | 📝 错题总数: {len(load_user_model()['error_log'])} 条 | 🕐 上次学习: {load_user_model().get('last_session', '暂无')}")
