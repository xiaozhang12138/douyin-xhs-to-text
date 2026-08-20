#!/usr/bin/env python3
"""
抖红视频文案提取器 · 一键链路编排器

把「判断平台/类型 → 下载 → 转写/OCR → 汇总」串成一条命令，
并支持 --mode 双模：
  --mode accurate : 大模型 + 多 PSM 融合，慢但准
  --mode fast     : 小模型 + 单趟 OCR，非常快
  --mode balanced : 默认 small / --psm 3

路由规则：
  - 抖音（视频）          → get_media.py（redfox，本机 Key 开箱即用）
  - 小红书视频 / 图文     → xhs_getter.py（xsec_token CDN，免 Key）优先；
                            若图文/视频解析失败，回退 get_media.py（redfox）

依赖：scripts/ 同目录的 get_media / xhs_getter / transcribe / ocr_images
      以及它们各自的运行环境（ffmpeg / mlx-whisper / tesseract 等）。

用法:
  python3 run.py "<链接>" --mode fast
  python3 run.py "<链接1>" "<链接2>" --mode accurate --out-dir ./out
  python3 run.py "<链接>" --mode balanced --json
"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import get_media          # noqa: E402
import xhs_getter         # noqa: E402
import transcribe         # noqa: E402
import ocr_images         # noqa: E402

EXTS = ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.bmp")


def is_xhs(url: str) -> bool:
    return bool(get_media.is_valid_share_url(url)[1] == "小红书") or "xiaohongshu" in url or "xhslink" in url


def download(url: str, out_dir: str) -> dict:
    """返回 {ok, type, files, title, platform}。小红书优先走免 Key 的 xhs_getter。"""
    if is_xhs(url):
        # 小红书：免登录 CDN 直连（图文/视频都支持），更稳且免 Key
        xhs_getter.OUTPUT_DIR = out_dir
        try:
            r = xhs_getter.get_xhs_content(url)
        except Exception as e:
            print(f"[run] xhs_getter 失败: {e}，回退 redfox ...")
            r = None
        if r and r.get("files"):
            ntype = "image" if r.get("type") == "image" else "video"
            return {"ok": True, "type": ntype, "files": r["files"],
                    "title": r.get("title", ""), "platform": "小红书",
                    "save_dir": r.get("save_dir", out_dir)}
        # 解析失败 → 回退 redfox（视频仍可下；图文 redfox 支持弱，可能也失败）
        print("[run] 回退 get_media（redfox）...")
        res = get_media.fetch_one(url, out_dir, get_media.requests.Session(), get_media.get_api_key())
        if res.get("ok"):
            ntype = "image" if res.get("type") == "photo" else "video"
            return {"ok": True, "type": ntype, "files": res["files"],
                    "title": res.get("title", ""), "platform": res.get("platform", "小红书"),
                    "save_dir": out_dir}
        return {"ok": False, "error": res.get("error", "下载失败"), "files": []}

    # 抖音：只能走 redfox
    res = get_media.fetch_one(url, out_dir, get_media.requests.Session(), get_media.get_api_key())
    if res.get("ok"):
        ntype = "image" if res.get("type") == "photo" else "video"
        return {"ok": True, "type": ntype, "files": res["files"],
                "title": res.get("title", ""), "platform": res.get("platform", "抖音"),
                "save_dir": out_dir}
    return {"ok": False, "error": res.get("error", "下载失败"), "files": []}


def process(dl: dict, mode: str, out_dir: str) -> list:
    """对下载结果做转写/OCR，返回生成的 txt 文件路径列表。"""
    txts = []
    if dl["type"] == "video":
        for vid in dl["files"]:
            if not vid.lower().endswith((".mp4", ".mov", ".m4a", ".wav", ".webm")):
                continue
            out = transcribe.do_transcribe(vid, "auto", "auto", "Chinese", out_dir, mode)
            txts.append(out)
    else:
        # 图文：用图片所在目录做 OCR
        img_dir = dl.get("save_dir") or os.path.dirname(dl["files"][0])
        out = os.path.join(out_dir, (dl.get("title") or "ocr").replace(" ", "_")[:60] + "_ocr.txt")
        sys.argv = ["ocr_images.py", img_dir, "--out", out, "--mode", mode]
        ocr_images.main()
        if os.path.isfile(out):
            txts.append(out)
    return txts


def main():
    ap = argparse.ArgumentParser(description="抖红链接 → 文字稿 一键链路（支持 --mode 双模）")
    ap.add_argument("urls", nargs="+", help="抖音/小红书链接（可多个）")
    ap.add_argument("--mode", default="balanced", choices=["accurate", "balanced", "fast"])
    ap.add_argument("-o", "--out-dir", default="./xhs_output")
    ap.add_argument("--json", action="store_true", help="机器可读输出汇总")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    summary = []
    for url in args.urls:
        print(f"\n{'='*60}\n▶ {url}\n{'='*60}")
        dl = download(url, args.out_dir)
        if not dl.get("ok"):
            print(f"[run] ✗ 下载失败: {dl.get('error')}")
            summary.append({"url": url, "ok": False, "error": dl.get("error")})
            continue
        print(f"[run] 类型={dl['type']} 平台={dl['platform']} 文件数={len(dl['files'])}")
        txts = process(dl, args.mode, args.out_dir)
        summary.append({"url": url, "ok": True, "type": dl["type"],
                        "platform": dl["platform"], "title": dl.get("title"),
                        "media": dl["files"], "texts": txts})

    # 汇总一个合并文稿
    merged = os.path.join(args.out_dir, "汇总文稿.md")
    with open(merged, "w", encoding="utf-8") as f:
        for s in summary:
            if not s.get("ok"):
                continue
            f.write(f"\n\n# {s.get('title') or s['url']}\n")
            f.write(f"> 平台: {s['platform']} | 类型: {s['type']} | 模式: {args.mode}\n")
            for t in s.get("texts", []):
                if os.path.isfile(t):
                    f.write(f"\n---\n\n{open(t, encoding='utf-8').read()}")

    print(f"\n{'='*60}")
    print(f"[run] 完成 {sum(1 for s in summary if s.get('ok'))}/{len(summary)} 条 → 合并稿: {merged}")
    if args.json:
        print("===JSON_RESULT===")
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
