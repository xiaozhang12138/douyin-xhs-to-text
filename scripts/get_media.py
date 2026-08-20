#!/usr/bin/env python3
"""
统一媒体下载器（redfox 路线，复用 video-downloader 方法）

支持：抖音视频、小红书视频、小红书图文（photo）
原理：调用 redfox.hk parseWork/parse 接口，返回无水印直链。
Key 优先级：本机环境变量 REDFOX_API_KEY（已预置，开箱即用）> video-downloader 内置公共 key 兜底。
依赖：requests 仅此一个。

用法:
  python3 get_media.py "<链接>" --output-dir <dir>
  python3 get_media.py "<链接1>" "<链接2>" --output-dir <dir>
  python3 get_media.py "<链接>" -o . --json      # 输出 JSON 便于 AI 解析

输出：
  成功下载的文件路径，每行一个，前缀 [✓]；
  --json 时输出 {url, platform, type, files:[...]} 数组。
"""
import argparse
import json
import os
import re
import sys
import warnings
from pathlib import Path

import requests

warnings.filterwarnings("ignore", category=Warning)

API_URL = "https://redfox.hk/story/api/parseWork/parse"
# video-downloader 内置的公共 key，作为本机无个人 key 时的兜底
REDFOX_PUBLIC_KEY = "ak_b45b6a6881f4400fb321428947eb6661"

PLATFORM_MAP = {
    "dy": "抖音", "xhs": "小红书", "xhsw": "小红书", "ks": "快手", "bili": "B站",
}

GREEN = "\033[92m"; YELLOW = "\033[93m"; RED = "\033[91m"
CYAN = "\033[96m"; BOLD = "\033[1m"; RESET = "\033[0m"


def info(msg): print(f"{GREEN}[✓]{RESET} {msg}")
def warn(msg): print(f"{YELLOW}[!]{RESET} {msg}")
def error(msg): print(f"{RED}[✗]{RESET} {msg}")
def step(msg): print(f"{CYAN}[→]{RESET} {msg}")


def get_api_key() -> str:
    """本机预置 REDFOX_API_KEY 优先，否则回退 video-downloader 内置公共 key。"""
    return os.environ.get("REDFOX_API_KEY") or REDFOX_PUBLIC_KEY


def sanitize_filename(name: str) -> str:
    if not name:
        return None
    name = re.sub(r'[\\/*?:"<>|]', "", name).strip().replace(" ", "_")
    return (name[:120]) or None


def is_valid_share_url(url: str):
    """返回 (is_valid, platform_name)。只认抖音 / 小红书。"""
    patterns = [
        (r'(https?://)?(www\.)?v\.douyin\.com/', '抖音'),
        (r'(https?://)?(www\.)?douyin\.com/(video|jingxuan|note)/', '抖音'),
        (r'(https?://)?(www\.)?xhslink\.(com|cn)/', '小红书'),
        (r'(https?://)?(www\.)?xiaohongshu\.com/', '小红书'),
    ]
    for pat, name in patterns:
        if re.search(pat, url, re.IGNORECASE):
            return True, name
    return False, None


def download_file(session: requests.Session, url: str, filepath: str, desc="下载中") -> bool:
    try:
        resp = session.get(url, stream=True, timeout=120)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = int(downloaded * 100 / total)
                        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                        print(f"\r  {bar} {pct}%", end="", flush=True)
        print()
        return True
    except requests.exceptions.RequestException as e:
        error(f"下载失败: {e}")
        return False


def fetch_one(url: str, output_dir: str, session: requests.Session, api_key: str) -> dict:
    """解析并下载单个链接，返回结构化结果。"""
    url = url.strip().strip('"').strip("'")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    is_valid, platform = is_valid_share_url(url)
    if not is_valid:
        return {"url": url, "ok": False, "error": "不支持的链接格式（仅抖音/小红书）", "files": []}

    step(f"平台: {platform} | 调用 redfox API ...")
    try:
        resp = session.post(API_URL, json={"url": url, "source": "douyin-xhs-to-text"},
                            timeout=30)
        result = resp.json()
    except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
        return {"url": url, "ok": False, "error": f"API 请求失败: {e}", "files": []}

    code = result.get("code")
    if not str(code).startswith("2"):
        msg = result.get("msg", "")
        if code == 3106:
            return {"url": url, "ok": False, "error": "缺少 API Key", "files": []}
        if code == 3107:
            return {"url": url, "ok": False, "error": "API Key 无效或已失效", "files": []}
        return {"url": url, "ok": False, "error": f"API 错误 (code {code}): {msg}", "files": []}

    data = result.get("data")
    if not data:
        return {"url": url, "ok": False, "error": "API 返回空 data", "files": []}

    aweme_type = data.get("awemeType")
    title = data.get("title", "untitled")
    info(f"标题: {title[:80]}")

    os.makedirs(output_dir, exist_ok=True)
    files = []

    if aweme_type == "video":
        video_url = data.get("videoUrl")
        if not video_url:
            return {"url": url, "ok": False, "error": "API 未返回视频地址", "files": []}
        safe = sanitize_filename(title) or f"video_{platform}"
        fp = os.path.join(output_dir, f"{safe}.mp4")
        step("下载视频...")
        if download_file(session, video_url, fp):
            files.append(fp)

    elif aweme_type == "photo":
        image_urls = data.get("imageUrls") or []
        if not image_urls:
            return {"url": url, "ok": False, "error": "API 未返回图片地址", "files": []}
        safe = sanitize_filename(title) or f"photo_{platform}"
        total = len(image_urls)
        info(f"图文（共 {total} 张）")
        for i, img_url in enumerate(image_urls, 1):
            ext = os.path.splitext(img_url.split("?")[0])[1] or ".jpg"
            fp = os.path.join(output_dir, f"{safe}_{i}{ext}")
            step(f"下载图片 {i}/{total}...")
            if download_file(session, img_url, fp):
                files.append(fp)
    else:
        return {"url": url, "ok": False, "error": f"未知类型: {aweme_type}", "files": []}

    if files:
        return {"url": url, "platform": platform, "type": aweme_type,
                "title": title, "ok": True, "files": files}
    return {"url": url, "ok": False, "error": "下载未产生文件", "files": []}


def main():
    ap = argparse.ArgumentParser(description="统一媒体下载器（redfox 路线）")
    ap.add_argument("urls", nargs="+", help="抖音/小红书链接（可多个）")
    ap.add_argument("-o", "--output-dir", default=".")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = ap.parse_args()

    api_key = get_api_key()
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "X-API-KEY": api_key})

    results = []
    for url in args.urls:
        r = fetch_one(url, args.output_dir, session, api_key)
        results.append(r)
        if r.get("ok"):
            for f in r["files"]:
                size = os.path.getsize(f) / (1024 * 1024)
                info(f"已保存: {f} ({size:.1f} MB)")
        else:
            error(r.get("error", "未知错误"))
        print()

    if args.json:
        print("===JSON_RESULT===")
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(f"{BOLD}完成：{sum(1 for r in results if r.get('ok'))}/{len(results)} 个成功{RESET}")


if __name__ == "__main__":
    main()
