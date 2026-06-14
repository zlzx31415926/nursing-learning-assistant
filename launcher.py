"""启动 Streamlit 服务器"""
import subprocess
import sys
import os

# 确保工作目录正确
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 启动 streamlit
subprocess.run([
    sys.executable, "-m", "streamlit", "run",
    "学习助手.py",
    "--server.port", "8501"
])
