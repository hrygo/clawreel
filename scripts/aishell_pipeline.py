#!/usr/bin/env python3
"""Antigravity 专用：非交互式内容创作流水线封装。
为 AI 智能体编排 HITL 流程提供 CLI 接口。
"""
import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

# 确保能导入 src
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.script_generator import generate_script
from src.tts_voice import generate_voice
from src.video_generator import generate_video
from src.image_generator import generate_image
from src.music_generator import generate_music
from src.composer import compose
from src.post_processor import post_process
from src.publisher import publish

# 禁用基础日志输出到 stdout，以免干扰 JSON 解析
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("aishell_pipeline")


def print_json(data: Any):
    """将结果以 JSON 格式输出到 stdout。"""
    print(json.dumps(data, ensure_ascii=False, indent=2))


async def cmd_script(args):
    """阶段 0：脚本生成。"""
    result = await generate_script(args.topic)
    print_json(result)


async def cmd_tts(args):
    """阶段 1：配音生成。"""
    path = await generate_voice(
        args.text,
        voice_id=args.voice,
        provider=args.provider
    )
    print_json({"path": str(path)})


async def cmd_assets(args):
    """阶段 2：素材生成（并行）。"""
    tasks = []
    # 视频 Hook
    tasks.append(generate_video(args.hook_prompt, type="t2v", duration=6))
    # 正文图片
    tasks.append(generate_image(args.image_prompt, count=args.count))
    # 背景音乐
    tasks.append(generate_music(prompt=args.music_prompt, duration=60))
    
    video, images, music = await asyncio.gather(*tasks)
    print_json({
        "video": str(video),
        "images": [str(p) for p in images],
        "music": str(music)
    })


async def cmd_compose(args):
    """阶段 3：音视频合成。"""
    path = await compose(
        tts_path=Path(args.tts),
        image_paths=[Path(p) for p in args.images],
        music_path=Path(args.music),
        hook_video_path=Path(args.hook) if args.hook else None
    )
    print_json({"path": str(path)})


async def cmd_post(args):
    """阶段 4：后期处理。"""
    path = await post_process(Path(args.video), args.title)
    print_json({"path": str(path)})


async def cmd_publish(args):
    """阶段 5：发布。"""
    results = await publish(
        Path(args.video),
        title=args.title,
        platforms=args.platforms
    )
    print_json({"results": results})


def main():
    parser = argparse.ArgumentParser(description="Antigravity Content Pipeline CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # script
    p_script = subparsers.add_parser("script")
    p_script.add_argument("--topic", "-t", required=True)

    # tts
    p_tts = subparsers.add_parser("tts")
    p_tts.add_argument("--text", required=True)
    p_tts.add_argument("--voice", default=None)
    p_tts.add_argument("--provider", default=None)

    # assets
    p_assets = subparsers.add_parser("assets")
    p_assets.add_argument("--hook-prompt", required=True)
    p_assets.add_argument("--image-prompt", required=True)
    p_assets.add_argument("--count", type=int, default=3)
    p_assets.add_argument("--music-prompt", default="轻快、节奏感强、适合短视频的背景音乐")

    # compose
    p_compose = subparsers.add_parser("compose")
    p_compose.add_argument("--tts", required=True)
    p_compose.add_argument("--images", nargs="+", required=True)
    p_compose.add_argument("--music", required=True)
    p_compose.add_argument("--hook", default=None)

    # post
    p_post = subparsers.add_parser("post")
    p_post.add_argument("--video", required=True)
    p_post.add_argument("--title", required=True)

    # publish
    p_publish = subparsers.add_parser("publish")
    p_publish.add_argument("--video", required=True)
    p_publish.add_argument("--title", required=True)
    p_publish.add_argument("--platforms", nargs="+", default=["xiaohongshu", "douyin"])

    args = parser.parse_args()

    async def run():
        try:
            if args.command == "script":
                await cmd_script(args)
            elif args.command == "tts":
                await cmd_tts(args)
            elif args.command == "assets":
                await cmd_assets(args)
            elif args.command == "compose":
                await cmd_compose(args)
            elif args.command == "post":
                await cmd_post(args)
            elif args.command == "publish":
                await cmd_publish(args)
        except Exception as e:
            logger.exception("命令执行失败: %s", args.command)
            print_json({"success": False, "error": str(e)})
            sys.exit(1)
        finally:
            # 确保关闭 aiohttp session
            try:
                from src.api_client import close_session
                await close_session()
            except ImportError:
                pass

    asyncio.run(run())


if __name__ == "__main__":
    main()
