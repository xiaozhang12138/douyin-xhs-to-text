# xhs-link-to-text 详细流程与避坑

## 端到端流程

```
用户给链接
   │
   ▼
xhs_getter.py 下载
   ├─ 解析短链 (xhslink.com) → 真实 URL
   ├─ requests + BS4 抓 og:image / og:video / og:title / nickname
   ├─ 图文 → 下载原图到 xhs_content/<昵称>_<note_id>/
   └─ 视频 → 下载无水印 MP4（并附封面）
   │
   ▼
判断类型
   ├─ 图文 → 宿主多模态读图逐张 OCR → 拼成文稿（跳过 logo 占位图）
   └─ 视频 → transcribe.py
                   ├─ --mode accurate : large-v3-turbo + beam5 + temp 回退（慢而准）
                   ├─ --mode fast     : base + 贪心解码（非常快）
                   ├─ --mode balanced : small（默认）
                   └─ 失败/Vosk → 离线兜底
   │
   ▼
AI 二次整理（去口语、顺逻辑、保留数据）→ 通顺话术稿
```

## 实测选型结论（2026-08-19 真机验证）

| 环节 | 实际可用 | 备注 |
|---|---|---|
| 下载-图文 | `xhs_getter.py` (requests) | 带 xsec_token 直连 CDN，免登录、免 Key 成功 |
| 下载-视频 | `get_media.py` (redfox API) | 本机预置 REDFOX_API_KEY 开箱即用；无个人 Key 时回退内置公共 Key |
| 视频转写 | mlx-whisper（Apple Silicon 加速） | 默认 small；**明显优于** Vosk small-cn（Vosk 把 EPA/DHA/炎症 识别成乱码，弃用）；accurate 用 large-v3-turbo、fast 用 base |
| 图文 OCR | 宿主 Read 多模态 / `ocr_images.py` | 多模态精校几乎零误识；脚本 OCR fast=单趟、accurate=多 PSM 融合+放大+术语校正 |

## 双模（--mode）设计要点（2026-08-20 新增）

- **accurate（慢但准）**：转写 `large-v3-turbo-q4`（4bit 量化，~1GB，已缓存）+ 单温度 + `condition_on_previous_text`；OCR 灰度2x放大 + 多 PSM(3/6/11) 融合取最长 + 套用 `term_corrections.json`。实测 90s 片段 ≈ 235s（约 45× fast）。
- **fast（非常快）**：转写 `base` + 贪心（`temperature=0`）；OCR 单趟 `--psm 6` 不放大。实测 90s 片段 ≈ 5s。
- **balanced（默认）**：转写 `small`；OCR `--psm 3`（可选 `--preprocess`）。
- mlx-whisper **不支持 beam_size/best_of**，解码仅 `temperature`(元组=回退序列) 与 `condition_on_previous_text` 有效；故准确度靠模型尺寸拉开。
- `large-v3-turbo` 的 fp16(3GB) 在本机内存压力下会严重 swap（90s 片段 6~11 分钟不可用），accurate 改用 4bit 量化版 `large-v3-turbo-q4`。
- 本机已缓存 `base / small / large-v3-turbo-q4` 三个 mlx 模型，两种模式均**免联网下载**；非 Apple 芯片回退 openai-whisper 时 accurate 封顶 medium。
- 术语校正词典 `references/term_corrections.json` 与 transcribe 共用，OCR accurate 模式也会套用。

> Whisper 模型下载走 OpenAI CDN（非 HuggingFace）。实测 HuggingFace 代理 502 时 whisper CLI 仍可下；Vosk 完全离线无需联网。

## 常见坑

1. **同音误识**：whisper 把 DHA 写成"跌垂"、炎症写成"盐症"、ISSN 写错。产出后必须人工校正关键数据（剂量、百分比、专有名词），存疑用括号标。
2. **相对路径报错**：transcribe.py 用绝对路径调用，避免工作目录错位。
3. **xsec_token 必带**：短链/xhslink 可自动解析；explore 长链必须带 xsec_token 才能拿到 CDN 资源。
4. **封面/占位图**：图文第 1 张常是小红书 logo，识别时跳过，避免污染文稿。

## 合规提示

- 下载内容仅用于个人学习、归档与二次创作，遵守原作者版权与小红书平台规则。
- 对外发布衍生内容前，按自有账号合规要求再核医学/事实/剂量边界（本 Skill 不做事实核验）。

## 图文 OCR：脚本化 vs 多模态（2026-08-19 实测）

| 方案 | 工具 | 质量 | 速度 | 适用 |
|---|---|---|---|---|
| 脚本批量 | tesseract(chi_sim) + `ocr_images.py` | 骨架/关键词可达，形近错字、Ω→Q、emoji 乱码 | 一步出稿、自动批处理 | 快速草稿、批量归档、索引 |
| 多模态精校 | 宿主 Read 逐张读 | 几乎零误识 | 手动逐张 | 要发布的精校稿 |

**脚本实测**（13 张知识科普图）：识别 12 张、跳过 1 张 logo 占位；内容骨架完整，但存在：
- 形近错字：低芥酸→低苜酸、二十碳→二十碌、炎症→炎狄
- 符号误识：Ω3/Ω6→Q3/06、α-亚麻酸→ta-亚麻酸
- emoji/语气词变乱码（"画画""略略""国鸿"等拟声）

**优化点已落地**：`ocr_images.py` 已加自然排序（避免 _10 排到 _2 前）+ 中文字间去空格后处理，可读性大幅提升。

**建议工作流**：先用 `ocr_images.py` 一步出草稿抓全貌 → 关键笔记/要发布的再用多模态 Read 精校 → AI 二次整理成通顺话术。
