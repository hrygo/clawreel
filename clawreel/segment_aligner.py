"""语义对齐 — 将 Edge TTS 逐词时间戳按语义分句，对齐到真实时间轴。

流水线：WordTimestamp → 语义分句 → 时间轴赋值 → prompt 提纯 → ScriptSegment

不依赖 Whisper，不依赖网络，纯本地计算。
"""
import logging
import re
from typing import TypedDict, Optional, List, Union, Dict, Any, Tuple
from pathlib import Path

from .utils import WordTimestamp, parse_srt_timestamp

logger = logging.getLogger(__name__)


# ── 类型定义 ────────────────────────────────────────────────────────────────

class ScriptSegment(TypedDict):
    """语义段落：一句话 + 精确时间轴 + 图片 prompt。"""
    index: int
    text: str
    start_sec: float
    end_sec: float
    duration_sec: float
    image_prompt: str
    is_hook: bool


# ── 常量 ────────────────────────────────────────────────────────────────────

SENTENCE_DELIMITERS = frozenset("。！？.?!|")
SHORT_SEGMENT_THRESHOLD = 1.0   # 秒；低于此值的短句合并到前一句
MAX_SEGMENT_DURATION = 5.0      # 秒；超过此值触发拆分
MIN_CHUNK_DURATION = 2.0         # 秒；拆分后每块至少这么久
MAX_SENTENCE_COUNT = 40          # 句子数上限

CHUNK_DELIMITERS = [
    "，", "、",
    "因为", "所以", "但是", "然而", "如果", "不过",
]

FILLER_WORDS = frozenset("啊吧呢呀哦嗯嘛哈哇呃噢")


# ── 公开 API ────────────────────────────────────────────────────────────────

def align_segments(
    text: str,
    word_timestamps: List[WordTimestamp],
    sentences: Optional[List[str]] = None,
    image_prompts: Optional[List[str]] = None,
    audio_duration: float = 0.0,
) -> List[ScriptSegment]:
    """将逐词时间戳按语义分句，对齐到真实时间轴。

    当 word_timestamps 为空时（MiniMax 降级模式），使用均匀时长估算：
    将 audio_duration 按句子数量均分，作为近似时间轴。

    image_prompts 与 sentences 一一对应；未提供时降级为 refine_image_prompt()。

    Args:
        text:            TTS 合成的完整文本（与 word_timestamps 严格对应）
        word_timestamps: Edge TTS 逐词时间戳列表
        audio_duration:   总音频时长（秒），用于 MiniMax 降级模式下的均匀估算
        image_prompts:   LLM 预生成的配图提示词列表（与 sentences 对应）

    Returns:
        有序 ScriptSegment 列表，每段含时间轴和配图提示词

    Raises:
        ValueError: word_timestamps 为空且未提供 audio_duration，或句子数超过上限
    """
    # 判断是否需要回退到均匀估算：
    # - word_timestamps 为空（MiniMax 降级）
    # - 或词级时间轴严重损坏（Edge TTS 对部分语言/文本无法生成逐词边界）
    use_fallback = False
    if not word_timestamps:
        use_fallback = True
    elif audio_duration > 0:
        wts_total = word_timestamps[-1]["end_sec"] - word_timestamps[0]["start_sec"]
        if wts_total < audio_duration * 0.05:  # 词轴总时长不足音频的 5%，认为损坏
            use_fallback = True

    if use_fallback:
        if audio_duration <= 0:
            raise ValueError(
                "word_timestamps 无效且未提供 audio_duration，无法对齐。"
                "使用 Edge TTS 以获得有效词级时间戳。"
            )
        # 均匀估算模式
        if not sentences:
            sentences = _split_sentences(text)
        
        if not sentences:
            raise ValueError(f"文本无法分句，分句结果为空: {text[:50]!r}")
            
        if len(sentences) > MAX_SENTENCE_COUNT:
            raise ValueError(
                f"句子数 {len(sentences)} 超过上限 {MAX_SENTENCE_COUNT}，"
                "建议拆分脚本为多个短视频"
            )
        gap = 0.2
        avail = audio_duration - gap * (len(sentences) - 1) - 0.4
        total_chars = sum(len(s) for s in sentences)
        cursor = 0.2
        segments: List[ScriptSegment] = []
        for i, sent in enumerate(sentences):
            # char-weighted: long sentences get more time
            char_weight = len(sent) / total_chars if total_chars > 0 else 1 / len(sentences)
            per_sent = char_weight * avail
            per_sent = max(per_sent, 0.5)
            start_sec = cursor
            end_sec = cursor + per_sent - gap
            cursor = end_sec + gap
            duration_sec = end_sec - start_sec
            prompt = (
                image_prompts[i].strip()
                if image_prompts and i < len(image_prompts)
                else refine_image_prompt(sent.strip())
            )
            segments.append(ScriptSegment(
                index=i,
                text=sent.strip(),
                start_sec=start_sec,
                end_sec=end_sec,
                duration_sec=duration_sec,
                image_prompt=prompt,
                is_hook=(i == 0),
            ))
        logger.warning(
            "⚠️ 词级时间轴损坏（%.3f 秒），使用均匀估算时间轴（%d 句）",
            word_timestamps[-1]["end_sec"] if word_timestamps else 0,
            len(sentences),
        )
        return segments

    if not sentences:
        sentences = _split_sentences(text)
        if not sentences:
            raise ValueError(f"文本无法分句，分句结果为空: {text[:50]!r}")

        if len(sentences) > MAX_SENTENCE_COUNT:
            raise ValueError(
                f"句子数 {len(sentences)} 超过上限 {MAX_SENTENCE_COUNT}，"
                "建议拆分脚本为多个短视频"
            )

        # 仅在自动分句时合并短句
        sentences = _merge_short_sentences(sentences, word_timestamps)

    # 词-句分配
    assignments = _assign_words_to_sentences(sentences, word_timestamps)

    # 组装 ScriptSegment
    segments: List[ScriptSegment] = []
    for i, (sentence_text, start_idx, end_idx) in enumerate(assignments):
        start_sec = word_timestamps[start_idx]["start_sec"]
        end_sec = word_timestamps[end_idx]["end_sec"]
        duration_sec = end_sec - start_sec
        if duration_sec <= 0:
            raise ValueError(
                f"段落 {i} 时长异常：start={start_sec}, end={end_sec}，"
                f"text={sentence_text!r}"
            )
        segments.append(ScriptSegment(
            index=i,
            text=sentence_text.strip(),
            start_sec=start_sec,
            end_sec=end_sec,
            duration_sec=duration_sec,
            image_prompt=(
                image_prompts[i].strip()
                if image_prompts and i < len(image_prompts)
                else refine_image_prompt(sentence_text.strip())
            ),
            is_hook=(i == 0),
        ))

    return segments


def split_long_segments(segments: List[ScriptSegment]) -> List[ScriptSegment]:
    """将 duration_sec > MAX_SEGMENT_DURATION 的段落拆分。

    Args:
        segments: align_segments() 输出的段落列表

    Returns:
        拆分后的段落列表（时长全部 <= MAX_SEGMENT_DURATION）
    """
    result: List[ScriptSegment] = []
    sub_index_counter = 0

    for seg in segments:
        if seg["duration_sec"] <= MAX_SEGMENT_DURATION:
            result.append(seg)
            continue

        # 按 CHUNK_DELIMITERS 拆分
        sub_texts = _split_by_chunk_delimiters(seg["text"])
        if len(sub_texts) <= 1:
            result.append(seg)
            continue

        # 按原始时长比例分配子段时长
        total_chars = sum(len(t) for t in sub_texts)
        sub_durations: List[float] = []
        for t in sub_texts:
            frac = len(t) / total_chars
            sub_durations.append(seg["duration_sec"] * frac)

        # 合并过短子段（< MIN_CHUNK_DURATION）
        # 策略：累积短块直到达到阈值，再作为独立 segment 输出
        merged_texts: List[str] = []
        merged_durations: List[float] = []
        buf_text = ""
        buf_dur = 0.0

        for t, d in zip(sub_texts, sub_durations):
            buf_text += t
            buf_dur += d
            if buf_dur >= MIN_CHUNK_DURATION:
                merged_texts.append(buf_text)
                merged_durations.append(buf_dur)
                buf_text = ""
                buf_dur = 0.0

        # 剩余不足阈值块：合并到前一个 segment（若存在）
        if buf_dur > 0 and merged_texts:
            merged_texts[-1] += buf_text
            merged_durations[-1] += buf_dur
        elif buf_dur > 0:
            # 没有可合并的前块，保留作为独立段
            merged_texts.append(buf_text)
            merged_durations.append(buf_dur)

        # 累积 start_sec，生成子段落
        cursor = seg["start_sec"]
        for j, (sub_text, sub_dur) in enumerate(zip(merged_texts, merged_durations)):
            result.append(ScriptSegment(
                index=sub_index_counter,
                text=sub_text.strip(),
                start_sec=cursor,
                end_sec=cursor + sub_dur,
                duration_sec=sub_dur,
                image_prompt=refine_image_prompt(sub_text.strip()),
                is_hook=(sub_index_counter == 0),
            ))
            cursor += sub_dur
            sub_index_counter += 1

    return result


def refine_image_prompt(segment_text: str) -> str:
    """将句子文本提纯为图片生成 prompt。
    
    改进版：增加更多视觉描述词和构图暗示。
    """
    cleaned = segment_text
    for fw in FILLER_WORDS:
        cleaned = cleaned.replace(fw, "")

    visual_hooks = "cinematic, hyper-realistic, 8k resolution, detailed texture, professional lighting, shot on 35mm lens"
    return f"Professional Short Video Scene: {cleaned}. {visual_hooks}, 9:16 vertical orientation, vivid colors, minimalist composition."


def parse_srt_segments(srt_path: Union[str, Path]) -> List[ScriptSegment]:
    """从 SRT 文件解析句级时间轴（用于 burn-subs 或外部导入）。

    精度降为句级（无词级），每条字幕为一段。

    Args:
        srt_path: SRT 文件路径

    Returns:
        ScriptSegment 列表（无 image_prompt，调用方填充）

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 解析失败
    """
    path = Path(srt_path)
    if not path.exists():
        raise FileNotFoundError(f"SRT 文件不存在: {path}")

    content = path.read_text(encoding="utf-8")
    segments: List[ScriptSegment] = []

    # SRT 块正则：索引 + 时间行 + 文本行（可能多行）
    pattern = re.compile(
        r"\d+\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\n([\s\S]*?)(?=\n\n|\n*$)"
    )

    for i, m in enumerate(pattern.finditer(content)):
        start_str, end_str, text_block = m.group(1), m.group(2), m.group(3)
        text = " ".join(text_block.strip().splitlines())
        if not text:
            continue

        start_sec = parse_srt_timestamp(start_str)
        end_sec = parse_srt_timestamp(end_str)

        segments.append(ScriptSegment(
            index=i,
            text=text,
            start_sec=start_sec,
            end_sec=end_sec,
            duration_sec=end_sec - start_sec,
            image_prompt=refine_image_prompt(text),
        ))

    if not segments:
        raise ValueError(f"SRT 文件解析失败，无有效字幕条目: {srt_path}")

    return segments


# ── 内部实现 ────────────────────────────────────────────────────────────────

import re

def _split_sentences(text: str) -> List[str]:
    """按句子边界标记分割文本，返回不含标点的句子列表。
    
    能够正确识别标点符号，并且忽略浮点数中的点（如 5.1 不会被切断）。
    句子边界：。！？.?!
    """
    # 匹配中英文句号、叹号、问号，但不匹配被数字包围的英文字符 "."
    # (?<=[。！？\?!]) : 前面是中英文叹号、问号、句号
    # |(?<!\d)\.(?!\d) : 或者英文句号，且前后不能同时是数字
    # 注意我们需要捕获边界或者不保留边界？要求是不保留标点，所以可以直接作为切分依据。
    # 为了避免繁琐，可以直接切分并剔除空结果。
    pattern = r'[。！？\?!\|]|(?<!\d)\.(?!\d)'
    parts = re.split(pattern, text)
    
    sentences = [p.strip() for p in parts if len(p.strip()) >= 1]
    return sentences


def _merge_short_sentences(
    sentences: List[str],
    word_timestamps: List[WordTimestamp],
) -> List[str]:
    """合并持续时长 < SHORT_SEGMENT_THRESHOLD 的相邻短句。

    策略：计算每句在 word_timestamps 中的跨度，
    若某句 duration < SHORT_SEGMENT_THRESHOLD 则与前一句合并。
    """
    if len(sentences) <= 1:
        return sentences

    chars_per_sentence = [len(s) for s in sentences]
    total_chars = sum(chars_per_sentence)
    if total_chars == 0:
        return sentences

    total_dur = word_timestamps[-1]["end_sec"] - word_timestamps[0]["start_sec"]
    result: List[str] = []

    for i, sentence in enumerate(sentences):
        frac = chars_per_sentence[i] / total_chars
        estimated_dur = frac * total_dur

        if estimated_dur < SHORT_SEGMENT_THRESHOLD and result:
            result[-1] = result[-1] + sentence
        else:
            result.append(sentence)

    return result


def _assign_words_to_sentences(
    sentences: List[str],
    word_timestamps: List[WordTimestamp],
) -> List[tuple[str, int, int]]:
    """贪心分配：每个句子收集连续词，直到文本前缀匹配。

    Returns:
        List[(sentence_text, start_word_idx, end_word_idx)]
    """
    result: List[tuple[str, int, int]] = []
    cursor = 0
    num_sentences = len(sentences)
    num_words = len(word_timestamps)

    for i, sentence_text in enumerate(sentences):
        if cursor >= num_words:
            # 词已耗尽，剩余句子均匀分配剩余词
            remaining = num_sentences - i
            if remaining <= 0:
                break
            chunk_size = max(1, (num_words - cursor) // remaining)
            start_idx = cursor
            end_idx = min(cursor + chunk_size - 1, num_words - 1)
            result.append((sentence_text, start_idx, end_idx))
            cursor = end_idx + 1
            continue

        # 累积词直到文本前缀匹配
        accumulated = ""
        start_idx = cursor
        matched = False

        while cursor < num_words:
            accumulated += word_timestamps[cursor]["word"]
            # 允许 2 字符误差（处理标点缺失等边界情况）
            tolerance = 2
            if (
                accumulated.startswith(sentence_text[:len(accumulated) + tolerance])
                or sentence_text.startswith(accumulated[:len(sentence_text) + tolerance])
            ):
                end_idx = cursor
                result.append((sentence_text, start_idx, end_idx))
                cursor += 1
                matched = True
                break
            cursor += 1

        if not matched:
            # 兜底：均匀分配
            remaining = num_sentences - i
            chunk_size = max(1, (num_words - start_idx) // remaining)
            end_idx = min(start_idx + chunk_size - 1, num_words - 1)
            result.append((sentence_text, start_idx, end_idx))
            cursor = end_idx + 1

    return result


def _split_by_chunk_delimiters(text: str) -> List[str]:
    """按 CHUNK_DELIMITERS 拆分长句，返回子文本列表（保持顺序）。"""
    pattern = "|".join(re.escape(d) for d in CHUNK_DELIMITERS)
    parts = re.split(pattern, text)
    return [p for p in parts if p.strip()]

