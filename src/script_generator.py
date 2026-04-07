"""阶段0：脚本生成 - 使用 MiniMax M2.7 生成口播脚本.

M2.7 通过 Anthropic 兼容接口调用，端点：/anthropic/v1/messages
无需 GroupId，使用标准 Bearer Token 认证。
"""
import json
import logging
from typing import TypedDict

from .api_client import get_session
from .config import MINIMAX_API_KEY

logger = logging.getLogger(__name__)

# Anthropic 兼容接口端点
_ANTHROPIC_BASE_URL = "https://api.minimaxi.com/anthropic"


class ScriptData(TypedDict):
    """生成的脚本数据结构."""
    title: str
    script: str        # 60秒口播脚本（约150字）
    hooks: list[str]   # 钩子列表
    cta: str           # 结尾号召


SYSTEM_PROMPT = """你是一位抖音内容创作专家。请根据用户给定的主题，生成适合抖音口播的短视频脚本。

输出格式（JSON，必须严格遵循）：
{
  "title": "视频标题（吸引眼球，20字以内）",
  "script": "60秒口播脚本正文（约150字，语速适中，自然流畅）",
  "hooks": ["钩子1：开头3秒抓人眼球", "钩子2：设置悬念或痛点"],
  "cta": "结尾号召行动（如：关注我，带你xxx）"
}

注意：
- hooks 是开头用的高能片段，要有冲击力
- script 要口语化，像真实说话
- 不要使用 emoji"""


async def _call_m2n7(topic: str) -> str:
    """调用 MiniMax M2.7 API（Anthropic 兼容接口）."""
    url = f"{_ANTHROPIC_BASE_URL}/v1/messages"
    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
        "anthropic-dangerous-direct-browser-access": "true",
    }
    payload = {
        "model": "MiniMax-M2.7",
        "max_tokens": 1024,
        "temperature": 0.7,
        "system": SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": topic}]}
        ],
    }

    async with get_session() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"M2.7 API 错误 {resp.status}: {text}")
            result = await resp.json()

    # Anthropic API 返回格式：result.content[0].text
    content = result.get("content", [])
    if content and isinstance(content, list):
        for block in content:
            if block.get("type") == "text":
                return block["text"]
    raise RuntimeError(f"M2.7 Anthropic API 返回无 text: {result}")


async def _parse_script(topic: str) -> ScriptData:
    """调用 API 并解析 JSON 脚本."""
    raw = await _call_m2n7(topic)
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])
    data = json.loads(text)
    for field in ("title", "script", "hooks", "cta"):
        if field not in data:
            raise ValueError(f"脚本缺少字段: {field}")
    return ScriptData(
        title=str(data["title"]),
        script=str(data["script"]),
        hooks=list(data["hooks"]),
        cta=str(data["cta"]),
    )


async def generate_script(topic: str) -> ScriptData:
    """生成口播脚本.

    Args:
        topic: 视频主题

    Returns:
        ScriptData，包含 title、script、hooks、cta
    """
    logger.info("📝 正在生成脚本，主题: %s", topic)
    result = await _parse_script(topic)
    logger.info("✅ 脚本生成完成: %s", result["title"])
    return result
