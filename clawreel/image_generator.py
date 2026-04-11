"""Phase 5: 素材生成 — 视觉创意落地。

集成 MiniMax Image-01 (Vision) 生成风格连贯的 9:16 图片。
"""
import logging
import asyncio
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any

from .api_client import api_post, download_file
from .config import ASSETS_DIR, MODEL_IMAGE

logger = logging.getLogger(__name__)

_IMAGES_DIR = ASSETS_DIR / "images"


async def generate_images(
    prompt: str,
    output_filename: Optional[str] = None,
    count: int = 1,
) -> Tuple[List[Path], List[str]]:
    """生成图片，同时返回本地路径和 OSS URL（供后续视频生成或 HITL 展示用）。

    Returns:
        (本地路径列表, OSS URL列表) 元组
    """
    if output_filename is None:
        output_filename = f"image_{int(time.time() * 1000)}"

    _IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("🖼️ 正在生成 %d 张图片，prompt: %s", count, prompt[:100])

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

    # 下载图片
    paths = []
    for i, url in enumerate(image_urls):
        path = _IMAGES_DIR / f"{output_filename}_{i}.jpg"
        await download_file(url, path)
        paths.append(path)

    return paths, image_urls


async def generate_segment_images(
    segments: List[Dict],
    global_context: Optional[str] = None,
    style_prompt: Optional[str] = None,
    max_concurrent: int = 3,
) -> Tuple[List[Path], List[Optional[str]]]:
    """为语义段落列表批量生成图片。

    每段一张图，并发控制。
    返回 (图片路径列表, OSS_URL列表)，并更新 segments 中的 image_url。
    """
    logger.info("🖼️ 正在批量生成 %d 张图片，并发上限=%d", len(segments), max_concurrent)

    sem = asyncio.Semaphore(max_concurrent)

    async def _task(idx: int, seg: Dict) -> Tuple[int, Optional[Path], Optional[str]]:
        async with sem:
            prompt = seg["image_prompt"]
            # 构造分层提示词
            parts = []
            if global_context: parts.append(global_context)
            if style_prompt: parts.append(style_prompt)
            # 注入时序信息
            parts.append(f"[Sequence: Frame {idx+1} of {len(segments)}]")
            # 内容具体描述
            parts.append(prompt)
            
            combined = ", ".join(p.strip() for p in parts if p and p.strip())
            filename = f"seg_{seg.get('index', idx):03d}"
            
            try:
                paths, urls = await generate_images(combined, output_filename=filename, count=1)
                return idx, paths[0], urls[0]
            except Exception as e:
                logger.error("❌ 段落 %d 生成失败: %s", idx, e)
                return idx, None, None

    tasks = [_task(i, s) for i, s in enumerate(segments)]
    results = await asyncio.gather(*tasks)
    
    # 排序确保顺序一致
    results.sort(key=lambda x: x[0])
    
    paths = [r[1] for r in results]
    urls = [r[2] for r in results]
    
    # 将 URL 回填到 segments 供视频生成使用
    for i, seg in enumerate(segments):
        if urls[i]:
            seg["image_url"] = urls[i]

    return paths, urls
