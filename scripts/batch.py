#!/usr/bin/env python3
"""批量生成脚本.

用法:
    python batch.py --topics "主题1" "主题2" "主题3"

会并行处理多个主题的流水线任务。
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.generate import main as generate_for_topic

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def run_batch(topics: Sequence[str]) -> list[Path]:
    """批量执行流水线任务（串行，逐个完成以便复用素材）."""
    results: list[Path] = []
    for i, topic in enumerate(topics, 1):
        logger.info("========== [%d/%d] 主题: %s ==========", i, len(topics), topic)
        try:
            output = await generate_for_topic(topic)
            results.append(output)
            logger.info("✅ [%d/%d] 完成: %s", i, len(topics), topic)
        except Exception as e:
            logger.error("❌ [%d/%d] 失败: %s - %s", i, len(topics), topic, e)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="批量生成脚本")
    parser.add_argument(
        "--topics", "-t",
        nargs="+",
        required=True,
        help="视频主题列表",
    )
    parser.add_argument(
        "--parallel", "-p",
        action="store_true",
        default=True,
        help="并行执行（默认开启，并行消耗更多 API 配额）",
    )
    parser.add_argument(
        "--serial", "-s",
        action="store_true",
        help="串行执行（逐个完成）",
    )
    args = parser.parse_args()

    if args.serial:
        # 串行模式
        asyncio.run(run_batch(args.topics))
    else:
        # 并行模式（默认）
        tasks = [generate_for_topic(t) for t in args.topics]
        results = asyncio.run(asyncio.gather(*tasks, return_exceptions=True))
        for topic, result in zip(args.topics, results):
            if isinstance(result, Exception):
                logger.error("❌ 失败 [%s]: %s", topic, result)
            else:
                logger.info("✅ 完成 [%s]: %s", topic, result)
