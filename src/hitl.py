"""HITL（Human-In-The-Loop）模块 — 流水线人工审核节点。

三个关卡：
  HITL #1 — 脚本审核（阶段0 → 阶段1）
  HITL #2 — 素材审核（阶段阶段2 → 阶段3）
  HITL #3 — 成片终审（阶段4 → 阶段5）
"""
import logging
import asyncio
import threading
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# ── 全局开关 ─────────────────────────────────────────────────────────────

auto_approve: bool = False  # True 时所有 HITL 节点自动通过


@dataclass
class HITLResult:
    """审核结果."""
    approved: bool
    feedback: str | None = None  # 拒绝时的说明


# ── Slack 通知 ────────────────────────────────────────────────────────────────

_slack_channel: str | None = None


def set_slack_channel(channel: str) -> None:
    """设置 Slack channel ID（用于发送审核消息）。"""
    global _slack_channel
    _slack_channel = channel


def _try_slack_notify(blocks: list[dict]) -> None:
    """尝试通过 Slack 发送 Block Kit 通知（非阻塞）。"""
    if not _slack_channel:
        return
    try:
        from openclaw.tools import message
        t = threading.Thread(
            target=lambda: message(
                action="send",
                channel="slack",
                target=_slack_channel,
                interactive={"blocks": blocks},
            )
        )
        t.start()
    except Exception as e:
        logger.warning("Slack 通知发送失败: %s", e)


# ── HITL 节点实现 ─────────────────────────────────────────────────────────────

async def hitl_script_review(
    script_data: dict,
    topic: str,
) -> HITLResult:
    """HITL #1 — 脚本审核。"""
    if auto_approve:
        logger.info("⏭️ [AUTO-APPROVE] HITL #1 通过")
        return HITLResult(approved=True)

    logger.info("🛑 HITL #1 等待审核：脚本")

    title = script_data.get("title", "")
    script = script_data.get("script", "")
    hooks = script_data.get("hooks", [])
    cta = script_data.get("cta", "")

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🛑 HITL #1 — 脚本待审核", "emoji": True}
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*主题*\n{topic}"},
                {"type": "mrkdwn", "text": f"*标题*\n{title}"},
            ]
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*📝 口播脚本*\n{script}"}
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*🎣 Hooks*\n" + "\n".join(f"• {h}" for h in hooks) if hooks else "_无 hooks_"
            }
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*📢 CTA*\n{cta}"}
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "回复 'y' 通过，'r' 重新生成"}]
        }
    ]
    _try_slack_notify(blocks)

    # 控制台交互
    print("\n" + "=" * 60)
    print("🛑 HITL #1 — 脚本待审核")
    print("=" * 60)
    print(f"标题: {title}")
    print(f"脚本: {script}")
    print(f"Hooks: {hooks}")
    print(f"CTA: {cta}")
    print("=" * 60)
    print("输入 'y' 通过，'r' 重新生成: ", end="", flush=True)

    loop = asyncio.get_event_loop()
    try:
        answer = await loop.run_in_executor(None, input)
        answer = answer.strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "y"

    if answer == "r":
        logger.info("HITL #1 拒绝，重新生成脚本")
        return HITLResult(approved=False, feedback="用户要求重新生成")
    logger.info("HITL #1 通过")
    return HITLResult(approved=True)


async def hitl_assets_review(
    hook_video: Path,
    images: list[Path],
    music: Path,
    script: str,
) -> HITLResult:
    """HITL #2 — 素材审核。"""
    if auto_approve:
        logger.info("⏭️ [AUTO-APPROVE] HITL #2 通过")
        return HITLResult(approved=True)

    logger.info("🛑 HITL #2 等待审核：素材")

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🛑 HITL #2 — 素材待审核", "emoji": True}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*🎬 HOOK 视频*\n`{hook_video}`"}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*🖼️ 正文图片*\n{len(images)} 张"}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*🎵 背景音乐*\n`{music}`"}
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "回复 'y' 全部通过，'v' 仅视频，'i' 仅图片，'m' 仅音乐，'r' 全部重试"}]
        }
    ]
    _try_slack_notify(blocks)

    print("\n" + "=" * 60)
    print("🛑 HITL #2 — 素材待审核")
    print("=" * 60)
    print(f"HOOK 视频: {hook_video}")
    print(f"正文图片: {len(images)} 张")
    print(f"背景音乐: {music}")
    print("=" * 60)
    print("输入 'y' 全部通过，'v' 仅视频，'i' 仅图片，'m' 仅音乐，'r' 全部重试: ", end="", flush=True)

    loop = asyncio.get_event_loop()
    try:
        answer = await loop.run_in_executor(None, input)
        answer = answer.strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "y"

    if answer == "y":
        logger.info("HITL #2 通过")
        return HITLResult(approved=True)
    elif answer == "v":
        return HITLResult(approved=False, feedback="regen_video")
    elif answer == "i":
        return HITLResult(approved=False, feedback="regen_images")
    elif answer == "m":
        return HITLResult(approved=False, feedback="regen_music")
    else:
        return HITLResult(approved=False, feedback="regen_all")


async def hitl_final_review(
    final_video: Path,
    title: str,
) -> HITLResult:
    """HITL #3 — 成片终审。"""
    if auto_approve:
        logger.info("⏭️ [AUTO-APPROVE] HITL #3 通过")
        return HITLResult(approved=True)

    logger.info("🛑 HITL #3 等待审核：成片")

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🛑 HITL #3 — 成片终审", "emoji": True}
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*标题*\n{title}"},
                {"type": "mrkdwn", "text": f"*📁 文件*\n{str(final_video)}"},
            ]
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "回复 'y' 确认发布，'r' 重新后期处理"}]
        }
    ]
    _try_slack_notify(blocks)

    print("\n" + "=" * 60)
    print("🛑 HITL #3 — 成片终审")
    print("=" * 60)
    print(f"标题: {title}")
    print(f"最终文件: {final_video}")
    print("=" * 60)
    print("输入 'y' 确认发布，'r' 重新后期处理: ", end="", flush=True)

    loop = asyncio.get_event_loop()
    try:
        answer = await loop.run_in_executor(None, input)
        answer = answer.strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "y"

    if answer == "r":
        logger.info("HITL #3 拒绝，重新后期处理")
        return HITLResult(approved=False, feedback="regen_postprocess")
    logger.info("HITL #3 通过，进入发布")
    return HITLResult(approved=True)
