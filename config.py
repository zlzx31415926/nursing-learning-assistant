"""
护理学习助手 · 配置文件
=======================
在此设置你的 DeepSeek API Key 和其他偏好。
"""

import os
from pathlib import Path

# ============================================================
# API 配置
# ============================================================
DEEPSEEK_API_KEY = ""  # 在此填入，或运行时在侧边栏输入
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

# ============================================================
# 路径配置
# ============================================================
BASE_DIR = Path(__file__).parent
KNOWLEDGE_BASE_DIR = BASE_DIR / "knowledge_base"       # 生成的学习材料
USER_MODEL_FILE = BASE_DIR / "user_model.json"         # 用户掌握度数据
ERROR_LOG_FILE = BASE_DIR / "error_log.json"           # 错题记录
UPLOAD_DIR = BASE_DIR / "uploads"                      # 上传的原始文件
CONFIG_FILE = BASE_DIR / "api_key.txt"                 # API Key 存储

# 确保目录存在
for d in [KNOWLEDGE_BASE_DIR, UPLOAD_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ============================================================
# 档位判断规则
# ============================================================
TIER_RULES = {
    "tier1_threshold": 2,      # ≤2条 → 第一档
    "tier2_threshold": 5,      # 3-5条 → 第二档
    "tier3_threshold": 6,      # ≥6条 → 第三档
    "force_tier3_keywords": [  # 强制升第三档的关键词
        "禁用", "严禁", "绝对禁忌", "可致死", "最严重",
        "首选", "金标准", "最常见的并发症", "最重要的",
        "急救", "抢救", "立即", "紧急"
    ],
}

# ============================================================
# 错因类型
# ============================================================
ERROR_TYPES = [
    "数值混淆",
    "对偶记反",
    "副作用张冠李戴",
    "禁忌忽略",
    "癌变/恶化漏判",
    "跨章节断裂",
    "优先级判断错误",
    "其他",
]
