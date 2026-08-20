"""
视频语音转写封装（抖红视频文案提取器 / douyin-xhs-to-text）

转写引擎优先级：
  1. mlx-whisper（Apple Silicon 加速，最快；默认 small 中文）— 首选
  2. openai-whisper（CPU/CUDA，通用兜底）
  3. Vosk + vosk-model-small-cn-0.22（完全离线，无网环境兜底）

转写完成后自动套用 references/term_corrections.json 的【实测确认】同音词校正，
减少人工校对成本。方言等未确认项默认不启用。

依赖（运行时）：
  - ffmpeg（抽取音轨，已在 PATH）
  - Python 包：mlx-whisper（优先）/ openai-whisper / vosk
  - Vosk 中文模型（离线兜底用）

用法：
  python3 transcribe.py <video.mp4> [--model small] [--language Chinese] [--out-dir DIR]
  python3 transcribe.py <video.mp4> --text-only        # 只输出纯文本到 stdout
  python3 transcribe.py <video.mp4> --no-correct       # 关闭术语自动校正
  python3 transcribe.py <video.mp4> --engine openai    # 指定引擎
  python3 transcribe.py <video.mp4> --vosk             # 强制离线 Vosk
"""
import argparse
import json
import os
import shutil
import subprocess
import sys


def _find_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg"))


def _default_whisper() -> str | None:
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


def _load_corrections() -> dict[str, str]:
    """读取同音词校正词典（合并通用 + 各垂直领域）。"""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "..", "references", "term_corrections.json")
    p = os.path.normpath(p)
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


def _apply_corrections(text: str, corrections: dict[str, str]) -> str:
    if not corrections:
        return text
    for wrong, right in corrections.items():
        if wrong in text:
            text = text.replace(wrong, right)
    return text


def transcribe_mlx(video: str, model: str, language: str, out_dir: str | None) -> str:
    """mlx-whisper：Apple Silicon 加速，最快。"""
    if not _find_ffmpeg():
        raise RuntimeError("未找到 ffmpeg。请先安装 ffmpeg 并加入 PATH。")
    import mlx_whisper
    base = os.path.splitext(os.path.basename(video))[0]
    out_dir = out_dir or os.path.dirname(video) or "."
    os.makedirs(out_dir, exist_ok=True)
    out_txt = os.path.join(out_dir, base + ".txt")
    print(f"[transcribe] mlx-whisper {model} / {language}: {video}")
    result = mlx_whisper.transcribe(
        video,
        path_or_hf_repo=f"mlx-community/whisper-{model}-mlx",
        language=language.lower(),
        verbose=False,
    )
    text = result.get("text", "")
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write(text.strip() + "\n")
    return out_txt


def transcribe_openai(video: str, model: str, language: str, out_dir: str | None) -> str:
    """openai-whisper：通用兜底（CPU/CUDA）。"""
    whisper = _default_whisper()
    if not whisper:
        raise RuntimeError(
            "未找到 openai-whisper。请先安装：pip install openai-whisper\n"
            "或改用 --engine mlx / --vosk。"
        )
    if not _find_ffmpeg():
        raise RuntimeError("未找到 ffmpeg。请先安装 ffmpeg 并加入 PATH。")
    cmd = [whisper, video, "--model", model, "--language", language, "--output_format", "txt"]
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        cmd += ["--output_dir", out_dir]
    print(f"[transcribe] openai-whisper {model} / {language}: {video}")
    subprocess.run(cmd, check=True)
    base = os.path.splitext(os.path.basename(video))[0]
    return os.path.join(out_dir or os.path.dirname(video) or ".", base + ".txt")


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
    wav_path = out_path + ".wav" if out_path else video + ".wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", video, "-ar", "16000", "-ac", "1", "-f", "wav", wav_path],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    from vosk import Model, KaldiRecognizer
    import json as _json
    wf = wave.open(wav_path, "rb")
    rec = KaldiRecognizer(Model(model_dir), wf.getframerate())
    texts = []
    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            texts.append(_json.loads(rec.Result()).get("text", ""))
    texts.append(_json.loads(rec.FinalResult()).get("text", ""))
    out = out_path or (video + ".vosk.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(" ".join(t for t in texts if t))
    return out


def do_transcribe(video: str, engine: str, model: str, language: str, out_dir: str | None) -> str:
    if engine == "vosk":
        return transcribe_vosk(video, os.path.join(out_dir, os.path.splitext(os.path.basename(video))[0] + ".txt") if out_dir else None)
    if engine == "openai":
        return transcribe_openai(video, model, language, out_dir)
    if engine == "mlx":
        return transcribe_mlx(video, model, language, out_dir)
    # 默认：mlx 优先，失败回退 openai，再回退 vosk
    try:
        return transcribe_mlx(video, model, language, out_dir)
    except Exception as e_mlx:
        print(f"[transcribe] mlx 失败：{e_mlx}\n[transcribe] 回退 openai-whisper...")
        try:
            return transcribe_openai(video, model, language, out_dir)
        except Exception as e_open:
            print(f"[transcribe] openai 失败：{e_open}\n[transcribe] 回退离线 Vosk...")
            return transcribe_vosk(video, os.path.join(out_dir, os.path.splitext(os.path.basename(video))[0] + ".txt") if out_dir else None)


def main():
    ap = argparse.ArgumentParser(description="视频语音转文字（mlx-whisper 优先，openai/vosk 兜底）")
    ap.add_argument("video")
    ap.add_argument("--model", default="small")
    ap.add_argument("--language", default="Chinese")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--engine", default="auto", choices=["auto", "mlx", "openai", "vosk"])
    ap.add_argument("--text-only", action="store_true", help="只把纯文本打印到 stdout")
    ap.add_argument("--no-correct", action="store_true", help="关闭术语自动校正")
    args = ap.parse_args()

    out = do_transcribe(args.video, args.engine, args.model, args.language, args.out_dir)

    if args.no_correct:
        final = out
    else:
        corrections = _load_corrections()
        if corrections:
            raw = open(out, encoding="utf-8").read()
            fixed = _apply_corrections(raw, corrections)
            if fixed != raw:
                open(out, "w", encoding="utf-8").write(fixed)
                print(f"[transcribe] 已套用术语校正（{len(corrections)} 条候选）")
        final = out

    if args.text_only:
        print(open(final, encoding="utf-8").read())
    else:
        print(f"[transcribe] 完成：{final}")


if __name__ == "__main__":
    main()
