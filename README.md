# xhs-link-to-text · 小红书链接转文字 Skill

> 把一条小红书笔记链接，变成可编辑的文字稿。免登录、靠 `xsec_token` 直连 CDN 拉无水印原图/视频，图文走 OCR、视频走语音转写（ASR）。

**一句话简介**：输入小红书笔记链接（图文 / 视频），自动下载 → 识别 → 输出文字稿。给做内容归档、二次创作、竞品分析的人用，省去手动抄录和逐张读图。

---

## 它能做什么

| 输入 | 输出 |
|---|---|
| 小红书**图文**笔记链接 | 逐图 OCR 提取的文字稿 |
| 小红书**视频**笔记链接 | 语音转写（ASR）文字稿（可带时间戳）|

典型场景：小红书链接转文字、图文文案提取、视频字幕转写、社媒内容归档与二次创作素材收集。

## 特点

- **免登录**：解析链接里的 `xsec_token`，直连小红书 CDN 拿无水印原图/视频，不需要账号 Cookie。
- **双形态覆盖**：图文走 OCR，视频走 ASR，一条命令分辨类型自动分流。
- **转写双引擎**：默认 openai-whisper（small 中文，术语更准），无网/失败自动兜底 Vosk 离线模型。
- **自包含**：下载脚本、转写封装都打包在 `scripts/` 内，可独立运行。

## 安装

### 作为 WorkBuddy Skill 安装

将本仓库放到 `~/.workbuddy/skills/xhs-link-to-text/`（用户级）或 `<项目>/.workbuddy/skills/xhs-link-to-text/`（项目级）。

### 依赖

```bash
# 下载 + 视频转写
pip install requests beautifulsoup4 openai-whisper
# 离线兜底（可选）：pip install vosk  + 下载 vosk-model-small-cn-0.22
# 反爬兜底（可选）：pip install playwright && playwright install
# 图文批量 OCR（可选）：pip install pytesseract pillow  + 系统装 tesseract(chi_sim)
```

系统还需安装 **ffmpeg** 并加入 PATH（视频转写抽取音轨用）。

> 图文有两种识别路线：脚本 OCR（`ocr_images.py`，tesseract 批量，快但偶有错字）或宿主多模态读图（精校，几乎零误识，适合要发布的稿子）。

## 使用

```bash
# 1. 下载图文/视频（自动识别类型）
python3 scripts/xhs_getter.py "https://www.xiaohongshu.com/explore/<id>?xsec_token=..."

# 2a. 图文：批量 OCR 一步出稿（草稿）
python3 scripts/ocr_images.py "xhs_content/.../" --preprocess
#     精校：用宿主读图能力逐张识别后人工整理

# 2b. 视频：转写
python3 scripts/transcribe.py "xhs_content/.../<视频>.mp4" --out-dir .
#     离线兜底加 --vosk；只要纯文本加 --text-only
```

## 目录结构

```
xhs-link-to-text/
├── SKILL.md              # Skill 元信息与流程
├── README.md             # 本文件
├── scripts/
│   ├── xhs_getter.py     # 小红书内容下载（图文/视频，免登录）
│   ├── transcribe.py     # 视频语音转写封装（whisper 优先，vosk 兜底）
│   └── ocr_images.py     # 图文批量 OCR（tesseract，快速草稿）
└── references/
    └── workflow.md       # 详细流程、坑点与合规提示
```

## 已知边界

- 仅适配**小红书**链接；抖音/视频号需另接下载器。
- 小红书若加强风控导致 `og:` 元信息缺失，需 Playwright 或登录态兜底。
- whisper 中文小模型对专业术语有误识（如 DHA↔"跌垂"），关键数据须人工校正。
- 下载内容仅用于个人学习/二次创作，遵守原作者版权与平台规则。

## 命令行安装 / 给 AI 用

### 1. 下载（命令行，任何人都能拉）

```bash
git clone https://github.com/xiaozhang12138/xhs-link-to-text.git
cd xhs-link-to-text
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
cp -r . ~/.workbuddy/skills/xhs-link-to-text/

# 或项目级（仅当前项目）：
# cp -r . <你的项目>/.workbuddy/skills/xhs-link-to-text/
```

放进之后，agent 读取到 `SKILL.md` 就知道怎么用；你发一条小红书链接，它就能自动下载 → 识别 → 出文字稿。

> 注意：下载和自检脚本本身**不依赖 WorkBuddy**，纯 Python 就能跑（图文精校那条"多模态读图"路线才需要宿主支持）。所以即使没有 WorkBuddy，命令行也能完成下载 + OCR/转写。

## License

MIT —— 自由使用、修改、再发布，保留版权声明即可。
