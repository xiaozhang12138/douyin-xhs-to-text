"""
小红书内容获取器
输入带 xsec_token 的小红书笔记链接，自动下载无水印图文/视频到本地。

原理：
- 图文: <meta property="og:image"> → CDN 无水印原图
- 视频: <meta name="og:video"> → CDN 无水印 MP4 直链
水印是 APP 端渲染时叠加的，网页版不渲染水印层。

用法:
  python3 xhs_getter.py <笔记链接> [链接2 ...]
  python3 xhs_getter.py --file links.txt
  python3 xhs_getter.py --overwrite <链接>
"""

import re, os, sys, time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

# ── 配置 ──────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.xiaohongshu.com/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
OUTPUT_DIR = "xhs_content"
ALLOWED_IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif", ".avif"}


# ── HTML 解析 ─────────────────────────────────────────────
def fetch_by_requests(note_url: str):
    """方案 A: requests + BeautifulSoup"""
    session = requests.Session()
    session.headers.update(HEADERS)
    session.get("https://www.xiaohongshu.com", timeout=10)  # 拿 Cookie
    resp = session.get(note_url, timeout=15)
    resp.encoding = "utf-8"
    return _parse_html(resp.text)


def _parse_html(html: str):
    """从 HTML 提取 og:image, og:video, og:title 和博主昵称"""
    soup = BeautifulSoup(html, "html.parser")

    # ── 图片 ──
    images = []
    for tag in soup.find_all("meta", attrs={"property": re.compile(r"og:image", re.I)}):
        url = tag.get("content", "")
        if url and url not in images:
            # 处理协议相对 URL（以 // 开头）
            if url.startswith("//"):
                url = "https:" + url
            images.append(url)
    if not images:
        for tag in soup.find_all("meta", attrs={"name": re.compile(r"og:image", re.I)}):
            url = tag.get("content", "")
            if url and url not in images:
                if url.startswith("//"):
                    url = "https:" + url
                images.append(url)

    # ── 视频 ──
    video_url = ""
    for tag in soup.find_all("meta", attrs={"name": re.compile(r"og:video", re.I)}):
        url = tag.get("content", "")
        if url.startswith("//"):
            url = "https:" + url
        if url and ("mp4" in url.lower() or "video" in url.lower() or url.startswith("http")):
            video_url = url
            break
    if not video_url:
        for tag in soup.find_all("meta", attrs={"property": re.compile(r"og:video", re.I)}):
            url = tag.get("content", "")
            if url.startswith("//"):
                url = "https:" + url
            if url and ("mp4" in url.lower() or "video" in url.lower() or url.startswith("http")):
                video_url = url
                break

    # ── 标题 ──
    title = ""
    for tag in soup.find_all("meta", attrs={"property": re.compile(r"og:title", re.I)}):
        title = tag.get("content", "").replace(" - 小红书", "").strip()
        break

    # ── 博主昵称（从 HTML 内嵌 JSON 中获取）──
    nickname = ""
    m = re.search(r'"userInfo"\s*:\s*\{[^}]*?"nickname"\s*:\s*"([^"]+)"', html)
    if m:
        nickname = m.group(1)
    else:
        m = re.search(r'"nickname"\s*:\s*"([^"]+)"', html)
        if m:
            nickname = m.group(1)

    # ── 确定笔记类型 ──
    note_type = "video" if video_url else "image"

    return {
        "title": title,
        "images": images,
        "video_url": video_url,
        "nickname": nickname,
        "type": note_type,
    }


# ── 下载 ───────────────────────────────────────────────────
def download_images(images: list, save_dir: str, prefix: str = ""):
    """下载图片到本地"""
    os.makedirs(save_dir, exist_ok=True)
    results = []
    session = requests.Session()
    session.headers.update(HEADERS)
    for idx, img_url in enumerate(images):
        path = urlparse(img_url).path
        ext = os.path.splitext(path)[1].lower()
        if ext not in ALLOWED_IMG_EXTS:
            ext = ".jpg"
        filename = f"{prefix}{idx+1}{ext}" if prefix else f"img_{idx+1}{ext}"
        filepath = os.path.join(save_dir, filename)
        if os.path.exists(filepath):
            print(f"  → [{idx+1}/{len(images)}] 已存在, 跳过")
            results.append(filepath)
            continue
        print(f"  ↓ [{idx+1}/{len(images)}] 下载中...", end=" ")
        try:
            resp = session.get(img_url, timeout=20)
            if resp.status_code == 200 and len(resp.content) > 1024:
                with open(filepath, "wb") as f:
                    f.write(resp.content)
                print(f"✓ {len(resp.content)/1024:.0f} KB")
                results.append(filepath)
            else:
                print(f"✗ HTTP {resp.status_code}")
        except Exception as e:
            print(f"✗ {e}")
        time.sleep(0.3)
    return results


def download_video(video_url: str, save_dir: str, filename: str = "video.mp4"):
    """下载视频到本地（流式下载，支持大文件）"""
    os.makedirs(save_dir, exist_ok=True)
    filepath = os.path.join(save_dir, filename)

    if os.path.exists(filepath):
        print(f"  → 已存在, 跳过 ({filepath})")
        return filepath

    print(f"  ↓ 下载中...", end=" ")
    try:
        resp = requests.get(video_url, headers=HEADERS, timeout=60, stream=True)
        if resp.status_code != 200:
            print(f"✗ HTTP {resp.status_code}")
            return None

        # 获取文件大小
        total = int(resp.headers.get("content-length", 0))

        # 流式写入
        downloaded = 0
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)

        if downloaded > 10000:
            size_str = f"{downloaded / 1024 / 1024:.1f} MB" if downloaded > 1024 * 1024 else f"{downloaded / 1024:.0f} KB"
            print(f"✓ {size_str}")
            return filepath
        else:
            os.remove(filepath)
            print("✗ 文件过小, 已删除")
            return None
    except Exception as e:
        print(f"✗ {e}")
        if os.path.exists(filepath):
            os.remove(filepath)
        return None


# ── 工具函数 ──────────────────────────────────────────────
def safe_filename(s: str, max_len: int = 30) -> str:
    """将字符串转为安全的文件名"""
    s = re.sub(r'[\\/:*?"<>|]', "_", s).strip()
    return s[:max_len] if s else ""


def resolve_short_url(url: str) -> str:
    """解析 xhslink.com 等短链接，返回真实 URL"""
    if "xhslink.com" in url or "short" in url:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
            return resp.url
        except Exception:
            return url
    return url


def _extract_note_id(url: str) -> str:
    """从 URL 中提取 note_id"""
    m = re.search(r"(?:explore|discovery/item)/([a-f0-9]+)", url)
    return m.group(1) if m else ""


# ── 主入口 ─────────────────────────────────────────────────
def get_xhs_content(note_url: str, method: str = "auto", overwrite: bool = False):
    """获取单篇小红书笔记的内容（图文/视频）

    参数:
        note_url:  带 xsec_token 的笔记链接
        method:    "auto" | "requests" | "playwright"
        overwrite: 是否覆盖已存在的文件
    返回:
        {
            "type": "image"|"video",
            "title": str,
            "nickname": str,
            "images": [str],
            "video_url": str,
            "files": [str],
            "save_dir": str
        } | None
    """
    print(f"\n▶ {note_url}")

    # 解析短链接
    orig_url = note_url
    note_url = resolve_short_url(note_url)
    if note_url != orig_url:
        print(f"  → {note_url}")

    # 免登录直连 CDN（xsec_token 方案，无需浏览器、无需任何 key）
    result = fetch_by_requests(note_url)

    title = result.get("title", "")
    nickname = result.get("nickname", "")
    note_type = result.get("type", "image")
    images = result.get("images", [])
    video_url = result.get("video_url", "")

    # 从 URL 提取 note_id（支持短链接解析后的 URL）
    note_id = _extract_note_id(note_url)
    if not note_id:
        note_id = f"note_{int(time.time())}"

    # 文件夹命名
    safe_nick = safe_filename(nickname) if nickname else ""
    folder = f"{safe_nick}_{note_id}" if safe_nick and safe_nick != "小红书" else note_id
    save_dir = os.path.join(OUTPUT_DIR, folder)

    # 视频文件名
    safe_title = safe_filename(title, 20) if title else ""
    video_filename = f"{note_id}_{safe_title}.mp4" if safe_title else f"{note_id}.mp4"

    files = []

    if note_type == "video":
        # ── 视频笔记 ──
        print(f"  🎬 视频笔记")
        if nickname:
            print(f"  博主: {nickname}")
        if title:
            print(f"  标题: {title}")

        if not video_url:
            print("  ✗ 未找到视频地址")
            return

        # 从视频URL推断扩展名
        path = urlparse(video_url).path
        ext = os.path.splitext(path)[1].lower()
        if ext not in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
            ext = ".mp4"

        # 优先用 note_id 前缀确保唯一性
        video_filename = f"{note_id}_{safe_title}{ext}" if safe_title else f"{note_id}{ext}"

        print(f"  视频: {video_filename}")
        vid_file = download_video(video_url, save_dir, video_filename)
        if vid_file:
            files.append(vid_file)
            size_mb = os.path.getsize(vid_file) / 1024 / 1024
            print(f"  ✅ 完成 ({size_mb:.1f} MB)")

        # 也下载封面图（如果有）
        if images and images[0] and not images[0].endswith(".mp4"):
            cover_dir = os.path.join(save_dir, "cover")
            cover_files = download_images([images[0]], cover_dir, f"{note_id}_")
            files.extend(cover_files)

    else:
        # ── 图文笔记 ──
        print(f"  📷 图文笔记")
        if nickname:
            print(f"  博主: {nickname}")
        if title:
            print(f"  标题: {title}")

        if not images:
            print("  ✗ 未找到图片")
            return

        print(f"  图片: {len(images)} 张 → {save_dir}/")
        files = download_images(images, save_dir, prefix=f"{note_id}_")
        print(f"  ✅ 完成 ({len(files)} 张)")

    return {
        "type": note_type,
        "title": title,
        "nickname": nickname,
        "images": images,
        "video_url": video_url,
        "files": files,
        "save_dir": save_dir,
    }


# ── 命令行 ─────────────────────────────────────────────────
if __name__ == "__main__":
    urls = []
    overwrite = False

    args = sys.argv[1:]
    if "--overwrite" in args:
        overwrite = True
        args.remove("--overwrite")

    if args:
        if args[0] in ("--file", "-f"):
            filepath = args[1] if len(args) > 1 else "links.txt"
            with open(filepath) as f:
                urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        else:
            urls = args

    if not urls:
        print("用法:")
        print("  python3 xhs_getter.py <链接1> [链接2 ...]")
        print("  python3 xhs_getter.py --file links.txt")
        print("  python3 xhs_getter.py --overwrite <链接>")
        print()
        print("支持的链接格式:")
        print("  https://www.xiaohongshu.com/explore/<id>?xsec_token=...")
        print("  https://xhslink.com/<短码>")
        sys.exit(0)

    for url in urls:
        try:
            get_xhs_content(url, overwrite=overwrite)
        except Exception as e:
            print(f"\n✗ 处理失败: {e}")
        print()
