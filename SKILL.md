---
name: clawreel
description: 触发：用户要制作短视频、配音、音乐MV、直播脚本。流程：脚本生成 → TTS配音（Edge逐词时间戳）→ 图片生成 → 视频合成 → 字幕烧录 → 发布。不触发：视频播放问题、编码问题、手动剪辑现有视频。
---

# ClawReel - AI 短视频语义对齐流水线

> **声音、字幕、画面三同步。** 图片切换时机由 TTS 逐词时间戳（~50ms）精确驱动，每张图内容由对应语句语义生成。

---

## 架构原则

**CLI 工具只做工具该做的事，Agent 负责编排和创意决策。**

| 层级 | 职责 | 做什么 | 不做什么 |
|------|------|--------|----------|
| **script_generator** | 纯文案 | 生成口播脚本 | 不生成任何视觉描述 |
| **Agent（你）** | 创意编排 | 构建分层生图 prompt、审核质量 | 不直接调用 API |
| **image_generator** | 纯执行 | 按 prompt 调用 API 生图 | 不理解上下文 |

---

## ⛔ STOP GATES（强制熔断点）

> [!CAUTION]
> **违反 STOP GATE 将导致不可逆的成本浪费。**

| Gate | 时机 | 必须做的事 |
|------|------|-----------|
| **GATE 1** | `script` 生成后 | 展示 title + sentences 列表，等待用户确认 |
| **GATE 2** | 你构建完生图 prompt 后 | 展示所有 prompt，等待用户确认 |
| **GATE 3** | `assets` 生成后 | 展示所有图片，等待用户确认 |

---

## 完整流程 SOP

### Phase 0: 资源检查 ⚠️ 必做

```bash
clawreel check --topic "你的主题"
```

展示已有/缺失资源 → 展示成本估算 → **等待用户确认后再继续**。

---

### Phase 1: 脚本生成

```bash
clawreel script --topic "AI未来趋势"
```

输出示例：
```json
{
  "title": "AI觉醒",
  "script": "你有没有想过，未来会是什么样？| 就在昨天，一个AI震惊了科学家。| 看完你就明白了。",
  "sentences": ["你有没有想过，未来会是什么样？", "就在昨天，一个AI震惊了科学家。", "看完你就明白了。"],
  "hooks": ["你有没有想过？", "一个AI震惊了科学家"],
  "cta": "关注我，带你看清AI真相"
}
```

**注意：脚本纯文案，不含任何视觉 prompt。**

**⛔ STOP GATE 1**：展示 title 和 sentences 列表 → 等待用户确认。

---

### Phase 1.5: Agent 构建生图 Prompt（你的核心职责）

> [!IMPORTANT]
> **这一步由你（Agent）完成，不是 CLI 命令。** 生图模型没有上下文记忆，每次调用都是独立的。你必须在每一条 prompt 中注入完整的上下文信息。

**分层 Prompt 构建公式**：

```
最终 Prompt = [全局视觉基调] + [视觉风格] + [帧序号] + [本帧画面描述]
```

#### Step 1: 定义全局视觉基调（Global Visual Context）

根据视频主题和脚本内容，构建一段 80-120 字的**角色与场景锚定描述**：
- 核心人物的固定特征（发型、服装颜色款式、年龄、体型）
- 固定场景（办公室/机房/户外的具体陈设、光源位置）
- 核心道具（电脑型号、桌面物品）

示例：
> 一位30岁的亚裔男性程序员，戴黑框眼镜，穿深蓝色工装夹克，坐在一个赛博朋克风格的工位前。桌上有一台27寸曲面显示器、一个机械键盘和一杯黑咖啡。房间灯光以冷蓝色为主调，显示器光映在他脸上。

#### Step 2: 定义视觉风格（Style Prompt）

一段 40-60 字的**画质与构图描述**（所有帧共享）：

示例：
> 电影级4K画质，9:16竖屏构图，赛博朋克冷色调光影，浅景深虚化背景，侧逆光勾勒人物轮廓，高对比度，画面干净利落。

#### Step 3: 逐帧构建画面描述

对每一个 segment，构建 **50-80 字**的当前帧**动作/表情/变化描述**（不重复全局信息）：

示例（假设共 5 帧）：
```
Frame 1/5: 他双手放在键盘上，眉头紧锁，盯着屏幕上密密麻麻的报错日志，表情从期待变为失望。
Frame 2/5: 他无奈地靠回椅背，双手抱胸，显示器上弹出一个醒目的红色限流报错弹窗。
Frame 3/5: 他用右手扶额，左手无力地搭在键盘上，屏幕上显示着高额的订阅价格页面。
Frame 4/5: 他转头看向镜头，表情严肃，嘴角微微下撇，背景显示器上是一段完整的代码。
Frame 5/5: 他背着黑色双肩包，从暗色调的办公室走向门口，背影被走廊的暖光拉出长长的影子。
```

#### Step 4: 组装最终 Prompt

将上面三层拼装为一条完整的 prompt（每帧一条）：

```
[全局视觉基调], [视觉风格], [Sequence: Frame X of Y], [本帧画面描述]
```

#### Step 5: 写入 segments.json

将组装好的 prompt 写入 `segments.json` 的每个 segment 的 `image_prompt` 字段。

你可以直接编辑 segments.json 文件，或手动构建脚本 JSON 后传给 `align --script`。

**⛔ STOP GATE 2**：展示所有构建好的 prompt → 等待用户确认。

---

### Phase 2: TTS + 语义对齐

```bash
clawreel align \
  --text "脚本文本（用 | 分隔）" \
  --output assets/segments_xxx.json \
  --split-long
```

如果你已经构建好了脚本 JSON（含 image_prompts），可以传入：
```bash
clawreel align \
  --text "脚本文本" \
  --script assets/script_xxx.json \
  --output assets/segments_xxx.json \
  --split-long
```

输出 `segments.json` 结构：
```json
{
  "text": "完整文本",
  "global_visual_context": "全局视觉基调（如有）",
  "style_prompt": "视觉风格（如有）",
  "audio_path": "assets/tts_output.mp3",
  "segments": [
    {
      "index": 0,
      "text": "第一句口播",
      "start_sec": 0.0,
      "end_sec": 3.2,
      "duration_sec": 3.2,
      "image_prompt": "完整的分层 prompt",
      "is_hook": true
    }
  ]
}
```

**TTS 提供商**：

| Provider | 成本 | 时间戳 |
|----------|------|--------|
| `edge` | 免费 | ✅ 逐词（~50ms）**必选** |
| `minimax` | 付费 | ❌ 不支持对齐 |

---

### Phase 3: 图片生成

```bash
clawreel assets --segments assets/segments_xxx.json [--video]
```

- `--video`：同时生成 6 秒片头视频（I2V 优先，T2V 降级）
- 图片生成器会自动读取 segments.json 中的 `global_visual_context` 和 `style_prompt`，与每帧的 `image_prompt` 拼装后调用 API。

**输出**：`assets/images/seg_000_0.jpg`（片头）、`seg_001_0.jpg`...（正文）

**⛔ STOP GATE 3**：展示所有生成的图片 → 等待用户确认。

---

### Phase 4: 视频合成

```bash
clawreel compose \
  --tts assets/tts_output.mp3 \
  --segments assets/segments_xxx.json \
  --music assets/bg_music.mp3 \
  --hook-video assets/video_head.mp4
```

**自动处理**：
- ✅ 按 segments 精确时长拼接图片（FFmpeg xfade 转场）
- ✅ TTS 配音 + 背景音乐自动混音
- ✅ 末尾自适应补帧（防止语音未播完视频结束）

**时间轴**：
```
0s ──[片头视频]── 5.8s ──[正文图1]── 9.2s ──[正文图2]── 12.5s
│                 │                  │                  │
└──── TTS 配音（连续）─────────────────────────────────┘
└──── 背景音乐（循环）──────────────────────────────────┘
```

**输出**：`output/composed.mp4`

---

### Phase 5: 后期处理

```bash
clawreel post --video output/composed.mp4 --title "AI觉醒" --font-size 16
```

---

### Phase 6: 发布

```bash
clawreel publish --video output/final.mp4 --title "AI觉醒" --platforms douyin xiaohongshu
```

---

## 完整工作流示例

**用户**："帮我做一个智谱 Coding Plan 真实体验的短视频"

```
你 → clawreel check --topic "智谱 Coding Plan"
用户 → "开始"

你 → clawreel script --topic "智谱 Coding Plan 真实体验..."
你 → 展示 title + sentences 列表
⛔ STOP GATE 1
用户 → "第一句改成xxx，其余可以"

你 → 根据脚本内容，构建：
     1. 全局视觉基调（角色+场景锚定）
     2. 视觉风格
     3. 逐帧画面描述
     4. 拼装完整 prompt 列表
你 → 展示所有 prompt
⛔ STOP GATE 2
用户 → "可以"

你 → 将 prompt 写入脚本 JSON 的 image_prompts 字段
你 → clawreel align --text "脚本" --script assets/script_xxx.json --output assets/segments_xxx.json --split-long
你 → clawreel assets --segments assets/segments_xxx.json --video
你 → 展示生成的图片和 6s 片头视频
⛔ STOP GATE 3
用户 → "可以，合成吧"

你 → clawreel compose --tts assets/tts_output.mp3 --segments assets/segments_xxx.json --music assets/bg_music.mp3 --hook-video assets/video_head.mp4
你 → clawreel post --video output/composed.mp4 --title "xxx"
你 → clawreel publish --video output/final.mp4 --title "xxx" --platforms douyin xiaohongshu
```

---

## CLI 命令速查

### 主流程命令

```bash
# Phase 0: 资源检查（零成本）
clawreel check --topic "主题"

# Phase 1: 脚本生成（纯文案）
clawreel script --topic "主题"

# Phase 2: TTS + 语义对齐
clawreel align --text "文本" --script PATH --output PATH [--split-long]

# Phase 3: 素材准备（图片 + 可选视频）
clawreel assets --segments PATH [--video]

# Phase 3.5: 独立片头视频生成
clawreel video --segments PATH

# Phase 4: 视频合成
clawreel compose --tts PATH --segments PATH --music PATH [--hook-video PATH]

# Phase 5: 后期处理（字幕 + AIGC）
clawreel post --video PATH --title "标题" --font-size 16

# Phase 6: 多平台发布
clawreel publish --video PATH --platforms ...
```

### 辅助命令

```bash
clawreel music --prompt "风格" --duration 60
clawreel burn-subs --video PATH --model medium
```

---

## 关键原则

1. **成本控制** — 先 `check`（零成本），再生成
2. **Edge TTS 必选** — MiniMax 无逐词时间戳
3. **精确时长** — `duration_sec` 来自 TTS，不是估算
4. **每句一图** — 图片数量 = 句子数量
5. **Agent 构建 Prompt** — 生图模型无上下文，你必须在每条 prompt 中注入完整信息
6. **三道 STOP GATE** — 脚本确认 → prompt 确认 → 图片确认

---

## 文件约定

- 脚本：`assets/script_<主题>_<日期>.json`
- 片段：`assets/segments_<主题>_<日期>.json`
- 图片：`assets/images/seg_*.jpg`
- 视频：`output/composed.mp4` → `output/final.mp4`
