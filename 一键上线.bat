@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 护理学习助手 - 在线模式

echo.
echo ╔══════════════════════════════════════════════╗
echo ║     🩺 护理学习助手 · 一键上线              ║
echo ║     启动服务器 + 生成公开链接                ║
echo ╚══════════════════════════════════════════════╝
echo.
echo [1/2] 正在启动本地服务器...
start "Streamlit" /min python -m streamlit run "学习助手.py" --server.port 8501 --server.headless true

echo        等待服务器就绪...
timeout /t 8 /nobreak >nul

echo [2/2] 正在生成公开链接...
echo.
echo ───────────────────────────────────────────────
echo    📱 把这个链接发到手机上：
echo.
ssh -o StrictHostKeyChecking=no -R 80:localhost:8501 nokey@localhost.run 2>&1
echo ───────────────────────────────────────────────
echo.
echo    ⚠️ 按 Ctrl+C 关闭链接
echo    ⚠️ 不要关闭此窗口，否则手机无法访问
echo.
pause
