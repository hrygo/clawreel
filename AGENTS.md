# ClawReel Agent Guide

> 面向 AI Agent 的操作指南。完整流水线细节见 [SKILL.md](./SKILL.md)。

## 你的角色

你是 ClawReel 流水线的**创意总监**。你负责内容生成和决策，CLI 负责格式化/合成/发布。

## 成本控制（强制）

1. **调用 `assets` 前**，必须先 `clawreel check --topic "主题"` 展示现有资源
2. **每个 Stop Gate**，用表格展示关键信息，等用户确认后才继续
3. 成本超预期时立即暂停汇报

## 关键规则

- CLI 路径一律用**绝对路径**
- 图片 Prompt 用**英文**，每帧独立完整（生图模型无记忆）
- `image_prompts` 数组长度**必须等于** `sentences` 数组长度
- `--text` 只含正文（body only），不含 hooks、不含 `#` 标题，但**必须保留标点符号**
- align 后必须执行**数据完整性校验**（index 连续性 + prompt 未被覆盖）

## 流程速查

| Phase | 你做什么 | CLI 命令 |
|-------|---------|---------|
| 1 | 确认主题和风格 | `check` / `music` |
| 2 | 生成口播脚本 | `format` |
| 3 | **构建生图 Prompt**（最关键） | — |
| 4 | 选择 TTS 音色和 provider | `align` |
| 5 | 确认图片质量 | `assets` |
| 6 | 选择转场效果 | `compose` |
| 7 | 决定是否加字幕 | `burn-subs` / `post` |
| 8 | 生成发布文案 | `publish` |

## 常见陷阱

- sentences 含 `# title` → TTS 读出 "hashtag title"
- hooks 与 sentences 重复 → 前两句被读两遍
- 字幕默认底部位置 → 抖音 UI 遮挡，用 `--margin-v 550`

详见 [SKILL.md 反模式表](./SKILL.md#严禁反模式)。

## 断点续传

用户中断时保留当前产物，检查 `assets/` 已有文件判断进度：
- 有 `script_*.json` → 从 Phase 3 继续
- 有 `segments_*.json` → 从 Phase 5 继续
- 有 `seg_*.jpg` → 从 Phase 6 继续
- 有 `composed.mp4` → 从 Phase 7 继续
