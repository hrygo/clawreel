#!/usr/bin/env python3
"""MiniMax 内容创作流水线 - 主入口（含 HITL 人工审核节点）.

用法:
    python generate.py --topic "你的视频主题"

HITL 节点：
    HITL #1 — 阶段0之后，脚本审核
    HITL #2 — 阶段2之后，素材审核
    HITL #3 — 阶段4之后，成片终审
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.script_generator import generate_script
from src.tts_voice import generate_voice
from src.video_generator import generate_video
from src.image_generator import generate_image
from src.music_generator import generate_music
from src.composer import compose
from src.post_processor import post_process
from src.publisher import publish
from src.hitl import (
    hitl_script_review,
    hitl_assets_review,
    hitl_final_review,
    HITLResult,
    auto_approve,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main(topic: str) -> Path:
    """主流程编排（带 HITL 审核节点）。

    阶段0: 脚本生成
      → [HITL #1: 脚本审核]
    阶段1: TTS 配音
    阶段2: 素材生成（视频+图片+音乐，并行）
      → [HITL #2: 素材审核]
    阶段3: 音视频合成
    阶段4: 后期处理
      → [HITL #3: 成片终审]
    阶段5: 发布
    """
    logger.info("🚀 流水线启动，主题: %s", topic)

    # ── 阶段0：脚本 ─────────────────────────────────────────────────────────
    script_data = await generate_script(topic)
    logger.info("📋 标题: %s", script_data["title"])
    logger.info("📝 脚本预览: %s", script_data["script"][:80] + "...")

    # ── HITL #1：脚本审核 ───────────────────────────────────────────────────
    if auto_approve:
        logger.info("⏭️ [AUTO-APPROVE] HITL #1 跳过")
        hitl1 = HITLResult(approved=True)
    else:
        hitl1 = await hitl_script_review(script_data, topic)
    if not hitl1.approved:
        # 重新生成脚本，直到通过
        while not hitl1.approved:
            logger.info("🔄 重新生成脚本...")
            script_data = await generate_script(topic)
            hitl1 = await hitl_script_review(script_data, topic)
    logger.info("✅ HITL #1 通过")

    # ── 阶段1：配音 ─────────────────────────────────────────────────────────
    tts_path = await generate_voice(script_data["script"])
    logger.info("🎙️ TTS 完成: %s", tts_path)

    # ── 阶段2：素材生成（并行）───────────────────────────────────────────────
    logger.info("🎬 开始并行生成素材（视频+图片+音乐）...")

    hook_video, images, music = await asyncio.gather(
        generate_video(
            script_data["hooks"][0],
            type="t2v",
            duration=6,
        ),
        generate_image(script_data["script"], count=3),
        generate_music(
            prompt="轻快、节奏感强、适合短视频的背景音乐",
            duration=60,
        ),
    )

    logger.info("🎬 HOOK 视频完成: %s", hook_video)
    logger.info("🖼️ 图片生成完成: %d 张", len(images))
    logger.info("🎵 音乐生成完成: %s", music)

    # ── HITL #2：素材审核 ───────────────────────────────────────────────────
    if auto_approve:
        logger.info("⏭️ [AUTO-APPROVE] HITL #2 跳过")
        hitl2 = HITLResult(approved=True)
    else:
        hitl2 = await hitl_assets_review(hook_video, images, music, script_data["script"])
    if not hitl2.approved:
        # 根据反馈重新生成对应素材
        while not hitl2.approved:
            feedback = hitl2.feedback
            logger.info("🔄 HITL #2 反馈: %s，重新生成中...", feedback)

            if feedback == "regen_video":
                hook_video = await generate_video(
                    script_data["hooks"][0], type="t2v", duration=6,
                )
            elif feedback == "regen_images":
                images = await generate_image(script_data["script"], count=3)
            elif feedback == "regen_music":
                music = await generate_music(
                    prompt="轻快、节奏感强、适合短视频的背景音乐", duration=60,
                )
            else:  # regen_all
                hook_video, images, music = await asyncio.gather(
                    generate_video(script_data["hooks"][0], type="t2v", duration=6),
                    generate_image(script_data["script"], count=3),
                    generate_music(prompt="轻快、节奏感强、适合短视频的背景音乐", duration=60),
                )

            hitl2 = await hitl_assets_review(hook_video, images, music, script_data["script"])

    logger.info("✅ HITL #2 通过")

    # ── 阶段3：合成 ─────────────────────────────────────────────────────────
    composed = await compose(
        tts_path=tts_path,
        image_paths=images,
        music_path=music,
        hook_video_path=hook_video,
    )
    logger.info("🎞️ 合成完成: %s", composed)

    # ── 阶段4：后期处理 ──────────────────────────────────────────────────────
    final = await post_process(composed, script_data["title"])
    logger.info("🎨 后期处理完成: %s", final)

    # ── HITL #3：成片终审 ───────────────────────────────────────────────────
    if auto_approve:
        logger.info("⏭️ [AUTO-APPROVE] HITL #3 跳过")
        hitl3 = HITLResult(approved=True)
    else:
        hitl3 = await hitl_final_review(final, script_data["title"])
    if not hitl3.approved:
        # 重新后期处理
        while not hitl3.approved:
            logger.info("🔄 HITL #3 反馈: %s，重新后期处理...", hitl3.feedback)
            final = await post_process(composed, script_data["title"])
            hitl3 = await hitl_final_review(final, script_data["title"])

    logger.info("✅ HITL #3 通过，进入发布")

    # ── 阶段5：发布 ─────────────────────────────────────────────────────────
    publish_results = await publish(
        final,
        title=script_data["title"],
        platforms=["xiaohongshu", "douyin"],
    )
    for r in publish_results:
        status = "✅" if r["success"] else "❌"
        logger.info("%s %s: %s", status, r["platform"], r.get("error") or r.get("url") or "")

    logger.info("🏁 流水线执行完毕，最终文件: %s", final)
    return final


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MiniMax 内容创作流水线")
    parser.add_argument("--topic", "-t", required=True, help="视频主题")
    parser.add_argument(
        "--auto-approve", "-y",
        action="store_true",
        help="跳过所有 HITL 审核节点，自动通过（测试用）",
    )
    args = parser.parse_args()

    if args.auto_approve:
        import src.hitl as hitl_mod
        hitl_mod.auto_approve = True

    asyncio.run(main(args.topic))
