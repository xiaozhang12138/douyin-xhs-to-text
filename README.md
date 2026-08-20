# 抖红视频文案提取器 · douyin-xhs-to-text

> 把小红书 / 抖音笔记链接，变成可编辑的文字稿。视频走 redfox API 无水印下载（本机已预置 Key，开箱即用）；小红书图文免登录直连 CDN（免 Key）。图文走 OCR、视频走语音转写（ASR）。

**一句话简介**：输入社媒链接（图文 / 视频），自动下载 → 识别 → 输出文字稿。给做内容归档、二次创作、竞品分析的人用，省去手动抄录和逐张读图。

---

## 它能做什么

| 输入 | 输出 |
|---|---|
| 小红书**图文**笔记链接 | 逐图 OCR 提取的文字稿 |
| 小红书 / 抖音**视频**笔记链接 | 语音转写（ASR）文字稿（可带时间戳）|

典型场景：社媒链接转文字、图文文案提取、视频字幕转写、内容归档与二次创作素材收集。

## 特点

- **视频下载开箱即用**：`get_media.py` 走 redfox.hk API 拿无水印直链。本机已预置 `REDFOX_API_KEY`，无需安装浏览器、无需自己注册 Key；未预置时自动回退 video-downloader 内置公共 Key。
- **小红书图文免登录、免 Key**：`xhs_getter.py` 解析链接里的 `xsec_token`，直连小红书 CDN 拿无水印原图，不需要账号 Cookie、不依赖任何外部 API。
- **双形态覆盖**：图文走 OCR，视频走 ASR，按类型自动分流。
- **转写双引擎**：默认 openai-whisper（small 中文，术语更准），无网 / 失败自动兜底 Vosk 离线模型。
- **自包含**：下载脚本、转写封装都打包在 `scripts/` 内，可独立运行。

## 安装

### 作为 WorkBuddy Skill 安装

将本仓库放到 `~/.workbuddy/skills/douyin-xhs-to-text/`（用户级）或 `<项目>/.workbuddy/skills/douyin-xhs-to-text/`（项目级）。

### 依赖

```bash
pip install -r requirements.txt        # 核心：下载 + 图文 OCR
# 视频转写另装：pip install openai-whisper   （系统还需 ffmpeg）
# 系统级（非 pip）：brew install ffmpeg tesseract tesseract-lang
# 视频下载走 redfox API（与「短视频下载器」同款），本机已预置 Key，无需额外安装
```

> 图文有两种识别路线：脚本 OCR（`ocr_images.py`，tesseract 批量，快但偶有错字）或宿主多模态读图（精校，几乎零误识，适合要发布的稿子）。

## 使用

```bash
# 抖音 / 小红书视频：redfox 无水印下载（开箱即用，无需 Key、无需浏览器）
python3 scripts/get_media.py "https://v.douyin.com/xxxx" --output-dir .
python3 scripts/get_media.py "<链接1>" "<链接2>" --output-dir . --json

# 小红书图文：免登录、免 Key 直连 CDN
python3 scripts/xhs_getter.py "https://www.xiaohongshu.com/explore/<id>?xsec_token=..."
python3 scripts/xhs_getter.py --file links.txt

# 图文：批量 OCR 一步出稿（草稿）
python3 scripts/ocr_images.py "xhs_content/.../" --preprocess
#     精校：用宿主读图能力逐张识别后人工整理

# 视频：转写
python3 scripts/transcribe.py "<视频>.mp4" --out-dir .
#     离线兜底加 --vosk；只要纯文本加 --text-only
```

## 目录结构

```
douyin-xhs-to-text/
├── SKILL.md              # Skill 元信息与流程
├── README.md             # 本文件
├── scripts/
│   ├── get_media.py      # 视频下载（抖音/小红书，redfox API，开箱即用）
│   ├── xhs_getter.py     # 小红书图文下载（xsec_token CDN 直连，免 Key）
│   ├── transcribe.py     # 视频语音转写封装（whisper 优先，vosk 兜底）
│   └── ocr_images.py     # 图文批量 OCR（tesseract，快速草稿）
└── references/
    └── workflow.md       # 详细流程、坑点与合规提示
```

## 已知边界

- **视频下载依赖 redfox.hk API**：本机已预置 Key 开箱即用；公共 Key 兜底也可用但有额度，高频触发限流时配置个人 `REDFOX_API_KEY` 即可。
- **小红书图文走专属免 Key 路径**：`xsec_token` CDN 直连，极稳；若小红书加强风控导致 `og:` 元信息缺失，图文下载可能失败（视频仍可走 redfox）。
- whisper 中文小模型对专业术语有误识（如 DHA↔"跌垂"），关键数据须人工校正。
- 下载内容仅用于个人学习 / 二次创作，遵守原作者版权与平台规则。

## 命令行安装 / 给 AI 用

### 1. 下载（命令行，任何人都能拉）

```bash
git clone https://github.com/xiaozhang12138/douyin-xhs-to-text.git
cd douyin-xhs-to-text
```

### 2. 装依赖（一行）

```bash
pip install -r requirements.txt        # 核心：下载 + 图文 OCR
# 视频转写另装：pip install openai-whisper   （系统还需 ffmpeg）
# 系统级（非 pip）：brew install ffmpeg tesseract tesseract-lang
```

### 3. 自检环境（AI 拿到先跑这个，缺什么直接告诉你）

```bash
python3 scripts/check_env.py
```

### 4. 让 Agent 能直接调用

Skill 只有在 agent 的 skills 目录里才会被识别。把整个文件夹放进去即可：

```bash
# 用户级（所有项目/对话可用）：
cp -r . ~/.workbuddy/skills/douyin-xhs-to-text/

# 或项目级（仅当前项目）：
# cp -r . <你的项目>/.workbuddy/skills/douyin-xhs-to-text/
```

放进之后，agent 读取到 `SKILL.md` 就知道怎么用；你发一条小红书 / 抖音链接，它就能自动下载 → 识别 → 出文字稿。

> 注意：下载和自检脚本本身**不依赖 WorkBuddy**，纯 Python 就能跑（图文精校那条"多模态读图"路线才需要宿主支持）。所以即使没有 WorkBuddy，命令行也能完成下载 + OCR / 转写。

## License

MIT —— 自由使用、修改、再发布，保留版权声明即可。
