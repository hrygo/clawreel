---
name: clawreel
description: 触发：用户要制作短视频、配音、音乐MV、直播脚本。流程：脚本生成 → TTS配音（Edge逐词时间戳）→ 图片生成 → 视频合成 → 字幕烧录 → 发布。不触发：视频播放问题、编码问题、手动剪辑现有视频。
---

# ClawReel - AI 短视频语义对齐流水线

## 核心能力

> **声音、字幕、画面三同步。** 图片切换时机由 TTS 逐词时间戳（~50ms）精确驱动，每张图内容由对应语句语义生成。

---

## 流水线概览

```
check → script → align → assets → compose → post → publish
         │        │        │         │
         │        │        │         └─ 片头视频（segments[0] I2V/T2V）
         │        │        └─ 正文图片（segments[1:]）
         │        └─ segments.json（assets/segments_xxx.json）
         └─ script.json（assets/script_xxx.json）
```

**核心规则**：
- TTS 配音从 **0 秒开始**，片头 + 正文连续配音
- `segments[0]` 是片头，`segments[1:]` 是正文
- 片头时长由 TTS 自动决定（`segments[0].duration_sec`）
- 所有 JSON 文件保存到 `assets/` 目录

---

## ⚠️ CRITICAL: 成本控制

AI 素材有成本。在生成任何资源之前，必须先展示 `check` 结果并获得用户确认。

```bash
clawreel check --topic "你的主题"
```

**必须步骤：**
1. 展示已有/缺失资源列表
2. 展示成本估算
3. 询问："发现已有资源 X 个，预计成本 ¥Y。开始生成吗？"
4. **等待用户回复**后再执行任何生成

---

## Phase 0: 资源检查 ⚠️ 必做

```bash
clawreel check --topic "Your video topic"
```

---

## Phase 1: 脚本生成

```bash
clawreel script --topic "AI未来趋势"
```

M2.7 输出示例：
```json
{
  "title": "AI觉醒",
  "script": "你有没有想过，未来会是什么样？| 就在昨天，一个AI震惊了科学家。| 看完你就明白了。",
  "sentences": ["你有没有想过，未来会是什么样？", "就在昨天，一个AI震惊了科学家。", "看完你就明白了。"],
  "hook_text": "你有没有想过，未来会是什么样？",
  "hook_prompt": "科技感开场，AI 数据流动，未来主义视觉冲击，电影级画面",
  "style_prompt": "电影级科幻风格，高对比度冷色调光影，蓝紫色霓虹灯光，9:16 竖屏构图",
  "image_prompts": ["科技感开场，AI 数据流动", "一个AI震惊科学家的画面", "看完就会明白的揭秘时刻"],
  "cta": "关注我，带你看清AI真相"
}
```

**注意**：
- `script` 字段用 `|` 分隔多句，**第一句是片头文本**
- `hook_text` 是片头配音文本（与 `sentences[0]` 相同）
- `hook_prompt` 用于生成片头图片（I2V 优先）
- `style_prompt` 是全局风格，与每句的 `image_prompts` 合并后生成图片
- 脚本会自动保存到 `assets/script_<主题>_<日期>.json`

---

## Phase 2: TTS + 语义对齐 + 片头视频

```bash
# 一次性完成：TTS + 词级时间戳 + 语义分句 + 片头标记
clawreel align \
  --text "你有没有想过，未来会是什么样？| 就在昨天，一个AI震惊了科学家。| 看完你就明白了。" \
  --script assets/script_xxx.json \
  --output assets/segments_xxx.json \
  --split-long
```

**输出结构**（`assets/segments_xxx.json`）：
```json
{
  "segments": [
    {"index": 0, "text": "你有没有想过...", "start_sec": 0.0, "duration_sec": 5.8, "is_hook": true},
    {"index": 1, "text": "就在昨天...", "start_sec": 5.8, "duration_sec": 3.4}
  ]
}
```

**关键规则**：
- TTS 配音**从 0 秒开始**，片头 + 正文连续
- `segments[0]` 是片头（`is_hook: true`），`segments[1:]` 是正文
- 片头时长由 TTS 自动决定
- 片头图片 → I2V 视频优先，T2V 降级

**TTS 提供商**：

| Provider | 成本 | 时间戳 |
|----------|------|--------|
| `edge` | 免费 | ✅ 逐词（~50ms）**必选** |
| `minimax` | 付费 | ❌ 不支持对齐 |

---

## Phase 3: 图片生成

```bash
clawreel assets --segments assets/segments_xxx.json
```

**输出**：`assets/images/seg_000.jpg`（片头）、`seg_001.jpg`...（正文）

---

## Phase 4: 视频合成

```bash
clawreel compose \
  --tts assets/tts_output.mp3 \
  --segments assets/segments_xxx.json \
  --music assets/bg_music.mp3
```

**自动处理**：
- ✅ 复用 Phase 3 生成的 `seg_*.jpg` 图片（优先）
- ✅ 降级到 `body_*.jpg`（旧版本兼容）
- 片头视频：`segments[0]` 自动生成 I2V/T2V 动态视频（如未提供 `--hook-prompt`，使用 `segments[0].image_prompt`）
- 正文图片：`segments[1:]` 自动 FFmpeg xfade 转场合成
- 音视频混合：TTS 配音 + 背景音乐自动混音

**时间轴**：
```
0s ──[片头视频]── 5.8s ──[正文图1]── 9.2s ──[正文图2]── 12.5s
│                 │                  │                  │
└──── TTS 配音（连续）─────────────────────────────────┘
└──── 背景音乐（循环）──────────────────────────────────┘
```

**输出**：`output/composed.mp4`（总时长 = 片头 + 正文）

---

## Phase 5: 后期处理

```bash
clawreel post --video output/composed.mp4 --title "AI觉醒"
# Whisper 字幕提取 + FFmpeg 烧录 + AIGC 水印
```

---

## Phase 6: 发布

```bash
clawreel publish --video output/final.mp4 --title "AI觉醒" --platforms douyin xiaohongshu
```

---

## 完整工作流示例

**用户**："帮我做一个 AI 觉醒的短视频"

```
你 → clawreel check --topic "AI觉醒"
用户 → "开始"
你 → clawreel script --topic "AI觉醒" → 展示脚本 → 用户满意？
你 → clawreel align --text "<脚本>" --script assets/script_xxx.json --output assets/segments_xxx.json
你 → clawreel assets --segments assets/segments_xxx.json
你 → 展示图片 → 用户满意？
你 → clawreel compose --tts assets/tts_output.mp3 --segments assets/segments_xxx.json --music assets/bg_music.mp3
你 → clawreel post --video output/composed.mp4 --title "AI觉醒"
你 → clawreel publish --video output/final.mp4 --title "AI觉醒" --platforms douyin xiaohongshu
```

---

## 关键原则

1. **成本控制** — 先 `check`（零成本），再生成
2. **Edge TTS 必选** — 不支持 MiniMax（无逐词时间戳）
3. **精确时长** — `duration_sec` 来自 TTS，不是估算
4. **每句一图** — 图片数量 = 句子数量
5. **片头自动** — `segments[0].is_hook` 自动生成片头视频

---

## 常见问题

**"MiniMax TTS 不支持词级时间戳"**
→ 使用 Edge TTS：`--provider edge`

**"图片数量与分句不一致"**
→ 加 `--split-long` 参数拆分长句

**"句子数超过 30"**
→ 拆分为多个短视频（每条 ≤ 60s）

---

## CLI 命令

### 主流程命令（对应 SOP 7 阶段）

```bash
# Phase 0: 资源检查（零成本）
clawreel check --topic "主题"

# Phase 1: 脚本生成
clawreel script --topic "主题"

# Phase 2: TTS + 语义对齐（TTS 内置于 align）
clawreel align --text "文本" --script PATH --output PATH

# Phase 3: 图片生成
clawreel assets --segments PATH

# Phase 4: 视频合成（含 I2V/T2V 片头）
clawreel compose --tts PATH --segments PATH --music PATH

# Phase 5: 后期处理（字幕 + AIGC）
clawreel post --video PATH --title "标题"

# Phase 6: 多平台发布
clawreel publish --video PATH --platforms ...
```

### 辅助/调试命令

```bash
# 独立 TTS 测试（非流程命令）
clawreel tts --text "文本" --provider edge

# 独立音乐生成（可在任意阶段使用）
clawreel music --prompt "风格" --duration 60

# 字幕提取 + 烧录（独立工具）
clawreel burn-subs --video PATH --model medium
```

**文件约定**：
- 脚本：`assets/script_<主题>_<日期>.json`
- 片段：`assets/segments_<主题>_<日期>.json`
- 图片：`assets/images/seg_*.jpg`
- 视频：`output/composed.mp4` → `output/final.mp4`
