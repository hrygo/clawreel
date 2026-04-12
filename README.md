<div align="center">

![ClawReel Hero](hero.webp)

# ClawReel: AI 短视频生产工厂

**从创意到发布，只需一次对话。**

专为 AI 智能体打造的**语义对齐式**短视频全链路流水线

[![Install](https://img.shields.io/badge/install-pip%20install%20-e%20blue)](https://github.com/hrygo/clawreel)
[![Python](https://img.shields.io/badge/python-3.10+-green)](https://www.python.org/)

</div>

---

## 💡 为什么选择 ClawReel

### 对于创作者

- ⚡ **极致高效**：分钟级生成脚本、配音、配图、背景音乐、合成、字幕的完整短视频
- 🎯 **完全掌控**：每个阶段设有审核点，拒绝黑盒，内容始终符合预期
- 💰 **成本透明**：`check` 命令智能查重复用，节省 50%-80% 模型调用成本

### 对于 AI 智能体

- 🔌 **标准化接口**：全量 CLI 命令，输出统一 JSON，Agent 零障碍集成
- 🛡️ **安全中断协议**：主动暴露 Checkpoints，关键步骤请求人类授权
- 🌐 **跨环境部署**：一键安装，自动适配 Claude Code、OpenCode、OpenClaw 等

---

## 🔄 8 阶段工作流

```
✅ Check + Music  →  📝 Script  →  🎨 Prompt  →  🔊 TTS + Align
                                                      ↓
🚀 Publish  ←  ✨ Post  ←  🎬 Compose  ←  🖼️ Assets
```

| Phase | 做什么 | 核心能力 |
|:-----:|--------|---------|
| **1** | 资源检查 + 背景音乐 | 零成本扫描已有资源，按主题生成匹配 BGM |
| **2** | 脚本生成 + 格式化 | Agent 创作 → `format` 输出标准 JSON |
| **3** | 构建生图 Prompt | **决定视频质量的关键** — 每句对应独立画面 |
| **4** | TTS 配音 + 时间戳对齐 | 声音、字幕、画面三同步 |
| **5** | 批量生成图片 | 每句一张语义关联图片，可选 6s 片头视频 |
| **6** | FFmpeg 合成 | 抗坍缩转场补偿，精确时长拼接 |
| **7** | 字幕 + 标题 + 水印 | Whisper 烧录字幕，标题叠加 |
| **8** | 多平台发布 | 抖音、小红书、B站一键发布 |

---

## 🌟 核心特性

- **语义对齐流水线** — 图片切换时机由 TTS 时间戳精确驱动，每张图内容由对应语句语义生成
- **抗坍缩转场补偿** — 数学级 xfade 拼接补偿，防止视频后段错位与字幕消散
- **智能分句防火墙** — 上下文敏感断句，版本号、小数点不误拆（`GLM5.1`、`GPT-4.5` 完美兼容）
- **双 TTS 引擎** — Edge TTS（免费，逐词时间戳）+ MiniMax TTS（自然流畅，多音色）
- **策略模式发布** — 分发平台注册字典架构，轻松扩展新渠道

---

## 🚀 快速开始

### 一键安装

```bash
# 推荐
curl -fsSL https://raw.githubusercontent.com/hrygo/clawreel/main/install.sh | bash

# 或手动安装
pip install -e .
```

### 5 分钟出片

```bash
# 1️⃣ 检查资源 + 生成背景音乐
clawreel check --topic "AI未来趋势"
clawreel music --topic "AI未来趋势" --duration 60

# 2️⃣ 格式化脚本（内容由 Agent/SKILL.md 生成）
clawreel format --content "# AI觉醒时刻\n你敢信吗 | AI已经能自己写代码了 | 看完这个你就懂了" --title "AI觉醒时刻"

# 3️⃣ Agent 构建生图 Prompt（写入 script JSON 的 image_prompts 字段）

# 4️⃣ TTS 配音 + 对齐
clawreel align \
  --text "你敢信吗，AI已经能自己写代码了，看完这个你就懂了。" \
  --script assets/script_AI觉醒时刻_20260412.json \
  --provider minimax --voice presenter_male \
  --output assets/segments_AI觉醒时刻_20260412.json

# 5️⃣ 生成图片（每句一张）
clawreel assets --segments assets/segments_AI觉醒时刻_20260412.json

# 6️⃣ 合成视频
clawreel compose \
  --tts assets/tts_output.mp3 \
  --segments assets/segments_AI觉醒时刻_20260412.json \
  --music assets/bg_music_AI未来趋势.mp3 \
  --transition fade

# 7️⃣ 字幕 + 标题
clawreel burn-subs --video output/composed.mp4 --model medium --language zh --margin-v 550
clawreel post --video output/composed.subtitled.mp4 --title "AI觉醒时刻" --no-subtitles

# 8️⃣ 发布
clawreel publish --video output/final_composed.mp4 --title "AI觉醒时刻" --platforms douyin xiaohongshu
```

---

## 🤖 AI 模型支持

| 组件 | 模型 | 说明 |
|:----:|:----:|------|
| 脚本 | Agent (SKILL.md) | 内容创作，CLI 格式化 `\|` 分隔句子 |
| 配音 | Edge TTS / MiniMax TTS | Edge 免费 + 逐词时间戳；MiniMax 自然多音色 |
| 图片 | MiniMax image-01 | 9:16 竖屏，每句一张，语义关联 |
| 音乐 | MiniMax music-2.5 | 按主题生成匹配背景音乐 |
| 字幕 | Whisper medium/large | `burn-subs` 自动烧录 |

---

## 📖 Agent 集成指南

AI 助理请阅读 [**SKILL.md**](./SKILL.md) 获取完整 8 阶段流水线指引。

> **财务责任制**：生成图片和音乐有成本。调用 `assets` 前，必须先 `check` 展示现有资源并获用户确认。

---

## 🛠️ 技术栈

**Python 3.10+** · **FFmpeg (libass)** · **MiniMax (Vision/TTS/Music)** · **Edge TTS** · **OpenAI Whisper**

---

<div align="center">

© 2026 ClawReel Team. Built for the Agentic Era.

</div>
