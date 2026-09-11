# 91porna Windows 短剧工具

在 Windows 上抓取并下载 https://91porna.com/comic 的短剧。

## 文件说明

| 文件                        | 作用                              |
|----------------------------|-----------------------------------|
| `install.bat`              | 第一次使用时安装依赖              |
| `run.bat`                  | **最推荐**：一键抓取 + 下载       |
| `porna91_crawler.py`       | 只抓地址（进阶用）                |
| `windows_full_downloader.py` | 只下载（进阶用）                |

---

## 第一次使用流程（最简单）

1. 把整个文件夹复制到 Windows
2. 双击 `install.bat`（只需执行一次）
3. 双击 `run.bat`
4. 按提示输入：
   - 搜索关键词（例如 `AI短剧`）
   - 要抓几个
   - 保存路径（可直接回车）

工具会自动：
- 先抓取 m3u8 地址
- 再下载视频
- 自动调用 ffmpeg 转成 `.mp4`（如果检测到 ffmpeg）

---

## 进阶用法

只抓地址：
```powershell
python porna91_crawler.py -k "AI短剧" -n 6
```

只下载（使用已抓的文件）：
```powershell
python windows_full_downloader.py --from-json captured_91porna.json --out "D:\短剧"
```

---

## 推荐安装 ffmpeg（强烈建议）

下载地址：https://www.gyan.dev/ffmpeg/builds/

下载 `ffmpeg-release-essentials.zip`，解压后把 `bin` 文件夹加入系统环境变量。

装完后可以自动把 `.ts` 转成 `.mp4`。

---

## 注意事项

- 第一次必须运行 `install.bat`
- 建议一次不要抓太多（`-n` 建议 4~8）
- 文件会尽量使用网站原标题
- 音画不同步属于网站本身问题，可用 ffmpeg 重新封装修复

有问题随时问。
