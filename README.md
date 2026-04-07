# MiniMax 内容创作自动化流水线

> 使用 MiniMax API 全自动生成抖音/小红书短视频内容。
>
> 项目路径：`~/workspace/ai-content-pipeline/`

---

## 快速开始

### 1. 安装依赖

```bash
cd ~/workspace/ai-content-pipeline
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
export MINIMAX_API_KEY="sk-cp-xxx"
export MINIMAX_API_HOST="https://api.minimaxi.com"
```

或在项目根目录创建 `.env` 文件：

```
MINIMAX_API_KEY=sk-cp-xxx
MINIMAX_API_HOST=https://api.minimaxi.com
```

### 3. 运行

```bash
# 单个主题 — 端到端流水线
python scripts/generate.py --topic "如何快速学会Python"

# 批量生成（默认并行）
python scripts/batch.py --topics "主题1" "主题2" "主题3"

# 批量生成（串行，逐个完成）
python scripts/batch.py --topics "主题1" "主题2" --serial
```

### 4. 测试

```bash
python3 -m pytest tests/test_pipeline.py -v
```

---

## 流水线流程（6 阶段 + 3 个 HITL 关卡）

```
┌─────────────────────────────────────────────────────────────────┐
│  造物者输入: --topic "视频主题"                                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  阶段0：脚本生成                                                  │
│  模块: src/script_generator.py                                   │
│  模型: MiniMax-M2.7 (Anthropic 兼容接口)                          │
│  输出: { title, script, hooks: list[str], cta }                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  🛑 HITL #1 — 脚本审核                                           │
│  审核内容: title / script / hooks / cta                         │
│  拒绝处理: 重新生成脚本（不消耗后续配额）                          │
│  操作: 输入 'y' 通过，'r' 重新生成                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  阶段1：TTS 配音                                                  │
│  模块: src/tts_voice.py                                          │
│  模型: speech-2.8-hd，采样率 44100 Hz                            │
│  输出: assets/tts_output.mp3                                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  阶段2：素材并行生成（asyncio.gather）                              │
│  2a: HOOK 视频（MiniMax-Hailuo-02，6秒）                         │
│  2b: 正文图片（image-01，3张，9:16）                               │
│  2c: 背景音乐（music-2.5+，纯音乐）                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  🛑 HITL #2 — 素材审核                                           │
│  审核内容: 视频路径 / 图片列表 / 音乐路径                          │
│  拒绝处理: 可指定重新生成 video / images / music / 全部           │
│  操作: 'y' 全部通过，'v' 仅视频，'i' 仅图片，'m' 仅音乐，'r' 全部  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  阶段3：音视频合成                                                 │
│  模块: src/composer.py，工具: FFmpeg                             │
│  输出: assets/composed.mp4                                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  阶段4：后期处理                                                  │
│  模块: src/post_processor.py                                     │
│  内容: 字幕 burn-in / 封面生成 / AIGC 水印                       │
│  输出: output/final_*.mp4                                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  🛑 HITL #3 — 成片终审                                            │
│  审核内容: 最终视频路径 / 标题                                     │
│  拒绝处理: 重新执行后期处理                                        │
│  操作: 输入 'y' 确认发布，'r' 重新后期处理                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  阶段5：平台发布                                                  │
│  模块: src/publisher.py（占位，待接入平台 SDK）                    │
│  目标: 抖音、小红书（需要 OAuth 授权）                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 项目结构

```
ai-content-pipeline/
├── config.yaml              # 全局配置（API 密钥、路径、默认值）
├── requirements.txt         # Python 依赖
├── .env                     # 环境变量（不提交到 Git）
├── README.md                # 本文档
├── src/
│   ├── __init__.py
│   ├── api_client.py       # 统一 API 客户端（DRY 核心）
│   ├── hitl.py             # HITL 人工审核节点（3个关卡）
│   ├── config.py            # 配置加载 + 全局常量
│   ├── script_generator.py  # 阶段0：脚本生成（M2.7）
│   ├── tts_voice.py        # 阶段1：TTS 配音（speech-2.8-hd）
│   ├── video_generator.py   # 阶段2a：视频生成（Hailuo T2V/I2V）
│   ├── image_generator.py   # 阶段2b：图片生成（image-01）
│   ├── music_generator.py   # 阶段2c：音乐生成（music-2.5+）
│   ├── composer.py          # 阶段3：音视频合成（FFmpeg）
│   ├── post_processor.py    # 阶段4：后期处理（字幕/封面/AIGC）
│   └── publisher.py         # 阶段5：发布（占位，待接入）
├── scripts/
│   ├── generate.py          # 主入口：端到端流水线
│   └── batch.py             # 批量生成入口（默认并行）
├── assets/                  # 中间素材（TTS 音频、图片、音乐）
├── output/                  # 最终成品（视频、封面）
└── tests/
    └── test_pipeline.py     # 10 个单元测试
```

---

## API 架构

### 统一 API 客户端（api_client.py）

所有 MiniMax API 调用通过共享的 `api_client.py` 发起，禁止各模块各自实现 HTTP 逻辑。

```
api_client.py 提供：
├── api_post(endpoint, payload, params)     # 统一 POST
├── api_get(endpoint, params)               # 统一 GET
├── download_file(url, output_path)          # 文件下载
├── get_session()                           # AioHTTP Session 复用
└── generate_idempotency_key(*parts)        # 幂等性 Key
```

**Base URL 统一为 `/v1`**（MiniMax 所有端点均使用 `/v1` 前缀，Token Plan 和传统 API 通用）。

### API 端点一览

| 功能 | 端点 | 方法 |
|------|------|------|
| 脚本生成（LMM） | `/anthropic/v1/messages` | POST |
| TTS | `/v1/t2a_v2` | POST |
| 视频提交 | `/v1/video_generation` | POST |
| 视频查询 | `/v1/query/video_generation` | GET |
| 文件下载 | `/v1/files/retrieve` | GET |
| 图片生成 | `/v1/image_generation` | POST |
| 音乐提交 | `/v1/music_generation` | POST |
| 音乐查询 | `/v1/music_generation/query` | GET |

### 视频生成状态机

```
提交任务 → Preparing → Queueing → Processing → Success
                                              ↘ Fail
```
轮询间隔 5 秒，最长等待 300 秒。所有中间状态均为正常等待，无需报错。

---

## 技术规格

### 音频规格（抖音标准）

| 参数 | 值 | 说明 |
|------|-----|------|
| 采样率 | **44100 Hz** | 抖音标准，不是 32000 |
| 码率 | 128000 (128kbps) | |
| 格式 | mp3 | |
| TTS 模型 | speech-2.8-hd | |
| TTS 默认音色 | female-shaonv | |

### 视频规格

| 参数 | 值 |
|------|-----|
| 分辨率 | 768P（推荐）或 1080P |
| 帧率 | 25 fps |
| 码率 | 6-8 Mbps |
| 竖屏 | 1080×1920 |
| 编码 | H.264 (libx264), yuv420p |
| T2V 模型 | MiniMax-Hailuo-02 |
| I2V 模型 | MiniMax-Hailuo-2.3-Fast |

### 图片规格

| 参数 | 值 |
|------|-----|
| 模型 | image-01 |
| 比例 | 9:16（竖屏） |
| 尺寸 | 720×1280 |
| 数量上限 | 9 张/请求 |

### 封面规格

| 参数 | 值 |
|------|-----|
| 分辨率 | 720×1280 |
| 可见区域 | 1080×1464（顶部 456px 被抖音标题遮挡） |
| **要求** | **关键内容放在下半部分** |

---

## HITL（Human-In-The-Loop）人工审核

三个关卡按流水线顺序设置，越往后代价越高，越需要在进入前设置审核。

| 关卡 | 位置 | 审核内容 | 拒绝后果 |
|------|------|----------|----------|
| **HITL #1** | 阶段0 → 阶段1 | 脚本（title/script/hooks/cta） | 重新生成脚本，不消耗 TTS/素材配额 |
| **HITL #2** | 阶段2 → 阶段3 | 素材（视频/图片/音乐） | 可指定重新生成某一类素材 |
| **HITL #3** | 阶段4 → 阶段5 | 最终成片预览 | 重新后期处理，不触发发布 |

### HITL #1 — 脚本审核

在进入 TTS 配音之前，审核脚本质量：
- 标题是否吸引眼球
- 脚本是否口语化、自然流畅
- Hooks 是否有冲击力
- CTA 是否有力

**拒绝处理**：重新生成脚本，直到通过。

### HITL #2 — 素材审核

在进入合成之前，审核三个素材：
- HOOK 视频（6秒）
- 正文图片（3张）
- 背景音乐

**拒绝处理**：可选择重新生成 video / images / music / 全部。

### HITL #3 — 成片终审

在发布之前，最后确认：
- 字幕是否正确
- AIGC 标识是否到位
- 整体观感

**拒绝处理**：重新执行后期处理，不触发发布。

### 运行模式

```bash
# 控制台交互模式（默认）
python scripts/generate.py --topic "你的视频主题"
# 在每个 HITL 节点，终端会暂停等待输入：
#   'y' — 通过
#   'r' — 拒绝并重新生成
```

---

## 常见问题

### Q: 采样率为什么是 44100？
A: 抖音标准音频采样率为 44100 Hz，32000 会导致音质问题或上传失败。

### Q: music-2.5 和 music-2.5+ 有什么区别？
A: music-2.5 不支持纯音乐（`is_instrumental`），必须使用 `music-2.5+`。

### Q: 音乐生成 API 字段名是什么？
A: 是 `is_instrumental`（布尔值），不是 `instrumental`。

### Q: 封面关键内容为什么放在下半部分？
A: 抖音标题栏占用顶部约 456px，封面可见区域为 1080×1464，关键内容放在下半部分才能被看到。

### Q: 图片生成 API 参数名是什么？
A: 是 `n`（数量），不是 `num_images`；是 `image_urls`（返回字段），不是 `images`。

### Q: Token Plan 和传统 API 有什么区别？
A: 两者 API 端点相同（均为 `/v1`），区别在于认证方式。`sk-cp-` 开头的 Key 属于 Token Plan。

---

## 测试记录

### 单元测试（10/10 通过）

```
✅ test_sample_rate_is_44100
✅ test_audio_bit_rate
✅ test_cover_visible_region
✅ test_cover_full_resolution
✅ test_model_names
✅ test_image_model
✅ test_script_data_structure
✅ test_video_fps
✅ test_is_instrumental_field_name
✅ test_cover_visible_region_key_content_bottom
```

---

## 更新日志

### 2026-04-07 — 全面优化

**架构重构：**
- 新增 `api_client.py`：统一 API 调用层（DRY 核心），Session 复用（FINOPS）
- 移除各模块重复的 `_build_params()`、`aiohttp` HTTP 逻辑
- 移除 `MINIMAX_GROUP_ID` 及相关残留代码

**新增 HITL 模块：**
- 新增 `src/hitl.py`：三个人工审核关卡（脚本/素材/成片）
- `generate.py` 集成 HITL 节点，拒绝时自动重新生成对应内容
- 项目移动到 `~/workspace/ai-content-pipeline/`

**Bug 修复：**
- TTS：修正端点路径为 `/v1/t2a_v2`，改用 `output_format=hex` 直接返回音频
- 图片生成：`num_images` → `n`，`images` → `image_urls`，移除无效 `resolution` 字段
- 视频轮询：补全 5 种状态（Preparing/Queueing/Processing），不再将中间状态当错误

**其他改进：**
- batch.py 默认并行（`--parallel`），新增 `--serial` 串行选项
- config.yaml 移除误导的 `base_url` 注释
- config.py 职责单一化，API 路径逻辑统一

---

*最后更新: 2026-04-07 by Sisyphus 🤖*
