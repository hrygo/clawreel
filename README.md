![ClawReel Hero](assets/hero.webp)

# ClawReel: The AI Short-Video Production Factory

> **从创意到发布，只需一次对话。**
> 这是一个专为 **AI 智能体 (Agents)** 打造的**智能体驱动 / 分段编排式**短视频全链路流水线。

---

## 💡 为什么选择 ClawReel？ (Utility & Value)

### 对于人类创作者 (For Humans: Control & Efficiency)
*   **极致高效**：分钟级生成涵盖 脚本、配音、视频、配图与背景音乐 的高质量短视频。
*   **完全掌控 (HITL)**：拒绝“黑盒同步生成”，每个阶段（脚本、素材、合成）均设有审核点，确保内容符合预期。
*   **成本透明 (FinOps)**：内置资源查重与复用逻辑，通过 `check` 命令智能判定，平均节省 50%-80% 的模型调用成本。

### 对于 AI 智能体 (For Agents: Standard & Reliability)
*   **标准化接口**：全量 CLI 命令支持，输出统一为极其易读的 **JSON** 格式。
*   **安全中断协议**：专为 Agent 优化，主动暴露 Checkpoints，方便智能体在关键步骤请求人类授权。
*   **跨环境部署**：一键安装脚本，自动适配 Claude Code, OpenCode, OpenClaw 等多种环境。

---

## 🔄 工作流概览 (Workflow Overview)

**ClawReel** 将完整的视频创作拆解为 **6 个可独立执行的阶段**，Phase 0 为强制性的零成本资源检查，后续每个阶段均支持 HITL 审核点、断点续作与资源复用。

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'fontSize': '16px'}}}%%
graph LR
    A["✅ Phase 0\nCheck"] --> B["📝 Phase 1\nScript"]
    B --> C["🔊 Phase 2\nTTS"]
    C --> D["🎨 Phase 3\nAssets"]
    D --> E["🎬 Phase 4\nCompose"]
    E --> F["✨ Phase 5\nPost"]
    F --> G["🚀 Phase 6\nPublish"]

    classDef phase0 fill:#e0e7ff,stroke:#6366f1,stroke-width:2px,color:#333
    classDef phase1 fill:#dbeafe,stroke:#3b82f6,stroke-width:2px,color:#333
    classDef phase2 fill:#dcfce7,stroke:#22c55e,stroke-width:2px,color:#333
    classDef phase3 fill:#fef9c3,stroke:#eab308,stroke-width:2px,color:#333
    classDef phase4 fill:#ffe4e6,stroke:#f43f5e,stroke-width:2px,color:#333
    classDef phase5 fill:#f3e8ff,stroke:#a855f7,stroke-width:2px,color:#333
    classDef phase6 fill:#d1fae5,stroke:#10b981,stroke-width:2px,color:#333

    class A phase0; class B phase1; class C phase2; class D phase3
    class E phase4; class F phase5; class G phase6
```

* **Phase 0 – Check** ⚠️ 必做：零成本扫描现有资源，智能判定生成方案。  
* **Phase 1 – Script**：生成剧本、口播词与视觉提示词。  
* **Phase 2 – TTS**：将文字转为自然语音，支持多模型切换。  
* **Phase 3 – Assets**：并行获取视频、图片、音乐，FinOps 跳过已有资源。  
* **Phase 4 – Compose**：FFmpeg 精准合成。  
* **Phase 5 – Post**：字幕烧录、AIGC 标识。  
* **Phase 6 – Publish**：一键发布至抖音、小红书。

---

## 🌟 核心特性

-   **即插即用 CLI**：通过 `pip install -e .` 安装后，可在任何工作空间直接调用 `clawreel` 命令。
-   **FinOps 深度优化**：
    -   `clawreel check --topic "..."`: 零成本扫描现有资源，支持 `--smart` LLM 语义匹配。
    -   `clawreel assets --topic "..." --skip-existing`: 自动跳过已存在的同主题素材，防止高昂的 API 重复调用。
    -   `clawreel assets --force`: 强制重新生成，忽略本地缓存。
-   **策略模式驱动**：分发平台集成完全采用注册字典形式，易于扩展新渠道（如微信视频号）。
-   **网络层解耦**：所有 API 统一收束，支持异步轮询封装，消除冗余代码。

---

## 🚀 快速开始

### 一键安装（推荐，一行命令）

```bash
curl -fsSL https://raw.githubusercontent.com/hrygo/clawreel/main/install.sh | bash
```

该脚本自动完成：克隆源码 → 安装 CLI → 部署 Skill 到 Claude Code/OpenClaw/OpenCode 环境。

### 手动安装（可选）

```bash
# 1. 克隆仓库
git clone https://github.com/hrygo/clawreel && cd clawreel

# 2. 执行安装
./install.sh
```

### 初始化配置

```bash
# 设置 MiniMax API Key（视频/图片/音乐/TTS 需要）
export MINIMAX_API_KEY="your_key_here"
```

### 开始创作

```bash
# Phase 0: 零成本资源检查（必须先执行）
clawreel check --topic "AI未来趋势"
clawreel check --topic "AI未来趋势" --smart   # LLM 语义模式

# Phase 1-6: 依次执行
clawreel script --topic "AI未来趋势"
clawreel tts --text "..." --provider edge
clawreel assets \
  --hook-prompt "..." --image-prompt "..." --count 3 \
  --music-prompt "..." --topic "AI未来趋势" --skip-existing
clawreel compose --tts ... --images ... --music ... --hook ...
clawreel post --video ... --title "..."
clawreel publish --video ... --title "..." --platforms xiaohongshu douyin
```

---

## 📖 技能集成指南 (For Agents)

如果你是 AI 助理，请务必详细阅读 [**SKILL.md**](./SKILL.md)。

> [!IMPORTANT]
> **财务责任制**：生成视频、图片和音乐是有成本的。在调用 `assets` 之前，必须先通过 `check` 展示现有资源，并向用户确认支出意愿。

---

## 🛠️ 技术栈

*   **Logic**: Python 3.10+, FFmpeg
-   **AI Providers**: MiniMax (Vision/TTS), Microsoft Edge TTS
*   **Design Patterns**: Strategy, Factory, HITL Workflow

---

© 2026 ClawReel Team. Built for the Agentic Era.
