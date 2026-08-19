"""
小红书图文批量 OCR（替代手动逐张读图）

依赖（运行时，环境已具备）：
  - 系统 tesseract，且含 chi_sim 中文训练数据（brew install tesseract tesseract-lang）
  - Python 包 pytesseract + pillow

用法：
  python3 ocr_images.py <图片目录> [--out 输出.txt] [--min-kb 5] [--preprocess]
  python3 ocr_images.py <图片目录> --preprocess    # 灰度+2x 放大，提升小字识别

说明：
  - 自动按文件名排序逐张识别，图间用 [图N] 分隔，方便对照原图。
  - 小于 --min-kb 的图（如小红书 logo 占位，常 <5KB）自动跳过并标注。
  - 输出为纯文本草稿，建议人工快速润色（小红书艺术字/emoji 可能误识）。
  - 若需更高质量，可回到宿主多模态读图（逐张 Read）做精校。
"""
import argparse
import glob
import os
import re

from PIL import Image
import pytesseract

EXTS = ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.bmp")


def natural_key(s: str):
    """按文件名中的数字自然排序，避免 _10 排到 _2 前。"""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def ocr_one(path: str, preprocess: bool) -> str:
    img = Image.open(path)
    if preprocess:
        img = img.convert("L")
        img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    # 中文 + 英文；psm 3 = 全自动版面分析
    text = pytesseract.image_to_string(img, lang="chi_sim+eng", config="--psm 3")
    # 去中文字之间的空格（Tesseract 常把汉字逐字加空格），保留中英文边界
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    return text.strip()


def main():
    ap = argparse.ArgumentParser(description="小红书图文批量 OCR（去手动逐张读）")
    ap.add_argument("dir", help="图片所在目录")
    ap.add_argument("--out", default=None, help="输出 txt 路径，默认 <目录>_ocr.txt")
    ap.add_argument("--min-kb", type=int, default=5, help="跳过小于此 KB 的图（占位 logo）")
    ap.add_argument("--preprocess", action="store_true", help="灰度+2x 放大，提升小字识别")
    args = ap.parse_args()

    files = []
    for e in EXTS:
        files += glob.glob(os.path.join(args.dir, e))
    # 自然排序：避免 _10 排到 _2 前面
    files = sorted(set(files), key=lambda p: natural_key(os.path.basename(p)))
    if not files:
        print(f"[ocr] 目录中未找到图片：{args.dir}")
        return

    out = args.out or (args.dir.rstrip("/") + "_ocr.txt")
    done, skipped = 0, 0
    with open(out, "w", encoding="utf-8") as f:
        for i, p in enumerate(files, 1):
            size_kb = os.path.getsize(p) / 1024
            if size_kb < args.min_kb:
                f.write(f"\n\n[图{i}] {os.path.basename(p)} ({size_kb:.0f}KB) — 跳过(疑似占位)\n")
                skipped += 1
                continue
            text = ocr_one(p, args.preprocess)
            f.write(f"\n\n[图{i}] {os.path.basename(p)}\n{text}\n")
            done += 1

    print(f"[ocr] 完成：识别 {done} 张，跳过 {skipped} 张 → {out}")


if __name__ == "__main__":
    main()
