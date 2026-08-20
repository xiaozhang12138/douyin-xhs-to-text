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
  python3 transcribe.py <video.mp4> [--mode accurate|fast|balanced] [--language Chinese] [--out-dir DIR]
  python3 transcribe.py <video.mp4> --mode accurate    # 大模型+beam回退，慢而准
  python3 transcribe.py <video.mp4> --mode fast        # 小模型贪心，非常快
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


# ── 双模预设 ─────────────────────────────────────────────
# accurate : 大模型 + temperature 回退，慢但准（适合要发布的稿子）
# fast     : 小模型 + 单温度贪心，非常快（适合批量归档/抓大意）
# balanced : 默认 small，兼顾（原默认行为）
# 注：mlx-whisper 不支持 beam_size/best_of，解码仅 temperature(元组=回退序列)
#     + condition_on_previous_text 有效；准确度主要靠模型尺寸拉开差距。
#     实测：large-v3-turbo 的 fp16(3GB) 在本机内存压力下会严重 swap，90s 片段耗时
#     6~11 分钟不可用；改用 4bit 量化版 large-v3-turbo-q4（~1GB，已缓存），速度可接受
#     且准确度接近 fp16。故 accurate 用 q4 大模型 + 单温度，靠模型尺寸保证准确度。
MODE_PRESETS = {
    "accurate": dict(model="large-v3-turbo-q4",
                     temperature=(0.0,), condition_on_previous_text=True),
    "balanced": dict(model="small",
                     temperature=(0.0,), condition_on_previous_text=False),
    "fast":     dict(model="base",
                     temperature=(0.0,), condition_on_previous_text=False),
}
# mlx-community 仓库名并非统一带 -mlx 后缀，逐个映射避免拉错/重复下载
MLX_REPO = {
    "tiny": "mlx-community/whisper-tiny",
    "base": "mlx-community/whisper-base-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "large-v3-turbo-q4": "mlx-community/whisper-large-v3-turbo-q4",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
}
# openai-whisper 兜底（多为 CPU）时，accurate 封顶 medium，避免数十分钟
OPENAI_MODEL = {"fast": "tiny", "balanced": "small", "accurate": "medium"}


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


def transcribe_mlx(video: str, model: str, language: str, out_dir: str | None,
                   decode: dict | None = None) -> str:
    """mlx-whisper：Apple Silicon 加速，最快。decode 传解码参数（beam/temperature 等）。"""
    if not _find_ffmpeg():
        raise RuntimeError("未找到 ffmpeg。请先安装 ffmpeg 并加入 PATH。")
    import mlx_whisper
    base = os.path.splitext(os.path.basename(video))[0]
    out_dir = out_dir or os.path.dirname(video) or "."
    os.makedirs(out_dir, exist_ok=True)
    out_txt = os.path.join(out_dir, base + ".txt")
    repo = MLX_REPO.get(model, f"mlx-community/whisper-{model}-mlx")
    # mlx-whisper 仅支持 temperature(元组=回退序列) 与 condition_on_previous_text，
    # 不支持 beam_size/best_of，传了会直接报错。
    ALLOWED = ("temperature", "condition_on_previous_text")
    kwargs = {}
    if decode:
        for k in ALLOWED:
            if k in decode:
                kwargs[k] = decode[k]
    print(f"[transcribe] mlx-whisper {model} / {language} / {repo}"
          + (f" / decode={decode}" if decode else "") + f": {video}")
    result = mlx_whisper.transcribe(
        video,
        path_or_hf_repo=repo,
        language=language.lower(),
        verbose=False,
        **kwargs,
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


def do_transcribe(video: str, engine: str, model: str, language: str, out_dir: str | None,
                 mode: str = "balanced") -> str:
    preset = MODE_PRESETS.get(mode, MODE_PRESETS["balanced"])
    # --model 显式指定时优先，否则用模式预设
    if model == "auto":
        model = preset["model"]
    decode = {k: v for k, v in preset.items() if k != "model"}
    # openai 兜底路线用更小的模型名（CPU 跑大模型不现实）
    if engine == "openai":
        model = OPENAI_MODEL.get(mode, "small")
    if engine == "vosk":
        return transcribe_vosk(video, os.path.join(out_dir, os.path.splitext(os.path.basename(video))[0] + ".txt") if out_dir else None)
    if engine == "openai":
        return transcribe_openai(video, model, language, out_dir)
    if engine == "mlx":
        return transcribe_mlx(video, model, language, out_dir, decode)
    # 默认：mlx 优先，失败回退 openai，再回退 vosk
    try:
        return transcribe_mlx(video, model, language, out_dir, decode)
    except Exception as e_mlx:
        print(f"[transcribe] mlx 失败：{e_mlx}\n[transcribe] 回退 openai-whisper...")
        try:
            return transcribe_openai(video, OPENAI_MODEL.get(mode, "small"), language, out_dir)
        except Exception as e_open:
            print(f"[transcribe] openai 失败：{e_open}\n[transcribe] 回退离线 Vosk...")
            return transcribe_vosk(video, os.path.join(out_dir, os.path.splitext(os.path.basename(video))[0] + ".txt") if out_dir else None)


def main():
    ap = argparse.ArgumentParser(description="视频语音转文字（mlx-whisper 优先，openai/vosk 兜底；支持 --mode 双模）")
    ap.add_argument("video")
    ap.add_argument("--mode", default="balanced", choices=["accurate", "balanced", "fast"],
                    help="accurate=大模型慢而准 / fast=小模型非常快 / balanced=默认small")
    ap.add_argument("--model", default="auto", help="显式指定 whisper 模型（覆盖 --mode 默认）")
    ap.add_argument("--language", default="Chinese")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--engine", default="auto", choices=["auto", "mlx", "openai", "vosk"])
    ap.add_argument("--text-only", action="store_true", help="只把纯文本打印到 stdout")
    ap.add_argument("--no-correct", action="store_true", help="关闭术语自动校正")
    args = ap.parse_args()

    out = do_transcribe(args.video, args.engine, args.model, args.language, args.out_dir, args.mode)

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
