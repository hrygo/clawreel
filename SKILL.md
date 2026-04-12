---
name: clawreel
description: 触发：制作短视频、知识科普视频、话题讲解短片、产品展示视频、宠物/美食/生活记录短片、任何需要配音+配图+合成为竖屏视频的场景。不触发：视频播放/编码问题、手动剪辑现有视频、纯图文内容。
---

# ClawReel - AI 短视频语义对齐流水线

> 声音、字幕、画面三同步。图片切换时机由 TTS 逐词时间戳精确驱动，每张图内容由对应语句语义生成。

## 流程总览

| Phase | 做什么 | CLI 命令 | 产出 |
|-------|--------|----------|------|
| **1** | 资源检查 + 背景音乐 | `check` / `music` | 资源清单 + `bg_music_*.mp3` |
| **2** | 生成口播 → 格式化 → 保存 | `format` | `script_*.json` |
| **3** | 构建生图 Prompt | — | 含 `image_prompts` 的 script |
| **4** | TTS 配音 + 时间戳对齐 | `align` | 音频 + `segments_*.json` |
| **5** | 批量生成图片 + 可选片头视频 | `assets` / `video` | `seg_*.jpg` + 可选 `video_head.mp4` |
| **6** | FFmpeg 合成视频 | `compose` | `composed.mp4` |
| **7** | Whisper 字幕 + 标题 + 水印 | `burn-subs` / `post` | `final_composed.mp4` |
| **8** | 生成发布文案 + 多平台发布 | `publish` | 文案 + 抖音/小红书 |

```
Phase 2  format            →  script.json（title, sentences, hooks, cta）
Phase 3  Agent 编辑         →  script.json（+ image_prompts, style_prompt）
Phase 4  align              →  tts_output.mp3 + segments.json
Phase 5  assets             →  seg_*.jpg
Phase 6  compose            →  composed.mp4
Phase 7  burn-subs + post   →  final_composed.mp4
Phase 8  Agent 文案 + publish → 平台发布
```

## 核心规则

**分工**：Agent 做创意决策和内容生成，CLI 做格式化/合成/发布，生图模型无记忆需每帧独立完整 Prompt。

**约定**：CLI 路径用绝对路径 | 每个项目独立目录 `assets/<topic>_<YYYYMMDD>/` | topic 用简短英文（如 `claude-mem`、`parrot`） | 默认根目录 `assets/`（中间）/ `output/`（最终）

**断点续传**：用户中断时保留当前阶段产物，下次从断点 Phase 继续。检查 `assets/<topic>_<date>/` 判断进度：
- 有 `script.json` → 从 Phase 3 继续
- 有 `segments.json` → 从 Phase 5 继续
- 有 `images/seg_*.jpg` → 从 Phase 6 继续
- 有 `output/<topic>_<date>/composed.mp4` → 从 Phase 7 继续

### 严禁反模式

| 反模式 | 后果 | 正确做法 |
|--------|------|----------|
| sentences 含 `# title` | TTS 读出 "hashtag title" | title 单独存储 |
| sentences[0:2] 与 hooks 重复 | TTS 读两遍 | format 自动分离 |
| `--text` 含 hook 文本 | TTS 重复 | `--text` = body only |
| 用 segments JSON 生成字幕 | 声音-字幕不同步 | Whisper `burn-subs` |
| 图片 Prompt 含中文文字 | 生图乱码 | 英文 |
| align 后不校验 segments | index 错乱 + prompt 丢失 | Phase 4 后必校验 |
| 字幕默认底部位置 | 抖音 UI 遮挡 | `--margin-v 550` |

### 已知限制

| 限制 | 规避 |
|------|------|
| MiniMax 无词级时间戳（字符加权估算） | Edge TTS 或接受估算 |
| `clawreel assets` 无增量模式 | 缺图少时手动补或全量重跑 |

## STOP GATES（成本防护）

每个 Gate 展示关键信息表格，**等用户确认后**才继续。

| Gate | 时机 | 展示内容 |
|------|------|---------|
| **G1** | Phase 2 后 | title + 全部 sentences（编号 + 文本） |
| **G2** | Phase 3 后 | 全局基调 + Prompt 概要（编号 + 画面描述） |
| **G3** | Phase 5 后 | 6-8 张关键帧图片 |

---

## Phase 1: 资源检查 + 背景音乐

```bash
clawreel check --topic "主题" [--llm-suggest]
clawreel music --topic "主题" --duration 60
```

- `--llm-suggest`：LLM 复用建议（需 MINIMAX_API_KEY）
- 自定义风格：`clawreel music --prompt "风格描述" --duration 90 --output /abs/path/$PROJECT/bg_music.mp3`
- 风格推荐：宠物→轻快活泼、科技→电子感、美食→温馨治愈、知识科普→清新自然

## Phase 2: 脚本生成 + 格式化

### Step 1: 生成口播内容

格式：`# 标题` + 用 `|` 分隔句子。开头钩子 → 分段展开 → 总结 → CTA（5-40 句），每句一个核心信息点。`# 标题` format 自动剥离，不会被 TTS 读出。

### Step 2: 格式化 + 保存

```bash
clawreel format --content "# 标题\n句1 | 句2 | ..." --title "标题"
```

CLI 输出 JSON 到 stdout，**用 Write 工具保存为** `assets/<topic>_<YYYYMMDD>/script.json`。

⛔ **GATE 1** — 展示 title + sentences 表格，确认后继续。

涉及具体数字（星数、百分比等）时，优先从 GitHub API / 官方来源获取实时数据。

## Phase 3: 构建生图 Prompt

**决定视频质量的关键步骤。** 必须在 Phase 4 之前完成（align 从 script JSON 读取 `image_prompts`）。

**Prompt 公式**（每帧独立完整）：`[style_prompt], [global_visual_context], [本帧画面描述]`

### Step 1: 全局视觉基调

在 script JSON 根级添加：
- `global_visual_context`（80-120字）：场景、光源、氛围
- `style_prompt`（40-60字）：画质与构图

| 类型 | style_prompt |
|------|-------------|
| 宠物/动物 | `Cinematic 4K wildlife photography, 9:16 vertical portrait, shallow depth of field with bokeh, warm golden side-lighting, high contrast, shot on 85mm lens.` |
| 科技/数码 | `Cinematic 4K tech photography, 9:16 vertical portrait, shallow depth of field, cool blue-white studio lighting, clean modern aesthetic, high contrast.` |
| 生活/美食 | `Cinematic 4K lifestyle photography, 9:16 vertical portrait, shallow depth of field, warm natural window light, cozy atmosphere, food magazine quality.` |

### Step 2: 逐帧 Prompt（英文，50-80字/帧）

**实体一致性**：品牌/角色在所有帧保持相同视觉符号（如 OpenClaw → "red lobster icon"）。首帧定义，后续帧复用。

**关键**：`image_prompts` 数组长度 **必须等于** `sentences` 数组长度。

⛔ **GATE 2** — 展示全局基调 + Prompt 概要表格，确认后继续。

## Phase 4: TTS + 对齐

```bash
PROJECT=assets/<topic>_<YYYYMMDD>  # 例: assets/claude-mem_20260412
clawreel align \
  --text "正文（空格分隔，保留标点，不含 hooks/标题）" \
  --script /abs/path/$PROJECT/script.json \
  --provider minimax \
  [--voice <音色ID>] \
  --output /abs/path/$PROJECT/segments.json
```

- `--text`：**保留标点符号**（逗号、句号、感叹号），TTS 依赖标点控制语调和停顿
- `--provider`：`minimax`（自然）/ `edge`（免费但机械）
- `--split-long`：拆分 >5s 段落（**会重置 index，慎用**）

**hooks 拼接陷阱**：`--text` 不含 hooks 时，CLI 会插入 hooks 到 sentences 前面但 `image_prompts` 不同步偏移。**最佳实践**：`--text` 包含 hooks 文本，让 CLI 跳过拼接逻辑。

### MiniMax 音色

| voice_id | 风格 | 适用场景 |
|----------|------|---------|
| `presenter_male` | 男主持人 | 科技/知识科普 |
| `presenter_women` | 女主持人 | 温和专业感 |
| `male-qn-qingse` | 青涩男声 | 年轻化内容 |
| `male-qn-jingying` | 精英男声 | 商务/专业 |
| `male-qn-badao` | 霸道男声 | 强调型 |
| `male-qn-daxuesheng` | 大学生男声 | 校园/轻松 |
| `female-shaonv` | 少女音（默认） | 通用 |

试听：`clawreel tts --text "测试文本" --provider minimax --voice presenter_male`

### 数据完整性校验（Phase 4 后必做）

```python
PROJECT = "assets/<topic>_<YYYYMMDD>"
python3 -c "
import json
segs = json.load(open('${PROJECT}/segments.json'))
script = json.load(open('${PROJECT}/script.json'))
errors = []
for i, seg in enumerate(segs['segments']):
    if seg['index'] != i:
        errors.append(f'seg[{i}] index={seg[\"index\"]} ≠ {i}')
    if seg['image_prompt'].startswith('Professional Short Video Scene:'):
        errors.append(f'seg[{i}] prompt 是 CLI 默认模板')
if len(segs['segments']) != len(script.get('sentences', [])):
    print(f'⚠️ 段数不等，TTS 合并短句，正常')
if errors:
    print('❌ 问题：')
    for e in errors: print(f'  - {e}')
else:
    print('✅ 校验通过')
"
```

修复：index 不连续 → 遍历重写 `seg['index'] = i`；prompt 被覆盖 → 从 script JSON 回填。

## Phase 5: 素材生成

```bash
PROJECT=assets/<topic>_<YYYYMMDD>
clawreel assets --segments /abs/path/$PROJECT/segments.json [--video]
```

图片保存到 `$PROJECT/images/seg_*.jpg`。`--video` 同时生成 6 秒片头视频。

⛔ **GATE 3** — 展示 6-8 张关键帧图片，确认后继续。

缺图检查：遍历 segments 中每个 index，检查 `seg_{index:03d}_0.jpg` 是否存在。缺图少时手动补或全量重跑。

## Phase 6: 视频合成

```bash
PROJECT=assets/<topic>_<YYYYMMDD>
clawreel compose \
  --tts /abs/path/$PROJECT/tts.mp3 \
  --segments /abs/path/$PROJECT/segments.json \
  --music /abs/path/$PROJECT/bg_music.mp3 \
  --transition fade \
  [--hook-video /abs/path/$PROJECT/video_head.mp4]
```

转场：`fade`（默认）/ `slide_left` / `slide_right` / `zoom` / `none`

**OOM 降级**（30+ 帧时 exit 254，`body_xfade.mp4` 已生成）：

```bash
PROJECT=assets/<topic>_<YYYYMMDD>
OUTDIR=output/<topic>_<YYYYMMDD>
ffmpeg -y \
  -i /abs/path/assets/body_xfade.mp4 \
  -i /abs/path/$PROJECT/tts.mp3 \
  -i /abs/path/$PROJECT/bg_music.mp3 \
  -filter_complex "[2:a]volume=0.15[bg];[1:a][bg]amix=inputs=2:duration=first:dropout_transition=2,aresample=44100" \
  -c:v libx264 -preset fast -crf 23 -pix_fmt yuv420p -b:v 6M \
  -c:a aac -b:a 128000 -ar 44100 \
  -t <时长> /abs/path/$OUTDIR/composed.mp4
```

## Phase 7: 后期处理

```bash
PROJECT=assets/<topic>_<YYYYMMDD>
OUTDIR=output/<topic>_<YYYYMMDD>
```

### 选项 A：不加字幕

```bash
clawreel post --video /abs/path/$OUTDIR/composed.mp4 --title "标题" --no-subtitles
```

### 选项 B：加字幕

```bash
# Step 1: Whisper 烧录
clawreel burn-subs --video /abs/path/$OUTDIR/composed.mp4 --model medium --language zh --margin-v 550

# Step 2: 标题 + 水印
clawreel post --video /abs/path/$OUTDIR/composed.subtitled.mp4 --title "标题" --no-subtitles
```

`--margin-v` 参考（9:16 竖屏）：`0` 底部 | `550` 抖音推荐 | `700` 中央偏下

产出：`output/<topic>_<YYYYMMDD>/final.mp4`

## Phase 8: 发布

### Step 1: 生成发布文案（Agent 生成）

为每个平台生成适配的发布文案。

| 字段 | 说明 |
|------|------|
| `title` | 视频标题（平台显示） |
| `description` | 正文，含 hook + 核心卖点 + CTA |
| `tags` | 话题标签，5-10 个 |

**平台适配**：

| 平台 | 标题 | 正文 | 标签 |
|------|------|------|------|
| 抖音 | 口语化、悬念感、emoji | 短平快、痛点 | 5-8 个，含热点 |
| 小红书 | 笔记体、信息密度 | 分点罗列、干货 | 8-10 个，长尾词 |
| B站 | 信息型、偏专业 | 稍长可接受 | 5-8 个，技术标签 |

展示文案表格，确认后发布。

### Step 2: 发布

```bash
OUTDIR=output/<topic>_<YYYYMMDD>
clawreel publish --video /abs/path/$OUTDIR/final.mp4 --title "标题" --platforms douyin xiaohongshu
```

支持：`douyin`、`xiaohongshu`、`bilibili`

---

## 辅助命令

```bash
# 音色试听
clawreel tts --text "测试" --provider minimax --voice presenter_male

# 批量试听（保存到 /tmp 对比）
for v in presenter_male male-qn-jingying male-qn-badao; do
  clawreel tts --text "${v}测试" --provider minimax --voice "$v" 2>/dev/null \
    && cp assets/tts_output.mp3 "/tmp/voice_${v}.mp3"
done
open /tmp/voice_*.mp3
```

## 文件约定

项目目录 `P = assets/<topic>_<YYYYMMDD>/`，输出目录 `O = output/<topic>_<YYYYMMDD>/`。

| 类型 | 路径 |
|------|------|
| 脚本 | `$P/script.json` |
| 片段 | `$P/segments.json` |
| 图片 | `$P/images/seg_*.jpg` |
| 背景音乐 | `$P/bg_music.mp3` |
| TTS 音频 | `$P/tts.mp3` |
| 合成视频 | `$O/composed.mp4` |
| 最终视频 | `$O/final.mp4` |

兜底背景音乐：`assets/bg_music_default.mp3`（首次运行时生成）
