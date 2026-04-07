---
name: clawreel
description: Use this skill when you need to produce video content — especially short videos, social media clips, or TTS/voiceover audio. Covers the full pipeline: writing scripts, generating AI voiceovers, creating video clips/images, composing background music, and publishing to 抖音 (Douyin) or 小红书 (Xiaohongshu). Also use for music MV production, live-streaming scripts, narration generation, or any request spanning script → voice → video → publish. Does NOT trigger for video playback issues, codec questions, editing existing footage manually, or non-production questions.
---

# ClawReel - AI Video Content Pipeline

## ⚡ FinOps-Optimized Workflow

**Cost Control First**: Always check for existing resources before generating. AI-generated assets are expensive — never regenerate without user confirmation.

---

## Prerequisites

**一键安装（一行命令，自动完成克隆 + CLI + Skill 部署）：**

```bash
curl -fsSL https://raw.githubusercontent.com/hrygo/clawreel/main/install.sh | bash
```

**或手动安装：**

```bash
git clone https://github.com/hrygo/clawreel && cd clawreel && ./install.sh
```

**安装后确认：**

| Item | Verify Command |
|------|---------------|
| CLI 可用 | `clawreel --help` |
| Skill 已部署 | `ls ~/.claude/skills/clawreel/` |
| API Key | `cp .env.example .env` → 编辑填入 `MINIMAX_API_KEY` |

---

## When to Use This Skill

**✅ Triggers when:**
- User wants to create short videos for social media (抖音, 小红书, TikTok)
- User mentions script generation, TTS, AI-generated media
- User says "生成视频", "做短视频", "内容创作", "配音", "写脚本"
- User wants multi-platform publishing

**❌ Does NOT trigger for:**
- Video playback or viewing issues
- Manual video editing with tools like Premiere, Final Cut
- Codec or format conversion questions
- Non-production video questions

---

## ⚠️ CRITICAL: Resource Check Before Generation

**Always check existing resources FIRST — AI assets are expensive, never regenerate without confirmation.**

### Resource Decision Matrix

| Scenario | Action | API Calls |
|----------|--------|-----------|
| All resources exist | Use existing | 0 |
| Partial resources exist | Generate missing only | ~50% |
| New topic or user wants fresh | Generate all | 100% |
| Generation failed mid-way | Resume from failure | ~30% |

---

## FinOps Workflow (Aligned with CLI Phases)

### Phase 0: Inventory Check ⚠️ MANDATORY (Zero Cost)

```bash
clawreel check --topic "Your video topic"
clawreel check --topic "Your video topic" --smart   # LLM semantic mode
```

**Quick mode output:**
```json
{
  "topic": "Your video topic",
  "normalized_topic": "your_video_topic",
  "existing": {
    "script": "assets/script_topic_20260407.json",
    "tts": "assets/tts_topic_20260407.mp3",
    "video": null,
    "images": ["assets/img_topic_001.png"],
    "music": null
  },
  "missing": ["video", "music"],
  "recommendation": "generate_missing",
  "cost_estimate": {
    "full": "~¥1.5 (T2V + 3图片 + 音乐 + TTS)",
    "incremental": "~¥0.3-0.5 (仅缺失资源)"
  }
}
```

**Smart mode (`--smart`) additionally outputs:**
```json
{
  "recommendation": "llm_guided",
  "llm_suggestion": {
    "can_reuse": [
      {"type": "image", "path": "...", "reason": "科技风格图片可复用"},
      {"type": "music", "path": "...", "reason": "轻快背景音乐适合"}
    ],
    "must_regenerate": [{"type": "script", "reason": "主题不同需要新内容"}],
    "recommended_plan": "复用图片和音乐，只重新生成脚本和配音",
    "estimated_savings": "约 60%"
  }
}
```

**Required Action:**
1. Display existing resources and missing list
2. Show cost_estimate to user
3. Ask: "发现已有资源 X 个，缺失 Y 个，预计成本 ¥Z。要开始生成吗？"
4. **Wait for decision** before any generation

---

### Phase 1: Script Generation (If Needed)

**Only run if no script exists or user wants refresh:**

```bash
clawreel script --topic "Your video topic"
```

**Output:**
```json
{
  "title": "视频标题",
  "hooks": ["钩子1", "钩子2"],
  "script": "完整配音文本...",
  "hook_prompts": ["视频钩子提示词"],
  "image_prompts": ["图片提示词"]
}
```

**Required Action:**
1. Display title, hooks, and script to user
2. Ask: "脚本已生成，满意吗？"
3. **Wait for approval**

---

### Phase 2: TTS Generation (If Needed)

```bash
clawreel tts --text "配音文本" [--provider minimax|edge]
```

**Providers:**
| Provider | Cost | Quality | API Key |
|----------|------|---------|---------|
| `edge` | Free | Good | No |
| `minimax` | Paid | High | Yes |

**Recommendation:** Use `edge` for drafts, `minimax` for final production.

---

### Phase 3: Asset Generation ⚠️ CHECKPOINT

**Generate only missing assets:**

```bash
clawreel assets \
  --hook-prompt "视频开头画面描述" \
  --image-prompt "正文配图描述" \
  --count 3 \
  --music-prompt "背景音乐风格描述" \
  --topic "Your topic" \
  --skip-existing  # IMPORTANT: Skip if files exist
```

**Full parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `--hook-prompt` | required | 视频开头 6 秒的视觉提示词 |
| `--image-prompt` | required | 正文卡片图片提示词 |
| `--count` | 3 | 图片张数 |
| `--music-prompt` | 轻快短视频 | 背景音乐风格描述 |
| `--topic` | - | 主题名（用于 FinOps 匹配现有资源） |
| `--skip-existing` | false | 发现同主题资源则跳过 |
| `--force` | false | 强制重新生成（消耗 API） |
| `--video-duration` | 6 | 视频秒数（范围 3-30） |
| `--music-duration` | 60 | 音乐秒数（范围 15-300） |

**Output:**
```json
{
  "video": "assets/hook_video_topic_20260407.mp4",
  "images": ["assets/img_topic_001.png", "assets/img_topic_002.png"],
  "music": "assets/bg_music_topic_20260407.mp3",
  "skipped": ["music (already exists)"],
  "generated": ["视频", "2 images"],
  "cost_saved": 1,
  "summary": "生成 3 项，跳过 1 项（节省 API 调用）"
}
```

**FinOps Action:**
1. Show which assets were generated vs skipped
2. Report cost_saved count
3. Ask: "素材已生成，要继续合成吗？"

---

### Phase 4: Composition

```bash
clawreel compose \
  --tts assets/tts_topic_20260407.mp3 \
  --images assets/img_topic_001.png assets/img_topic_002.png \
  --music assets/bg_music_topic_20260407.mp3 \
  --hook assets/hook_video_topic_20260407.mp4
```

**Output:**
```json
{"path": "output/composed_topic_20260407.mp4"}
```

---

### Phase 5: Post-Processing

```bash
clawreel post \
  --video output/composed_topic_20260407.mp4 \
  --title "Your video title"
```

Adds subtitles (Whisper), AIGC watermark if configured in config.yaml.

---

### Phase 6: Publishing ⚠️ CHECKPOINT

```bash
clawreel publish \
  --video output/final_topic_20260407.mp4 \
  --title "Your title" \
  --platforms xiaohongshu douyin
```

**Required Action:**
1. Ask: "视频已准备就绪，要发布到抖音和小红书吗？"
2. **Wait for explicit confirmation**

---

## FinOps Error Recovery

### When Generation Fails Mid-Way

**❌ DO:** Check what's missing, generate only that
**✅ DO:** Use `clawreel check` to identify missing resources

```bash
# After a partial failure, check what's missing
clawreel check --topic "AI未来趋势"

# Output shows exactly what's missing
{
  "existing": {
    "tts": "assets/tts_ai未来趋势_20260407.mp3",
    "images": ["assets/img_ai未来趋势_001.png"],
    "music": null,
    "video": null
  },
  "missing": ["video", "music"],
  "recommendation": "generate_missing"
}

# Only generate the missing ones (use --skip-existing to avoid regen images)
clawreel assets \
  --hook-prompt "..." \
  --image-prompt "..." \
  --music-prompt "..." \
  --topic "AI未来趋势" \
  --skip-existing
```

### Cost-Saving Tips

1. **Reuse Images**: If you only changed the script, don't regenerate images
2. **Use Edge TTS First**: Test with free Edge TTS, upgrade to MiniMax for final
3. **Batch Similar Topics**: Group similar video topics to reuse background music
4. **Partial Regeneration**: If script changes, only regenerate TTS (not images/video)

---

## Cost Estimation Reference

| Resource | Approximate Cost (CNY) |
|----------|------------------------|
| T2V Video (6s) | ¥0.5 - ¥1.0 |
| Image | ¥0.1 - ¥0.2 |
| Music | ¥0.3 - ¥0.5 |
| TTS (MiniMax) | ¥0.1 / 100 chars |
| TTS (Edge) | Free |

**Tip:** A full video (1 T2V + 3 images + 1 music + TTS) costs approximately ¥1-2.

---

## Complete FinOps Workflow Example

**User:** "帮我做一个关于AI未来趋势的短视频"

```bash
# Phase 0: Check (always first)
clawreel check --topic "AI未来趋势"
# Ask user: "预计成本 ¥1.5，要开始吗？" → [User confirms]

# Phase 1-2: Script + TTS
clawreel script --topic "AI未来趋势"
# Ask user: "满意吗？" → [User approves]
clawreel tts --text "大家好..." --provider edge

# Phase 3: Assets (FinOps: only generate missing)
clawreel assets \
  --hook-prompt "未来科技城市" \
  --image-prompt "AI科技概念图" \
  --count 3 --topic "AI未来趋势" --skip-existing
# Ask user: "要继续合成吗？" → [User approves]

# Phase 4-6: Compose → Post → Publish
clawreel compose --tts ... --images ... --music ... --hook ...
clawreel post --video output/composed_ai未来趋势.mp4 --title "..."
# Ask user: "要发布到抖音和小红书吗？" → [User confirms]
clawreel publish --video output/final_ai未来趋势.mp4 \
  --title "..." --platforms xiaohongshu douyin
```

### When User Returns for Same Topic

```bash
clawreel check --topic "AI未来趋势"
# recommendation: "use_existing" → Ask: "发现已有资源，要复用吗？（预计 ¥0）"
# Skip to Phase 4
clawreel compose --tts assets/tts_ai未来趋势_20260407.mp3 \
  --images assets/img_ai未来趋势_001.png assets/img_ai未来趋势_002.png \
  --music assets/bg_music_ai未来趋势_20260407.mp3 \
  --hook assets/hook_video_ai未来趋势_20260407.mp4
```

---

## Error Handling

### Command Not Found

```bash
./install.sh
```

### API Key Missing

```json
{"success": false, "error": "API key not found"}
```

**Solution:**
```bash
# Add to .env file
echo "MINIMAX_API_KEY=your_key" >> .env
```

### Generation Failed

```json
{"success": false, "error": "rate limit exceeded"}
```

**Solution:**
1. Check what's missing: `clawreel check --topic "topic"`
2. Generate only the failed resource
3. Do NOT regenerate everything

### Partial Success

If only some assets were generated:

```bash
# Check what we have
clawreel check --topic "topic"

# Generate only missing (images already exist, only video + music needed)
clawreel assets --hook-prompt "..." --music-prompt "..." --topic "topic" --skip-existing
```

---

## Configuration File (config.yaml)

> ⚠️ 以下为实际生效的模型名称，与 MiniMax 官方 API 对应。

```yaml
minimax:
  api_key: "${MINIMAX_API_KEY}"
  models:
    t2v: "MiniMax-Hailuo-2.3"      # 视频 T2V（768P）
    i2v: "MiniMax-Hailuo-2.3-Fast" # 视频 I2V 加速版
    image: "image-01"
    tts: "speech-2.8-hd"
    music: "music-2.5"

tts:
  active_provider: "edge"  # edge 免费，minimax 付费高品质
  providers:
    minimax:
      voice_id: "female-shaonv"
      speed: 1.0
    edge:
      voice_id: "zh-CN-XiaoxiaoNeural"

video:
  duration_default: 6       # 秒（范围 3-30）

music:
  duration_default: 60      # 秒（范围 15-300）
```

---

## Key Principles

1. **Check Before Generate** - Always run `clawreel check` first (zero cost)
2. **Increment Over Replace** - Generate missing resources, not everything
3. **Show Cost Awareness** - Report what's being generated and what's reused
4. **Respect User Budget** - Ask before expensive operations
5. **Recover Smart** - On failure, only generate what failed
