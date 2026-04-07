# Contributing to ClawReel

🤝 Thank you for considering contributing to ClawReel!

ClawReel is an Agent-Driven (HITL) pipeline optimized for automated short video orchestration. We love pull requests from everyone. By participating in this project, you agree to abide by our code of conduct.

## Quick Start
1. Fork the repo and create your branch from `main`.
2. Install the package in editable mode:
   ```bash
   pip install -e .
   ```
3. Copy `.env.example` to `.env` and fill in your keys.
4. Run `clawreel --help` to ensure your setup works.

## Pull Request Guidelines

1. **DRY & SOLID Only**: Since this tool is heavily integrated with AI Agents, ensure APIs remain decoupled (`clawreel/api_client.py`), and any new content publisher logic implements the Strategy Pattern inside `clawreel/publisher.py`.
2. **JSON Outputs ONLY**: Ensure any console printing uses `sys.stderr` for logs, and outputs pure `JSON` to `stdout` so that Agents can parse it properly.
3. **No Interactive Input Blockers**: Do NOT use `input()`. Use environment variables or command-line parameters.

If you add a new sub-command or feature, update `README.md` and `SKILL.md` appropriately.
