---
name: clawreel
description: Use this skill when you need to produce video content — especially short videos, social media clips, or TTS/voiceover audio. Covers the full pipeline: writing scripts, generating AI voiceovers, creating video clips/images, composing background music, and publishing to 抖音 (Douyin) or 小红书 (Xiaohongshu). Also use for music MV production, live-streaming scripts, narration generation, or any request spanning script → voice → video → publish. Does NOT trigger for video playback issues, codec questions, editing existing footage manually, or non-production questions.
---

# ClawReel - AI Video Content Pipeline

Orchestrate end-to-end AI video content production with Human-In-The-Loop (HITL) checkpoints. The pipeline is divided into 6 stages with mandatory user approval at critical checkpoints.

## Prerequisites

**This skill requires the `clawreel` CLI tool to be installed and configured.**

### Installation
If the `clawreel` command is not found, you must install it by running the following in the project root:
```bash
./install.sh
```
*Note: This script handles Python package installation and environment setup for Claude Code, OpenClaw, and OpenCode.*

### Configuration
- **API Keys:** Requires `MINIMAX_API_KEY` in your environment or a `.env` file in your workspace.
- **Python:** Requires Python 3.10+.

## When to Use This Skill

**✅ SHOULD trigger when:**
- User wants to create short videos for social media (抖音, 小红书, TikTok, etc.)
- User mentions video content production, script generation, or AI-generated media
- User asks about TTS, video composition, or multi-platform publishing
- User says "生成视频", "做短视频", "内容创作", "视频剪辑"
- User mentions clawreel CLI or video pipeline

**❌ Should NOT trigger when:**
- Only asking about video playback or viewing
- Discussing video codecs/formats without production intent
- Editing existing videos manually (use video editing tools instead)

---

## Workflow Overview

The production process has **6 stages** with **2 mandatory checkpoints**:

### Stage 0: Script Generation ⚠️ CHECKPOINT
**Purpose:** Generate viral video script with title, hooks, and narration text.

**CLI Command:**
```bash
clawreel script --topic "[Topic]"
```

**Output Format:**
```json
{
  "title": "未来10年AI如何改变打工人的命运",
  "hooks": [
    "你有没有想过，10年后你的工作可能就不存在了？",
    "AI不是来抢饭碗的，是来换个吃饭方式的！"
  ],
  "script": "大家好，今天聊聊AI对就业的影响...",
  "hook_prompts": ["赛博朋克风格的机器人工厂"],
  "image_prompts": ["未来城市天际线"]
}
```

**✋ MANDATORY ACTION:**
1. Display the title, hooks, and script clearly to user
2. Ask: "这是生成的脚本，满意吗？需要调整吗？"
3. **WAIT** for user approval before proceeding
4. If feedback provided, re-run with adjusted topic

---

### Stage 1: TTS Generation
**Purpose:** Convert script narration to audio.

**CLI Command:**
```bash
clawreel tts --text "[Script Text]"
```

**Output Format:**
```json
{
  "path": "assets/tts_20260407_123456.mp3"
}
```

**Action:**
- Inform user: "配音已生成: assets/tts_xxx.mp3"
- No checkpoint needed, proceed to next stage

---

### Stage 2: Asset Generation ⚠️ CHECKPOINT
**Purpose:** Generate video hook, images, and background music in parallel.

**CLI Command:**
```bash
clawreel assets \
  --hook-prompt "[First Hook Prompt]" \
  --image-prompt "[Image Prompt]" \
  --music-prompt "upbeat background music" \
  --count 3
```

**Output Format:**
```json
{
  "video": "assets/hook_video_20260407.mp4",
  "images": [
    "assets/image_001.png",
    "assets/image_002.png",
    "assets/image_003.png"
  ],
  "music": "assets/bg_music_20260407.mp3"
}
```

**✋ MANDATORY ACTION:**
1. Display all generated file paths
2. If possible, describe what was generated
3. Ask: "素材生成完毕，看起来怎么样？需要重新生成吗？"
4. **WAIT** for user approval
5. If feedback, re-run with adjusted prompts

---

### Stage 3: Composition
**Purpose:** Combine TTS, images, music, and hook video into final video.

**CLI Command:**
```bash
clawreel compose \
  --tts assets/tts_20260407_123456.mp3 \
  --images assets/image_001.png assets/image_002.png assets/image_003.png \
  --music assets/bg_music_20260407.mp3 \
  --hook assets/hook_video_20260407.mp4
```

**Output Format:**
```json
{
  "path": "output/composed_20260407_123456.mp4"
}
```

**Action:**
- Inform user: "视频已合成: output/composed_xxx.mp4"
- No checkpoint needed

---

### Stage 4: Post-Processing
**Purpose:** Add final touches, subtitles, and optimize for platforms.

**CLI Command:**
```bash
clawreel post \
  --video output/composed_20260407_123456.mp4 \
  --title "[Title]"
```

**Output Format:**
```json
{
  "path": "output/final_20260407_123456.mp4"
}
```

**Action:**
- Display final output path
- No checkpoint needed

---

### Stage 5: Publishing
**Purpose:** Publish to social media platforms.

**CLI Command:**
```bash
clawreel publish \
  --video output/final_20260407_123456.mp4 \
  --title "[Title]" \
  --platforms xiaohongshu douyin
```

**Output Format:**
```json
{
  "results": {
    "xiaohongshu": {"status": "success", "post_id": "abc123"},
    "douyin": {"status": "success", "post_id": "def456"}
  }
}
```

**✋ MANDATORY ACTION:**
1. **ASK EXPLICITLY**: "视频已准备就绪，要发布到抖音和小红书吗？"
2. **WAIT** for explicit user confirmation
3. Only execute publish command after approval

---

## Complete Workflow Example

Here's a full end-to-end example:

**User:** "帮我做一个关于AI未来趋势的短视频"

**Agent Actions:**

```bash
# Stage 0: Script
clawreel script --topic "AI未来10年趋势"

# Output received, show to user:
"""
标题：AI未来10年将如何改变我们的生活
钩子1：你准备好迎接AI时代了吗？
钩子2：这些变化比你想象的更快！
正文：大家好，今天聊聊AI在未来10年将如何...
"""

# Ask user: "脚本已生成，满意吗？"
# [User approves]

# Stage 1: TTS
clawreel tts --text "大家好，今天聊聊AI在未来10年将如何..."

# Stage 2: Assets
clawreel assets \
  --hook-prompt "未来科技城市，AI机器人" \
  --image-prompt "AI科技概念图" \
  --music-prompt "科技感背景音乐" \
  --count 3

# Show user: "视频、图片、音乐已生成"
# [User approves]

# Stage 3: Compose
clawreel compose \
  --tts assets/tts_xxx.mp3 \
  --images assets/image_001.png assets/image_002.png assets/image_003.png \
  --music assets/bg_music_xxx.mp3 \
  --hook assets/hook_video_xxx.mp4

# Stage 4: Post
clawreel post \
  --video output/composed_xxx.mp4 \
  --title "AI未来10年趋势"

# Stage 5: Ask before publishing
"视频已完成！要发布到抖音和小红书吗？"
# [User confirms]
clawreel publish \
  --video output/final_xxx.mp4 \
  --title "AI未来10年趋势" \
  --platforms xiaohongshu douyin
```

---

## Key Principles

1. **Always Pause at Checkpoints:** Stages 0 and 2 require explicit user approval
2. **Show Outputs Clearly:** Display generated content (scripts, file paths) to user
3. **Respect Feedback:** If user wants changes, adjust prompts and re-run
4. **Transparent Communication:** Tell user which stage you're entering
5. **Error Handling:** If any command fails, show error message and ask user how to proceed

## CLI Tool Location

- **Global Command:** `clawreel` (after `pip install -e .`)
- **Config:** Requires `config.yaml` and `.env` with `MINIMAX_API_KEY`
- **Output Directories:** `assets/` (intermediate) and `output/` (final)

---

## Error Handling

If a command fails, the CLI will output:

```json
{
  "success": false,
  "error": "API request failed: timeout"
}
```

**Action:**
1. Display the error message to user
2. **If command `clawreel` is not found:** Inform the user that the tool is not installed and ask for permission to run `./install.sh` in the project root.
3. Suggest possible fixes (check API key, network, etc.)
4. Ask if user wants to retry or abort
