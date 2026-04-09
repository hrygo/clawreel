"""FinOps 资源索引模块 - 支持语义相似度匹配和资源复用建议。

设计原则:
1. LLM 判断优先：使用 LLM 理解语义，比代码更灵活
2. 零成本预检：先用关键词快速筛选，减少 LLM 调用
3. 透明建议：明确告诉用户为什么推荐这个资源
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, List, Dict
import math

from .api_client import call_anthropic_api
from .config import MINIMAX_API_KEY
from .utils import CLEAN_CHAR_CLASS_RE


# ─────────────────────────────────────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ResourceEntry:
    """资源条目"""

    resource_type: str  # script, tts, video, image, music
    file_path: str
    topic: str  # 原始主题
    keywords: List[str] = field(default_factory=list)  # 提取的关键词
    created_at: str = ""
    size_bytes: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ResourceManifest:
    """资源清单"""

    version: str = "1.0"
    topics: Dict[str, dict] = field(
        default_factory=dict
    )  # topic -> {keywords, resources}

    def save(self, path: Path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {"version": self.version, "topics": self.topics},
                f,
                ensure_ascii=False,
                indent=2,
            )

    @classmethod
    def load(cls, path: Path) -> "ResourceManifest":
        if not path.exists():
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        manifest = cls(version=data.get("version", "1.0"))
        manifest.topics = data.get("topics", {})
        return manifest


@dataclass
class SimilarityResult:
    """相似度结果"""

    source_topic: str
    matched_topic: str
    resource_type: str
    file_path: str
    score: float  # 0-1 相似度分数
    match_method: str  # keyword_jaccard, tfidf, embedding
    keywords_overlap: List[str] = field(default_factory=list)
    reason: str = ""  # 为什么推荐这个资源


# ─────────────────────────────────────────────────────────────────────────────
# 中文分词和关键词提取
# ─────────────────────────────────────────────────────────────────────────────

# 中文停用词
CHINESE_STOPWORDS = {
    "的",
    "了",
    "是",
    "在",
    "我",
    "有",
    "和",
    "就",
    "不",
    "人",
    "都",
    "一",
    "一个",
    "上",
    "也",
    "很",
    "到",
    "说",
    "要",
    "去",
    "你",
    "会",
    "着",
    "没有",
    "看",
    "好",
    "自己",
    "这",
    "那",
    "么",
    "它",
    "什么",
    "怎么",
    "如何",
    "为什么",
    "怎么样",
    "关于",
    "对于",
    "这个",
    "那个",
    "可以",
    "能",
    "应该",
    "需要",
    "可能",
    "一定",
    "最",
    "更",
    "非常",
    "特别",
    "真的",
    "其实",
    "当然",
    "而且",
    "或者",
    "以及",
    "因为",
    "所以",
    "如果",
    "虽然",
    "但是",
    "然后",
    "还是",
    "以及",
    "并",
    "之",
    "与",
    "及",
    "等",
    "种",
    "个",
    "些",
    "点",
    "方面",
    "问题",
    "情况",
}

# 常见同义词映射（用于归一化）
SYNONYM_MAP = {
    "ai": ["ai", "人工智能", "AI", "Artificial Intelligence", "机器学习", "ML"],
    "未来": ["未来", "将来", "以后", "的趋势", "发展方向"],
    "趋势": ["趋势", "动向", "发展", "演变", "变化"],
    "视频": ["视频", "短视频", "内容", "作品"],
    "科技": ["科技", "技术", "科技发展", "科技趋势"],
    "工作": ["工作", "职场", "职业", "就业", "打工"],
    "生活": ["生活", "日常生活", "生活方式"],
    "健康": ["健康", "养生", "保健"],
    "美食": ["美食", "食物", "烹饪", "做菜"],
    "旅游": ["旅游", "旅行", "出行", "游玩"],
}


class KeywordExtractor:
    """中文关键词提取器"""

    # 常用两字词/多字词词频（简化版，实际应该用更大的词库）
    COMMON_WORDS = {
        "未来",
        "趋势",
        "发展",
        "变化",
        "影响",
        "重要",
        "关键",
        "机会",
        "挑战",
        "技术",
        "创新",
        "改变",
        "行业",
        "市场",
        "社会",
        "生活",
        "工作",
        "学习",
        "健康",
        "财富",
        "投资",
        "创业",
        "科技",
        "互联网",
        "数字化",
        "智能化",
        "人工智能",
        "机器学习",
        "大数据",
        "云计算",
        "区块链",
        "元宇宙",
        "虚拟现实",
        "短视频",
        "直播",
        "电商",
        "网红",
        "品牌",
        "营销",
        "运营",
        "内容创作",
    }

    def __init__(self):
        self.synonym_map = SYNONYM_MAP

    def extract(self, text: str, top_k: int = 10) -> List[str]:
        """提取关键词"""
        # 1. 清理文本
        text = self._clean_text(text)

        # 2. 提取中文词
        chinese_words = self._extract_chinese_words(text)

        # 3. 过滤停用词和单字
        words = [w for w in chinese_words if len(w) >= 2 and w not in CHINESE_STOPWORDS]

        # 4. 词频统计
        word_freq = Counter(words)

        # 5. 提取高频词
        top_words = [w for w, _ in word_freq.most_common(top_k)]

        # 6. 归一化同义词
        normalized = self._normalize_synonyms(top_words)

        return normalized

    def _clean_text(self, text: str) -> str:
        """清理文本"""
        return CLEAN_CHAR_CLASS_RE.sub(" ", text)

    def _extract_chinese_words(self, text: str) -> List[str]:
        """提取中文词（简单基于字符 n-gram）"""
        words = []

        # 提取 2-4 字词
        for n in [2, 3, 4]:
            for i in range(len(text) - n + 1):
                word = text[i : i + n]
                # 只保留包含中文字的词
                if re.match(r"^[\u4e00-\u9fff]+$", word):
                    words.append(word)

        return words

    def _normalize_synonyms(self, words: List[str]) -> List[str]:
        """归一化同义词 - 将同义词映射到标准词"""
        normalized = []
        seen = set()

        for word in words:
            found = False
            for canonical, synonyms in self.synonym_map.items():
                if word in synonyms or word == canonical:
                    if canonical not in seen:
                        normalized.append(canonical)
                        seen.add(canonical)
                        found = True
                        break
            if not found:
                normalized.append(word)
                seen.add(word)

        return normalized


# ─────────────────────────────────────────────────────────────────────────────
# 相似度计算
# ─────────────────────────────────────────────────────────────────────────────


class SimilarityCalculator:
    """相似度计算器"""

    def __init__(self):
        self.extractor = KeywordExtractor()

    def calculate_jaccard(self, keywords1: List[str], keywords2: List[str]) -> float:
        """Jaccard 相似度"""
        if not keywords1 or not keywords2:
            return 0.0

        set1, set2 = set(keywords1), set(keywords2)
        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    def calculate_tfidf_similarity(
        self, keywords1: List[str], keywords2: List[str]
    ) -> float:
        """TF-IDF 相似度（简化版，使用词频）"""
        if not keywords1 or not keywords2:
            return 0.0

        # 构建词频向量
        all_words = list(set(keywords1) | set(keywords2))
        if not all_words:
            return 0.0

        tf1 = Counter(keywords1)
        tf2 = Counter(keywords2)

        # TF 加权相似度（简化版，非标准 TF-IDF）
        # 权重：词出现在当前文档=1.0，不在对比文档=0.5
        def tfidf_vector(words, other_words):
            vec = []
            for word in all_words:
                tf = words.get(word, 0)
                # IDF: 如果词也出现在其他文档，权重降低
                idf = 1.0 if word not in other_words else 0.5
                vec.append(tf * idf)
            return vec

        vec1 = tfidf_vector(tf1, tf2)
        vec2 = tfidf_vector(tf2, tf1)

        # 余弦相似度
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def calculate_similarity(self, topic1: str, topic2: str) -> dict:
        """综合相似度计算"""
        # 提取关键词
        kw1 = self.extractor.extract(topic1)
        kw2 = self.extractor.extract(topic2)

        # 计算各种相似度
        jaccard = self.calculate_jaccard(kw1, kw2)
        tfidf = self.calculate_tfidf_similarity(kw1, kw2)

        # 综合得分（加权平均）
        # TF-IDF 更准确，给更高权重
        combined = 0.4 * jaccard + 0.6 * tfidf

        # 计算重叠关键词
        overlap = list(set(kw1) & set(kw2))

        return {
            "keywords1": kw1,
            "keywords2": kw2,
            "overlap": overlap,
            "jaccard": round(jaccard, 3),
            "tfidf": round(tfidf, 3),
            "combined": round(combined, 3),
        }


# ─────────────────────────────────────────────────────────────────────────────
# 资源索引管理器
# ─────────────────────────────────────────────────────────────────────────────


class ResourceIndexer:
    """资源索引管理器 - 维护资源清单并提供语义搜索"""

    def __init__(self, manifest_path: Path):
        self.manifest_path = manifest_path
        self.manifest = ResourceManifest.load(manifest_path)
        self.similarity = SimilarityCalculator()
        self.extractor = KeywordExtractor()

    def register_resource(self, resource_type: str, file_path: str, topic: str):
        """注册新资源"""
        # 提取关键词
        keywords = self.extractor.extract(topic)

        # 获取文件信息
        path = Path(file_path)
        size = path.stat().st_size if path.exists() else 0
        created = (
            datetime.fromtimestamp(path.stat().st_ctime).isoformat()
            if path.exists()
            else ""
        )

        # 更新清单
        if topic not in self.manifest.topics:
            self.manifest.topics[topic] = {"keywords": keywords, "resources": []}

        # 添加资源
        self.manifest.topics[topic]["resources"].append(
            {
                "type": resource_type,
                "path": str(file_path),
                "size": size,
                "created": created,
            }
        )

        # 保存
        self.manifest.save(self.manifest_path)

    def find_similar(
        self, topic: str, threshold: float = 0.3
    ) -> List[SimilarityResult]:
        """查找相似主题的资源"""
        results = []

        for existing_topic, data in self.manifest.topics.items():
            if existing_topic == topic:
                continue

            # 计算相似度
            sim = self.similarity.calculate_similarity(topic, existing_topic)

            if sim["combined"] >= threshold:
                for resource in data.get("resources", []):
                    results.append(
                        SimilarityResult(
                            source_topic=topic,
                            matched_topic=existing_topic,
                            resource_type=resource["type"],
                            file_path=resource["path"],
                            score=sim["combined"],
                            match_method="keyword_tfidf",
                            keywords_overlap=sim["overlap"],
                            reason=f"主题相似度 {sim['combined']:.0%}，共享关键词: {', '.join(sim['overlap'][:5])}",
                        )
                    )

        # 按相似度排序
        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def get_topic_keywords(self, topic: str) -> List[str]:
        """获取主题关键词"""
        return self.manifest.topics.get(topic, {}).get("keywords", [])


# ─────────────────────────────────────────────────────────────────────────────
# 智能资源建议生成器
# ─────────────────────────────────────────────────────────────────────────────


class SmartSuggestionGenerator:
    """智能建议生成器"""

    SIMILARITY_THRESHOLDS = {
        "high": 0.6,  # 高度相似，可直接推荐
        "medium": 0.4,  # 中度相似，建议考虑
        "low": 0.25,  # 低度相似，提示有相关资源
    }

    def __init__(self, indexer: ResourceIndexer):
        self.indexer = indexer
        self.similarity = SimilarityCalculator()

    def generate_suggestions(
        self, topic: str, needed_types: Optional[List[str]] = None
    ) -> dict:
        """生成资源复用建议

        Args:
            topic: 查询主题
            needed_types: 需要的资源类型列表，如 ["image", "music"]

        Returns:
            包含建议的字典
        """
        if needed_types is None:
            needed_types = ["script", "tts", "video", "image", "music"]

        result = {
            "query_topic": topic,
            "query_keywords": self.similarity.extractor.extract(topic),
            "exact_match": None,
            "similar_matches": [],
            "suggestions": [],
            "cost_savings": {"estimated": "¥0", "reason": ""},
        }

        # 1. 精确匹配检查
        if topic in self.indexer.manifest.topics:
            result["exact_match"] = {
                "topic": topic,
                "keywords": self.indexer.manifest.topics[topic].get("keywords", []),
                "resources": self.indexer.manifest.topics[topic].get("resources", []),
                "count": len(self.indexer.manifest.topics[topic].get("resources", [])),
            }
            result["cost_savings"] = {
                "estimated": "¥0（100% 复用）",
                "reason": "找到完全匹配的资源",
            }
            return result

        # 2. 语义相似搜索
        similar = self.indexer.find_similar(
            topic, threshold=self.SIMILARITY_THRESHOLDS["low"]
        )

        # 3. 按资源类型分组
        by_type = {}
        for sim_result in similar:
            rtype = sim_result.resource_type
            if needed_types and rtype not in needed_types:
                continue

            if rtype not in by_type:
                by_type[rtype] = []
            by_type[rtype].append(sim_result)

        # 4. 为每种资源类型生成建议
        for rtype, matches in by_type.items():
            if not matches:
                continue

            best = matches[0]  # 最高相似度
            confidence = self._get_confidence(best.score)

            result["similar_matches"].append(
                {
                    "type": rtype,
                    "suggested_path": best.file_path,
                    "matched_topic": best.matched_topic,
                    "similarity_score": best.score,
                    "confidence": confidence,
                    "shared_keywords": best.keywords_overlap,
                    "reason": best.reason,
                }
            )

        # 5. 计算节省成本
        if result["similar_matches"]:
            count = len(result["similar_matches"])
            # 粗略估算：每项资源 ¥0.3
            estimated_savings = count * 0.3
            result["cost_savings"] = {
                "estimated": f"~¥{estimated_savings:.1f}",
                "reason": f"可复用 {count} 项相似资源",
            }

        # 6. 生成行动建议
        result["suggestions"] = self._generate_action_suggestions(result)

        return result

    def _get_confidence(self, score: float) -> str:
        """根据分数获取置信度描述"""
        if score >= self.SIMILARITY_THRESHOLDS["high"]:
            return "high"
        elif score >= self.SIMILARITY_THRESHOLDS["medium"]:
            return "medium"
        else:
            return "low"

    def _generate_action_suggestions(self, result: dict) -> List[str]:
        """生成行动建议"""
        suggestions = []

        if result["exact_match"]:
            suggestions.append("✅ 发现完全匹配的资源，建议直接复用")
            suggestions.append("💡 可以修改脚本内容，其他资源保持不变")
        elif result["similar_matches"]:
            high_conf = [
                m for m in result["similar_matches"] if m["confidence"] == "high"
            ]
            if high_conf:
                suggestions.append(
                    f"🎯 发现 {len(high_conf)} 个高度相似的资源，可考虑复用"
                )
            suggestions.append("💡 如果主题相近，可以复用图片/音乐，只重新生成脚本")
        else:
            suggestions.append("🆕 未发现相似资源，需要全新生成")

        return suggestions


# ─────────────────────────────────────────────────────────────────────────────
# 便捷函数
# ─────────────────────────────────────────────────────────────────────────────


def check_resources(topic: str, manifest_path: Optional[Path] = None) -> dict:
    """检查资源并生成建议（便捷函数）"""
    if manifest_path is None:
        from .config import ASSETS_DIR

        manifest_path = ASSETS_DIR / ".resource_manifest.json"

    indexer = ResourceIndexer(manifest_path)
    generator = SmartSuggestionGenerator(indexer)

    return generator.generate_suggestions(topic)


# ─────────────────────────────────────────────────────────────────────────────
# LLM 语义判断模块（低成本，更灵活）
# ─────────────────────────────────────────────────────────────────────────────

LLM_REUSE_PROMPT = """你是一个资源复用顾问。用户想要制作一个关于「{new_topic}」的短视频。

项目已有以下资源：
{existing_resources}

请判断：
1. 已有资源中，哪些可以复用到新视频中？
2. 哪些必须重新生成？
3. 给出一个最优的资源复用方案。

请用 JSON 格式回答：
{{
  "can_reuse": [
    {{
      "type": "资源类型",
      "path": "文件路径",
      "reason": "为什么可以复用"
    }}
  ],
  "must_regenerate": [
    {{
      "type": "资源类型",
      "reason": "为什么必须重新生成"
    }}
  ],
  "recommended_plan": "推荐的执行方案",
  "estimated_savings": "预估节省成本（百分比或金额）",
  "confidence": "判断置信度（high/medium/low）"
}}

注意：
- 图片和音乐风格相似时可以复用
- 如果新主题与已有资源主题高度相关，脚本可以参考结构但需要重新生成
- 配音必须重新生成（除非是完全相同的内容）
"""


async def llm_check_and_suggest(
    topic: str, existing_resources: Dict[str, list], api_key: Optional[str] = None
) -> Dict[str, Any]:
    """使用 LLM 判断资源复用方案（更智能的方案）

    Args:
        topic: 新主题
        existing_resources: 已有资源，格式为 {type: [paths]}
        api_key: API Key（可选，从环境变量读取）

    Returns:
        LLM 判断结果
    """
    if api_key is None:
        api_key = MINIMAX_API_KEY

    if not api_key:
        return {
            "error": "需要 MINIMAX_API_KEY 来使用 LLM 语义判断",
            "fallback": "请使用 check 命令的关键词匹配模式",
        }

    # 构建资源列表
    resources_text = []
    for rtype, paths in existing_resources.items():
        if paths:
            resources_text.append(f"- {rtype}: {', '.join(str(p) for p in paths)}")

    if not resources_text:
        resources_text = ["（暂无已有资源）"]
    else:
        resources_text = ["已有资源："] + resources_text

    # 调用 LLM（使用统一的 api_client.call_anthropic_api）
    try:
        prompt = LLM_REUSE_PROMPT.format(
            new_topic=topic, existing_resources="\n".join(resources_text)
        )

        content = await call_anthropic_api(
            prompt=prompt,
            model="MiniMax-M2.7",
            system="你是一个资源复用顾问。请根据给定的信息，判断哪些资源可以复用，并给出最优方案。",
            max_tokens=1024,
            temperature=0.3,
        )

        if not content:
            return {
                "error": "LLM 返回内容为空",
                "fallback": "请使用 check 命令的关键词匹配模式",
            }

        # 尝试解析 JSON（改进的正则：优先匹配代码块）
        import json as json_module

        try:
            # 优先从代码块提取
            code_match = re.search(r"```(?:json)?\s*(\{.+)", content, re.DOTALL)
            if code_match:
                # 去掉末尾可能的代码块结束标记
                candidate = code_match.group(1).rstrip("`").rstrip()
                parsed = json_module.loads(candidate)
                parsed["llm_reasoning"] = content[:500]
                return parsed

            # 回退到全局搜索（贪婪匹配）
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                parsed = json_module.loads(json_match.group())
                parsed["llm_reasoning"] = content[:500]
                return parsed
        except json_module.JSONDecodeError:
            pass

        return {
            "raw_response": content[:500],
            "confidence": "low",
            "recommended_plan": "无法解析 LLM 响应，请手动检查资源",
        }

    except Exception as e:
        return {
            "error": f"LLM 调用失败: {str(e)}",
            "fallback": "请使用 check 命令的关键词匹配模式",
        }
