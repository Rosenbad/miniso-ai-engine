# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - NLP 处理流水线单元测试 (Task 6)
# ==============================================================================
# 对应 Task 6: NLP 处理流水线
# 覆盖:
#   1. DataCleaner        - 去广告(正则) + 去重 + 语言检测
#   2. TopicClusterer     - TF-IDF + KMeans 话题聚类
#   3. SentimentAnalyzer  - SnowNLP 中文情感 + Z 世代审美标签识别
#   4. TrendPredictor     - Prophet 时序预测 + 线性外推降级
# ==============================================================================

"""
测试 NLP 处理流水线的 4 个处理器。

测试策略 (TDD):
  1. DataCleaner       - 正则去广告模式 / 去重 / 多语言检测
  2. TopicClusterer    - TF-IDF+KMeans 聚类 / 关键词提取 / 边界场景
  3. SentimentAnalyzer - 正负面情感检测 / 7 类 Z 世代标签识别 / 大小写不敏感
  4. TrendPredictor    - 上升/峰值/衰退生命周期 / 周环比增长率 / 线性降级

环境说明:
  - SnowNLP / jieba / scikit-learn 已安装, 情感与聚类测试使用真实库
  - Prophet 可能未安装, 趋势预测优先走线性外推降级路径
    (另设独立测试 mock Prophet 验证 prophet 路径)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from trendpulse.processors.cleaner import DataCleaner
from trendpulse.processors.sentiment_analyzer import SentimentAnalyzer
from trendpulse.processors.topic_clusterer import TopicClusterer
from trendpulse.processors.trend_predictor import TrendPredictor


# ==============================================================================
# 1. DataCleaner 测试
# ==============================================================================


class TestDataCleaner:
    """DataCleaner 测试 - 去广告 / 去重 / 语言检测。"""

    # --- 构造与基本行为 ---

    def test_clean_empty_list_returns_empty(self) -> None:
        """空列表输入应返回空列表。"""
        cleaner = DataCleaner()
        assert cleaner.clean([]) == []

    def test_clean_returns_list_of_dict(self) -> None:
        """clean() 应返回 list[dict]。"""
        cleaner = DataCleaner()
        items = [{"topic": "测试", "content": "这是一条正常内容", "source": "test"}]
        result = cleaner.clean(items)
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], dict)

    def test_clean_adds_language_field(self) -> None:
        """clean() 应为每条数据添加 language 字段。"""
        cleaner = DataCleaner()
        items = [{"topic": "测试", "content": "这是一条中文内容", "source": "test"}]
        result = cleaner.clean(items)
        assert "language" in result[0]
        assert result[0]["language"] == "zh"

    # --- 去广告 _remove_ads ---

    def test_remove_ads_strips_http_urls(self) -> None:
        """应移除 http/https 链接。"""
        cleaner = DataCleaner()
        text = "这个产品很好用 详情见 https://example.com/product 了解更多"
        cleaned = cleaner._remove_ads(text)
        assert "https://example.com" not in cleaned
        assert "http" not in cleaned
        assert "这个产品很好用" in cleaned

    def test_remove_ads_strips_wechat_patterns(self) -> None:
        """应移除微信相关推广内容 (加微信/微信号/wechat)。"""
        cleaner = DataCleaner()
        for pattern in ["加微信", "微信号", "wechat", "WeChat"]:
            text = f"好物推荐 {pattern} abc123 获取优惠"
            cleaned = cleaner._remove_ads(text)
            assert pattern.lower() not in cleaned.lower(), (
                f"应移除 '{pattern}'"
            )

    def test_remove_ads_strips_promotional_patterns(self) -> None:
        """应移除促销相关关键词 (促销/限时/折扣/秒杀/优惠券/点击链接)。"""
        cleaner = DataCleaner()
        patterns = ["促销", "限时", "折扣", "秒杀", "优惠券", "点击链接"]
        for p in patterns:
            text = f"今日推荐 {p}中 快来买"
            cleaned = cleaner._remove_ads(text)
            assert p not in cleaned, f"应移除促销关键词 '{p}'"

    def test_remove_ads_strips_contact_patterns(self) -> None:
        """应移除联系方式 (联系QQ/电话/加群)。"""
        cleaner = DataCleaner()
        patterns = ["联系QQ", "电话", "加群"]
        for p in patterns:
            text = f"感兴趣 {p} 123456"
            cleaned = cleaner._remove_ads(text)
            assert p not in cleaned, f"应移除联系方式 '{p}'"

    def test_remove_ads_preserves_normal_text(self) -> None:
        """正常文本 (无广告) 应保持不变 (仅首尾空白清理)。"""
        cleaner = DataCleaner()
        text = "侘寂风家居搭配自然质感材质"
        cleaned = cleaner._remove_ads(text)
        assert cleaned.strip() == text

    def test_remove_ads_strips_multiple_patterns_at_once(self) -> None:
        """同时包含多种广告模式时应全部移除。"""
        cleaner = DataCleaner()
        text = (
            "好物推荐 加微信xhs123 限时折扣 "
            "链接 https://t.co/abc 联系QQ:999"
        )
        cleaned = cleaner._remove_ads(text)
        assert "加微信" not in cleaned
        assert "限时" not in cleaned
        assert "折扣" not in cleaned
        assert "https" not in cleaned
        assert "联系QQ" not in cleaned

    def test_clean_removes_ads_from_content_field(self) -> None:
        """clean() 应清理 item 的 content 字段中的广告。"""
        cleaner = DataCleaner()
        items = [
            {
                "topic": "推荐",
                "content": "好物推荐 加微信abc 限时折扣",
                "source": "test",
            }
        ]
        result = cleaner.clean(items)
        assert "加微信" not in result[0]["content"]
        assert "限时" not in result[0]["content"]
        assert "折扣" not in result[0]["content"]

    # --- 去重 _deduplicate ---

    def test_deduplicate_removes_exact_duplicates(self) -> None:
        """应移除内容完全相同的重复项。"""
        cleaner = DataCleaner()
        items = [
            {"topic": "A", "content": "侘寂风家居搭配", "source": "xhs"},
            {"topic": "B", "content": "侘寂风家居搭配", "source": "douyin"},
        ]
        result = cleaner._deduplicate(items)
        assert len(result) == 1

    def test_deduplicate_removes_whitespace_only_diff(self) -> None:
        """仅空白差异的内容应视为重复。"""
        cleaner = DataCleaner()
        items = [
            {"topic": "A", "content": "  侘寂 风 家居  ", "source": "xhs"},
            {"topic": "B", "content": "侘寂风家居", "source": "douyin"},
        ]
        result = cleaner._deduplicate(items)
        assert len(result) == 1

    def test_deduplicate_keeps_different_items(self) -> None:
        """不同内容的项应全部保留。"""
        cleaner = DataCleaner()
        items = [
            {"topic": "A", "content": "侘寂风家居搭配", "source": "xhs"},
            {"topic": "B", "content": "Y2K千禧风穿搭", "source": "douyin"},
            {"topic": "C", "content": "多巴胺彩色配色", "source": "tiktok"},
        ]
        result = cleaner._deduplicate(items)
        assert len(result) == 3

    def test_deduplicate_near_duplicates_removed(self) -> None:
        """高度相似 (近重复) 的内容应视为重复。"""
        cleaner = DataCleaner()
        items = [
            {"topic": "A", "content": "侘寂风家居搭配自然质感", "source": "xhs"},
            {"topic": "B", "content": "侘寂风家居搭配自然质感！", "source": "douyin"},
        ]
        result = cleaner._deduplicate(items)
        assert len(result) == 1

    def test_deduplicate_empty_list(self) -> None:
        """空列表去重后仍为空。"""
        cleaner = DataCleaner()
        assert cleaner._deduplicate([]) == []

    def test_clean_deduplicates_in_pipeline(self) -> None:
        """clean() 完整流水线应去重。"""
        cleaner = DataCleaner()
        items = [
            {"topic": "A", "content": "侘寂风家居自然质感", "source": "xhs"},
            {"topic": "B", "content": "侘寂风家居自然质感", "source": "douyin"},
            {"topic": "C", "content": "Y2K千禧风穿搭", "source": "tiktok"},
        ]
        result = cleaner.clean(items)
        assert len(result) == 2

    # --- 语言检测 _detect_language ---

    def test_detect_language_chinese(self) -> None:
        """应检测中文为 zh。"""
        cleaner = DataCleaner()
        assert cleaner._detect_language("这是一段中文文本") == "zh"

    def test_detect_language_english(self) -> None:
        """应检测英文为 en。"""
        cleaner = DataCleaner()
        assert cleaner._detect_language("This is an English text") == "en"

    def test_detect_language_japanese(self) -> None:
        """应检测日语 (含平假名/片假名) 为 ja。"""
        cleaner = DataCleaner()
        assert cleaner._detect_language("これは日本語のテキストです") == "ja"

    def test_detect_language_korean(self) -> None:
        """应检测韩语 (含韩文音节) 为 ko。"""
        cleaner = DataCleaner()
        assert cleaner._detect_language("이것은 한국어 텍스트입니다") == "ko"

    def test_detect_language_thai(self) -> None:
        """应检测泰语 (含泰文字符) 为 th。"""
        cleaner = DataCleaner()
        assert cleaner._detect_language("นี่คือข้อความภาษาไทย") == "th"

    def test_detect_language_other_for_empty(self) -> None:
        """空字符串应返回 other。"""
        cleaner = DataCleaner()
        assert cleaner._detect_language("") == "other"

    def test_detect_language_other_for_numbers_only(self) -> None:
        """纯数字/符号应返回 other。"""
        cleaner = DataCleaner()
        assert cleaner._detect_language("12345 !!!") == "other"

    def test_clean_detects_language_for_mixed_items(self) -> None:
        """clean() 应为不同语言的内容添加正确的 language 字段。"""
        cleaner = DataCleaner()
        items = [
            {"topic": "中文", "content": "这是一条中文内容", "source": "xhs"},
            {"topic": "English", "content": "This is English content", "source": "tiktok"},
            {"topic": "日本語", "content": "これは日本語です", "source": "instagram"},
        ]
        result = cleaner.clean(items)
        languages = [item["language"] for item in result]
        assert "zh" in languages
        assert "en" in languages
        assert "ja" in languages


# ==============================================================================
# 2. TopicClusterer 测试
# ==============================================================================


class TestTopicClusterer:
    """TopicClusterer 测试 - TF-IDF + KMeans 聚类。"""

    # --- 边界场景 ---

    def test_cluster_empty_list_returns_empty(self) -> None:
        """空列表应返回空列表。"""
        clusterer = TopicClusterer()
        assert clusterer.cluster([]) == []

    def test_cluster_single_item_returns_one_cluster(self) -> None:
        """单项输入应返回 1 个聚类。"""
        clusterer = TopicClusterer()
        items = [{"topic": "测试", "content": "侘寂风家居自然质感", "source": "xhs"}]
        result = clusterer.cluster(items)
        assert len(result) == 1
        assert result[0]["items_count"] == 1

    def test_cluster_all_identical_returns_one_cluster(self) -> None:
        """全部相同内容应聚为 1 类。"""
        clusterer = TopicClusterer()
        items = [
            {"topic": "A", "content": "侘寂风家居自然质感极简", "source": "xhs"},
            {"topic": "B", "content": "侘寂风家居自然质感极简", "source": "douyin"},
            {"topic": "C", "content": "侘寂风家居自然质感极简", "source": "tiktok"},
        ]
        result = clusterer.cluster(items, n_clusters=3)
        assert len(result) == 1
        assert result[0]["items_count"] == 3

    # --- 聚类结构 ---

    def test_cluster_returns_correct_structure(self) -> None:
        """每个聚类摘要应包含 topic_name/items_count/keywords/representative_text/items。"""
        clusterer = TopicClusterer()
        items = [
            {"topic": "A", "content": "侘寂风家居自然质感极简", "source": "xhs"},
            {"topic": "B", "content": "Y2K千禧风复古金属低腰", "source": "douyin"},
        ]
        result = clusterer.cluster(items, n_clusters=2)
        assert len(result) >= 1
        for cluster_summary in result:
            assert "topic_name" in cluster_summary
            assert "items_count" in cluster_summary
            assert "keywords" in cluster_summary
            assert "representative_text" in cluster_summary
            assert "items" in cluster_summary
            assert isinstance(cluster_summary["keywords"], list)
            assert isinstance(cluster_summary["items"], list)
            assert cluster_summary["items_count"] == len(cluster_summary["items"])

    def test_cluster_n_clusters_capped_by_item_count(self) -> None:
        """n_clusters 不应超过输入项数。"""
        clusterer = TopicClusterer()
        items = [
            {"topic": "A", "content": "侘寂风家居", "source": "xhs"},
            {"topic": "B", "content": "Y2K穿搭", "source": "douyin"},
        ]
        result = clusterer.cluster(items, n_clusters=10)
        # 聚类数不应超过输入项数
        assert len(result) <= 2

    def test_cluster_groups_similar_items_together(self) -> None:
        """相似内容的项应被分到同一聚类。"""
        clusterer = TopicClusterer()
        items = [
            {"topic": "A", "content": "侘寂风家居自然质感极简质朴", "source": "xhs"},
            {"topic": "B", "content": "侘寂风极简自然家居设计", "source": "douyin"},
            {"topic": "C", "content": "Y2K千禧风复古金属低腰穿搭", "source": "tiktok"},
            {"topic": "D", "content": "Y2K复古千禧金属风时尚", "source": "instagram"},
        ]
        result = clusterer.cluster(items, n_clusters=2)
        assert len(result) == 2
        total_items = sum(c["items_count"] for c in result)
        assert total_items == 4

    def test_cluster_representative_text_is_non_empty(self) -> None:
        """每个聚类的 representative_text 应为非空字符串。"""
        clusterer = TopicClusterer()
        items = [
            {"topic": "A", "content": "侘寂风家居自然质感极简", "source": "xhs"},
            {"topic": "B", "content": "Y2K千禧风复古金属低腰", "source": "douyin"},
        ]
        result = clusterer.cluster(items, n_clusters=2)
        for cluster_summary in result:
            assert isinstance(cluster_summary["representative_text"], str)
            assert len(cluster_summary["representative_text"]) > 0

    # --- 关键词提取 ---

    def test_extract_keywords_returns_list(self) -> None:
        """_extract_keywords 应返回 list[str]。"""
        clusterer = TopicClusterer()
        texts = ["侘寂风家居自然质感", "侘寂极简家居设计", "自然质感侘寂风格"]
        keywords = clusterer._extract_keywords(texts, top_n=3)
        assert isinstance(keywords, list)
        assert len(keywords) <= 3

    def test_extract_keywords_relevant_terms(self) -> None:
        """关键词应包含文本中高频且具区分性的词。"""
        clusterer = TopicClusterer()
        texts = [
            "侘寂风家居自然质感极简",
            "侘寂风家居设计自然质感",
            "极简侘寂风家居自然",
        ]
        keywords = clusterer._extract_keywords(texts, top_n=5)
        # 至少应包含 "侘寂" 或 "家居" 等高频词
        keyword_str = " ".join(keywords)
        assert any(
            kw in keyword_str for kw in ["侘寂", "家居", "自然", "极简", "质感"]
        )

    def test_extract_keywords_empty_input(self) -> None:
        """空输入应返回空列表。"""
        clusterer = TopicClusterer()
        assert clusterer._extract_keywords([], top_n=5) == []

    # --- 话题名生成 ---

    def test_generate_topic_name_returns_string(self) -> None:
        """_generate_topic_name 应返回非空字符串。"""
        clusterer = TopicClusterer()
        name = clusterer._generate_topic_name(["侘寂", "家居", "极简"])
        assert isinstance(name, str)
        assert len(name) > 0

    def test_generate_topic_name_includes_keywords(self) -> None:
        """话题名应包含至少一个关键词。"""
        clusterer = TopicClusterer()
        keywords = ["侘寂", "家居", "极简"]
        name = clusterer._generate_topic_name(keywords)
        assert any(kw in name for kw in keywords)

    def test_generate_topic_name_empty_keywords(self) -> None:
        """空关键词列表应返回默认话题名。"""
        clusterer = TopicClusterer()
        name = clusterer._generate_topic_name([])
        assert isinstance(name, str)
        assert len(name) > 0


# ==============================================================================
# 3. SentimentAnalyzer 测试
# ==============================================================================


class TestSentimentAnalyzer:
    """SentimentAnalyzer 测试 - SnowNLP 情感 + Z 世代标签识别。"""

    # --- Z_GEN_TAGS 常量 ---

    def test_z_gen_tags_contains_all_seven_tags(self) -> None:
        """Z_GEN_TAGS 应包含 7 类审美标签。"""
        expected_tags = {"Y2K", "多巴胺", "废土", "侘寂", "老钱风", "赛博朋克", "新中式"}
        assert set(SentimentAnalyzer.Z_GEN_TAGS.keys()) == expected_tags

    def test_z_gen_tags_values_are_non_empty_lists(self) -> None:
        """每个标签的关键词列表应非空。"""
        for tag, keywords in SentimentAnalyzer.Z_GEN_TAGS.items():
            assert isinstance(keywords, list), f"{tag} 的关键词应为 list"
            assert len(keywords) > 0, f"{tag} 的关键词列表不应为空"

    def test_z_gen_tags_y2k_keywords(self) -> None:
        """Y2K 标签应包含核心关键词。"""
        y2k_keywords = SentimentAnalyzer.Z_GEN_TAGS["Y2K"]
        assert "y2k" in y2k_keywords
        assert "千禧风" in y2k_keywords

    def test_z_gen_tags_dopamine_keywords(self) -> None:
        """多巴胺标签应包含核心关键词。"""
        keywords = SentimentAnalyzer.Z_GEN_TAGS["多巴胺"]
        assert "多巴胺" in keywords
        assert "dopamine" in keywords

    # --- 情感分析 _analyze_sentiment ---

    def test_analyze_sentiment_positive_chinese(self) -> None:
        """正面中文文本应返回正向情感 (>0)。"""
        analyzer = SentimentAnalyzer()
        text = "这个产品包装精美，材质上乘，设计感十足，用起来很舒服，性价比很高"
        score = analyzer._analyze_sentiment(text)
        assert isinstance(score, float)
        assert score > 0.3, f"正面文本情感分应 >0.3, 实际: {score}"

    def test_analyze_sentiment_negative_chinese(self) -> None:
        """负面中文文本应返回负向情感 (<0)。"""
        analyzer = SentimentAnalyzer()
        text = "收到货发现破损严重，客服态度恶劣，退款流程繁琐，体验极差"
        score = analyzer._analyze_sentiment(text)
        assert isinstance(score, float)
        assert score < -0.3, f"负面文本情感分应 <-0.3, 实际: {score}"

    def test_analyze_sentiment_non_chinese_neutral(self) -> None:
        """非中文文本应返回中性 (0.0)。"""
        analyzer = SentimentAnalyzer()
        text = "This product is amazing and wonderful"
        score = analyzer._analyze_sentiment(text)
        assert score == 0.0

    def test_analyze_sentiment_range(self) -> None:
        """情感分应在 [-1, 1] 范围内。"""
        analyzer = SentimentAnalyzer()
        texts = [
            "这个产品太棒了，非常满意，强烈推荐",
            "质量极差，完全不能用，非常失望",
            "这是一段普通的中性描述文本",
        ]
        for text in texts:
            score = analyzer._analyze_sentiment(text)
            assert -1.0 <= score <= 1.0

    def test_analyze_sentiment_empty_text(self) -> None:
        """空文本应返回中性 (0.0)。"""
        analyzer = SentimentAnalyzer()
        assert analyzer._analyze_sentiment("") == 0.0

    # --- Z 世代标签检测 _detect_z_gen_tags ---

    def test_detect_y2k_tag(self) -> None:
        """应识别 Y2K 标签。"""
        analyzer = SentimentAnalyzer()
        tags = analyzer._detect_z_gen_tags("Y2K千禧风复古穿搭")
        assert "Y2K" in tags

    def test_detect_dopamine_tag(self) -> None:
        """应识别多巴胺标签。"""
        analyzer = SentimentAnalyzer()
        tags = analyzer._detect_z_gen_tags("多巴胺彩色明亮撞色搭配")
        assert "多巴胺" in tags

    def test_detect_wasteland_tag(self) -> None:
        """应识别废土标签。"""
        analyzer = SentimentAnalyzer()
        tags = analyzer._detect_z_gen_tags("废土风末日机能解构设计")
        assert "废土" in tags

    def test_detect_wabi_sabi_tag(self) -> None:
        """应识别侘寂标签。"""
        analyzer = SentimentAnalyzer()
        tags = analyzer._detect_z_gen_tags("侘寂风极简自然质朴家居")
        assert "侘寂" in tags

    def test_detect_old_money_tag(self) -> None:
        """应识别老钱风标签。"""
        analyzer = SentimentAnalyzer()
        tags = analyzer._detect_z_gen_tags("老钱风低调奢华经典穿搭")
        assert "老钱风" in tags

    def test_detect_cyberpunk_tag(self) -> None:
        """应识别赛博朋克标签。"""
        analyzer = SentimentAnalyzer()
        tags = analyzer._detect_z_gen_tags("赛博朋克霓虹未来科技感")
        assert "赛博朋克" in tags

    def test_detect_new_chinese_style_tag(self) -> None:
        """应识别新中式标签。"""
        analyzer = SentimentAnalyzer()
        tags = analyzer._detect_z_gen_tags("新中式国风东方水墨汉服")
        assert "新中式" in tags

    def test_detect_tags_case_insensitive(self) -> None:
        """标签匹配应大小写不敏感。"""
        analyzer = SentimentAnalyzer()
        tags = analyzer._detect_z_gen_tags("y2k CYBERPUNK Dopamine")
        assert "Y2K" in tags
        assert "赛博朋克" in tags
        assert "多巴胺" in tags

    def test_detect_tags_multiple_at_once(self) -> None:
        """可同时识别多个标签。"""
        analyzer = SentimentAnalyzer()
        text = "Y2K千禧风搭配多巴胺彩色，融合赛博朋克霓虹元素"
        tags = analyzer._detect_z_gen_tags(text)
        assert "Y2K" in tags
        assert "多巴胺" in tags
        assert "赛博朋克" in tags

    def test_detect_tags_no_match_returns_empty(self) -> None:
        """无匹配时应返回空列表。"""
        analyzer = SentimentAnalyzer()
        tags = analyzer._detect_z_gen_tags("今天天气不错出去散步")
        assert tags == []

    # --- analyze 主入口 ---

    def test_analyze_returns_correct_structure(self) -> None:
        """analyze() 应返回 {sentiment, z_gen_tags} 结构。"""
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("Y2K千禧风真的太好看了，超级喜欢")
        assert "sentiment" in result
        assert "z_gen_tags" in result
        assert isinstance(result["sentiment"], float)
        assert isinstance(result["z_gen_tags"], list)

    def test_analyze_combines_sentiment_and_tags(self) -> None:
        """analyze() 应同时返回情感分和 Z 世代标签。"""
        analyzer = SentimentAnalyzer()
        text = "多巴胺彩色穿搭真的太美了，色彩明亮，非常喜欢"
        result = analyzer.analyze(text)
        assert "多巴胺" in result["z_gen_tags"]
        assert result["sentiment"] > 0  # 正面情感

    def test_analyze_neutral_text_no_tags(self) -> None:
        """中性无标签文本应返回中性情感和空标签。"""
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze("This is a plain English text")
        assert result["sentiment"] == 0.0
        assert result["z_gen_tags"] == []


# ==============================================================================
# 4. TrendPredictor 测试
# ==============================================================================


def _make_historical_data(
    start_value: float,
    daily_delta: float,
    days: int = 21,
    start_date: str = "2025-01-01",
) -> List[Dict[str, Any]]:
    """生成模拟历史时序数据。

    参数:
        start_value : 起始值
        daily_delta : 每日增量 (正=上升, 负=下降, 0=平稳)
        days        : 天数
        start_date  : 起始日期 (YYYY-MM-DD)

    返回:
        [{date, value}, ...] 按日期升序排列
    """
    base = datetime.strptime(start_date, "%Y-%m-%d")
    data = []
    for i in range(days):
        date_str = (base + timedelta(days=i)).strftime("%Y-%m-%d")
        value = start_value + daily_delta * i
        data.append({"date": date_str, "value": round(value, 2)})
    return data


class TestTrendPredictor:
    """TrendPredictor 测试 - Prophet 时序预测 + 线性外推降级。"""

    # --- 基本结构 ---

    def test_predict_returns_correct_structure(self) -> None:
        """predict() 应返回 {lifecycle, predict_window, predicted_values, growth_rate}。"""
        predictor = TrendPredictor()
        data = _make_historical_data(
            start_value=100, daily_delta=2, days=21
        )
        result = predictor.predict(data, forecast_days=14)
        assert "lifecycle" in result
        assert "predict_window" in result
        assert "predicted_values" in result
        assert "growth_rate" in result

    def test_predict_lifecycle_valid_value(self) -> None:
        """lifecycle 应为 rising/peak/declining 之一。"""
        predictor = TrendPredictor()
        data = _make_historical_data(
            start_value=100, daily_delta=2, days=21
        )
        result = predictor.predict(data, forecast_days=14)
        assert result["lifecycle"] in ("rising", "peak", "declining")

    def test_predict_predicted_values_count(self) -> None:
        """predicted_values 应包含 forecast_days 条预测。"""
        predictor = TrendPredictor()
        data = _make_historical_data(
            start_value=100, daily_delta=2, days=21
        )
        result = predictor.predict(data, forecast_days=14)
        assert len(result["predicted_values"]) == 14

    def test_predict_predicted_values_structure(self) -> None:
        """每条预测应包含 date 和 value 字段。"""
        predictor = TrendPredictor()
        data = _make_historical_data(
            start_value=100, daily_delta=2, days=21
        )
        result = predictor.predict(data, forecast_days=7)
        for item in result["predicted_values"]:
            assert "date" in item
            assert "value" in item

    def test_predict_predict_window_contains_week(self) -> None:
        """predict_window 应包含 '周' 字。"""
        predictor = TrendPredictor()
        data = _make_historical_data(
            start_value=100, daily_delta=2, days=21
        )
        result = predictor.predict(data, forecast_days=14)
        assert "周" in result["predict_window"]

    def test_predict_predict_window_default_14_days(self) -> None:
        """默认 forecast_days=14 时 predict_window 应为 '2-4周'。"""
        predictor = TrendPredictor()
        data = _make_historical_data(
            start_value=100, daily_delta=2, days=21
        )
        result = predictor.predict(data, forecast_days=14)
        assert result["predict_window"] == "2-4周"

    def test_predict_growth_rate_is_float(self) -> None:
        """growth_rate 应为 float 类型。"""
        predictor = TrendPredictor()
        data = _make_historical_data(
            start_value=100, daily_delta=2, days=21
        )
        result = predictor.predict(data, forecast_days=14)
        assert isinstance(result["growth_rate"], float)

    # --- 生命周期判定 ---

    def test_lifecycle_rising_for_upward_trend(self) -> None:
        """历史数据持续上升时, lifecycle 应为 rising。"""
        predictor = TrendPredictor()
        data = _make_historical_data(
            start_value=100, daily_delta=5, days=21
        )
        result = predictor.predict(data, forecast_days=14)
        assert result["lifecycle"] == "rising"

    def test_lifecycle_declining_for_downward_trend(self) -> None:
        """历史数据持续下降时, lifecycle 应为 declining。"""
        predictor = TrendPredictor()
        data = _make_historical_data(
            start_value=200, daily_delta=-5, days=21
        )
        result = predictor.predict(data, forecast_days=14)
        assert result["lifecycle"] == "declining"

    def test_lifecycle_peak_for_flat_trend(self) -> None:
        """历史数据平稳时, lifecycle 应为 peak。"""
        predictor = TrendPredictor()
        data = _make_historical_data(
            start_value=150, daily_delta=0, days=21
        )
        result = predictor.predict(data, forecast_days=14)
        assert result["lifecycle"] == "peak"

    # --- 增长率 ---

    def test_growth_rate_positive_for_rising(self) -> None:
        """上升趋势的周环比增长率应为正。"""
        predictor = TrendPredictor()
        data = _make_historical_data(
            start_value=100, daily_delta=2, days=21
        )
        rate = predictor._calculate_growth_rate(data)
        assert rate > 0

    def test_growth_rate_negative_for_declining(self) -> None:
        """下降趋势的周环比增长率应为负。"""
        predictor = TrendPredictor()
        data = _make_historical_data(
            start_value=200, daily_delta=-2, days=21
        )
        rate = predictor._calculate_growth_rate(data)
        assert rate < 0

    def test_growth_rate_zero_for_flat(self) -> None:
        """平稳趋势的周环比增长率应接近 0。"""
        predictor = TrendPredictor()
        data = _make_historical_data(
            start_value=150, daily_delta=0, days=21
        )
        rate = predictor._calculate_growth_rate(data)
        assert abs(rate) < 1.0  # 接近 0

    def test_growth_rate_insufficient_data(self) -> None:
        """数据不足一周时增长率应返回 0.0 (不抛异常)。"""
        predictor = TrendPredictor()
        data = _make_historical_data(
            start_value=100, daily_delta=2, days=3
        )
        rate = predictor._calculate_growth_rate(data)
        assert rate == 0.0

    # --- 线性降级 ---

    def test_linear_fallback_returns_correct_count(self) -> None:
        """线性降级应返回 forecast_days 条预测。"""
        predictor = TrendPredictor()
        data = _make_historical_data(
            start_value=100, daily_delta=2, days=21
        )
        predicted = predictor._linear_fallback(data, forecast_days=14)
        assert len(predicted) == 14
        for item in predicted:
            assert "date" in item
            assert "value" in item

    def test_linear_fallback_extrapolates_upward(self) -> None:
        """上升数据的线性外推预测值应大于最后一个历史值。"""
        predictor = TrendPredictor()
        data = _make_historical_data(
            start_value=100, daily_delta=5, days=21
        )
        predicted = predictor._linear_fallback(data, forecast_days=7)
        last_historical = data[-1]["value"]
        # 预测值应呈上升趋势 (最后一个预测 > 最后一个历史值)
        assert predicted[-1]["value"] > last_historical

    def test_linear_fallback_extrapolates_downward(self) -> None:
        """下降数据的线性外推预测值应小于最后一个历史值。"""
        predictor = TrendPredictor()
        data = _make_historical_data(
            start_value=200, daily_delta=-5, days=21
        )
        predicted = predictor._linear_fallback(data, forecast_days=7)
        last_historical = data[-1]["value"]
        assert predicted[-1]["value"] < last_historical

    def test_linear_fallback_dates_continue_from_last(self) -> None:
        """线性降级的预测日期应从最后历史日期的次日开始。"""
        predictor = TrendPredictor()
        data = _make_historical_data(
            start_value=100, daily_delta=2, days=21
        )
        predicted = predictor._linear_fallback(data, forecast_days=7)
        last_date = datetime.strptime(data[-1]["date"], "%Y-%m-%d")
        first_pred_date = datetime.strptime(predicted[0]["date"], "%Y-%m-%d")
        assert (first_pred_date - last_date).days == 1

    def test_predict_works_without_prophet(self) -> None:
        """Prophet 未安装时 predict() 应通过线性降级正常工作。"""
        predictor = TrendPredictor()
        data = _make_historical_data(
            start_value=100, daily_delta=3, days=21
        )
        # 不应抛异常, 应通过线性降级返回结果
        result = predictor.predict(data, forecast_days=14)
        assert len(result["predicted_values"]) == 14
        assert result["lifecycle"] in ("rising", "peak", "declining")

    # --- Prophet 路径 (mock) ---

    def test_predict_uses_prophet_when_available(self) -> None:
        """Prophet 可用时, _prophet_predict 应被调用并返回预测结果。"""
        predictor = TrendPredictor()
        data = _make_historical_data(
            start_value=100, daily_delta=2, days=21
        )

        # Mock _prophet_predict 返回固定预测列表
        mock_predicted = [
            {"date": f"2025-01-{22 + i:02d}", "value": 142.0 + i}
            for i in range(7)
        ]
        with patch.object(
            predictor,
            "_prophet_predict",
            return_value=mock_predicted,
        ) as mock_prophet:
            result = predictor.predict(data, forecast_days=7)
            mock_prophet.assert_called_once()
            assert len(result["predicted_values"]) == 7

    def test_prophet_predict_returns_list_of_dicts(self) -> None:
        """_prophet_predict 应返回 list[dict] (含 date/value)。

        若 Prophet 未安装, 该方法应抛出 ImportError (由调用方降级)。
        """
        predictor = TrendPredictor()
        import pandas as pd

        df = pd.DataFrame(
            {
                "ds": pd.date_range("2025-01-01", periods=14),
                "y": [100 + i * 2 for i in range(14)],
            }
        )
        try:
            result = predictor._prophet_predict(df, forecast_days=7)
            # Prophet 可用时验证结构
            assert isinstance(result, list)
            for item in result:
                assert "date" in item
                assert "value" in item
        except ImportError:
            # Prophet 未安装, 允许抛 ImportError
            pytest.skip("Prophet 未安装, 跳过 Prophet 路径验证")

    # --- 边界场景 ---

    def test_predict_empty_data(self) -> None:
        """空历史数据不应抛异常。"""
        predictor = TrendPredictor()
        result = predictor.predict([], forecast_days=14)
        assert result["lifecycle"] in ("rising", "peak", "declining")
        assert isinstance(result["predicted_values"], list)

    def test_predict_single_data_point(self) -> None:
        """单条历史数据不应抛异常。"""
        predictor = TrendPredictor()
        data = [{"date": "2025-01-01", "value": 100.0}]
        result = predictor.predict(data, forecast_days=7)
        assert isinstance(result["predicted_values"], list)

    def test_determine_lifecycle_rising(self) -> None:
        """预测值上升时 _determine_lifecycle 应返回 rising。"""
        predictor = TrendPredictor()
        historical = _make_historical_data(100, 2, days=14)
        predicted = [
            {"date": f"2025-01-{15+i:02d}", "value": 130 + i * 2}
            for i in range(7)
        ]
        assert predictor._determine_lifecycle(historical, predicted) == "rising"

    def test_determine_lifecycle_declining(self) -> None:
        """预测值下降时 _determine_lifecycle 应返回 declining。"""
        predictor = TrendPredictor()
        historical = _make_historical_data(200, -2, days=14)
        predicted = [
            {"date": f"2025-01-{15+i:02d}", "value": 170 - i * 2}
            for i in range(7)
        ]
        assert predictor._determine_lifecycle(historical, predicted) == "declining"

    def test_determine_lifecycle_peak(self) -> None:
        """预测值平稳时 _determine_lifecycle 应返回 peak。"""
        predictor = TrendPredictor()
        historical = _make_historical_data(150, 0, days=14)
        predicted = [
            {"date": f"2025-01-{15+i:02d}", "value": 150.0}
            for i in range(7)
        ]
        assert predictor._determine_lifecycle(historical, predicted) == "peak"
