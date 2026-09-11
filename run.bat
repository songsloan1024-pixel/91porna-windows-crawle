@echo off
chcp 65001 >nul
title 91porna 一键工具

:: ============================================================
:: 91porna 短剧工具 - 一键抓取 + 下载（Windows 版）
::
:: 功能说明：
::   本脚本会自动完成两步操作：
::   1. 根据关键词搜索并抓取真实 m3u8 播放地址
::   2. 下载视频并尽量使用 ffmpeg 转成 .mp4
::
:: 使用前请确保：
::   - 已双击运行过 install.bat
::   - 推荐安装 ffmpeg（用于转 mp4 和修复音画同步）
::
:: 文件会尽量使用网站原标题命名。
:: ============================================================

chcp 65001 >nul
title 91porna 一键工具

echo =====================================================
echo   91porna 短剧工具（抓取 + 下载）
echo =====================================================
echo.

:: ==================== 第一步：抓取地址 ====================
echo [1/2] 抓取短剧播放地址
echo.

set /p keyword=请输入搜索关键词（直接回车默认 "短剧"）: 
if "%keyword%"=="" set keyword=短剧

set /p num=要抓取多少个？（直接回车默认 5）: 
if "%num%"=="" set num=5

echo.
echo 正在抓取 "%keyword%"，共抓取 %num% 个...
python porna91_crawler.py -k "%keyword%" -n %num%

if not exist "captured_91porna.json" (
    echo.
    echo 抓取失败或没有结果，程序结束。
    pause
    exit /b
)

echo.
echo 地址抓取完成！
echo.
pause

:: ==================== 第二步：下载设置 ====================
echo.
echo [2/2] 下载设置
echo.

set /p outdir=请输入保存路径（直接回车默认 downloads）: 
if "%outdir%"=="" set outdir=downloads

:: ==================== 检测 ffmpeg ====================
echo.
echo 正在检测 ffmpeg...

where ffmpeg >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo [警告] 未检测到 ffmpeg！
    echo.
    echo 强烈建议安装 ffmpeg，否则：
    echo - 只能生成 .ts 文件
    echo - 可能出现音画不同步问题
    echo - 无法自动转成 .mp4
    echo.
    echo 推荐安装方式：
    echo 1. 访问 https://www.gyan.dev/ffmpeg/builds/
    echo 2. 下载 "ffmpeg-release-essentials.zip"
    echo 3. 解压后把 bin 文件夹加入系统环境变量 PATH
    echo 4. 重启命令行窗口后再运行
    echo.
    set /p continue=是否继续只生成 .ts 文件？(Y/N): 
    if /i not "%continue%"=="Y" (
        echo 已取消。
        pause
        exit /b
    )
) else (
    echo 检测到 ffmpeg，将自动转成 .mp4
)

echo.
echo 开始下载到 "%outdir%" ...
python windows_full_downloader.py --from-json captured_91porna.json --out "%outdir%"

echo.
echo =====================================================
echo   全部完成！
echo =====================================================
echo.
pause
