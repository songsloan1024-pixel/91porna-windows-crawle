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
import re
import sys

# Windows 控制台默认 GBK，避免打印 ✓ 等字符时报错
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

try:
    import httpx
except ImportError:
    print("请先安装 httpx: pip install httpx")
    sys.exit(1)

try:
    from Crypto.Cipher import AES
except ImportError:
    AES = None  # 遇到 AES-128 加密的 m3u8 时再提示安装


CONCURRENCY = 8   # 同时下载的分片数
RETRIES = 3       # 每个分片最多重试次数

_ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def sanitize_filename(name: str, max_len: int = 150) -> str:
    """去掉 Windows 文件名非法字符，保留其余原标题"""
    name = _ILLEGAL_CHARS.sub(" ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:max_len].rstrip(" .")


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


def parse_ext_x_key(line: str, base_url: str) -> dict | None:
    """解析 #EXT-X-KEY 标签，返回 {method, uri, iv}"""
    attrs = {}
    for m in re.finditer(r'([A-Z0-9-]+)=("([^"]*)"|([^,]*))', line.split(":", 1)[1]):
        attrs[m.group(1)] = m.group(3) if m.group(3) is not None else m.group(4)
    method = attrs.get("METHOD", "NONE").upper()
    if method == "NONE":
        return None
    iv = attrs.get("IV")
    if iv:
        iv = bytes.fromhex(iv[2:] if iv.lower().startswith("0x") else iv).rjust(16, b"\x00")
    return {"method": method, "uri": urljoin(base_url, attrs.get("URI", "")), "iv": iv}


def decrypt_segment(data: bytes, key: bytes, iv: bytes) -> bytes:
    """AES-128-CBC 解密一个分片，并去掉 PKCS7 填充"""
    cipher = AES.new(key, AES.MODE_CBC, iv)
    plain = cipher.decrypt(data)
    pad = plain[-1] if plain else 0
    if 1 <= pad <= 16 and plain.endswith(bytes([pad]) * pad):
        plain = plain[:-pad]
    return plain


async def download_m3u8_segments(m3u8_url: str, output_dir: Path, client: httpx.AsyncClient) -> list[Path]:
    """下载 m3u8 及其所有 ts 分片（支持 AES-128 加密）"""
    print(f"  正在解析播放列表...")
    resp = await client.get(m3u8_url)
    if resp.status_code != 200:
        print(f"  无法获取 m3u8: {resp.status_code}")
        return []

    content = resp.text
    base_url = str(resp.url).rsplit("/", 1)[0] + "/"

    # 每个分片记录 (url, key_info)，key_info 为 None 表示未加密
    segments = []
    current_key = None
    media_sequence = 0
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXT-X-KEY"):
            current_key = parse_ext_x_key(line, base_url)
            continue
        if line.startswith("#EXT-X-MEDIA-SEQUENCE"):
            media_sequence = int(line.split(":", 1)[1].strip() or 0)
            continue
        if line.startswith("#"):
            continue
        segments.append((urljoin(base_url, line), current_key))

    if not segments:
        print("  播放列表中没有找到分片")
        return []

    # 预先获取所有用到的密钥
    key_cache: dict[str, bytes] = {}
    for _, key_info in segments:
        if key_info and key_info["uri"] not in key_cache:
            if key_info["method"] != "AES-128":
                print(f"  不支持的加密方式: {key_info['method']}")
                return []
            if AES is None:
                print("  该视频为 AES-128 加密，请先安装依赖: pip install pycryptodome")
                return []
            kr = await client.get(key_info["uri"], timeout=30)
            if kr.status_code != 200 or len(kr.content) != 16:
                print(f"  获取解密密钥失败: {kr.status_code}")
                return []
            key_cache[key_info["uri"]] = kr.content
    if key_cache:
        print("  检测到 AES-128 加密，已获取密钥，下载时自动解密")

    print(f"  共 {len(segments)} 个分片，开始下载...")

    sem = asyncio.Semaphore(CONCURRENCY)
    done = 0

    async def fetch_one(i: int, seg_url: str, key_info: dict | None) -> Path | None:
        nonlocal done
        seg_path = output_dir / f"seg_{i:05d}.ts"
        async with sem:
            for attempt in range(1, RETRIES + 1):
                try:
                    r = await client.get(seg_url, timeout=30)
                    if r.status_code == 200 and r.content:
                        data = r.content
                        if key_info:
                            # 未指定 IV 时，按 HLS 规范用媒体序号作为 IV
                            iv = key_info["iv"] or (media_sequence + i - 1).to_bytes(16, "big")
                            data = decrypt_segment(data, key_cache[key_info["uri"]], iv)
                        seg_path.write_bytes(data)
                        done += 1
                        if done % 20 == 0 or done == len(segments):
                            print(f"    已下载 {done}/{len(segments)}")
                        return seg_path
                    print(f"    分片 {i} 返回 {r.status_code}（第 {attempt} 次）")
                except Exception as e:
                    print(f"    分片 {i} 出错: {e}（第 {attempt} 次）")
                await asyncio.sleep(1.5 * attempt)
        return None

    results = await asyncio.gather(
        *(fetch_one(i, url, key) for i, (url, key) in enumerate(segments, 1))
    )
    missing = [i for i, r in enumerate(results, 1) if r is None]
    if missing:
        print(f"  有 {len(missing)} 个分片下载失败（例如第 {missing[0]} 片），为避免生成残缺视频，本条放弃。请稍后重试。")
        return []

    return list(results)


def merge_with_ffmpeg(segment_files: list[Path], output_file: Path, ffmpeg_path: str):
    """使用 ffmpeg 合并 ts 分片"""
    # 创建 concat 文件
    concat_file = output_file.parent / "concat_list.txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for seg in segment_files:
            # Windows 下路径要处理
            f.write(f"file '{seg.as_posix()}'\n")

    cmd = [
        ffmpeg_path, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        "-movflags", "+faststart",
        str(output_file)
    ]

    print(f"  使用 ffmpeg 合并 → {output_file.name}")
    try:
        # ffmpeg 输出里带中文文件名，必须按 UTF-8 解码，否则 Windows 默认 GBK 会报错
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
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

    # 尽量保留原标题，只去掉 Windows 文件名不允许的字符
    safe_title = sanitize_filename(title) or f"video_{item.get('video_key', 'unknown')}"
    # 有 ffmpeg 直接输出 .mp4，没有则只能输出 .ts
    mp4_file = out_dir / f"{safe_title}.mp4"
    ts_file = out_dir / f"{safe_title}.ts"
    output_file = mp4_file if ffmpeg_path else ts_file

    for existing in (mp4_file, ts_file):
        if existing.exists():
            print(f"已存在，跳过: {existing.name}")
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
                output_file.unlink(missing_ok=True)
                with open(ts_file, "wb") as out:
                    for seg in segments:
                        out.write(seg.read_bytes())
                print(f"  简单拼接完成: {ts_file}")
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
