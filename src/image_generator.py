"""阶段2b：图片生成 — 使用统一 api_client。

模型: image-01，9:16 竖屏。
官方文档: POST /v1/image_generation
"""
import hashlib
import logging
import time
from pathlib import Path

from .api_client import api_post, download_file, get_session
from .config import ASSETS_DIR, MODEL_IMAGE

logger = logging.getLogger(__name__)

_IMAGES_DIR = ASSETS_DIR / "images"


async def generate_image(
    prompt: str,
    output_filename: str | None = None,
    count: int = 1,
) -> list[Path]:
    """生成图片列表。

    Args:
        prompt: 图片描述
        output_filename: 输出文件名（不含扩展名）
        count: 生成数量，1-9

    Returns:
        图片路径列表
    """
    if output_filename is None:
        output_filename = f"image_{int(time.time() * 1000)}"

    _IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("🖼️ 正在生成 %d 张图片，prompt: %s", count, prompt[:50])

    # 官方字段: model, prompt, n, aspect_ratio
    result = await api_post(
        endpoint="/image_generation",
        payload={
            "model": MODEL_IMAGE,
            "prompt": prompt,
            "aspect_ratio": "9:16",
            "n": count,
        },
    )

    # 官方返回: data.image_urls（数组）
    image_urls = result.get("data", {}).get("image_urls", [])
    if not image_urls:
        raise RuntimeError(f"Image API 返回无图片: {result}")

    # 并行下载所有图片
    import asyncio
    _IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    async def _download_single(i: int, img_url: str) -> Path | None:
        """下载单张图片。"""
        ext = "png"
        fname = f"{output_filename}_{i}.{ext}"
        out_path = _IMAGES_DIR / fname
        try:
            await download_file(img_url, out_path)
            logger.info("✅ 图片已保存: %s", out_path)
            return out_path
        except Exception as e:
            logger.warning("图片下载失败: %s — %s", img_url, e)
            return None

    tasks = [_download_single(i, url) for i, url in enumerate(image_urls)]
    results = await asyncio.gather(*tasks)
    paths = [p for p in results if p is not None]

    if len(paths) == 0:
        raise RuntimeError("所有图片下载失败，请检查网络或图片 URL 是否可访问")

    return paths


async def generate_cover(
    title: str,
    count: int = 3,
) -> list[Path]:
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
