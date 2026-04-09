#!/bin/bash

# ClawReel One-Click Installer (Ver 4.0)
# - Standalone mode: curl ... | bash  (auto-clones repo first)
# - Post-clone mode: ./install.sh     (already inside repo)
# Compatible with Bash 3.2+ (MacOS Default)

set -e

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

# ── Repository info ───────────────────────────────────────────────────────────
REPO_URL="https://github.com/hrygo/clawreel.git"
INSTALL_DIR="${HOME}/.clawreel-install"
SKILL_URL="https://raw.githubusercontent.com/hrygo/clawreel/main/SKILL.md"

info()    { echo -e "${GREEN}[clawreel]${NC} $1"; }
warn()    { echo -e "${YELLOW}[clawreel]${NC} $1"; }
err()     { echo -e "${RED}[clawreel]${NC} $1"; exit 1; }
confirm() { echo -e "${YELLOW}[clawreel]${NC} $1"; }

# ── Detect: am I inside the repo? ────────────────────────────────────────────
inside_repo() {
    [[ -f "pyproject.toml" && -d ".git" ]]
}

# ── Self-update: fetch latest install.sh ──────────────────────────────────────
update_self() {
    local tmp
    tmp=$(mktemp)
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "https://raw.githubusercontent.com/hrygo/clawreel/main/install.sh" -o "$tmp"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "$tmp" "https://raw.githubusercontent.com/hrygo/clawreel/main/install.sh"
    else
        err "curl or wget is required to download the installer."
    fi
    chmod +x "$tmp"
    exec "$tmp" "$@"
}

# ── Clone (or update) the repo ────────────────────────────────────────────────
clone_or_pull() {
    info "📦 Cloning / updating ClawReel..."

    if [[ -d "${INSTALL_DIR}/.git" ]]; then
        info "Repo already exists at ${INSTALL_DIR}, pulling latest..."
        git -C "$INSTALL_DIR" pull --ff-only origin main 2>/dev/null || \
            warn "Pull failed (可能是本地修改)，继续使用现有版本..."
    else
        rm -rf "$INSTALL_DIR"
        git clone --depth=1 "$REPO_URL" "$INSTALL_DIR"
        info "✅ 源码克隆完成"
    fi
}

# ── FFmpeg (required for video compose + hard subtitle burn) ─────────────────
check_brew() {
    if ! command -v brew >/dev/null 2>&1; then
        warn "Homebrew 未安装，跳过 ffmpeg-full 安装。"
        warn "如有需要，请手动执行: brew install ffmpeg-full"
        return 1
    fi
    return 0
}

install_ffmpeg_full() {
    info "⚙️  检查 FFmpeg (libass 硬字幕烧录依赖)..."

    # 检查 ffmpeg-full 是否已安装且可解析 ass 滤镜
    FULL="/opt/homebrew/Cellar/ffmpeg-full"
    if [[ -d "$FULL" ]]; then
        # 验证 ass 滤镜可用
        local ffmpeg_bin
        ffmpeg_bin=$(brew --prefix ffmpeg-full 2>/dev/null || echo "")/bin/ffmpeg
        if [[ -x "$ffmpeg_bin" ]] && "$ffmpeg_bin" -filters 2>/dev/null | grep -q "^\s\+\.\. ass"; then
            info "✅ ffmpeg-full (libass) 已就绪"
            return 0
        fi
    fi

    # 检查 PATH 中的 ffmpeg 是否为 full 版本
    if command -v ffmpeg >/dev/null 2>&1 && \
       ffmpeg -filters 2>/dev/null | grep -q "^\s\+\.\. ass"; then
        info "✅ PATH 中的 ffmpeg 已包含 libass"
        return 0
    fi

    # 尝试安装/升级 ffmpeg-full
    if check_brew; then
        info "📦 安装 ffmpeg-full (包含 libass，支持硬字幕烧录)..."
        if HOMEBREW_NO_AUTO_UPDATE=1 brew install ffmpeg-full 2>&1; then
            # 优先用 ffmpeg-full 接管 PATH
            HOMEBREW_NO_AUTO_UPDATE=1 brew unlink ffmpeg 2>/dev/null || true
            HOMEBREW_NO_AUTO_UPDATE=1 brew link ffmpeg-full 2>/dev/null || true
            if ffmpeg -filters 2>/dev/null | grep -q "^\s\+\.\. ass"; then
                info "✅ ffmpeg-full 安装并配置完成"
                return 0
            fi
        fi
        warn "ffmpeg-full 安装未成功，软字幕功能仍可用（硬字幕需要 libass）"
    fi
}

# ── Core: pip install CLI + deploy skill ─────────────────────────────────────
do_install() {
    local repo_dir="${1:-.}"

    info "🚀 开始安装 ClawReel..."

    # 1. FFmpeg
    install_ffmpeg_full

    # 2. CLI
    info "⚙️  安装 clawreel CLI..."
    if pip install -e "$repo_dir" > /dev/null 2>&1; then
        info "✅ CLI 'clawreel' 安装成功"
    else
        err "❌ pip install -e . 失败，请检查 Python 环境（需要 Python 3.10+）"
    fi

    # Deploy SKILL.md to known agent environments
    info "🤖 部署 Skill 到 AI Agent 环境..."

    # Determine skill targets
    local targets=()
    [[ -d "${HOME}/.claude/skills" ]]        && targets+=("${HOME}/.claude/skills")
    [[ -d "${HOME}/.openclaw/skills" ]]       && targets+=("${HOME}/.openclaw/skills")
    [[ -d "${HOME}/.opencode/skills" ]]       && targets+=("${HOME}/.opencode/skills")
    [[ -d "${HOME}/.config/opencode/skills" ]] && targets+=("${HOME}/.config/opencode/skills")
    [[ -d "$(pwd)/.agents/skills" ]]         && targets+=("$(pwd)/.agents/skills")

    if [[ ${#targets[@]} -eq 0 ]]; then
        warn "未检测到 Claude Code / OpenClaw / OpenCode 环境，跳过 Skill 部署。"
        warn "Skill 文件位于: ${repo_dir}/SKILL.md"
    else
        for dir in "${targets[@]}"; do
            mkdir -p "$dir/clawreel"
            ln -sf "${repo_dir}/SKILL.md" "$dir/clawreel/SKILL.md"
            info "  ✅ 部署到 ${dir/#$HOME/~}/clawreel/"
        done
    fi

    # 3. Env setup hint
    if [[ -z "${MINIMAX_API_KEY}" ]]; then
        echo ""
        info "⚙️  环境配置提示:"
        warn "请设置环境变量 MINIMAX_API_KEY（视频/图片/音乐/TTS 需要）"
        warn "方法：export MINIMAX_API_KEY=\"your_key_here\""
    fi
}

# ── Entry ─────────────────────────────────────────────────────────────────────
main() {
    echo -e "${CYAN}[clawreel]${NC} 欢迎使用 AI 短视频自动化流水线 v4.0"
    echo ""

    if inside_repo; then
        info "检测到已在仓库目录内，执行本地安装..."
        do_install "$(pwd)"
    else
        info "检测到不在仓库目录内，准备完整安装..."
        clone_or_pull
        do_install "$INSTALL_DIR"
    fi

    echo ""
    info "✅ 安装完成!"
    echo ""
    info "下一步："
    echo -e "  1. 设置 API Key:  ${YELLOW}export MINIMAX_API_KEY=\"your_key\"${NC}"
    echo -e "  2. 验证 CLI:      ${YELLOW}clawreel --help${NC}"
    echo -e "  3. 开始创作:      ${YELLOW}clawreel check --topic \"AI未来趋势\"${NC}"
    echo ""
    echo -e "  文档: ${YELLOW}https://github.com/hrygo/clawreel${NC}"
}

main "$@"
