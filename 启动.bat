@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 护理学习助手

echo.
echo ╔══════════════════════════════════════════╗
echo ║     🩺 护理学习助手 · 六阶段学习环       ║
echo ║     基于 DeepSeek AI + 交互式学习         ║
echo ╚══════════════════════════════════════════╝
echo.
echo 正在启动...
echo 浏览器将自动打开 http://localhost:8501
echo 关闭此窗口即可停止程序
echo.

streamlit run "学习助手.py" --server.port 8501 --browser.serverAddress localhost

pause
