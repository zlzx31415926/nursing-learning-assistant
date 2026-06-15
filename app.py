"""
2303/205机密文件 - Streamlit Cloud 入口（含密码门禁）
"""
import streamlit as st
import os, sys

st.set_page_config(page_title="2303/205机密文件", page_icon="🩺", layout="wide", initial_sidebar_state="expanded")

# ── 密码门禁 ──
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    try:
        real_password = st.secrets["app_password"]
    except:
        real_password = "123456"

    st.title("🩺 2303/205机密文件")
    st.markdown("---")
    pwd = st.text_input("请输入访问密码", type="password", placeholder="输入密码后按回车")
    if pwd:
        if pwd == real_password:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("密码错误，请重试")
    st.stop()

# ── 密码通过 → 加载完整应用 ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "学习助手.py"), encoding="utf-8").read(), "学习助手.py", "exec"))
