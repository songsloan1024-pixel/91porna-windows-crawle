@echo off
chcp 65001 >nul

echo ============================================
echo   正在为 91porna 工具安装环境...
echo ============================================
echo.

cd /d "%~dp0"

where python >nul 2>nul
if not %errorlevel%==0 (
    echo [错误] 未检测到 python，请先到 https://www.python.org/downloads/ 安装，
    echo        安装时务必勾选 "Add python.exe to PATH"，然后重新运行本脚本。
    pause
    exit /b
)

echo [1/2] 安装 Python 依赖...
python -m pip install -r requirements.txt
if not %errorlevel%==0 goto install_failed

echo.
echo [2/2] 下载 Chromium 浏览器（必须）...
python -m playwright install chromium
if not %errorlevel%==0 goto install_failed

echo.
echo ============================================
echo   安装完成！
echo.
echo 现在可以双击 run.bat 开始使用了。
echo ============================================
pause
exit /b

:install_failed
echo.
echo [错误] 安装失败，请把上面的报错截图发出来。
pause
exit /b
