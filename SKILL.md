---
name: douyin-xhs-to-text
display_name: 抖红视频文案提取器
description: 把小红书 / 抖音笔记链接（图文或视频）转成可编辑文字稿。视频走 redfox.hk API 无水印下载（本机预置 Key 开箱即用，内置公共 Key 兜底）；小红书图文免登录直连 CDN。图文逐图 OCR，视频语音转写（ASR）。适用于「社媒链接转文字 / 图文 OCR / 视频字幕转写 / 内容归档」。
version: 1.3.0
author: 健康的蛤蟆 / WorkBuddy
---

# 抖红视频文案提取器（douyin-xhs-to-text）

## 这是什么

一个把**小红书 / 抖音**笔记链接变成文字稿的 Skill。

- **小红书图文** → 下载原图 → 逐图 OCR 提取文字 → 整理文稿
- **小红书视频 / 抖音视频** → 下载无水印视频 → 语音转写（ASR）→ 文字稿

下载层两路，均已**去除浏览器依赖**：

- **视频（抖音 + 小红书）**：`scripts/get_media.py` 调用 redfox.hk API 拿无水印直链。Key 优先级：本机 `REDFOX_API_KEY`（已预置，开箱即用）> video-downloader 内置公共 Key 兜底。**无需安装浏览器、无需自己注册 Key。**
- **小红书图文**：`scripts/xhs_getter.py` 解析链接里的 `xsec_token`、直连小红书 CDN 拿无水印原图。**真正零 Key、零外部服务。**（redfox 对小红书图文解析支持弱，故图文走专属免 Key 路径。）

## 什么时候用

- 用户发来小红书 / 抖音链接，要"转成文字 / 提取文案 / 视频转字幕"
- 做竞品 / 爆款内容归档、二次创作素材收集
- 把社媒内容沉淀为可检索、可编辑的文本

## 核心能力

1. **视频下载（抖音 + 小红书）**：`scripts/get_media.py`，redfox.hk API 无水印直链（本机 Key 开箱即用，公共 Key 兜底）
2. **小红书图文下载**：`scripts/xhs_getter.py`（requests + BeautifulSoup，解析 `og:image`，免登录、免 Key）
3. **图文识别**：tesseract 批量 OCR（`ocr_images.py`，快速草稿）+ 宿主多模态读图（精校）
4. **视频转写**：`scripts/transcribe.py`（openai-whisper 优先，Vosk 离线兜底）

## 使用流程

```
链接 → 判断平台/类型
   ├─ 抖音视频 / 小红书视频 → get_media.py 下载（redfox，开箱即用）
   └─ 小红书图文           → xhs_getter.py 下载（xsec_token CDN，免 Key）
        ↓
   ├─ 图文 → OCR / 多模态读图
   └─ 视频 → transcribe.py 转写
        ↓
   AI 二次整理（去口语、顺逻辑、保留数据）→ 通顺话术稿
```

### 步骤 1：下载

视频（抖音 / 小红书），开箱即用，无需 Key、无需浏览器：

```bash
python3 scripts/get_media.py "<抖音或小红书链接>" --output-dir .
# 多个链接：python3 scripts/get_media.py "<链接1>" "<链接2>" --output-dir .
# 机器可读输出：加 --json
```

小红书图文（免登录、免 Key）：

```bash
python3 scripts/xhs_getter.py "<小红书图文链接>"         # 自动识别类型
python3 scripts/xhs_getter.py --file links.txt          # 批量（每行一个链接）
```

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
| requests + beautifulsoup4 | 下载解析（含小红书图文 CDN 直连） | `pip install requests beautifulsoup4` |
| ffmpeg | 视频转写抽取音轨 | 系统包管理器安装并加入 PATH |
| openai-whisper | 视频中文转写（推荐） | `pip install openai-whisper` |
| vosk + vosk-model-small-cn-0.22 | 离线转写兜底 | `pip install vosk`（模型另下） |
| tesseract(chi_sim) + pytesseract | 图文批量 OCR（快速草稿） | 系统装 tesseract + `pip install pytesseract pillow` |
| REDFOX_API_KEY（本机已预置） | 视频下载（redfox） | 本机已预置，开箱即用；未预置时自动回退 video-downloader 内置公共 Key |
| 多模态读图能力 | 图文精校 OCR | 宿主提供（如 WorkBuddy Read） |

> 注：视频下载走 redfox.hk API（与「短视频下载器」Skill 同款方法）。本机已预置 `REDFOX_API_KEY`，故**开箱即用、无需配置**；即使没有个人 Key，脚本也会回退 video-downloader 内置的公共 Key，依然能跑（公共 Key 有调用额度，个人 Key 更稳定）。小红书图文走 `xsec_token` CDN 直连，**完全免 Key**。视频转写需联网下载 whisper 模型（走 OpenAI CDN），Vosk 路线完全离线。

## 已知边界 / 坑点

- **视频下载依赖 redfox.hk API**：本机已预置 Key，开箱即用；公共 Key 兜底也可用但有额度。若批量 / 高频触发限流，配置个人 `REDFOX_API_KEY` 即可。
- **小红书图文走专属免 Key 路径**：`xsec_token` CDN 直连，极稳。若小红书加强风控导致 `og:` 元信息缺失，则图文下载可能失败（此时视频仍可走 redfox）。
- whisper 中文小模型对专业术语有误识，必须人工校正关键数据（剂量、百分比、专有名词）。
- 下载内容仅用于个人学习 / 二次创作，注意原作者版权与平台合规。

详见 `references/workflow.md`。
