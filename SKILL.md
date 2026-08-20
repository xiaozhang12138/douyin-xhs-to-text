---
name: douyin-xhs-to-text
display_name: 抖红视频文案提取器
description: 把小红书 / 抖音笔记链接（图文或视频）转成可编辑文字稿。小红书免登录直连 CDN；抖音走 Playwright 无头浏览器免 key 拦截下载。图文逐图 OCR，视频语音转写（ASR）。适用于「社媒链接转文字 / 图文 OCR / 视频字幕转写 / 内容归档」。
version: 1.2.0
author: 健康的蛤蟆 / WorkBuddy
---

# 抖红视频文案提取器（douyin-xhs-to-text）

## 这是什么

一个把**小红书 / 抖音**笔记链接变成文字稿的 Skill。

- **小红书图文** → 下载原图 → 逐图 OCR 提取文字 → 整理文稿
- **小红书视频 / 抖音视频** → 下载无水印视频 → 语音转写（ASR）→ 文字稿
- （抖音图文暂未验证，待补充）

小红书部分**免登录**：靠链接里的 `xsec_token` 直连 CDN。抖音部分**默认免 key**：用 Playwright 无头浏览器打开分享页、原生生成签名并拦截真实视频请求；仅当浏览器不可用时，才回退到 redfox.hk API（需 Key，属可选兜底）。

## 什么时候用

- 用户发来小红书 / 抖音链接，要"转成文字 / 提取文案 / 视频转字幕"
- 做竞品 / 爆款内容归档、二次创作素材收集
- 把社媒内容沉淀为可检索、可编辑的文本

## 核心能力

1. **小红书下载**：`scripts/xhs_getter.py`（requests + BeautifulSoup，解析 `og:image` / `og:video` 元信息，免登录）
2. **抖音 / 多平台下载**：`scripts/douyin_getter.py`（Playwright 无头浏览器免 key 拦截真实视频请求；redfox.hk API 仅作可选兜底，需 Key）
3. **图文识别**：tesseract 批量 OCR（`ocr_images.py`，快速草稿）+ 宿主多模态读图（精校）
4. **视频转写**：`scripts/transcribe.py`（openai-whisper 优先，Vosk 离线兜底）

## 使用流程

```
链接 → 判断平台
   ├─ 小红书 → xhs_getter.py 下载 → 图文 OCR / 视频转写
   └─ 抖音   → douyin_getter.py 下载 → transcribe.py 转写
```

### 步骤 1：下载

小红书（免登录）：

```bash
python3 scripts/xhs_getter.py "<小红书链接>" ["<链接2>" ...]
```

抖音（**默认免 key**，需先装浏览器）：

```bash
# 一次性安装浏览器（约 150MB）
pip install playwright && playwright install chromium
# 直接下载，无需任何 Key
python3 scripts/douyin_getter.py "<抖音链接>" --output-dir .
# 例：python3 scripts/douyin_getter.py "https://v.douyin.com/xxxx" --output-dir .
```

> 仅当 Playwright 不可用、且你确有 redfox key 时，才用兜底：
> `python3 scripts/douyin_getter.py "<抖音链接>" --use-redfox`  （需 `REDFOX_API_KEY`）

### 步骤 2a：图文 → 文字

两条路线，按速度 / 质量取舍：

- **快速草稿（推荐先用）**：`python3 scripts/ocr_images.py <图片目录> --preprocess`
  用 tesseract(chi_sim) 批量识别，一步出稿，自动跳过 logo 占位图（<5KB）。适合批量归档、抓大意、做索引。
- **精校稿**：用宿主多模态读图能力（如 WorkBuddy 的 Read 工具）逐张读取，几乎零误识，适合要对外发布的稿子。

> Tesseract 对艺术字 / Ω 符号 / emoji 有误识（如 Ω3→Q3、低芥酸→低苜酸），关键内容建议回退多模态精校。详见 `references/workflow.md`。

### 步骤 2b：视频 → 文字

```bash
python3 scripts/transcribe.py "<视频>.mp4" --out-dir .
# 离线兜底：--vosk；只要纯文本：--text-only
```

whisper 对同音词（如 DHA↔"跌垂"、炎症↔"盐症"）可能误识，产出后需人工校正明显错误，存疑处用括号标注。

### 步骤 3：AI 二次整理（推荐）

把原始稿交给 AI 去口语、顺逻辑、保留关键数据，输出通顺话术。

## 依赖

| 依赖 | 用途 | 安装 |
|---|---|---|
| Python 3.9+ | 运行脚本 | 系统自带 |
| requests + beautifulsoup4 | 下载解析 | `pip install requests beautifulsoup4` |
| ffmpeg | 视频转写抽取音轨 | 系统包管理器安装并加入 PATH |
| openai-whisper | 视频中文转写（推荐） | `pip install openai-whisper` |
| vosk + vosk-model-small-cn-0.22 | 离线转写兜底 | `pip install vosk`（模型另下） |
| tesseract(chi_sim) + pytesseract | 图文批量 OCR（快速草稿） | 系统装 tesseract + `pip install pytesseract pillow` |
| **playwright + chromium** | **抖音免 key 下载（主路径）** | `pip install playwright && playwright install chromium` |
| REDFOX_API_KEY（可选） | 抖音下载兜底（仅 Playwright 不可用时） | 去 [redfox.hk](https://redfox.hk/settings/api-keys) 注册获取 |
| 多模态读图能力 | 图文精校 OCR | 宿主提供（如 WorkBuddy Read） |

> 注：小红书下载默认用 requests，免登录。抖音下载默认走 Playwright（免 key，浏览器原生生成签名）；仅在浏览器缺失且你提供 redfox key 时才回退 redfox。**抖音线现在默认零 Key、零外部服务**。视频转写需联网下载 whisper 模型（走 OpenAI CDN），Vosk 路线完全离线。

## 已知边界 / 坑点

- **抖音下载默认免 key**：Playwright 无头浏览器拦截真实视频请求（需先 `playwright install chromium`）。仅当浏览器不可用且你有 redfox key 时，才回退 redfox（可选兜底）。抖音图文未验证。
- 小红书若加强风控，`og:` 元信息可能缺失，此时需 Playwright 或登录态兜底。
- whisper 中文小模型对专业术语有误识，必须人工校正关键数据（剂量、百分比、专有名词）。
- 下载内容仅用于个人学习 / 二次创作，注意原作者版权与平台合规。

详见 `references/workflow.md`。
