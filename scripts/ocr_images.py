"""
小红书图文批量 OCR（替代手动逐张读图）

依赖（运行时，环境已具备）：
  - 系统 tesseract，且含 chi_sim 中文训练数据（brew install tesseract tesseract-lang）
  - Python 包 pytesseract + pillow

用法：
  python3 ocr_images.py <图片目录> [--out 输出.txt] [--min-kb 5]
  python3 ocr_images.py <图片目录> --mode accurate   # 多PSM融合+放大+术语校正，慢但准
  python3 ocr_images.py <图片目录> --mode fast       # 单趟 --psm 6，非常快
  python3 ocr_images.py <图片目录> --preprocess      # (balanced 下)灰度+2x 放大

说明：
  - 自动按文件名排序逐张识别，图间用 [图N] 分隔，方便对照原图。
  - 小于 --min-kb 的图（如小红书 logo 占位，常 <5KB）自动跳过并标注。
  - 输出为纯文本草稿，建议人工快速润色（小红书艺术字/emoji 可能误识）。
  - 若需更高质量，可回到宿主多模态读图（逐张 Read）做精校。
"""
import argparse
import glob
import json
import os
import re

from PIL import Image
import pytesseract

EXTS = ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.bmp")

# ── 双模预设 ─────────────────────────────────────────────
# accurate : 灰度2x放大 + 多 PSM(3/6/11) 融合取最长 + 术语校正，慢但准
# fast     : 单趟 --psm 6 不放大，非常快（适合批量/抓大意）
# balanced : 原默认（--psm 3，--preprocess 可选）
MODE_PRESETS = {
    "accurate": dict(preprocess=True, psms=[3, 6, 11], correct=True),
    "balanced": dict(preprocess=False, psms=[3], correct=False),
    "fast":     dict(preprocess=False, psms=[6], correct=False),
}


def natural_key(s: str):
    """按文件名中的数字自然排序，避免 _10 排到 _2 前。"""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def _load_corrections() -> dict[str, str]:
    """读取同音词校正词典（与 transcribe 共用）。"""
    p = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       "..", "references", "term_corrections.json"))
    if not os.path.isfile(p):
        return {}
    try:
        data = json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}
    merged: dict[str, str] = {}
    for k, v in data.items():
        if k.startswith("_") or not isinstance(v, dict):
            continue
        merged.update(v)
    return merged


def _clean(text: str) -> str:
    # 去中文字之间的空格（Tesseract 常把汉字逐字加空格），保留中英文边界
    return re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text).strip()


def _char_count(text: str) -> int:
    """估算有效字符数（CJK + 字母数字），用于多策略融合择优。"""
    return len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text))


def ocr_one(path: str, preprocess: bool, psm: int) -> str:
    img = Image.open(path)
    if preprocess:
        img = img.convert("L")
        img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    # 中文 + 英文；psm 3=全自动版面分析，6=假设统一块，11=稀疏文本
    text = pytesseract.image_to_string(img, lang="chi_sim+eng", config=f"--psm {psm}")
    return _clean(text)


def ocr_best(path: str, preprocess: bool, psms) -> str:
    """多 PSM 融合：跑多个配置，取有效字符最多的结果（通常最完整）。"""
    best, best_n = "", -1
    for psm in psms:
        t = ocr_one(path, preprocess, psm)
        n = _char_count(t)
        if n > best_n:
            best, best_n = t, n
    return best


def main():
    ap = argparse.ArgumentParser(description="小红书图文批量 OCR（去手动逐张读；支持 --mode 双模）")
    ap.add_argument("dir", help="图片所在目录")
    ap.add_argument("--out", default=None, help="输出 txt 路径，默认 <目录>_ocr.txt")
    ap.add_argument("--min-kb", type=int, default=5, help="跳过小于此 KB 的图（占位 logo）")
    ap.add_argument("--mode", default="balanced", choices=["accurate", "balanced", "fast"],
                    help="accurate=多PSM融合+放大+术语校正 / fast=单趟最快 / balanced=原默认")
    ap.add_argument("--preprocess", action="store_true", help="(balanced 下)灰度+2x 放大")
    args = ap.parse_args()

    preset = MODE_PRESETS.get(args.mode, MODE_PRESETS["balanced"])
    preprocess = args.preprocess or preset["preprocess"]
    psms = preset["psms"]
    corrections = _load_corrections() if preset["correct"] else {}

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
            text = ocr_best(p, preprocess, psms)
            if corrections:
                for wrong, right in corrections.items():
                    if wrong in text:
                        text = text.replace(wrong, right)
            f.write(f"\n\n[图{i}] {os.path.basename(p)}\n{text}\n")
            done += 1

    print(f"[ocr] 完成：识别 {done} 张，跳过 {skipped} 张 → {out}"
          + (f"（模式={args.mode}）" if args.mode != "balanced" else ""))


if __name__ == "__main__":
    main()
