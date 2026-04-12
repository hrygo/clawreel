# ClawReel

> AI 短视频语义对齐流水线 — 从创意到发布，只需一次对话。

## 为什么选择 ClawReel

- **全链路覆盖**：脚本、配音、配图、背景音乐、合成、字幕、发布，8 个阶段一站完成
- **语义对齐**：图片切换时机由 TTS 时间戳精确驱动，每张图内容由对应语句语义生成
- **HITL 审核点**：每个阶段设有 Stop Gate，人类审核后才继续，拒绝黑盒
- **成本透明**：`check` 命令智能查重复用，节省 50%-80% 模型调用成本

## 工作流

```
Phase 1  Check + Music    →  资源清单 + 背景音乐
Phase 2  Script           →  script.json
Phase 3  Visual Prompt    →  image_prompts（Agent 构建）
Phase 4  TTS + Align      →  tts_output.mp3 + segments.json
Phase 5  Assets           →  seg_*.jpg
Phase 6  Compose          →  composed.mp4
Phase 7  Post             →  final_composed.mp4
Phase 8  Publish          →  抖音 / 小红书 / B站
```

## 快速开始

```bash
# 安装
pip install -e .

# 或一键安装
curl -fsSL https://raw.githubusercontent.com/hrygo/clawreel/main/install.sh | bash
```

```bash
# 1. 资源检查 + 背景音乐
clawreel check --topic "AI未来趋势"
clawreel music --topic "AI未来趋势" --duration 60

# 2. 格式化脚本（内容由 Agent/SKILL.md 生成）
clawreel format --content "# 标题\n句1 | 句2 | 句3" --title "标题"

# 3. Agent 构建生图 Prompt（写入 script JSON，无 CLI 命令）

# 4. TTS + 对齐
clawreel align \
  --text "句1 句2 句3" \
  --script assets/script_topic_date.json \
  --provider minimax \
  --output assets/segments_topic_date.json

# 5. 生成图片
clawreel assets --segments assets/segments_topic_date.json

# 6. 合成视频
clawreel compose \
  --tts assets/tts_output.mp3 \
  --segments assets/segments_topic_date.json \
  --music assets/bg_music_topic.mp3 \
  --transition fade

# 7. 后期处理（字幕 + 标题）
clawreel burn-subs --video output/composed.mp4 --model medium --language zh
clawreel post --video output/composed.subtitled.mp4 --title "标题" --no-subtitles

# 8. 发布
clawreel publish --video output/final_composed.mp4 --title "标题" --platforms douyin
```

## AI 模型

| 组件 | 模型 | 说明 |
|------|------|------|
| 脚本 | Agent (SKILL.md) | 内容创作，CLI 格式化 `\|` 分隔句子 |
| 配音 | Edge TTS / MiniMax TTS | Edge 免费带逐词时间戳；MiniMax 自然流畅 |
| 图片 | MiniMax image-01 | 9:16 竖屏，每句一张 |
| 音乐 | MiniMax music-2.5 | 按主题生成背景音乐 |
| 字幕 | Whisper medium/large | `burn-subs` 烧录 |

## Agent 集成

AI 助理请阅读 [SKILL.md](./SKILL.md) 获取完整流水线指引。

> **财务责任制**：生成图片和音乐有成本。调用 `assets` 前，必须先 `check` 展示现有资源并获用户确认。

## 技术栈

Python 3.10+ | FFmpeg (libass) | MiniMax (Vision/TTS/Music) | Edge TTS | OpenAI Whisper

---

© 2026 ClawReel Team. Built for the Agentic Era.
