"""阶段1：脚本生成 — 使用 MiniMax M2.7 生成口播脚本。

单一职责：仅生成口播文本脚本（title、script、sentences、hooks、cta）。
配图 prompt 的构建由 Agent（SKILL.md）在编排阶段完成，不在此处生成。

M2.7 通过 Anthropic 兼容接口调用，端点：/anthropic/v1/messages
script 字段使用 | 分隔多句，供语义对齐流水线使用。
"""
import json
import logging
from typing import List, TypedDict

from .api_client import call_anthropic_api

logger = logging.getLogger(__name__)


class ScriptData(TypedDict):
    """生成的脚本数据结构（纯文案，不含视觉 prompt）。"""
    title: str
    script: str             # 用 | 分隔的多句文本
    sentences: List[str]    # 解析后的句子列表（不含 |）
    hooks: List[str]        # 钩子列表（开头吸引力句）
    cta: str                # 结尾号召


SYSTEM_PROMPT = """你是一位抖音内容创作专家。请根据用户给定的主题，生成适合抖音口播的短视频脚本。

**仅输出口播文本，不生成任何图片/视觉描述。**

输出格式（JSON，必须严格遵循）：
{
  "title": "视频标题（吸引眼球，20字以内）",
  "script": "口播脚本正文，用 | 分隔多句。每句独立表达一个完整意思，5-20 字。如：你有没有想过未来会改变？| 就在昨天，一件事震惊了所有人。| 看完你就会有答案。",
  "hooks": ["开头钩子1：3秒抓人", "开头钩子2：悬念或痛点"],
  "cta": "结尾号召行动（如：关注我，带你xxx）"
}

核心要求：
1. **script** 字段必须使用 | 作为句子分隔符。
2. 每句长度 5-20 字，**口语化**表达，不要书面语。
3. 第一句必须是"钩子"——3 秒内吸引观众停留。
4. 最后一句要有"行动暗示"（但不要太生硬）。
5. 总句数建议 10-20 句（约 30-60 秒视频）。
6. 不要包含 emoji、标签、# 等非口播内容。
7. 不要输出任何图片描述、配图提示词、style_prompt 等视觉相关字段。
"""


async def _generate_script_content(topic: str) -> str:
    """调用 MiniMax M2.7 API 生成脚本内容。"""
    return await call_anthropic_api(
        prompt=topic,
        model="MiniMax-M2.7",
        system=SYSTEM_PROMPT,
        max_tokens=4096,
        temperature=0.7,
    )


async def _parse_script(topic: str) -> ScriptData:
    """调用 API 并解析 JSON 脚本。"""
    raw = await _generate_script_content(topic)
    text = raw.strip()
    start_idx = text.find('{')
    end_idx = text.rfind('}')

    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        text = text[start_idx:end_idx + 1]

    data = json.loads(text)
    for field in ("title", "script", "hooks", "cta"):
        if field not in data:
            raise ValueError(f"脚本缺少字段: {field}")

    script_str = str(data["script"])
    sentences = [s.strip() for s in script_str.split("|") if s.strip()]

    if len(sentences) < 2:
        raise ValueError(f"脚本句子数过少（{len(sentences)}句），请检查 | 分隔符")

    return ScriptData(
        title=str(data["title"]),
        script=script_str,
        sentences=sentences,
        hooks=list(data["hooks"]),
        cta=str(data["cta"]),
    )


async def generate_script(topic: str) -> ScriptData:
    """生成口播脚本（纯文案）。

    Args:
        topic: 视频主题

    Returns:
        ScriptData，包含 title、script、sentences、hooks、cta
    """
    logger.info("📝 正在生成脚本，主题: %s", topic)
    result = await _parse_script(topic)
    logger.info(
        "✅ 脚本生成完成: %s（%d 句）",
        result["title"], len(result["sentences"])
    )
    return result
