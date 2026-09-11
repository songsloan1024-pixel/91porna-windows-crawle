@echo off
chcp 65001 >nul

echo ============================================
echo   正在为 91porna 工具安装环境...
echo ============================================
echo.

echo [1/2] 安装 Python 依赖...
pip install -r requirements.txt

echo.
echo [2/2] 下载 Chromium 浏览器（必须）...
playwright install chromium

echo.
echo ============================================
echo   安装完成！
echo.
echo 现在可以双击 run.bat 开始使用了。
echo ============================================
pause
