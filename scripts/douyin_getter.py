"""
抖音 / 多平台视频下载器（免 key 优先）

设计目标：默认【零 key】。

下载优先级：
  1. Playwright 无头浏览器拦截真实视频请求（免 key，需浏览器二进制 ~150MB）
     —— 浏览器原生生成抖音签名，无需 redfox / 无需任何 key
  2. (可选兜底) redfox.hk API：仅当显式 --use-redfox 或环境变量 REDFOX_API_KEY 存在
     且 Playwright 不可用时使用。这是外部服务，非默认路径。

依赖：
  - requests（解析短链 / 兜底下载）
  - playwright + chromium（免 key 主路径）：pip install playwright && playwright install chromium

用法：
  python3 douyin_getter.py "<抖音分享链接>" --output-dir ./downloads
  python3 douyin_getter.py "<链接>" --use-redfox          # 强制走 redfox（需 key）
  python3 douyin_getter.py "<链接>" --no-playwright        # 跳过浏览器，仅 redfox（需 key）

说明：
  - 抖音分享短链（v.douyin.com/xxx/）会被自动解析为真实页面。
  - 视频文件名取自页面标题，自动清理非法字符。
"""
import argparse
import os
import re
import sys

import requests


UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")
HEADERS = {"User-Agent": UA, "Referer": "https://www.douyin.com/"}


def _safe_name(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|\n\r\t#]', "_", s).strip()
    return s[:80] or "douyin_video"


def _download(url: str, dest: str, referer: str = "https://www.douyin.com/") -> str:
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    with requests.get(url, headers={"User-Agent": UA, "Referer": referer},
                      stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1024 * 256):
                if chunk:
                    f.write(chunk)
    return dest


# ----------------------------- 免 key：Playwright 拦截 -----------------------------

def _download_playwright(url: str, output_dir: str) -> str:
    from playwright.sync_api import sync_playwright

    captured = {}
    title = "douyin_video"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True,
                                    args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = browser.new_context(
            user_agent=UA,
            viewport={"width": 390, "height": 844},
            locale="zh-CN",
        )
        page = ctx.new_page()

        def on_response(resp):
            u = resp.url
            ct = resp.headers.get("content-type", "")
            if ("video" in ct) or u.endswith((".mp4", ".mov", ".m4s")) or "playaddr" in u or "365yg" in u:
                size = int(resp.headers.get("content-length", 0) or 0)
                if size > captured.get("size", 0):
                    captured["url"] = u
                    captured["size"] = size
                    captured["referer"] = resp.headers.get("referer", "https://www.douyin.com/")

        page.on("response", on_response)

        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        # 取标题
        try:
            title = page.title() or title
        except Exception:
            pass
        # 触发播放 / 滚动，强制浏览器发出视频请求
        try:
            page.evaluate("() => { const v=document.querySelector('video'); if(v){ v.muted=true; v.play().catch(()=>{}); } }")
        except Exception:
            pass
        try:
            page.mouse.wheel(0, 400)
        except Exception:
            pass
        # 等待视频请求出现
        try:
            page.wait_for_event("response",
                                lambda r: ("video" in r.headers.get("content-type", "")) or
                                           r.url.endswith((".mp4", ".mov", ".m4s")) or
                                           "playaddr" in r.url,
                                timeout=30000)
        except Exception:
            pass
        # 兜底：再从 DOM 拿 <video> src
        if "url" not in captured:
            try:
                src = page.evaluate("() => { const v=document.querySelector('video'); return v? (v.src||(v.querySelector('source')&&v.querySelector('source').src)) : null; }")
                if src:
                    captured["url"] = src
                    captured["size"] = 0
            except Exception:
                pass
        browser.close()

    if "url" not in captured:
        raise RuntimeError("Playwright 未拦截到视频请求（抖音可能改版或需登录）。可加 --use-redfox 走兜底。")

    dest = os.path.join(output_dir, _safe_name(title) + ".mp4")
    _download(captured["url"], dest, referer=captured.get("referer", "https://www.douyin.com/"))
    return dest


# ----------------------------- 兜底：redfox API（需 key）-----------------------------

REDFOX_URL = "https://redfox.hk/story/api/parseWork/parse"


def _download_redfox(url: str, output_dir: str, api_key: str | None, source: str = "douyin-xhs-to-text") -> str:
    key = api_key or os.environ.get("REDFOX_API_KEY")
    if not key:
        raise RuntimeError("redfox 兜底需要 REDFOX_API_KEY（免 key 主路径失败，请安装 playwright chromium 后重试）。")
    r = requests.post(REDFOX_URL, json={"url": url, "source": source},
                      headers={"Content-Type": "application/json", "X-API-KEY": key}, timeout=60)
    data = r.json()
    if data.get("code") not in (0, 200, 2000, "0", "200", "2000"):
        raise RuntimeError(f"redfox 解析失败：{data}")
    info = data["data"]
    video_url = info.get("videoUrl") or info.get("url") or info.get("video")
    if not video_url:
        raise RuntimeError("redfox 未返回视频地址（字段：videoUrl）。")
    title = _safe_name(info.get("title", "douyin_video"))
    dest = os.path.join(output_dir, title + ".mp4")
    _download(video_url, dest)
    return dest


# ----------------------------- 入口 -----------------------------

def download(url: str, output_dir: str = ".", use_redfox: bool = False,
             no_playwright: bool = False, api_key: str | None = None) -> str:
    os.makedirs(output_dir, exist_ok=True)

    # 1) 免 key 主路径：Playwright
    if not use_redfox and not no_playwright:
        try:
            return _download_playwright(url, output_dir)
        except Exception as e:
            print(f"[douyin] Playwright 免 key 路径失败：{e}", file=sys.stderr)
            if not os.environ.get("REDFOX_API_KEY") and not api_key:
                raise RuntimeError("免 key 路径不可用，且未检测到 REDFOX_API_KEY。请安装浏览器：pip install playwright && playwright install chromium")
            print("[douyin] 回退 redfox 兜底（需 key）...", file=sys.stderr)

    # 2) 兜底：redfox（需 key）
    return _download_redfox(url, output_dir, api_key)


def main():
    ap = argparse.ArgumentParser(description="抖音/多平台视频下载（免 key 优先）")
    ap.add_argument("url")
    ap.add_argument("--output-dir", default=".")
    ap.add_argument("--use-redfox", action="store_true", help="强制走 redfox（需 REDFOX_API_KEY）")
    ap.add_argument("--no-playwright", action="store_true", help="跳过浏览器，仅 redfox（需 key）")
    ap.add_argument("--api-key", default=None, help="redfox key（也可设环境变量 REDFOX_API_KEY）")
    args = ap.parse_args()

    dest = download(args.url, args.output_dir, args.use_redfox, args.no_playwright, args.api_key)
    print(f"[douyin] 完成：{dest}")


if __name__ == "__main__":
    main()
