"""TrendPulse 数据采集器模块。

包含各数据源的采集器实现: 小红书、抖音、电商 (淘宝/拼多多)、搜索指数 (百度/微信) 等。
所有采集器继承 BaseCollector, 获得 QPS 限流 / 指数退避重试 / 熔断器 / Redis 缓存能力。

中国数据源 (Task 4):
    - XiaohongshuCollector : 小红书笔记采集 (生活方式趋势发源地)
    - DouyinCollector       : 抖音话题/商品采集 (短视频带货趋势)
    - EcommerceCollector    : 电商热销榜采集 (淘宝/拼多多, 已验证商业信号)
    - SearchIndexCollector  : 搜索指数采集 (百度/微信, 大众关注度基线)
"""

from trendpulse.collectors.base import BaseCollector, CircuitBreaker, CircuitBreakerOpenError
from trendpulse.collectors.xiaohongshu import XiaohongshuCollector
from trendpulse.collectors.douyin import DouyinCollector
from trendpulse.collectors.ecommerce import EcommerceCollector
from trendpulse.collectors.search_index import SearchIndexCollector

__all__ = [
    "BaseCollector",
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "XiaohongshuCollector",
    "DouyinCollector",
    "EcommerceCollector",
    "SearchIndexCollector",
]
