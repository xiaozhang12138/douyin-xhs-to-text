---
name: xhs-link-to-text
description: 把小红书笔记链接（图文或视频）转成可编辑的文字稿。输入带 xsec_token 的笔记链接，自动下载无水印图文/视频，图文逐图 OCR 提取文字，视频用语音识别（ASR）转写。适用于「小红书链接转文字 / 图文 OCR / 视频字幕转写 / 社媒内容抓取归档」等场景。免登录，靠 xsec_token 直连 CDN。
version: 1.0.0
author: 健康的蛤蟆 / WorkBuddy
---

# 小红书链接转文字（xhs-link-to-text）

## 这是什么

一个把小红书笔记链接变成文字稿的 Skill。支持两种笔记：

- **图文笔记** → 下载原图 → 逐图 OCR 提取图片里的文字 → 整理成文稿
- **视频笔记** → 下载无水印视频 → 语音转写（ASR）→ 输出带/不带时间戳的文字稿

整个过程**免登录**：靠链接里的 `xsec_token` 参数直连小红书 CDN 拉原图/视频，不需要账号 Cookie。

## 什么时候用

- 用户发来一条小红书链接，要"转成文字 / 提取文案 / 视频转字幕"
- 做竞品/爆款内容归档、二次创作素材收集
- 把社媒内容沉淀为可检索、可编辑的文本

## 核心能力

1. **下载**：`scripts/xhs_getter.py`，基于 requests + BeautifulSoup，解析 `og:image` / `og:video` 元信息直连 CDN，无水印。
2. **图文识别**：下载的图片交给宿主的多模态读图能力（如 WorkBuddy 的 Read 工具）逐图识别文字，人工拼成文稿。
3. **视频转写**：`scripts/transcribe.py`，优先 openai-whisper（small 中文模型，术语识别更准），无网/失败自动兜底 Vosk 离线模型。

## 使用流程

```
链接 → xhs_getter.py 下载 → 判断类型
                          ├─ 图文 → 读图 OCR → 整理文字稿
                          └─ 视频 → transcribe.py 转写 → 校正文字稿
```

### 步骤 1：下载

```bash
python3 scripts/xhs_getter.py "<小红书链接>" ["<链接2>" ...]
# 或批量：python3 scripts/xhs_getter.py --file links.txt
```

下载到 `xhs_content/<博主>_<note_id>/`，图文为 `.jpg/.png`，视频为 `.mp4`。

### 步骤 2a：图文 → 文字

两条路线，按速度/质量取舍：

- **快速草稿（推荐先用）**：`python3 scripts/ocr_images.py <图片目录> --preprocess`
  用 tesseract(chi_sim) 批量识别，一步出稿，自动跳过 logo 占位图（<5KB）。适合批量归档、抓大意、做索引。
- **精校稿**：用宿主多模态读图能力（如 WorkBuddy 的 Read 工具）逐张读取，几乎零误识，适合要对外发布的稿子。

> Tesseract 对艺术字 / Ω 符号 / emoji 有误识（如 Ω3→Q3、低芥酸→低苜酸），关键内容建议回退多模态精校。详见 `references/workflow.md`。

### 步骤 2b：视频 → 文字

```bash
python3 scripts/transcribe.py "xhs_content/.../<视频>.mp4" --out-dir .
# 离线兜底：--vosk；只要纯文本：--text-only
```

whisper 对同音词（如 DHA↔"跌垂"、炎症↔"盐症"）可能误识，产出后需人工校正明显错误，存疑处用括号标注。

### 步骤 3：AI 二次整理（推荐）

把两份原始稿交给 AI 去口语、顺逻辑、保留关键数据，输出通顺话术（见上一轮产出的 `鱼油科普_AI整理通顺版.md` 范式）。

## 依赖

| 依赖 | 用途 | 安装 |
|---|---|---|
| Python 3.9+ | 运行脚本 | 系统自带 |
| requests + beautifulsoup4 | 下载解析 | `pip install requests beautifulsoup4` |
| ffmpeg | 视频转写抽取音轨 | 系统包管理器安装并加入 PATH |
| openai-whisper | 视频中文转写（推荐） | `pip install openai-whisper` |
| vosk + vosk-model-small-cn-0.22 | 离线转写兜底 | `pip install vosk`（模型另下） |
| tesseract(chi_sim) + pytesseract | 图文批量 OCR（快速草稿） | 系统装 tesseract + `pip install pytesseract pillow` |
| 多模态读图能力 | 图文精校 OCR | 宿主提供（如 WorkBuddy Read） |
| playwright（可选） | 反爬兜底 | `pip install playwright` 后 `playwright install` |

> 注：`xhs_getter.py` 默认用 requests；遇反爬可自动/手动切 Playwright。视频转写需联网下载 whisper 模型（走 OpenAI CDN），Vosk 路线完全离线。

## 已知边界 / 坑点

- 抖音、视频号等**非小红书**链接不适配本 Skill，需另接对应下载器。
- 小红书若加强风控，`og:` 元信息可能缺失，此时需 Playwright 或登录态兜底。
- whisper 中文小模型对专业术语有误识，必须人工校正关键数据（剂量、百分比、专有名词）。
- 下载内容仅用于个人学习/二次创作，注意原作者版权与平台合规。

详见 `references/workflow.md`。
