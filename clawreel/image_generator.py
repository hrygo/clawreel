"""阶段2b：图片生成 — 使用统一 api_client。

模型: image-01，9:16 竖屏。
官方文档: POST /v1/image_generation
"""
import asyncio
import hashlib
import logging
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Union

from .api_client import api_post, download_file
from .config import ASSETS_DIR, MODEL_IMAGE

logger = logging.getLogger(__name__)

_IMAGES_DIR = ASSETS_DIR / "images"


async def _download_single(output_filename: str, i: int, img_url: str) -> Optional[Path]:
    """下载单张图片，返回本地路径或 None。"""
    ext = "png" if ".png" in img_url.lower() else "jpg"
    fname = f"{output_filename}_{i}.{ext}"
    out_path = _IMAGES_DIR / fname
    try:
        await download_file(img_url, out_path)
        logger.info("✅ 图片已保存: %s", out_path)
        return out_path
    except Exception as e:
        logger.warning("图片下载失败: %s — %s", img_url, e)
        return None


async def generate_image(
    prompt: str,
    output_filename: Optional[str] = None,
    count: int = 1,
) -> List[Path]:
    """生成图片列表。

    Returns:
        本地图片路径列表（供合成使用）
    """
    paths, _ = await generate_image_with_urls(prompt, output_filename, count)
    return paths


async def generate_image_with_urls(
    prompt: str,
    output_filename: Optional[str] = None,
    count: int = 1,
) -> Tuple[List[Path], List[str]]:
    """生成图片，同时返回本地路径和 OSS URL（供 HITL 展示用）。

    Returns:
        (本地路径列表, OSS URL列表) 元组
    """
    if output_filename is None:
        output_filename = f"image_{int(time.time() * 1000)}"

    _IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("🖼️ 正在生成 %d 张图片，prompt: %s", count, prompt[:50])

    result = await api_post(
        endpoint="/image_generation",
        payload={
            "model": MODEL_IMAGE,
            "prompt": prompt,
            "aspect_ratio": "9:16",
            "n": count,
        },
    )

    image_urls = result.get("data", {}).get("image_urls", [])
    if not image_urls:
        raise RuntimeError(f"Image API 返回无图片: {result}")

    tasks = [_download_single(output_filename, i, url) for i, url in enumerate(image_urls)]
    results = await asyncio.gather(*tasks)
    paths = [p for p in results if p is not None]

    if len(paths) == 0:
        raise RuntimeError("所有图片下载失败，请检查网络或图片 URL 是否可访问")

    return paths, image_urls


async def generate_segment_images(
    segments: List[Dict],
    max_concurrent: int = 3,
) -> List[Path]:
    """为语义段落列表批量生成图片。

    每段一张图，并发控制避免 API 限流。
    返回图片路径列表，与 segments 一一对应。

    Args:
        segments:       ScriptSegment 列表（需含 image_prompt 字段）
        max_concurrent: 最大并发数，默认 3

    Returns:
        本地图片路径列表（与 segments 顺序对应）
        若某段生成失败，该位置为 None，最终抛出 ValueError

    Raises:
        ValueError: 有效图片少于 2 张，或任意段缺失 image_prompt
    """
    if not segments:
        raise ValueError("segments 不能为空")
    if any("image_prompt" not in seg or not seg["image_prompt"] for seg in segments):
        raise ValueError("每段必须包含 non-empty image_prompt 字段")

    _IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("🖼️ 正在批量生成 %d 张图片，并发上限=%d", len(segments), max_concurrent)

    semaphore = asyncio.Semaphore(max_concurrent)

    async def generate_one(i: int, seg: Dict) -> Tuple[int, Optional[Path]]:
        async with semaphore:
            try:
                paths = await generate_image(
                    prompt=seg["image_prompt"],
                    output_filename=f"seg_{i:03d}",
                    count=1,
                )
                return i, paths[0] if paths else None
            except Exception as e:
                logger.warning("⚠️ 图片 %d 生成失败: %s", i, e)
                return i, None

    tasks = [generate_one(i, seg) for i, seg in enumerate(segments)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 按 index 排序还原顺序，同时计数有效结果
    ordered: List[Optional[Path]] = [None] * len(segments)
    valid_count = 0
    for r in results:
        if isinstance(r, Exception):
            continue
        i, path = r
        ordered[i] = path
        valid_count += 1

    if valid_count < 2:
        raise ValueError(f"有效图片不足 2 张（{valid_count} 张），无法合成视频")

    return ordered


async def generate_cover(
    title: str,
    count: int = 3,
) -> List[Path]:
    """生成封面图（关键内容必须放在下半部分）。"""
    safe_title = hashlib.md5(title.encode()).hexdigest()[:8]
    return await generate_image(
        prompt=(
            f"抖音短视频封面，标题风格：{title}。"
            "画面下半部分展示核心内容，人物/产品居中偏下。"
            "文字清晰醒目，背景简洁有冲击力。竖屏9:16。"
        ),
        output_filename=f"cover_{safe_title}",
        count=count,
    )
