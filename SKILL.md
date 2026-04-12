---
name: clawreel
description: 触发：制作短视频、知识科普视频、话题讲解短片、产品展示视频、宠物/美食/生活记录短片、任何需要配音+配图+合成为竖屏视频的场景。不触发：视频播放/编码问题、手动剪辑现有视频、纯图文内容。
---

# ClawReel - AI 短视频语义对齐流水线

> **声音、字幕、画面三同步。** 图片切换时机由 TTS 逐词时间戳（~50ms）精确驱动，每张图内容由对应语句语义生成。

## 流程总览

| Phase | 做什么 | CLI 命令 | 产出 |
|-------|--------|----------|------|
| **1** | 资源检查 + 背景音乐 | `check` / `music` | 资源清单 + `bg_music_*.mp3` |
| **2** | 生成口播 → 格式化 → 保存 | `format` | `script_*.json` |
| **3** | **构建生图 Prompt** | — | 含 `image_prompts` 的 script |
| **4** | TTS 配音 + 时间戳对齐 | `align` | 音频 + `segments_*.json` |
| **5** | 批量生成图片 + 可选片头视频 | `assets` / `video` | `seg_*.jpg` + 可选 `video_head.mp4` |
| **6** | FFmpeg 合成视频 | `compose` | `composed.mp4` |
| **7** | Whisper 字幕 + 标题 + 水印 | `burn-subs` / `post` | `final_composed.mp4` |
| **8** | 生成发布文案 + 多平台发布 | `publish` | 文案 + 抖音/小红书 |

### 数据流（关键！）

```
Phase 2  format --content  →  script.json（title, sentences, hooks, cta）
Phase 3  Agent 编辑         →  script.json（+ image_prompts, style_prompt）
Phase 4  align --text=<sentences 空格拼接> --script=<script.json>
                             →  tts_output.mp3 + segments.json
  ⚠️     数据完整性校验      →  检查 index 连续性 + prompt 未被覆盖
Phase 5  assets             →  seg_*.jpg
Phase 6  compose            →  composed.mp4
Phase 7  burn-subs(--margin-v) + post → final_composed.mp4
Phase 8  Agent 生成文案 + publish → 抖音/小红书/B站
```

**Phase 4 的 `--text` 构造方法**：从 script JSON 的 `sentences` 数组中取出所有句，**保留标点符号**，用空格拼接。不含 hooks，不含 `#` 标题。代码会自动处理 hook 拼接和去重。标点影响 TTS 语调和停顿，不可省略。

## 架构原则

| 层级 | 职责 | 边界 |
|------|------|------|
| Agent（你） | 创意决策、内容生成、Prompt 构建 | 不直接调用 API，不做格式化 |
| CLI | 格式化、TTS、配音、合成、发布 | 不理解上下文，只做执行 |
| 生图模型 | 按 Prompt 生成图片 | 无记忆，每次独立调用 |

## 通用规则

1. **所有 CLI 路径参数用绝对路径** — `resolve()` 防止工作目录变化导致找不到文件
2. **文件命名**：`script_<主题>_<日期>.json`、`segments_<主题>_<日期>.json`、`bg_music_<主题>.mp3`
3. **默认目录**：`assets/`（中间产物）、`output/`（最终产物）、`assets/images/`（图片）

## 反模式（严禁）

| 反模式 | 后果 | 正确做法 |
|--------|------|----------|
| sentences 包含 `# title` 前缀 | TTS 读出 "hashtag title" | sentences = 纯口播文本，title 单独存储 |
| sentences[0:2] 与 hooks 重复 | 前两句被 TTS 读两遍 | format 自动分离，Agent 不要手动复制 |
| `--text` 包含 hook 文本 | 同上（TTS 重复） | `--text` = 正文 body only，hooks 从 script JSON 读取 |
| 用 segments JSON 生成字幕 | 声音-字幕不同步 | 默认用 Whisper `burn-subs` 烧录字幕 |
| 图片 Prompt 含中文文字 | AI 生图出现乱码文字 | 图片中的文字一律用英文 |
| 盲目使用 edge TTS | 声音生硬机械 | 追求自然感用 `--provider minimax` |
| align 后不校验 segments | index 错乱 + prompt 丢失 → 缺图/错图 | Phase 4 后必须执行「数据完整性校验」（见下） |
| 烧录字幕使用默认底部位置 | 抖音 UI 遮挡底部 1/4 | 用 `--margin-v 550` 上移字幕 |

### 已知限制

| 限制 | 影响 | 规避 |
|------|------|------|
| MiniMax 无词级时间戳 | 时间戳精度为字符加权均匀估算 | Edge TTS 获取精确时间戳，或接受均匀估算 |
| `clawreel assets` 无增量模式 | 每次全量生成，缺 1 张也要重跑全部 | 缺图少时手动调 API 补图（见 Phase 5 增量补图）|

## STOP GATES（成本防护）

在每个 Gate 前，用表格向用户展示关键信息，**等待用户明确确认**后才执行下一步。

| Gate | 时机 | 展示内容（用表格） |
|------|------|-------------------|
| **G1** | Phase 2 后 | title + 全部 sentences（编号 + 文本） |
| **G2** | Phase 3 后 | 全局基调 + 每句 Prompt 概要（编号 + 画面描述） |
| **G3** | Phase 5 后 | 6-8 张关键帧图片（首帧、每段首帧、总结帧、CTA帧） |

---

## Phase 1: 资源检查 + 背景音乐

### 资源检查

```bash
clawreel check --topic "主题" [--llm-suggest]
```

- 扫描 `assets/` 目录已有资源，估算缺失资源成本
- `--llm-suggest`：LLM 智能复用建议（需 MINIMAX_API_KEY）
- **决策**：已有脚本/图片 → 评估复用；成本超预期 → 先汇报

### 背景音乐

每个视频按主题生成匹配的背景音乐。`bg_music_default.mp3` 仅作首次运行兜底。

```bash
# 按主题生成（自动命名为 bg_music_<topic>.mp3）
clawreel music --topic "鹦鹉" --duration 60

# 自定义风格
clawreel music --prompt "轻快活泼的尤克里里配乐，热带风情" --duration 90 --output /abs/path/assets/bg_music_parrot.mp3
```

**风格推荐**：宠物→轻快活泼、科技→电子感、美食→温馨治愈、知识科普→清新自然

## Phase 2: 脚本生成 + 格式化

### Step 1: 生成口播内容

基于用户输入，生成口语化脚本。格式：`# 标题` + 用 `|` 分隔句子。

```
# 猫咪为何沉迷纸箱
你有没有发现 | 每次拆快递 | 猫比你还兴奋 | ...
```

要求：
- 开头钩子 → 分段展开 → 总结 → CTA（5-40 句）
- 每句一个核心信息点，便于生成独立画面
- 末尾必须有明确 CTA（如"关注我带你了解..."）
- `# 标题` 仅作存档标记，**不会被 TTS 读出**（format 自动剥离）

### Step 2: 格式化 + 保存

```bash
clawreel format --content "# 标题\n句1 | 句2 | ..." --title "标题"
```

CLI 输出 JSON 到 stdout。**用 Write 工具将完整 JSON 保存为** `assets/script_<主题>_<日期>.json`。

⛔ **GATE 1** — 向用户展示 title + sentences 表格，确认后继续。

**数据核实**：涉及具体数字（星数、百分比、排名等），优先从 GitHub API / 官方来源获取实时数据，避免幻觉。

## Phase 3: 构建生图 Prompt（核心步骤）

**这是决定视频质量的关键步骤。** `align` 命令会读取 script JSON 中的 `image_prompts`，所以必须在 Phase 4 之前完成。

### Prompt 组装公式

每帧 Prompt 独立完整（生图模型无记忆）：

```
[全局视觉基调], [视觉风格], [本帧画面描述]
```

### Step 1: 设定全局视觉基调

在 script JSON 根级添加两个字段：

- `global_visual_context`（80-120字）：场景、光源、氛围
- `style_prompt`（40-60字）：画质与构图，所有帧共享

**常用风格模板**：

| 类型 | style_prompt |
|------|-------------|
| 宠物/动物 | `Cinematic 4K wildlife photography, 9:16 vertical portrait, shallow depth of field with bokeh, warm golden side-lighting, high contrast, shot on 85mm lens.` |
| 科技/数码 | `Cinematic 4K tech photography, 9:16 vertical portrait, shallow depth of field, cool blue-white studio lighting, clean modern aesthetic, high contrast.` |
| 生活/美食 | `Cinematic 4K lifestyle photography, 9:16 vertical portrait, shallow depth of field, warm natural window light, cozy atmosphere, food magazine quality.` |

### Step 2: 为每句构建逐帧 Prompt

Prompt **用英文**（生图模型理解更好），每帧 50-80 字，描述具体画面。

**实体一致性**：涉及品牌/角色/产品时，在 Prompt 中保持视觉符号一致。例如 OpenClaw 始终用 "red lobster icon"，Hermes 始终用 "winged sandals and caduceus"。在首帧定义，后续帧复用相同描述。

**批量策略**：按段落分组，每组共用场景和角色，只变化动作/表情。

**示例 — 宠物视频 Prompt 模式**：

```
Frame 1: [style]. Title card: bold text "Cat Secrets", magazine cover layout with cat silhouette.
Frame 2: [style]. Curious cat peering into a cardboard box, wide eyes, spotlight on box.
Frame 3: [style]. Cat completely inside box, only ears and eyes visible, cozy expression.
```

### Step 3: 写入 script JSON

```json
{
  "title": "...",
  "script": "...",
  "sentences": ["...", "..."],
  "hooks": ["..."],
  "cta": "...",
  "global_visual_context": "Warm indoor pet photography, golden sunlight, wooden floor.",
  "style_prompt": "Cinematic 4K wildlife photography, 9:16 vertical portrait, shallow depth of field.",
  "image_prompts": [
    "Cinematic 4K..., Warm indoor..., Title card: bold text with cat silhouette.",
    "Cinematic 4K..., Warm indoor..., Curious cat peering into cardboard box."
  ]
}
```

**关键**：`image_prompts` 数组长度 **必须等于** `sentences` 数组长度，一一对应。

⛔ **GATE 2** — 向用户展示全局基调 + 段落 Prompt 概要表格，确认后继续。

## Phase 4: TTS + 对齐

```bash
clawreel align \
  --text "正文文本（空格分隔各句，不含 hooks、不含 # 标题）" \
  --script /abs/path/assets/script_<主题>_<日期>.json \
  --provider minimax \
  [--voice <音色ID>] \
  --output /abs/path/assets/segments_<主题>_<日期>.json \
  [--split-long]
```

- `--text`：**正文 body only**（不含 hooks、不含 `#` 标题），各句用空格分隔（不是 `|`）。**必须保留标点符号**（逗号、句号、感叹号），TTS 依赖标点控制语调和停顿，无标点会导致语音生硬
- `--script`：Phase 2 保存的 script JSON（align 从中读取 hooks、image_prompts）
- `--provider`：推荐 `minimax`（自然语音）；`edge`（免费但机械感强）
- `--voice`：可选，默认从 config 读取
- `--split-long`：自动拆分 >5s 的长段落（**注意：会重置 segment index，慎用**）

**⚠️ hooks 拼接陷阱**：当 hooks 不在 `--text` 中时，CLI 会把 hooks 插入 sentences 前面，但 `image_prompts` 不同步偏移。**最佳实践**：`--text` 应包含 hooks 文本（与 sentences 空格拼接即可），让 CLI 跳过拼接逻辑。

产出：`assets/tts_output.mp3` + `assets/segments_<主题>_<日期>.json`

| TTS Provider | 成本 | 音质 | 时间戳精度 |
|-------------|------|------|-----------|
| `edge`（默认）| 免费 | 机械感强 | 逐词 ~50ms |
| `minimax` | 付费 | 自然流畅 | 不支持（按字数加权估算降级） |

**MiniMax 可用音色**（`--voice` 参数，实测可用）：

| voice_id | 风格 | 适用场景 |
|----------|------|---------|
| `presenter_male` | 男主持人 | 科技产品介绍、知识科普 |
| `presenter_women` | 女主持人 | 温和专业感 |
| `male-qn-qingse` | 青涩男声 | 年轻化内容 |
| `male-qn-jingying` | 精英男声 | 商务/专业内容 |
| `male-qn-badao` | 霸道男声 | 强调型内容 |
| `male-qn-daxuesheng` | 大学生男声 | 校园/轻松风格 |
| `female-shaonv` | 少女音（默认） | 通用 |
| `zh-CN-XiaoxiaoNeural` | Edge 中文女声 | Edge 模式默认 |

**试听**：`clawreel tts --text "测试文本" --provider minimax --voice presenter_male`

### Phase 4 后：数据完整性校验（关键！）

align 后 segments JSON 可能有以下数据损坏，**必须在校验后再进入 Phase 5**：

```python
# 用 Bash 执行此 Python 校验脚本
python3 -c "
import json
with open('assets/segments_<主题>_<日期>.json') as f:
    segs = json.load(f)
with open('assets/script_<主题>_<日期>.json') as f:
    script = json.load(f)

errors = []
# 1. index 连续性：每个 segment 的 index 必须等于其数组位置
for i, seg in enumerate(segs['segments']):
    if seg['index'] != i:
        errors.append(f'seg[{i}] index={seg[\"index\"]} ≠ expected {i}')

# 2. prompt 未被覆盖：检查是否使用了 CLI 默认模板
for i, seg in enumerate(segs['segments']):
    if seg['image_prompt'].startswith('Professional Short Video Scene:'):
        errors.append(f'seg[{i}] prompt 是 CLI 默认模板，非 Agent 构建')

# 3. image 数量与 sentences 对应
if len(segs['segments']) != len(script.get('sentences', [])):
    print(f'⚠️ segments({len(segs[\"segments\"])}) ≠ sentences({len(script[\"sentences\"])})，'
          f'TTS 可能合并了短句，这是正常的')

if errors:
    print('❌ 发现问题：')
    for e in errors: print(f'  - {e}')
    print('需要修复后再继续')
else:
    print('✅ 数据完整性校验通过')
"
```

**常见问题及修复**：

| 问题 | 修复方法 |
|------|---------|
| index 不连续 | `python3 -c "import json; ..."` 遍历重写 `seg['index'] = i` |
| prompt 被 CLI 模板覆盖 | 从 script JSON 的 `image_prompts` 按 text 匹配回填 |
| TTS 合并短句导致段数 < 句数 | 正常现象，但需确保每段有正确的 prompt |

## Phase 5: 素材生成（图片 + 片头视频）

```bash
# 批量生成图片
clawreel assets --segments /abs/path/assets/segments_<主题>_<日期>.json [--video]

# 单独生成 6 秒片头视频（I2V/T2V）
clawreel video --segments /abs/path/assets/segments_<主题>_<日期>.json
```

- `--video`：assets 命令同时生成片头视频（第一帧 hook 的 6 秒动态视频）
- 图片保存到 `assets/images/seg_*.jpg`

⛔ **GATE 3** — 向用户展示 **6-8 张关键帧**图片，确认后继续。

### 增量补图（缺图时）

`clawreel assets` 不支持 `--only`，每次全量生成。若只有少量缺图，用 API 直接补：

```bash
# 检查缺图
ls assets/images/seg_*.jpg | sort > /tmp/existing.txt
python3 -c "
import json
with open('assets/segments_<主题>_<日期>.json') as f:
    segs = json.load(f)
for seg in segs['segments']:
    from pathlib import Path
    idx = seg['index']
    p = Path(f'assets/images/seg_{idx:03d}_0.jpg')
    if not p.exists():
        print(f'MISSING: seg_{idx:03d} → {seg[\"text\"][:30]}')
"
```

补图需手动调用 MiniMax Image API 或重跑 `clawreel assets`（全量）。

## Phase 6: 视频合成

```bash
clawreel compose \
  --tts /abs/path/assets/tts_output.mp3 \
  --segments /abs/path/assets/segments_<主题>_<日期>.json \
  --music /abs/path/assets/bg_music_<主题>.mp3 \
  --transition fade \
  [--hook-video /abs/path/assets/video_head.mp4]
```

**转场选项** `--transition`：

| 值 | 效果 |
|----|------|
| `fade`（默认） | 淡入淡出 |
| `slide_left` | 左滑切换 |
| `slide_right` | 右滑切换 |
| `zoom` | 缩放过渡 |
| `none` | 无转场（直接拼接） |

**常见失败恢复**：

| 失败现象 | 原因 | 恢复 |
|----------|------|------|
| `bg_music: No such file` | 路径非绝对 | 使用绝对路径 |
| exit code 254 (OOM) | 30+ 帧 xfade 内存不足 | `body_xfade.mp4` 已生成，手动合并音频（见下方） |
| TTS 音频翻倍 | align hooks 拼接导致重复 | 检查 `--text` 是否已包含 hook 文本 |

**手动合并音频降级方案**：

```bash
ffmpeg -y \
  -i /abs/path/assets/body_xfade.mp4 \
  -i /abs/path/assets/tts_output.mp3 \
  -i /abs/path/assets/bg_music_<主题>.mp3 \
  -filter_complex "[2:a]volume=0.15[bg];[1:a][bg]amix=inputs=2:duration=first:dropout_transition=2,aresample=44100" \
  -c:v libx264 -preset fast -crf 23 -pix_fmt yuv420p -b:v 6M \
  -c:a aac -b:a 128000 -ar 44100 \
  -t <视频时长> \
  /abs/path/output/composed.mp4
```

## Phase 7: 后期处理

根据需要选择是否加字幕。

### 选项 A：不加字幕（直接加标题）

```bash
clawreel post --video /abs/path/output/composed.mp4 --title "标题" --no-subtitles
```

### 选项 B：加字幕（Whisper 烧录 + 标题）

#### Step 1: 字幕烧录

```bash
# 一步完成：Whisper 转写 + 字幕烧录
# --margin-v 控制字幕距底部像素数（9:16 竖屏 1920px 高）
clawreel burn-subs --video /abs/path/output/composed.mp4 --model medium --language zh --margin-v 550
```

**--margin-v 参考**（9:16 竖屏 1920px 高）：

| 值 | 效果 | 适用场景 |
|----|------|---------|
| `0`（默认） | 字幕在屏幕底部 | 无遮挡平台 |
| `550` | 字幕上移至底部 1/4 以上 | 抖音（底部有 UI 遮挡） |
| `700` | 字幕在屏幕中央偏下 | 强调画面底部内容时 |

#### Step 2: 标题 + AIGC 水印

```bash
clawreel post --video /abs/path/output/composed.subtitled.mp4 --title "标题" --no-subtitles
```

字幕来源优先级：Whisper burn-subs（推荐） > 显式 SRT > segments JSON（可能不同步）

产出：`output/final_composed.mp4`

## Phase 8: 发布

### Step 1: 生成发布文案（Agent 生成，不调用 CLI）

基于脚本内容，为每个平台生成适配的发布文案。**不同平台风格不同，需分别生成**。

**Agent 生成内容**：

| 字段 | 说明 | 示例 |
|------|------|------|
| `title` | 视频标题（平台显示标题，非脚本 title） | "给你的龙虾装上长期记忆 🦞" |
| `description` | 正文/描述，含 hook + 核心卖点 + CTA | "每次关闭 Claude Code 就失忆？..." |
| `tags` | 话题标签，5-10 个 | #Claude #AI编程 #OpenClaw ..." |

**平台适配要点**：

| 平台 | 标题风格 | 正文风格 | 标签 |
|------|---------|---------|------|
| **抖音** | 口语化、悬念感、带 emoji | 短平快、突出痛点 | 5-8 个，含热点标签 |
| **小红书** | 笔记体、信息密度高、带 emoji | 分点罗列、干货感强 | 8-10 个，含长尾关键词 |
| **B站** | 信息型、偏专业 | 稍长可接受、技术细节 | 5-8 个，含技术标签 |

**向用户展示文案表格，确认后进入 Step 2。**

### Step 2: 发布

```bash
clawreel publish --video /abs/path/output/final_composed.mp4 --title "标题" --platforms douyin xiaohongshu
```

支持平台：`douyin`、`xiaohongshu`、`bilibili`

---

## 辅助命令

```bash
# TTS 音色试听（合成前测试音色效果）
clawreel tts --text "测试文本" --provider minimax --voice presenter_male

# 批量试听多个音色（保存到 /tmp 逐个对比）
for v in presenter_male male-qn-jingying male-qn-badao; do
  clawreel tts --text "这是${v}音色的测试" --provider minimax --voice "$v" 2>/dev/null     && cp assets/tts_output.mp3 "/tmp/voice_${v}.mp3"
done
open /tmp/voice_*.mp3
```

---

## 文件约定

| 类型 | 路径 |
|------|------|
| 脚本 | `assets/script_<主题>_<日期>.json` |
| 片段 | `assets/segments_<主题>_<日期>.json` |
| 图片 | `assets/images/seg_*.jpg` |
| 背景音乐 | `assets/bg_music_<主题>.mp3` |
| TTS 音频 | `assets/tts_output.mp3` |
| 合成视频 | `output/composed.mp4` |
| 最终视频 | `output/final_composed.mp4` |

## 错误处理

| 场景 | 处理 |
|------|------|
| 用户中断 | 保留当前阶段产物，下次从断点继续 |
| API 调用失败 | 重试 3 次，指数退避；仍失败则展示错误等指令 |
| 路径失败 | 检查绝对路径 → 降级为手动 ffmpeg |
| 资源缺失 | 明确指出缺失文件，指导补充 |
| 成本超预期 | 立即暂停，汇报实际成本等确认 |
| OOM (exit 254) | `body_xfade.mp4` 已生成，用 Phase 6 的手动合并降级方案 |
