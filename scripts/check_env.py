"""
xhs-link-to-text 环境自检

运行前一行命令确认依赖是否齐全，缺什么直接告诉你怎么装：
    python3 scripts/check_env.py

不依赖网络，只检查本机已安装的工具/包。
"""
import importlib
import os
import shutil
import subprocess
import sys


def have(mod: str) -> bool:
    try:
        importlib.import_module(mod)
        return True
    except Exception:
        return False


def check(name: str, ok: bool, hint: str = "") -> None:
    mark = "✓" if ok else "✗"
    line = f"  {mark} {name}"
    if not ok and hint:
        line += f"   →  {hint}"
    print(line)


def main() -> None:
    print("=== xhs-link-to-text 环境自检 ===\n")
    print(f"[Python] {sys.version.split()[0]}  (要求 >= 3.9)")
    py_ok = sys.version_info >= (3, 9)
    check("Python >= 3.9", py_ok)

    print("\n[Python 包]")
    check("requests", have("requests"), "pip install requests")
    check("beautifulsoup4", have("bs4"), "pip install beautifulsoup4")
    check("pytesseract", have("pytesseract"), "pip install pytesseract")
    check("pillow", have("PIL"), "pip install pillow")
    check("openai-whisper (视频转写)", have("whisper"), "pip install openai-whisper")
    check("vosk (离线兜底, 可选)", have("vosk"), "pip install vosk")

    print("\n[系统二进制]")
    ff = shutil.which("ffmpeg")
    check("ffmpeg", bool(ff), "brew install ffmpeg / apt install ffmpeg")
    ts = shutil.which("tesseract")
    check("tesseract", bool(ts), "brew install tesseract tesseract-lang")
    if ts:
        try:
            out = subprocess.run([ts, "--list-langs"], capture_output=True, text=True).stderr
            check("  tesseract 中文包 chi_sim", "chi_sim" in out,
                  "brew install tesseract-lang")
        except Exception:
            pass

    print("\n[Vosk 离线模型 (可选)]")
    cands = [os.environ.get("VOSK_MODEL_DIR"),
             os.path.expanduser("~/.workbuddy/binaries/vosk-model/vosk-model-small-cn-0.22"),
             os.path.expanduser("~/vosk-model-small-cn-0.22")]
    found = any(c and os.path.isdir(c) for c in cands if c)
    check("vosk-model-small-cn-0.22", found,
          "下载模型并设 VOSK_MODEL_DIR 指向该目录")

    print("\n=== 结论 ===")
    print("核心可用（下载 + 图文 OCR）：需 requests / bs4 / pytesseract / pillow / ffmpeg / tesseract(chi_sim)")
    print("视频转写：需 openai-whisper（联网下载模型）或 vosk + 上述模型（离线）")
    print("缺项按上面 → 提示安装即可，无需改动代码。")


if __name__ == "__main__":
    main()
