"""TrendPulse 数据处理器模块。

包含数据清洗、话题聚类、情感分析、趋势预测等 NLP 数据处理逻辑。

对应 spec §3.2 NLP 处理流水线:
    1. DataCleaner       - 清洗去噪 (去广告/去重/语言检测)
    2. TopicClusterer    - 话题聚类 (TF-IDF + KMeans, 生产环境替换为 BERTopic)
    3. SentimentAnalyzer - 情感分析 (SnowNLP 中文 + Z 世代审美标签)
    4. TrendPredictor    - 趋势预测 (Prophet 时序 + 线性外推降级)
"""

from trendpulse.processors.cleaner import DataCleaner
from trendpulse.processors.sentiment_analyzer import SentimentAnalyzer
from trendpulse.processors.topic_clusterer import TopicClusterer
from trendpulse.processors.trend_predictor import TrendPredictor

__all__ = [
    "DataCleaner",
    "TopicClusterer",
    "SentimentAnalyzer",
    "TrendPredictor",
]
