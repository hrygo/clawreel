"""Phase 2: 脚本生成 — 格式化口播脚本为标准结构。

单一职责：接收口播文本（已由 Agent/SKILL.md 生成），输出标准化 JSON 结构。
不生成任何内容创意，所有内容由 SKILL.md 中 Agent 负责。

SKILL.md 负责：
- 接收用户模糊/部分输入
- 补全为完整口播内容（口语化、多角度、情感层次）
- 控制句数、节奏、情感曲线

本模块负责：
- 将文本格式化为标准 JSON（title、script、sentences、hooks、cta）
- script 字段使用 | 分隔多句，供语义对齐流水线使用
"""

import json
import logging
import re
from typing import List, TypedDict

logger = logging.getLogger(__name__)


class ScriptData(TypedDict):
    title: str
    script: str
    sentences: List[str]
    hooks: List[str]
    cta: str


def _extract_title(raw_lines: List[str]) -> str:
    """从内容中提取或生成标题。"""
    # 优先找以 # 开头的行作为标题
    for line in raw_lines:
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
    # 否则取第一句的前15字
    if raw_lines:
        return raw_lines[0].strip()[:15]
    return "未命名视频"


def _identify_hooks(sentences: List[str]) -> List[str]:
    """识别前1-2句作为开头钩子。"""
    return sentences[:2] if len(sentences) >= 2 else sentences


def _extract_cta(raw_text: str) -> str:
    """从内容末尾提取 CTA，或生成默认 CTA。"""
    # 匹配到 | 分隔符为止，避免贪婪匹配整个文本
    cta_patterns = [
        r"(?:关注|点赞|评论|收藏|转发)[我你]?[，,，]?[^|]*",
    ]
    # Search from the end — take the last CTA-like segment
    for pattern in cta_patterns:
        matches = list(re.finditer(pattern, raw_text))
        if matches:
            return matches[-1].group(0).strip()
    # Fallback: check last segment for CTA keywords
    segments = [s.strip() for s in raw_text.split("|") if s.strip()]
    if segments:
        last = segments[-1]
        if re.search(r"(?:关注|点赞|评论|收藏|转发)", last):
            return last
    return "关注我带你了解更多"

def _split_sentences(text: str) -> List[str]:
    """将文本按 | 或换行分割为句子列表。"""
    # 优先用 | 分隔
    if "|" in text:
        sentences = [s.strip() for s in text.split("|") if s.strip()]
        if sentences:
            return sentences

    # 否则按换行分割
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    # 过滤掉标题行（以 # 开头）
    sentences = [l for l in lines if not l.startswith("#")]

    # 如果分割后句子太长，尝试进一步拆分
    result = []
    for s in sentences:
        # 跳过 CTA 行（如果 CTA 已经单独提取）
        if s.startswith("关注") or s.startswith("点赞"):
            continue
        result.append(s)
    return result if result else sentences


def format_script(
    content: str,
    title: str | None = None,
    cta: str | None = None,
) -> ScriptData:
    """将口播文本格式化为标准脚本结构。

    职责分离：
    - SKILL.md/Agent 生成 content（完整口语化内容）
    - 本函数仅负责格式化（分割、提取、组装）

    Args:
        content: 完整的口播文本，用 | 分隔句子，或多行文本
        title: 可选，指定标题（否则自动提取）
        cta: 可选，指定 CTA（否则自动生成）

    Returns:
        ScriptData，包含 title、script、sentences、hooks、cta
    """
    raw_lines = content.strip().split("\n")

    # 提取标题
    final_title = title or _extract_title(raw_lines)

    # 分割句子
    sentences = _split_sentences(content)

    # 识别钩子
    hooks = _identify_hooks(sentences)

    # 提取或生成 CTA
    final_cta = cta or _extract_cta(content)

    # 组装 script 字段
    script_str = " | ".join(sentences)

    logger.info("✅ 脚本格式化完成: %s（%d 句）", final_title, len(sentences))

    return ScriptData(
        title=final_title,
        script=script_str,
        sentences=sentences,
        hooks=hooks,
        cta=final_cta,
    )
