#!/usr/bin/env python3
"""
91porna Windows Full Downloader (with real download capability)

功能：
- 从 captured_91porna.json 读取已抓的 m3u8
- 或者现场抓取
- 真正下载视频分片并合并
- 使用原标题作为文件名（不额外重命名）

依赖：
- httpx（下载分片）
- 可选：ffmpeg（强烈推荐，用于可靠合并）

用法示例：

# 方式1：从已抓文件下载
python windows_full_downloader.py --from-json captured_91porna.json --out "D:\短剧下载"

# 方式2：直接抓 + 下载
python windows_full_downloader.py -k "AI短剧" -n 4 --out "D:\短剧下载"

# 方式3：只抓不下载（推荐先抓）
python porna91_crawler.py -k "AI短剧" -n 6
"""

import asyncio
import json
import argparse
import subprocess
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlparse
import sys

try:
    import httpx
except ImportError:
    print("请先安装 httpx: pip install httpx")
    sys.exit(1)


def find_ffmpeg():
    """检测系统是否有 ffmpeg"""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    # 常见 Windows 安装路径
    common_paths = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
    ]
    for p in common_paths:
        if Path(p).exists():
            return p
    return None


async def download_m3u8_segments(m3u8_url: str, output_dir: Path, client: httpx.AsyncClient) -> list[Path]:
    """下载 m3u8 及其所有 ts 分片"""
    print(f"  正在解析播放列表...")
    resp = await client.get(m3u8_url)
    if resp.status_code != 200:
        print(f"  无法获取 m3u8: {resp.status_code}")
        return []

    content = resp.text
    base_url = str(resp.url).rsplit("/", 1)[0] + "/"

    segments = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        seg_url = urljoin(base_url, line)
        segments.append(seg_url)

    if not segments:
        print("  播放列表中没有找到分片")
        return []

    print(f"  共 {len(segments)} 个分片，开始下载...")

    segment_files = []
    for i, seg_url in enumerate(segments, 1):
        seg_name = f"seg_{i:05d}.ts"
        seg_path = output_dir / seg_name

        try:
            r = await client.get(seg_url, timeout=30)
            if r.status_code == 200:
                seg_path.write_bytes(r.content)
                segment_files.append(seg_path)
                if i % 20 == 0:
                    print(f"    已下载 {i}/{len(segments)}")
            else:
                print(f"    分片下载失败: {seg_url}")
        except Exception as e:
            print(f"    下载分片出错: {e}")

    return segment_files


def merge_with_ffmpeg(segment_files: list[Path], output_file: Path, ffmpeg_path: str):
    """使用 ffmpeg 合并 ts 分片"""
    # 创建 concat 文件
    concat_file = output_file.parent / "concat_list.txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for seg in segment_files:
            # Windows 下路径要处理
            f.write(f"file '{seg.as_posix()}'\n")

    cmd = [
        ffmpeg_path,
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(output_file)
    ]

    print(f"  使用 ffmpeg 合并 → {output_file.name}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  ✓ 合并成功: {output_file}")
            return True
        else:
            print(f"  ffmpeg 合并失败: {result.stderr[-300:]}")
            return False
    finally:
        concat_file.unlink(missing_ok=True)


async def download_one_drama(item: dict, out_dir: Path, ffmpeg_path: str | None):
    title = item.get("title", f"video_{item.get('video_key', 'unknown')}")
    m3u8_url = item["m3u8_url"]

    # 直接使用原标题
    safe_title = title.strip()
    output_file = out_dir / f"{safe_title}.ts"

    if output_file.exists():
        print(f"已存在，跳过: {output_file.name}")
        return

    print(f"\n下载: {safe_title}")

    temp_dir = Path(tempfile.mkdtemp(prefix="91porna_"))
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }) as client:
            segments = await download_m3u8_segments(m3u8_url, temp_dir, client)

        if not segments:
            print("  没有下载到任何分片")
            return

        if ffmpeg_path:
            success = merge_with_ffmpeg(segments, output_file, ffmpeg_path)
            if not success:
                # 降级：简单二进制拼接
                print("  ffmpeg 失败，尝试简单拼接...")
                with open(output_file, "wb") as out:
                    for seg in segments:
                        out.write(seg.read_bytes())
                print(f"  简单拼接完成: {output_file}")
        else:
            print("  未检测到 ffmpeg，使用简单二进制拼接（可能有音画问题）")
            with open(output_file, "wb") as out:
                for seg in segments:
                    out.write(seg.read_bytes())
            print(f"  ✓ 已保存: {output_file}")

    except Exception as e:
        print(f"  下载失败: {e}")
    finally:
        # 清理临时分片
        try:
            for f in temp_dir.glob("*"):
                f.unlink(missing_ok=True)
            temp_dir.rmdir()
        except:
            pass


async def main():
    parser = argparse.ArgumentParser(description="91porna Windows 下载工具")
    parser.add_argument("-k", "--keyword", default="短剧", help="搜索关键词并抓取+下载")
    parser.add_argument("-n", "--max", type=int, default=5, help="最多抓取下载几个")
    parser.add_argument("--from-json", help="从已抓的 json 文件下载")
    parser.add_argument("--out", default="downloads", help="输出目录")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg = find_ffmpeg()
    if ffmpeg:
        print(f"检测到 ffmpeg: {ffmpeg}")
    else:
        print("警告: 未检测到 ffmpeg，下载后可能出现音画不同步问题。")
        print("建议安装 ffmpeg 并加入系统 PATH。")

    items = []

    if args.from_json:
        p = Path(args.from_json)
        if not p.exists():
            print(f"找不到文件: {p}")
            return
        items = json.loads(p.read_text(encoding="utf-8"))
        print(f"从 {p} 加载了 {len(items)} 条记录")
    else:
        # 现场抓取
        print("现场抓取模式...")
        try:
            from porna91_crawler import crawl
            items = await crawl(args.keyword, args.max, download=False, out_dir=str(out_dir))
        except Exception as e:
            print(f"抓取失败: {e}")
            return

    if not items:
        print("没有可下载的项目")
        return

    print(f"\n准备下载 {len(items)} 个短剧到: {out_dir}\n")

    for i, item in enumerate(items, 1):
        print(f"[{i}/{len(items)}]")
        await download_one_drama(item, out_dir, ffmpeg)

    print("\n全部下载完成！")


if __name__ == "__main__":
    asyncio.run(main())
