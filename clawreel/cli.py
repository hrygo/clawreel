from typing import Optional, List, Dict, Union, Any, Tuple

#!/usr/bin/env python3
"""ClawReel CLI — AI 短视频语义对齐流水线。

命令分类：
  【主流程命令 - 对应 SOP 7 阶段】
    check      Phase 0: 资源扫描 + 成本估算
    script     Phase 1: 脚本生成（输出含 sentences）
    align      Phase 2: TTS + 语义对齐 → segments JSON
    assets     Phase 3: 图片生成（由 segments 驱动）
    compose    Phase 4: 视频合成（T2V/I2V 片头 + FFmpeg 转场）
    post       Phase 5: 后期处理（字幕、AIGC 水印）
    publish    Phase 6: 多平台发布

  【辅助/调试命令】
    tts        独立 TTS 测试（非流程命令，返回 word_timestamps）
    music      背景音乐生成（可在任意阶段使用）
    burn-subs  Whisper 字幕提取 + FFmpeg 烧录（独立工具）
"""
import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from .config import ASSETS_DIR, OUTPUT_DIR
from .script_generator import generate_script, format_script
from .resource_index import check_resources, llm_check_and_suggest
from .tts_voice import generate_voice
from .segment_aligner import align_segments, split_long_segments
from .image_generator import generate_segment_images
from .video_generator import generate_video
from .composer import compose_sequential
from .post_processor import post_process
from .publisher import publish
from .subtitle_extractor import extract_subtitles
from .music_generator import generate_music
from .utils import (
    get_media_duration,
    print_json,
    SCRIPT_SEPARATOR,
    CLEAN_CHAR_CLASS_RE,
    segments_to_srt,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("clawreel")

# 脚本句子分隔符（与 script_generator.py 保持一致）
SCRIPT_SEPARATOR = "|"


def print_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


# ─────────────────────────────────────────────────────────────────────────────
# 命令实现
# ─────────────────────────────────────────────────────────────────────────────

# 成本估算常量（MiniMax 官方定价，2025）
_API_COSTS = {
    "image": 0.035,  # image-01，单张约 ¥0.035
    "music": 0.15,  # music-2.5，60s 约 ¥0.15
    "tts_minimax": 0.005,  # MiniMax TTS，每 1000 字符约 ¥0.5
    "tts_edge": 0.0,  # Edge TTS 免费
}

_MIN_IMAGES_PER_VIDEO = 3
_MAX_IMAGES_PER_VIDEO = 15
_DEFAULT_IMAGES = 9
_DEFAULT_MUSIC_DURATION = 60  # 秒


def _estimate_cost(found: dict, topic: Optional[str]) -> dict:
    """根据已有资源估算缺失资源的成本。"""
    has_script = bool(found.get("script"))
    has_tts = bool(found.get("tts"))
    has_images = found.get("images", [])
    has_music = bool(found.get("music"))

    # 估算缺失资源
    seg_count = len(has_images) if has_images else 0

    missing_images = max(0, _DEFAULT_IMAGES - seg_count)
    missing_music = 0 if has_music else 1
    tts_cost = 0.0  # Edge TTS 免费

    total = (
        missing_images * _API_COSTS["image"]
        + missing_music * _API_COSTS["music"]
        + tts_cost
    )

    missing = []
    if not has_script:
        missing.append("script")
    if not has_tts:
        missing.append("tts")
    if missing_images > 0:
        missing.append(f"images({missing_images}张)")
    if missing_music:
        missing.append("music")

    return {
        "total_yuan": round(total, 2),
        "missing": missing,
        "has_script": has_script,
        "has_tts": has_tts,
        "has_images_count": seg_count,
        "has_music": has_music,
    }


def cmd_check(args):
    """扫描 assets 目录 + LLM 智能资源建议。"""
    assets = Path(args.assets_dir) if args.assets_dir else Path("assets")
    topic = args.topic or ""

    all_patterns = {
        "script": list(assets.glob("script_*.json")),
        "tts": list(assets.glob("tts_*.mp3")),
        "images": list(assets.glob("seg_*.jpg")) + list(assets.glob("seg_*.png")),
        "music": list(assets.glob("bg_music_*.mp3")),
    }

    def matches_topic(p: Path) -> bool:
        if not topic:
            return True
        return topic.lower() in p.stem.lower()

    found = {
        k: sorted(
            [p for p in v if matches_topic(p)],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for k, v in all_patterns.items()
    }

    cost = _estimate_cost(found, topic)

    result = {
        "topic": topic,
        "assets_dir": str(assets),
        "resources": {k: [str(p) for p in v] for k, v in found.items()},
        "has_any": any(v for v in found.values()),
        "cost_estimate_yuan": cost["total_yuan"],
        "missing_resources": cost["missing"],
        "summary": (
            f"已有: "
            + ("脚本✓ " if cost["has_script"] else "脚本✗ ")
            + ("配音✓ " if cost["has_tts"] else "配音✗ ")
            + (
                f"图片{cost['has_images_count']}张 "
                if cost["has_images_count"]
                else "图片✗ "
            )
            + ("音乐✓ " if cost["has_music"] else "音乐✗ ")
            + f"| 缺失: {', '.join(cost['missing']) if cost['missing'] else '无'} | 估算成本: ¥{cost['total_yuan']}"
        ),
    }

    # LLM 智能建议（如果 API key 可用）
    if args.llm_suggest:
        from .config import MINIMAX_API_KEY

        if MINIMAX_API_KEY:
            existing = {k: v for k, v in found.items() if v}
            if existing:
                try:
                    llm_result = asyncio.run(llm_check_and_suggest(topic, existing))
                    result["llm_suggestion"] = llm_result
                except Exception as e:
                    result["llm_suggestion"] = {"error": str(e)}
        else:
            result["llm_suggestion"] = {"error": "需要 MINIMAX_API_KEY"}

    print_json(result)


async def cmd_script(args):
    """脚本生成，输出含 sentences 字段。"""
    result = await generate_script(args.topic)
    print_json(dict(result))


async def cmd_format(args):
    """格式化口播文本为标准脚本 JSON（内容由 Agent/SKILL.md 生成）。"""
    result = format_script(
        content=args.content,
        title=args.title,
        cta=args.cta,
    )
    print_json(dict(result))


async def cmd_tts(args):
    """TTS 生成，始终返回 word_timestamps。"""
    result = await generate_voice(
        text=args.text,
        voice_id=args.voice,
        provider=args.provider,
    )
    print_json(
        {
            "audio_path": str(result["audio_path"]),
            "srt": str(result["srt_path"]) if result["srt_path"] else None,
            "word_timestamps_count": len(result["word_timestamps"]),
        }
    )


async def cmd_align(args):
    """给定文本 + TTS 音频，独立输出对齐后的 segments JSON。"""
    script_data = None
    hooks_text = None
    sentences = None
    global_visual_context = None
    style_prompt = None
    image_prompts = None

    if args.script:
        try:
            script_data = json.loads(Path(args.script).read_text(encoding="utf-8"))

            if "hooks" in script_data:
                hooks_text = script_data["hooks"]
                logger.info(
                    "✅ 从脚本 %s 读取 %d 个 hooks", args.script, len(hooks_text)
                )

            if "global_visual_context" in script_data:
                global_visual_context = script_data["global_visual_context"]
                logger.info("✅ 从脚本 %s 读取 global_visual_context", args.script)

            if "style_prompt" in script_data:
                style_prompt = script_data["style_prompt"]
                logger.info("✅ 从脚本 %s 读取 style_prompt", args.script)

            if "sentences" in script_data:
                sentences = script_data["sentences"]

            if "image_prompts" in script_data:
                image_prompts = script_data["image_prompts"]
                logger.info(
                    "✅ 从脚本 %s 读取 %d 个 image_prompts（Agent 预构建）",
                    args.script,
                    len(image_prompts),
                )
            else:
                logger.info(
                    "ℹ️ 脚本文件 %s 未包含 image_prompts，将使用默认 prompt 模板",
                    args.script,
                )

        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.warning("⚠️ 脚本文件读取失败: %s，跳过", e)

    if not image_prompts and args.image_prompts:
        try:
            image_prompts = json.loads(args.image_prompts)
            logger.warning("⚠️ 使用已废弃的 --image-prompts 参数，建议使用 --script")
        except json.JSONDecodeError as e:
            logger.warning("⚠️ image_prompts JSON 解析失败: %s，跳过", e)

    full_text = args.text
    hooks_count = 0

    if hooks_text and script_data:
        # 鲁棒性匹配：忽略标点和空白符来检查正文是否已包含 hook
        def clean_str(s):
            import re

            return re.sub(r"[^\w\u4e00-\u9fa5]", "", s).strip()

        clean_body_head = clean_str(args.text[: len(hooks_text[0]) + 10])
        clean_hook_head = clean_str(hooks_text[0])

        if clean_body_head.startswith(clean_hook_head):
            hooks_count = len(hooks_text)
            logger.info(
                "✅ hooks 文本已在正文中 (忽略标点匹配)，hooks 数量=%d", hooks_count
            )
        else:
            hooks_joined = SCRIPT_SEPARATOR.join(hooks_text)
            full_text = f"{hooks_joined}{SCRIPT_SEPARATOR}{args.text}"
            hooks_count = len(hooks_text)
            # 同步更新 sentences 列表
            if sentences:
                sentences = hooks_text + sentences
            logger.info("✅ hooks 文本拼接到正文前面，hooks 数量=%d", hooks_count)

    result = await generate_voice(
        text=full_text,
        provider="edge",
        voice_id=args.voice,
    )

    audio_duration = get_media_duration(result["audio_path"])
    segments = align_segments(
        full_text,
        result["word_timestamps"],
        audio_duration=audio_duration,
        sentences=sentences,
        image_prompts=image_prompts,
    )
    if args.split_long:
        segments = split_long_segments(segments)

    # 导出最终对齐好的 SRT（基于修正后的时间轴）
    srt_content = segments_to_srt(segments)
    srt_path = Path(result["audio_path"]).with_suffix(".srt")
    srt_path.write_text(srt_content, encoding="utf-8")
    logger.info("✅ 最终对齐 SRT 已导出: %s", srt_path)

    output = {
        "text": full_text,
        "global_visual_context": global_visual_context,
        "style_prompt": style_prompt,
        "audio_path": str(result["audio_path"]),
        "srt": str(result["srt_path"]) if result["srt_path"] else None,
        "segments": [
            {
                "index": s["index"],
                "text": s["text"],
                "start_sec": round(s["start_sec"], 3),
                "end_sec": round(s["end_sec"], 3),
                "duration_sec": round(s["duration_sec"], 3),
                "image_prompt": s["image_prompt"],
                "is_hook": s.get("is_hook", False),
            }
            for s in segments
        ],
    }

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print_json({"written": str(out_path), "segments_count": len(segments)})
    else:
        print_json(output)


async def cmd_assets(args):
    """图片生成（由 segments 驱动）。"""
    segments_path = Path(args.segments)
    data = json.loads(segments_path.read_text(encoding="utf-8"))
    segments = data.get("segments") or data
    if not segments:
        raise ValueError("segments JSON 为空")

    # 1. 生成图片
    image_paths, image_urls = await generate_segment_images(
        segments,
        global_context=data.get("global_visual_context"),
        style_prompt=data.get("style_prompt"),
        max_concurrent=args.max_concurrent,
    )

    # 2. 如果开启了 --video，自动生成视频头
    video_info = None
    if getattr(args, "video", False):
        logger.info("🎬 检测到 --video 开启，开始生成片头视频...")
        video_info = await generate_hook_video(
            segments,
            global_context=data.get("global_visual_context"),
            style_prompt=data.get("style_prompt"),
        )

    print_json(
        {
            "images": [str(p) if p else None for p in image_paths],
            "video": video_info,
            "segments_count": len(segments),
        }
    )


async def generate_hook_video(
    segments: List[Dict],
    global_context: Optional[str] = None,
    style_prompt: Optional[str] = None,
) -> Optional[Dict]:
    """为 segments 中的 hook 片段生成视频（目前仅支持第一个片段）。"""
    hook_seg = None
    for seg in segments:
        if seg.get("is_hook"):
            hook_seg = seg
            break

    if not hook_seg:
        logger.warning("⚠️ 未发现标记为 is_hook 的片段，跳过视频生成")
        return None

    # 优先使用 OSS URL 作为 I2V 输入（MiniMax API 要求）
    input_image = hook_seg.get("image_url")
    if not input_image:
        # 降级：寻找本地图
        img_dir = Path("assets/images")
        first_frame = img_dir / f"seg_{hook_seg['index']:03d}_0.jpg"
        input_image = str(first_frame) if first_frame.exists() else None
        if input_image:
            logger.warning(
                "⚠️ 缺失 OSS URL，降级使用本地路径（可能导致 API 错误）: %s", input_image
            )

    final_prompt = hook_seg["image_prompt"]
    if global_context or style_prompt:
        parts = []
        if global_context:
            parts.append(global_context)
        if style_prompt:
            parts.append(style_prompt)
        parts.append("[Sequence: Hook/Intro]")
        parts.append(hook_seg["image_prompt"])
        final_prompt = ", ".join(p for p in parts if p)

    try:
        video_path = await generate_video(
            prompt=final_prompt,
            duration=6,
            input_image=input_image,
            output_filename="video_head.mp4",
        )
        return {"path": str(video_path)}
    except Exception as e:
        logger.error("❌ 片头视频生成失败: %s", e)
        return {"error": str(e)}


async def cmd_video(args):
    """独立视频生成命令。"""
    segments_path = Path(args.segments)
    data = json.loads(segments_path.read_text(encoding="utf-8"))
    segments = data.get("segments") or data

    result = await generate_hook_video(segments)
    print_json(result)


async def cmd_compose(args):
    """视频合成（compose_sequential）。"""
    data = json.loads(Path(args.segments).read_text(encoding="utf-8"))
    segments = data.get("segments") or data

    video_path = await compose_sequential(
        tts_path=Path(args.tts).resolve(),
        segments=segments,
        music_path=Path(args.music).resolve(),
        output_path=Path(args.output).resolve() if args.output else None,
        transition=args.transition,
        hook_video_path=Path(args.hook_video).resolve() if args.hook_video else None,
    )
    print_json({"path": str(video_path)})


async def cmd_post(args):
    """后期处理。"""
    srt_path = Path(args.srt) if getattr(args, "srt", None) else None
    segments_path = Path(args.segments) if getattr(args, "segments", None) else None
    path = await post_process(
        Path(args.video),
        args.title,
        add_subtitles=not args.no_subtitles,
        output_path=Path(args.output) if getattr(args, "output", None) else None,
        srt_path=srt_path,
        segments_path=segments_path,
        subtitle_model=getattr(args, "subtitle_model", "medium"),
        subtitle_language=getattr(args, "subtitle_language", "auto"),
        font_size=getattr(args, "font_size", 16),
    )
    print_json({"path": str(path)})


async def cmd_burn_subs(args):
    """Whisper 字幕提取 + FFmpeg 烧录。"""
    video_path = Path(args.video)

    srt_path = extract_subtitles(
        video_path,
        output_srt=Path(args.srt) if args.srt else None,
        model=args.model,
        language=args.language,
        word_timestamps=args.word_timestamps,
    )
    if not srt_path:
        raise RuntimeError("Whisper 字幕提取失败")

    await post_process(
        video_path,
        title=video_path.stem,
        add_subtitles=True,
        add_aigc=False,
        output_path=Path(args.output).resolve() if args.output else None,
        srt_path=srt_path,
        subtitle_model=args.model,
        subtitle_language=args.language,
    )
    print_json({"success": True, "srt": str(srt_path)})


async def cmd_publish(args):
    """多平台发布。"""
    results = await publish(
        Path(args.video),
        title=args.title,
        platforms=args.platforms,
    )
    print_json({"results": results})


async def cmd_music(args):
    """背景音乐生成。"""
    output_filename = (
        args.output.name if args.output else f"bg_music_{args.topic or 'default'}.mp3"
    )
    path = await generate_music(
        prompt=args.prompt,
        duration=args.duration,
        is_instrumental=args.instrumental,
        output_filename=output_filename,
    )
    print_json({"path": str(path), "duration_sec": args.duration})


# ─────────────────────────────────────────────────────────────────────────────
# argparse 定义
# ─────────────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="ClawReel — AI 短视频语义对齐流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 完整流程
  clawreel check --topic "AI觉醒"
  clawreel script --topic "AI觉醒"
  clawreel align --text "脚本内容" --script assets/script_xxx.json --output assets/segments_xxx.json
  clawreel assets --segments assets/segments_xxx.json
  clawreel compose --tts assets/tts_xxx.mp3 --segments assets/segments_xxx.json --music assets/bg_music.mp3
  clawreel post --video output/composed.mp4 --title "AI觉醒"
  clawreel publish --video output/final.mp4 --title "AI觉醒" --platforms douyin xiaohongshu

  # 辅助命令
  clawreel music --prompt "轻快背景音乐" --duration 60
  clawreel burn-subs --video output/composed.mp4 --model medium
        """,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ─────────────────────────────────────────────────────────────────────────────
    # 主流程命令（对应 SOP 7 阶段）
    # ─────────────────────────────────────────────────────────────────────────────

    # Phase 0: check
    p = subparsers.add_parser("check", help="[Phase 0] 扫描已有资源 + 成本估算")
    p.add_argument("--topic", "-t", help="视频主题（用于过滤文件名）")
    p.add_argument("--assets-dir", default="assets", help="资源目录（默认 assets）")
    p.add_argument("--llm-suggest", action="store_true", help="启用 LLM 智能复用建议")

    # Phase 1: script (deprecated) / format
    p = subparsers.add_parser(
        "script", help="[Phase 1] 生成口播脚本（已弃用，请使用 format）"
    )
    p.add_argument("--topic", "-t", required=True, help="视频主题")

    p = subparsers.add_parser("format", help="[Phase 1] 格式化口播内容为标准 JSON")
    p.add_argument(
        "--content", "-c", required=True, help="完整口播内容（用 | 或换行分隔句子）"
    )
    p.add_argument("--title", default=None, help="视频标题（默认自动提取）")
    p.add_argument("--cta", default=None, help="结尾 CTA（默认自动生成）")

    # Phase 2: align
    p = subparsers.add_parser("align", help="[Phase 2] TTS + 语义对齐 → segments JSON")
    p.add_argument("--text", required=True, help="配音文本")
    p.add_argument("--voice", default="zh-CN-XiaoxiaoNeural", help="音色 ID")
    p.add_argument("--split-long", action="store_true", help="自动拆分 >5s 长段")
    p.add_argument("--output", "-o", default=None, help="输出路径")
    p.add_argument(
        "--script",
        default=None,
        help="脚本 JSON 文件路径（自动读取其中的 image_prompts 字段）",
    )
    p.add_argument(
        "--image-prompts",
        default=None,
        help="LLM 预生成的配图提示词 JSON 数组（与 sentences 对应，已被 --script 取代）",
    )

    # Phase 3: assets
    p = subparsers.add_parser("assets", help="[Phase 3] 图片生成")
    p.add_argument(
        "--segments", "-s", required=True, metavar="PATH", help="segments JSON 文件"
    )
    p.add_argument("--max-concurrent", type=int, default=3)
    p.add_argument(
        "--video", action="store_true", help="一并生成 6 秒片头视频 (I2V/T2V)"
    )

    # Phase 3.5: video (Explicit hook video generation)
    p = subparsers.add_parser(
        "video", help="[Phase 3.5] 生成 6 秒片头视频 (I2V/T2V 优先)"
    )
    p.add_argument(
        "--segments", "-s", required=True, metavar="PATH", help="segments JSON 文件"
    )

    # Phase 4: compose
    p = subparsers.add_parser("compose", help="[Phase 4] 视频合成（FFmpeg 转场）")
    p.add_argument("--tts", required=True, metavar="PATH")
    p.add_argument("--segments", "-s", required=True, metavar="PATH")
    p.add_argument("--music", required=True, metavar="PATH")
    p.add_argument("--output", "-o", default=None, metavar="PATH")
    p.add_argument(
        "--transition",
        default="fade",
        choices=["fade", "slide_left", "slide_right", "zoom", "none"],
        help="图片转场效果",
    )
    p.add_argument(
        "--hook-video",
        default=None,
        help="外部片头视频路径（如：video_head.mp4），将覆盖第一段素材",
    )

    # Phase 5: post
    p = subparsers.add_parser("post", help="[Phase 5] 后期处理（字幕 + AIGC）")
    p.add_argument("--video", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--srt", default=None)
    p.add_argument("--no-subtitles", action="store_true")
    p.add_argument(
        "--subtitle-model",
        default="medium",
        choices=["tiny", "base", "small", "medium", "large"],
    )
    p.add_argument("--subtitle-language", default="auto")
    p.add_argument(
        "--segments", default=None, help="segments JSON 路径（用于读取 TTS 生成的字幕）"
    )
    p.add_argument("--font-size", type=int, default=16, help="字幕字号大小")
    p.add_argument("--output", "-o", default=None, help="输出文件路径")

    # Phase 6: publish
    p = subparsers.add_parser("publish", help="[Phase 6] 多平台发布")
    p.add_argument("--video", required=True)
    p.add_argument("--title", required=True)
    p.add_argument(
        "--platforms",
        nargs="+",
        default=["xiaohongshu", "douyin"],
        choices=["xiaohongshu", "douyin", "bilibili"],
    )

    # ─────────────────────────────────────────────────────────────────────────────
    # 辅助/调试命令
    # ─────────────────────────────────────────────────────────────────────────────

    # tts - 独立 TTS 测试
    p = subparsers.add_parser("tts", help="[辅助] 独立 TTS 测试（非流程命令）")
    p.add_argument("--text", required=True, help="配音文本")
    p.add_argument("--voice", default=None, help="音色 ID")
    p.add_argument("--provider", default="edge", choices=["edge", "minimax"])

    # music - 背景音乐生成
    p = subparsers.add_parser("music", help="[辅助] 背景音乐生成")
    p.add_argument(
        "--prompt", default="轻快的背景音乐，适合短视频", help="音乐风格描述"
    )
    p.add_argument("--duration", type=int, default=60, help="时长（秒），默认60")
    p.add_argument(
        "--instrumental", action="store_true", default=True, help="纯器乐（默认开）"
    )
    p.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="输出路径（默认 assets/bg_music_<topic>.mp3）",
    )
    p.add_argument("--topic", default=None, help="视频主题（用于默认文件名）")

    # burn-subs - 字幕提取 + 烧录
    p = subparsers.add_parser("burn-subs", help="[辅助] Whisper 字幕提取 + FFmpeg 烧录")
    p.add_argument("--video", "-v", required=True)
    p.add_argument("--output", "-o", default=None)
    p.add_argument("--srt", default=None)
    p.add_argument(
        "--model",
        default="medium",
        choices=["tiny", "base", "small", "medium", "large"],
    )
    p.add_argument("--language", default="auto")
    p.add_argument("--word-timestamps", action="store_true")

    args = parser.parse_args()

    async def run():
        try:
            if args.command == "check":
                cmd_check(args)
            elif args.command == "script":
                await cmd_script(args)
            elif args.command == "format":
                await cmd_format(args)
            elif args.command == "tts":
                await cmd_tts(args)
            elif args.command == "align":
                await cmd_align(args)
            elif args.command == "assets":
                await cmd_assets(args)
            elif args.command == "video":
                await cmd_video(args)
            elif args.command == "compose":
                await cmd_compose(args)
            elif args.command == "post":
                await cmd_post(args)
            elif args.command == "burn-subs":
                await cmd_burn_subs(args)
            elif args.command == "publish":
                await cmd_publish(args)
            elif args.command == "music":
                await cmd_music(args)
        except Exception as e:
            logger.exception("命令执行失败: %s", args.command)
            print_json({"success": False, "error": str(e)})
            sys.exit(1)
        finally:
            try:
                from .api_client import close_session

                await close_session()
            except ImportError:
                pass

    asyncio.run(run())


if __name__ == "__main__":
    main()
