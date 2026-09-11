#!/usr/bin/env python3
"""
91porna Windows Crawler - Improved Version

抓取 https://91porna.com/comic 上的短剧真实 m3u8 地址。

改进点：
- 随机延迟，降低被检测风险
- 尝试从详情页提取更准确的标题
- 更稳定的等待和点击逻辑
- 输出更完整的 JSON（包含 title, video_key, m3u8_url）

用法示例：
python porna91_crawler.py -k "AI短剧" -n 6
python porna91_crawler.py -k "短剧" -n 4 --download
"""

import asyncio
import json
import random
import re
import argparse
import sys
from pathlib import Path
from urllib.parse import quote
from playwright.async_api import async_playwright

# Windows 控制台默认 GBK，避免打印特殊字符时报错
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

CAPTURED = []

def on_request(request):
    url = request.url
    if ".m3u8" in url.lower():
        print(f"[捕获] {url[:110]}")
        CAPTURED.append({
            "m3u8_url": url,
            "referer": request.headers.get("referer", "")
        })

async def get_title_from_detail(page, detail_url: str) -> str:
    """访问详情页尝试获取真实标题"""
    try:
        await page.goto(detail_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(random.uniform(1.2, 2.0))

        # 尝试多种方式拿标题
        selectors = [
            "h1",
            ".title",
            "[class*='title']",
            "meta[property='og:title']",
            "title"
        ]
        for sel in selectors:
            try:
                if sel == "title":
                    t = await page.title()
                elif sel.startswith("meta"):
                    el = await page.query_selector(sel)
                    t = await el.get_attribute("content") if el else ""
                else:
                    el = await page.query_selector(sel)
                    t = await el.inner_text() if el else ""
                
                if t and len(t.strip()) > 6 and "91porna" not in t.lower():
                    return t.strip()[:80]
            except:
                continue
    except Exception as e:
        print(f"  获取标题失败: {e}")
    return ""

async def crawl(keyword: str, max_items: int, download: bool, out_dir: str):
    if download:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
    kw = quote(keyword)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        page.on("request", on_request)

        targets = []
        seen = set()
        page_num = 1
        max_pages = 50  # 安全上限，防止无限翻页

        while len(targets) < max_items and page_num <= max_pages:
            if page_num == 1:
                url = f"https://91porna.com/comic/index/search?keyword={kw}"
            else:
                url = f"https://91porna.com/comic/index/search?keyword={kw}&page={page_num}"

            print(f"正在访问第 {page_num} 页...")
            await page.goto(url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(random.uniform(1.5, 2.8))

            links = await page.eval_on_selector_all(
                'a[href*="/comic/index/detail?video_key="]',
                "els => els.map(e => ({href: e.href}))"
            )

            new_count = 0
            for link in links:
                m = re.search(r"video_key=(\d+)", link["href"])
                if m:
                    vk = m.group(1)
                    if vk not in seen:
                        seen.add(vk)
                        targets.append({"video_key": vk, "detail_url": link["href"]})
                        new_count += 1
                        if len(targets) >= max_items:
                            break

            print(f"  第 {page_num} 页新增 {new_count} 个，当前共 {len(targets)} 个")

            if new_count == 0:
                print("  本页没有新内容，停止翻页")
                break

            page_num += 1

        print(f"最终收集到 {len(targets)} 个短剧（已翻 {page_num-1} 页）")
        targets = targets[:max_items]

        results = []

        for i, t in enumerate(targets, 1):
            print(f"\n[{i}/{len(targets)}] 处理 VID={t['video_key']}")

            # 记录本轮开始前已捕获的数量，只把之后新捕获到的 m3u8 归到这个视频
            capture_start = len(CAPTURED)

            # 访问 embed 页触发播放器
            embed = f"https://91porna.com/comic/index/embed?id={t['video_key']}"
            try:
                await page.goto(embed, wait_until="domcontentloaded", timeout=25000)
            except Exception as e:
                print(f"  打开播放页失败: {e}")
                continue
            await asyncio.sleep(random.uniform(3.5, 5.5))

            # 尝试点击播放
            try:
                await page.click("video, .xgplayer-start, .xgplayer-play", timeout=4000)
                await asyncio.sleep(2.5)
            except:
                pass

            # 获取更好标题
            title = await get_title_from_detail(page, t["detail_url"])
            if not title:
                title = f"video-{t['video_key']}"

            # 收集本次访问捕获到的 m3u8
            this_round = CAPTURED[capture_start:]
            if not this_round:
                print(f"  未捕获到 m3u8，跳过 VID={t['video_key']}")

            for item in this_round:
                results.append({
                    "video_key": t["video_key"],
                    "title": title,
                    "m3u8_url": item["m3u8_url"]
                })

            # 随机等待，模拟真人
            await asyncio.sleep(random.uniform(2.5, 4.5))

        await browser.close()

    # 去重：同一个视频只保留第一条 m3u8（同一视频常被捕获多次，仅 auth_key 参数不同）
    seen = set()
    final = []
    for r in results:
        if r["video_key"] not in seen:
            seen.add(r["video_key"])
            final.append(r)

    # 保存结果
    out = Path("captured_91porna.json")
    out.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n共保存 {len(final)} 条记录 → captured_91porna.json")

    if download:
        print("\n开始下载 m3u8 ...")
        await download_m3u8s(final, out_dir)

    return final


async def download_m3u8s(items, out_dir):
    """简单保存 m3u8 文件（不处理 AES，适合先保存地址）"""
    import httpx
    Path(out_dir).mkdir(exist_ok=True)

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for i, item in enumerate(items, 1):
            safe = "".join(c for c in item["title"] if c.isalnum() or c in " _-")[:55]
            filename = f"{safe}.m3u8"
            try:
                r = await client.get(item["m3u8_url"])
                if r.status_code == 200:
                    (Path(out_dir) / filename).write_bytes(r.content)
                    print(f"[{i}] 已保存 {filename}")
            except Exception as e:
                print(f"[{i}] 下载失败: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-k", "--keyword", default="短剧")
    parser.add_argument("-n", "--max", type=int, default=5)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--out", default="downloads")
    args = parser.parse_args()

    final = asyncio.run(crawl(args.keyword, args.max, args.download, args.out))
    if not final:
        print("没有抓到任何 m3u8 地址。")
        sys.exit(1)
