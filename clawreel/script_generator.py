"""阶段0：脚本生成 — 使用 MiniMax M2.7 生成口播脚本。

M2.7 通过 Anthropic 兼容接口调用，端点：/anthropic/v1/messages
script 字段使用 | 分隔多句，供语义对齐流水线使用。
image_prompts 与 sentences 一一对应，由 LLM 根据每句内容生成专业配图提示词。
"""
import json
import logging
from typing import Optional, List, Dict, Union, Any, Tuple, TypedDict

from .api_client import call_anthropic_api

logger = logging.getLogger(__name__)


class ScriptData(TypedDict):
    """生成的脚本数据结构（含语义分句及配图提示词）。"""
    title: str
    style_prompt: str        # 整体视觉风格描述
    script: str             # 用 | 分隔的多句文本
    sentences: List[str]     # 解析后的句子列表（不含 |）
    hooks: List[str]        # 钩子列表
    hook_prompt: str        # 片头配图提示词（融合 title 主题）
    cta: str                # 结尾号召
    image_prompts: List[str]  # 与 sentences 一一对应的配图提示词


SYSTEM_PROMPT = """你是一位抖音内容创作专家。请根据用户给定的主题，生成适合抖音口播的短视频脚本。

输出格式（JSON，必须严格遵循）：
{
  "title": "视频标题（吸引眼球，20字以内）",
  "style_prompt": "整体视觉风格描述（会被添加到所有 image_prompts 和 hook_prompt 前），如：温馨治愈风格，高质量摄影作品，自然暖色调光线，侧逆光打造柔和轮廓，竖屏中央构图，画面干净简洁，背景适度虚化突出主体，抖音竖屏9:16规格",
  "script": "口播脚本正文，用 | 分隔多句，每句独立表达一个完整意思，如：你有没有想过未来会改变？| 就在昨天，一件事震惊了所有人。| 看完你就会有答案。",
  "hooks": ["开头钩子1：3秒抓人", "开头钩子2：悬念或痛点"],
  "hook_prompt": "片头画面提示词（具体场景部分），必须融合 title 核心主题，如：特写镜头捕捉金太阳鹦鹉正面表情，羽毛金黄鲜亮，翅膀边缘翠绿色，圆溜溜黑眼睛充满灵气，歪头杀萌态十足",
  "cta": "结尾号召行动（如：关注我，带你xxx）",
  "image_prompts": [
    "第1句配图提示词（具体场景部分）：必须融入 title 核心主题关键词，描述具体场景，如：金太阳鹦鹉站在手指上歪头看镜头，表情呆萌可爱，背景温馨家居",
    "第2句配图提示词（具体场景部分）",
    "..."
  ]
}

核心要求：
1. **结构化提示词（1+1 组合）**：
   - style_prompt: 定义整体视觉风格（光线、构图、质感等）
   - image_prompts: 只写具体场景描述，不重复 style_prompt 内容
   - hook_prompt: 只写片头具体场景描述，不重复 style_prompt 内容
   - 最终提示词 = style_prompt + ", " + image_prompts[i] 或 hook_prompt

2. **主题一致性（最重要）**：
   - image_prompts 每条必须融入 title 核心主题关键词，确保画面不跑题
   - hook_prompt 也必须融入 title 核心主题，片头画面要直接体现主题

3. **句子结构**：
   - script 字段必须使用 | 作为句子分隔符
   - 每句长度 5-20 字，口语化表达
   - image_prompts 数量与 script 分割后的句子数量完全一致

4. **画面提示词要求**：
   - image_prompts 和 hook_prompt 只描述具体画面场景，不包含风格标签
   - 必须包含主题关键词（如 title 中的"金太阳鹦鹉"）
   - 不要使用 emoji
   - 风格标签统一在 style_prompt 中定义

示例（主题：金太阳鹦鹉）：
{
  "title": "金太阳鹦鹉萌翻全场！这谁顶得住啊",
  "style_prompt": "温馨治愈风格，高质量摄影作品，自然暖色调光线，侧逆光打造柔和轮廓，竖屏中央构图，画面干净简洁，背景适度虚化突出主体，抖音竖屏9:16规格",
  "hook_prompt": "特写镜头捕捉金太阳鹦鹉正面表情，羽毛金黄鲜亮，翅膀边缘翠绿色，圆溜溜黑眼睛充满灵气，歪头杀萌态十足",
  "image_prompts": [
    "金太阳鹦鹉站在主人手指上，歪着头好奇地看向镜头，黑眼珠圆溜溜的，羽毛金黄发亮，展现金太阳鹦鹉的黏人特性",
    "一只金太阳鹦鹉站在木棍上，翅膀半张开，做出可爱的歪头动作，羽毛质感细腻，阳光从窗户斜照进来，照亮金黄色的羽毛"
  ]
}

最终组合效果：
- hook_prompt 组合 = style_prompt + ", " + hook_prompt
- image_prompts[0] 组合 = style_prompt + ", " + image_prompts[0]
"""


async def _generate_script_content(topic: str) -> str:
    """调用 MiniMax M2.7 API 生成脚本内容。"""
    return await call_anthropic_api(
        prompt=topic,
        model="MiniMax-M2.7",
        system=SYSTEM_PROMPT,
        max_tokens=8192,
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
    for field in ("title", "style_prompt", "script", "hooks", "hook_prompt", "cta", "image_prompts"):
        if field not in data:
            raise ValueError(f"脚本缺少字段: {field}")

    script_str = str(data["script"])
    sentences = [s.strip() for s in script_str.split("|") if s.strip()]
    image_prompts = list(data["image_prompts"])

    if len(image_prompts) != len(sentences):
        logger.warning(
            "⚠️ image_prompts 数量（%d）与 sentences 数量（%d）不一致，截断对齐",
            len(image_prompts), len(sentences),
        )
        image_prompts = image_prompts[:len(sentences)]

    return ScriptData(
        title=str(data["title"]),
        script=script_str,
        sentences=sentences,
        hooks=list(data["hooks"]),
        hook_prompt=str(data["hook_prompt"]),
        cta=str(data["cta"]),
        image_prompts=image_prompts,
    )


async def generate_script(topic: str) -> ScriptData:
    """生成口播脚本（含配图提示词）。

    Args:
        topic: 视频主题

    Returns:
        ScriptData，包含 title、script、sentences、hooks、cta、image_prompts
    """
    logger.info("📝 正在生成脚本，主题: %s", topic)
    result = await _parse_script(topic)
    logger.info(
        "✅ 脚本生成完成: %s（%d 句，配图提示词 %d 条）",
        result["title"], len(result["sentences"]), len(result["image_prompts"])
    )
    return result
