@echo off
chcp 65001 >nul
title 91porna 一键工具

:: ============================================================
:: 91porna 短剧工具 - 一键抓取 + 下载（Windows 版）
::
:: 功能说明：
::   本脚本会自动完成三步操作：
::   1. 一次性输入关键词、数量、保存路径，并检测 ffmpeg
::   2. 根据关键词搜索并抓取真实 m3u8 播放地址
::   3. 下载视频并尽量使用 ffmpeg 转成 .mp4
::
:: 使用前请确保：
::   - 已双击运行过 install.bat
::   - 推荐安装 ffmpeg（用于转 mp4 和修复音画同步）
::
:: 文件会尽量使用网站原标题命名。
:: ============================================================

cd /d "%~dp0"

where python >nul 2>nul
if not %errorlevel%==0 (
    echo [错误] 未检测到 python，请先安装 Python 并勾选 "Add to PATH"，再运行 install.bat
    pause
    exit /b
)

echo =====================================================
echo   91porna 短剧工具（抓取 + 下载）
echo =====================================================
echo.

:: ==================== 第一步：设置 ====================
echo [1/3] 设置
echo.

set /p keyword=请输入搜索关键词（直接回车默认 "短剧"）: 
if "%keyword%"=="" set keyword=短剧

set /p num=要抓取多少个？（直接回车默认 5）: 
if "%num%"=="" set num=5

set /p outdir=请输入保存路径（直接回车默认 downloads）: 
if "%outdir%"=="" set outdir=downloads

:: ==================== 检测 ffmpeg ====================
echo.
echo 正在检测 ffmpeg...

where ffmpeg >nul 2>nul
if %errorlevel%==0 goto has_ffmpeg

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
set continue=
set /p continue=是否继续只生成 .ts 文件？[Y/N]: 
if /i "%continue%"=="Y" goto start_crawl
echo 已取消。
pause
exit /b

:has_ffmpeg
echo 检测到 ffmpeg，将自动转成 .mp4

:: ==================== 第二步：抓取地址 ====================
:start_crawl
echo.
echo [2/3] 抓取短剧播放地址
echo.
echo 正在抓取 "%keyword%"，共抓取 %num% 个...
if exist "captured_91porna.json" del /q "captured_91porna.json"
python porna91_crawler.py -k "%keyword%" -n %num%
if not %errorlevel%==0 goto crawl_failed
if not exist "captured_91porna.json" goto crawl_failed
goto start_download

:crawl_failed
echo.
echo 抓取失败或没有结果，程序结束。
pause
exit /b

:: ==================== 第三步：下载 ====================
:start_download
echo.
echo 地址抓取完成！
echo.
echo [3/3] 开始下载到 "%outdir%" ...
echo.
python windows_full_downloader.py --from-json captured_91porna.json --out "%outdir%"

echo.
echo =====================================================
echo   全部完成！
echo =====================================================
echo.
pause
