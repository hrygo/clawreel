"""阶段5：发布 - 发布到小红书/抖音.

平台 SDK 集成待接入。当前返回成功/失败结果的结构化占位。
"""
import logging
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)


class PublishResult(TypedDict):
    """发布结果."""
    platform: str
    success: bool
    url: str | None
    error: str | None


async def publish_to_xiaohongshu(
    video_path: Path,
    title: str,
    description: str,
    cookies: str = "",
) -> PublishResult:
    """发布到小红书.

    Args:
        video_path: 视频文件路径
        title: 标题
        description: 描述
        cookies: 小红书登录 cookies

    Returns:
        PublishResult
    """
    logger.warning("小红书发布功能待接入（需平台 SDK）")
    return PublishResult(
        platform="xiaohongshu",
        success=False,
        url=None,
        error="小红书发布功能待接入，需平台 SDK",
    )


async def publish_to_douyin(
    video_path: Path,
    title: str,
    description: str,
    cookies: str = "",
) -> PublishResult:
    """发布到抖音.

    Args:
        video_path: 视频文件路径
        title: 标题
        description: 描述
        cookies: 抖音登录 cookies

    Returns:
        PublishResult
    """
    logger.warning("抖音发布功能待接入（需平台 SDK）")
    return PublishResult(
        platform="douyin",
        success=False,
        url=None,
        error="抖音发布功能待接入，需平台 SDK",
    )


async def publish(
    video_path: Path,
    title: str,
    platforms: list[str] | None = None,
    cookies: dict[str, str] | None = None,
) -> list[PublishResult]:
    """发布到多个平台.

    Args:
        video_path: 视频文件路径
        title: 标题
        platforms: 目标平台列表，默认 ["xiaohongshu", "douyin"]
        cookies: 各平台 cookies，格式 {"xiaohongshu": "...", "douyin": "..."}

    Returns:
        各平台发布结果列表
    """
    if platforms is None:
        platforms = ["xiaohongshu", "douyin"]
    if cookies is None:
        cookies = {}

    logger.info("📤 开始发布到平台: %s", platforms)

    results: list[PublishResult] = []
    description = f"{title}\n\n内容由AI生成"

    for platform in platforms:
        if platform == "xiaohongshu":
            result = await publish_to_xiaohongshu(
                video_path=video_path,
                title=title,
                description=description,
                cookies=cookies.get("xiaohongshu", ""),
            )
        elif platform == "douyin":
            result = await publish_to_douyin(
                video_path=video_path,
                title=title,
                description=description,
                cookies=cookies.get("douyin", ""),
            )
        else:
            result = PublishResult(
                platform=platform,
                success=False,
                url=None,
                error=f"未知平台: {platform}",
            )
        results.append(result)

    return results
