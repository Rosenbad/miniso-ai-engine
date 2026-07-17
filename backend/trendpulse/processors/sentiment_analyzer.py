# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 情感分析器 (Task 6)
# ==============================================================================
# 对应 spec §3.2 NLP 处理流水线 - 情感分析:
#   SnowNLP (中文) + 多语言大模型 (海外) + Z 世代审美标签识别
#
# SentimentAnalyzer 负责 NLP 流水线的第 3 阶段:
#   1. SnowNLP 中文情感分析 (0-1 → -1~1 转换)
#   2. 非中文文本默认中性 (0.0), 后续可扩展多语言大模型
#   3. Z 世代审美标签识别 (Y2K/废土/侘寂/多巴胺/老钱风/赛博朋克/新中式)
#
# 设计要点:
#   - SnowNLP 延迟导入, 不可用时降级为中性
#   - Z_GEN_TAGS 为类常量, 7 类标签 × 关键词列表
#   - 标签匹配大小写不敏感 (关键词转为小写后与文本小写比对)
#   - 中文检测复用 cleaner 的 CJK 字符区间判断
# ==============================================================================

"""
情感分析器模块。

NLP 处理流水线第 3 阶段: 情感分析 + Z 世代审美标签识别。

类:
    SentimentAnalyzer - SnowNLP 中文情感 + Z_GEN_TAGS 标签识别

用法::

    analyzer = SentimentAnalyzer()
    result = analyzer.analyze("多巴胺彩色穿搭太美了")
    # result: {sentiment: 0.85, z_gen_tags: ["多巴胺"]}
"""

from __future__ import annotations

import re
from typing import Dict, List

from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# 中文检测正则 (CJK 统一汉字)
# ==============================================================================

_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")


# ==============================================================================
# SentimentAnalyzer 情感分析器
# ==============================================================================


class SentimentAnalyzer:
    """情感分析器 - NLP 流水线第 3 阶段 (情感分析 + Z 世代标签)。

    两大功能 (spec §3.2):
        1. 情感分析: SnowNLP 中文情感 (0-1 → -1~1), 非中文默认中性
        2. Z 世代审美标签: 7 类标签关键词匹配 (大小写不敏感)

    类常量:
        Z_GEN_TAGS: 7 类 Z 世代审美标签 → 关键词列表映射

    用法::

        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("Y2K千禧风太好看了")
        # result: {sentiment: 0.72, z_gen_tags: ["Y2K"]}
    """

    # Z 世代审美标签 → 关键词列表 (spec §3.2)
    Z_GEN_TAGS: Dict[str, List[str]] = {
        "Y2K": ["y2k", "千禧风", "复古", "金属", "低腰"],
        "多巴胺": ["多巴胺", "dopamine", "彩色", "明亮", "撞色"],
        "废土": ["废土", "wasteland", "末日", "机能", "解构"],
        "侘寂": ["侘寂", "wabi-sabi", "极简", "自然", "质朴"],
        "老钱风": ["老钱", "old money", "低调", "奢华", "经典"],
        "赛博朋克": ["赛博", "cyberpunk", "霓虹", "未来", "科技"],
        "新中式": ["新中式", "国风", "东方", "水墨", "汉服"],
    }

    # ==================================================================
    # analyze() - 主入口
    # ==================================================================

    def analyze(self, text: str) -> Dict[str, object]:
        """情感分析主入口 — 返回情感分 + Z 世代标签。

        参数:
            text: 待分析文本

        返回:
            ``{sentiment: float, z_gen_tags: list[str]}``
            - sentiment: -1~1 情感分 (中文用 SnowNLP, 非中文默认 0.0)
            - z_gen_tags: 匹配到的 Z 世代审美标签列表
        """
        if not text:
            return {"sentiment": 0.0, "z_gen_tags": []}

        sentiment = self._analyze_sentiment(text)
        z_gen_tags = self._detect_z_gen_tags(text)

        return {"sentiment": sentiment, "z_gen_tags": z_gen_tags}

    # ==================================================================
    # _analyze_sentiment - SnowNLP 情感分析
    # ==================================================================

    def _analyze_sentiment(self, text: str) -> float:
        """中文情感分析 (SnowNLP)。

        SnowNLP 返回 0-1 的情感概率 (0.5 = 中性):
            - 0 → 最负面
            - 0.5 → 中性
            - 1 → 最正面

        转换为 -1~1: ``(score - 0.5) * 2``

        非中文文本返回 0.0 (中性), 后续可扩展多语言大模型 (spec §3.2)。

        参数:
            text: 待分析文本

        返回:
            -1~1 的情感分 (中文), 或 0.0 (非中文/空文本/SnowNLP不可用)
        """
        if not text or not text.strip():
            return 0.0

        # 仅对含中文的文本执行 SnowNLP 情感分析
        if not _CJK_PATTERN.search(text):
            return 0.0

        try:
            from snownlp import SnowNLP

            s = SnowNLP(text)
            raw_score = s.sentiments  # 0-1, 0.5 = 中性
            # 转换为 -1~1: (score - 0.5) * 2
            sentiment = (raw_score - 0.5) * 2
            # 裁剪到 [-1, 1] 范围 (浮点精度保护)
            return max(-1.0, min(1.0, sentiment))
        except ImportError:
            logger.debug("SnowNLP 未安装, 情感分析降级为中性 (0.0)")
            return 0.0
        except Exception as exc:
            logger.debug(f"SnowNLP 情感分析异常, 降级为中性 (0.0): {exc}")
            return 0.0

    # ==================================================================
    # _detect_z_gen_tags - Z 世代审美标签识别
    # ==================================================================

    def _detect_z_gen_tags(self, text: str) -> List[str]:
        """识别文本中的 Z 世代审美标签。

        对 Z_GEN_TAGS 中每个标签的关键词列表进行匹配:
            - 大小写不敏感 (文本与关键词均转小写比对)
            - 任一关键词出现在文本中即判定该标签命中
            - 按标签在 Z_GEN_TAGS 中的定义顺序返回

        参数:
            text: 待检测文本

        返回:
            匹配到的标签名列表 (如 ``["Y2K", "多巴胺"]``)
            无匹配返回空列表
        """
        if not text:
            return []

        text_lower = text.lower()
        matched_tags: List[str] = []

        for tag_name, keywords in self.Z_GEN_TAGS.items():
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    matched_tags.append(tag_name)
                    break  # 该标签已命中, 不再检查其他关键词

        return matched_tags


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["SentimentAnalyzer"]
