#!/bin/bash

# ClawReel One-Click Installer - Strategic Refactor (Ver 2.0)
# - Environment Awareness: Claude Code (~/.claude), OpenClaw (~/.openclaw), OpenCode (~/.opencode)
# - Standards Compliance: npx skill (.agents/skills)
# - CLI Installation: Global (pip install -e .)
# Compatible with Bash 3.2+ (MacOS Default)

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Starting ClawReel Strategic Installation...${NC}"

# 1. Define Verified Global Skill Paths (Home-based)
# Claude Code: ~/.claude/skills
# OpenClaw: ~/.openclaw/skills
# OpenCode: ~/.opencode/skills
# OpenCode (Config): ~/.config/opencode/skills
AGENT_NAMES=("Claude Code" "OpenClaw" "OpenCode" "OpenCode (Config)")
AGENT_PATHS=(
    "$HOME/.claude/skills"
    "$HOME/.openclaw/skills"
    "$HOME/.opencode/skills"
    "$HOME/.config/opencode/skills"
)

# 2. Workspace Root Detection (for npx skill / local agents)
CURRENT_DIR=$(pwd)
WORKSPACE_ROOT="$CURRENT_DIR"
while [[ "$WORKSPACE_ROOT" != "/" && ! -d "$WORKSPACE_ROOT/.git" && ! -f "$WORKSPACE_ROOT/pyproject.toml" && ! -d "$WORKSPACE_ROOT/.agents" ]]; do
    PARENT=$(dirname "$WORKSPACE_ROOT")
    if [[ "$PARENT" == "$WORKSPACE_ROOT" ]]; then break; fi
    WORKSPACE_ROOT="$PARENT"
done

# Add Workspace-local path (follows npx skill convention)
AGENT_NAMES+=("Project Local (.agents/skills)")
AGENT_PATHS+=("$WORKSPACE_ROOT/.agents/skills")

# 3. CLI Tool Installation
echo -e "\nInstalling ${YELLOW}clawreel${NC} CLI tool globally..."
if ! pip install -e . > /dev/null 2>&1; then
    echo -e "${RED}Error: CLI installation failed. Please check your Python environment.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ CLI tool 'clawreel' installed successfully.${NC}"

# 4. Multi-Platform Skill Deployment
echo -e "\n${GREEN}Checking for AI Agent environments...${NC}"

DEPLOYED_COUNT=0
for ((i=0; i<${#AGENT_NAMES[@]}; i++)); do
    NAME="${AGENT_NAMES[i]}"
    SKILLS_DIR="${AGENT_PATHS[i]}"
    TOOL_ROOT=$(dirname "$SKILLS_DIR")
    
    # Check if the tool root exists (indicating the environment is available)
    if [[ -d "$TOOL_ROOT" ]]; then
        SKILL_TARGET_DIR="$SKILLS_DIR/clawreel"
        mkdir -p "$SKILL_TARGET_DIR"
        
        echo -e "  - ${GREEN}$NAME${NC}: Found environment, deploying to ${YELLOW}${SKILLS_DIR/#$HOME/~}/clawreel${NC}..."
        ln -sf "$CURRENT_DIR/SKILL.md" "$SKILL_TARGET_DIR/SKILL.md"
        DEPLOYED_COUNT=$((DEPLOYED_COUNT + 1))
    fi
done

# 5. Configuration Guidance
echo -e "\n${GREEN}⚙️ Configuration Setup:${NC}"
echo -e "The ${YELLOW}Skill Definition${NC} (SKILL.md) has been deployed."
echo -e "The ${YELLOW}ClawReel Tool${NC} requires API keys (e.g., MINIMAX_API_KEY)."

echo -e "Note: The skill definition itself ${YELLOW}does NOT${NC} need a .env file."
echo -e "Recommendation: Set your API keys in your ${YELLOW}environment variables${NC} or in the project's ${YELLOW}.env${NC} file."

if [[ ! -f ".env" ]]; then
    if [[ -f ".env.example" ]]; then
        echo -e "${YELLOW}Notice: No .env file found in this project directory.${NC}"
    fi
else
    echo -e "${GREEN}Found .env file in project directory.${NC}"
fi

echo -e "\n${GREEN}✅ Installation Complete!${NC}"
echo -e "1. CLI: You can now use the ${YELLOW}clawreel${NC} command in any workspace."
echo -e "2. Skills: Deployed to ${YELLOW}$DEPLOYED_COUNT${NC} environment(s)."
echo -e "3. Verify: Check your Agent UI or run ${YELLOW}ls -l ~/.claude/skills/clawreel/SKILL.md${NC}\n"
