"""
视频语音转写封装（小红书链接转文字用）

优先使用 openai-whisper（默认 small 中文模型），对术语/专有名词识别明显优于
轻量离线模型。检测不到 whisper 时给出清晰报错与替代方案。

依赖（运行时）：
  - ffmpeg（whisper 提取音轨需要，已在 PATH）
  - Python 包 openai-whisper（提供 whisper CLI 或 Python API）
  - 备选：Vosk + vosk-model-small-cn-0.22（完全离线，无需联网）

用法：
  python3 transcribe.py <video.mp4> [--model small] [--language Chinese] [--out-dir DIR]
  python3 transcribe.py <video.mp4> --text-only        # 只输出纯文本到 stdout
  python3 transcribe.py <video.mp4> --vosk              # 强制用离线 Vosk（无网环境）
"""
import argparse
import os
import shutil
import subprocess
import sys


def _find_whisper() -> str | None:
    # 优先 PATH 中的 whisper，其次常见 venv 位置
    in_path = shutil.which("whisper")
    if in_path:
        return in_path
    candidates = [
        os.path.expanduser("~/.workbuddy/binaries/python/envs/default/bin/whisper"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def _find_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg"))


def _find_vosk_model() -> str | None:
    """定位 Vosk 中文模型目录：环境变量 > 常见位置 > 用户级 workbuddy 兜底。"""
    candidates = []
    env = os.environ.get("VOSK_MODEL_DIR")
    if env:
        candidates.append(env)
    candidates += [
        os.path.expanduser("~/.workbuddy/binaries/vosk-model/vosk-model-small-cn-0.22"),
        os.path.expanduser("~/vosk-model-small-cn-0.22"),
        os.path.expanduser("~/.cache/vosk-model-small-cn-0.22"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "vosk-model-small-cn-0.22"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return None


def transcribe_whisper(video: str, model: str, language: str, out_dir: str | None) -> str:
    whisper = _find_whisper()
    if not whisper:
        raise RuntimeError(
            "未找到 openai-whisper。请先安装：pip install openai-whisper\n"
            "或改用 --vosk 走离线 Vosk 路线。"
        )
    if not _find_ffmpeg():
        raise RuntimeError("未找到 ffmpeg。请先安装 ffmpeg 并加入 PATH。")
    cmd = [whisper, video, "--model", model, "--language", language, "--output_format", "txt"]
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        cmd += ["--output_dir", out_dir]
    print(f"[transcribe] whisper {model} / {language}: {video}")
    subprocess.run(cmd, check=True)
    base = os.path.splitext(os.path.basename(video))[0]
    out_txt = os.path.join(out_dir or os.path.dirname(video) or ".", base + ".txt")
    return out_txt


def transcribe_vosk(video: str, out_path: str | None) -> str:
    """离线兜底：Vosk + ffmpeg 抽取 16k 单声道 wav 后识别。"""
    if not _find_ffmpeg():
        raise RuntimeError("未找到 ffmpeg，Vosk 路线也需要它抽取音频。")
    try:
        import vosk
        import wave
    except ImportError:
        raise RuntimeError("未找到 vosk。请安装：pip install vosk，并下载 vosk-model-small-cn-0.22。")
    model_dir = _find_vosk_model()
    if not model_dir:
        raise RuntimeError(
            "未找到 Vosk 中文模型。请设置环境变量 VOSK_MODEL_DIR 指向下载好的 "
            "vosk-model-small-cn-0.22 目录，或把它放到 ~/vosk-model-small-cn-0.22。"
        )
    wav_path = (out_path or video + ".wav").replace(".wav.wav", ".wav") if out_path else video + ".wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", video, "-ar", "16000", "-ac", "1", "-f", "wav", wav_path],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    from vosk import Model, KaldiRecognizer
    wf = wave.open(wav_path, "rb")
    rec = KaldiRecognizer(Model(model_dir), wf.getframerate())
    texts = []
    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            import json
            texts.append(json.loads(rec.Result()).get("text", ""))
    import json
    texts.append(json.loads(rec.FinalResult()).get("text", ""))
    out = out_path or (video + ".vosk.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(" ".join(t for t in texts if t))
    return out


def main():
    ap = argparse.ArgumentParser(description="小红书视频语音转文字（whisper 优先，vosk 兜底）")
    ap.add_argument("video")
    ap.add_argument("--model", default="small")
    ap.add_argument("--language", default="Chinese")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--text-only", action="store_true", help="只把纯文本打印到 stdout")
    ap.add_argument("--vosk", action="store_true", help="强制走离线 Vosk")
    args = ap.parse_args()

    if args.vosk:
        out = transcribe_vosk(args.video, args.out_dir)
    else:
        try:
            out = transcribe_whisper(args.video, args.model, args.language, args.out_dir)
        except Exception as e:
            print(f"[transcribe] whisper 失败：{e}\n[transcribe] 尝试 Vosk 离线兜底...")
            out = transcribe_vosk(args.video, args.out_dir)

    if args.text_only:
        with open(out, encoding="utf-8") as f:
            print(f.read())
    else:
        print(f"[transcribe] 完成：{out}")


if __name__ == "__main__":
    main()
