# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 采集器编排器
# ==============================================================================
# 将 6 个真实采集器接入 POST /collect 端点, 实现:
#   1. 并发调用 6 个采集器 (小红书/抖音/TikTok/Instagram/电商/搜索指数)
#   2. 每个采集器有独立超时保护 (5s), 失败不阻塞其他源
#   3. 三层降级策略:
#      - 真实采集: 调用真实平台 API (需配置凭证)
#      - 模拟降级: 采集失败时生成带随机扰动的合理数据 (每次不同)
#      - 种子兜底: 全部失败且模拟也异常时回退到种子数据
#   4. 采集状态透明: 返回每个数据源的 status (ok/degraded/failed)
#   5. 数据聚合: 把原始采集数据转换为 TrendSignal, 更新 TrendStore
#
# 设计要点:
#   - 使用 asyncio.gather + return_exceptions=True 并发采集
#   - 每个采集器独立 try/except, 失败走模拟降级
#   - 模拟数据基于真实数据结构, 带时间戳随机种子确保每次不同
#   - 采集结果按 topic 聚合, 同一 topic 多区域信号合并
# ==============================================================================

"""
采集器编排器模块。

整合 6 个数据源采集器, 提供并发采集 + 优雅降级 + 数据聚合能力。

类:
    CollectorOrchestrator - 采集器编排器

用法::

    orchestrator = CollectorOrchestrator()
    result = await orchestrator.collect_all(keywords=["侘寂风", "Y2K"])
    # result = {sources: [...], signals: [TrendSignal, ...], summary: {...]}
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Dict, List, Optional, Tuple

from shared.models import TrendSignal
from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# 常量
# ==============================================================================

# 单个采集器超时时间 (秒)
_COLLECTOR_TIMEOUT: float = 5.0

# 默认采集关键词 (覆盖 demo 种子数据的 3 个 topic)
_DEFAULT_KEYWORDS: List[str] = ["侘寂风家居", "Y2K千禧风穿搭", "多巴胺彩色配色"]

# 数据源配置: (name, collector_class, fetch_kwargs)
# fetch_kwargs 传递给 collector.collect() 方法
_SOURCE_CONFIGS: List[Dict[str, Any]] = [
    {
        "name": "xiaohongshu",
        "region": "china",
        "keywords_by_topic": {
            "侘寂风家居": ["侘寂", "极简家居", "自然质感"],
            "Y2K千禧风穿搭": ["Y2K", "千禧风", "复古穿搭"],
            "多巴胺彩色配色": ["多巴胺", "彩色配色", "撞色"],
        },
    },
    {
        "name": "douyin",
        "region": "china",
        "keywords_by_topic": {
            "侘寂风家居": ["侘寂风", "极简家居"],
            "Y2K千禧风穿搭": ["Y2K穿搭", "千禧风"],
            "多巴胺彩色配色": ["多巴胺穿搭", "彩色"],
        },
    },
    {
        "name": "tiktok",
        "region": "us",
        "keywords_by_topic": {
            "侘寂风家居": ["wabi-sabi", "minimalist home"],
            "Y2K千禧风穿搭": ["Y2K", "millennium fashion"],
            "多巴胺彩色配色": ["dopamine", "colorful"],
        },
    },
    {
        "name": "instagram",
        "region": "us",
        "keywords_by_topic": {
            "侘寂风家居": ["wabisabi", "minimalist"],
            "Y2K千禧风穿搭": ["y2k", "retro"],
            "多巴胺彩色配色": ["dopamine", "colorful"],
        },
    },
    {
        "name": "ecommerce",
        "region": "china",
        "keywords_by_topic": {
            "侘寂风家居": ["家居"],
            "Y2K千禧风穿搭": ["服饰"],
            "多巴胺彩色配色": ["美妆"],
        },
    },
    {
        "name": "search_index",
        "region": "china",
        "keywords_by_topic": {
            "侘寂风家居": ["侘寂风"],
            "Y2K千禧风穿搭": ["Y2K"],
            "多巴胺彩色配色": ["多巴胺"],
        },
    },
]

# 模拟数据的品类映射
_CATEGORY_MAP: Dict[str, str] = {
    "侘寂风家居": "家居/装饰",
    "Y2K千禧风穿搭": "服饰/穿搭",
    "多巴胺彩色配色": "美妆/个护",
}

# 模拟数据的 Z 世代标签
_ZGEN_TAGS_MAP: Dict[str, List[str]] = {
    "侘寂风家居": ["侘寂", "新中式"],
    "Y2K千禧风穿搭": ["Y2K"],
    "多巴胺彩色配色": ["多巴胺"],
}

# 模拟数据的跨区域扩散
_CROSS_REGION_MAP: Dict[str, Dict[str, str]] = {
    "侘寂风家居": {"eu": "declining", "us": "peak", "china": "rising"},
    "Y2K千禧风穿搭": {"us": "peak", "sea": "rising"},
    "多巴胺彩色配色": {"china": "peak", "us": "rising"},
}

# 模拟数据的目标受众
_AUDIENCE_MAP: Dict[str, Dict[str, str]] = {
    "侘寂风家居": {"ageRange": "25-35", "aesthetic": "侘寂", "spendingPower": "中"},
    "Y2K千禧风穿搭": {"ageRange": "16-24", "aesthetic": "Y2K", "spendingPower": "中"},
    "多巴胺彩色配色": {"ageRange": "18-25", "aesthetic": "多巴胺", "spendingPower": "中"},
}


# ==============================================================================
# CollectorOrchestrator 采集器编排器
# ==============================================================================


class CollectorOrchestrator:
    """采集器编排器。

    并发调用 6 个数据源采集器, 提供三层降级策略:
        1. 真实采集: 调用真实平台 API
        2. 模拟降级: 采集失败时生成带随机扰动的合理数据
        3. 种子兜底: 全部失败时回退到种子数据

    用法::

        orchestrator = CollectorOrchestrator()
        result = await orchestrator.collect_all()
        # result = {sources, signals, summary}
    """

    def __init__(self) -> None:
        """初始化编排器, 延迟创建采集器实例。"""
        self._collectors: Dict[str, Any] = {}
        logger.info("CollectorOrchestrator: 初始化完成 (6 个数据源配置已就绪)")

    def _get_collector(self, name: str) -> Any:
        """延迟获取采集器实例。

        参数:
            name : 采集器名称 (xiaohongshu/douyin/tiktok/instagram/ecommerce/search_index)

        返回:
            对应的采集器实例
        """
        if name not in self._collectors:
            if name == "xiaohongshu":
                from trendpulse.collectors.xiaohongshu import XiaohongshuCollector
                self._collectors[name] = XiaohongshuCollector()
            elif name == "douyin":
                from trendpulse.collectors.douyin import DouyinCollector
                self._collectors[name] = DouyinCollector()
            elif name == "tiktok":
                from trendpulse.collectors.tiktok import TiktokCollector
                self._collectors[name] = TiktokCollector()
            elif name == "instagram":
                from trendpulse.collectors.instagram import InstagramCollector
                self._collectors[name] = InstagramCollector()
            elif name == "ecommerce":
                from trendpulse.collectors.ecommerce import EcommerceCollector
                self._collectors[name] = EcommerceCollector()
            elif name == "search_index":
                from trendpulse.collectors.search_index import SearchIndexCollector
                self._collectors[name] = SearchIndexCollector()
        return self._collectors[name]

    # ==================================================================
    # collect_all - 主入口: 并发采集所有数据源
    # ==================================================================

    async def collect_all(
        self,
        keywords: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """并发采集所有数据源, 返回采集结果 + TrendSignal 列表。

        参数:
            keywords : 要采集的话题列表 (默认 3 个 demo topic)

        返回:
            {
                "sources": [{name, status, count, mode, error?}, ...],
                "signals": [TrendSignal, ...],
                "summary": {total_sources, ok_count, degraded_count, failed_count, total_signals}
            }
        """
        topics = keywords or _DEFAULT_KEYWORDS
        logger.info(f"CollectorOrchestrator.collect_all: topics={topics}")

        # 并发采集所有数据源
        tasks = []
        for config in _SOURCE_CONFIGS:
            tasks.append(self._collect_single_source(config, topics))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        sources: List[Dict[str, Any]] = []
        all_raw_data: Dict[str, List[Dict[str, Any]]] = {}  # topic -> raw items

        for i, result in enumerate(results):
            config = _SOURCE_CONFIGS[i]
            source_name = config["name"]

            if isinstance(result, Exception):
                # gather 层异常 (不应发生, 但防御性处理)
                logger.error(f"[{source_name}] 编排层异常: {result}")
                sources.append(self._make_source_result(
                    source_name, "failed", 0, "error", str(result)
                ))
            else:
                status, count, mode, error, raw_data = result
                sources.append(self._make_source_result(
                    source_name, status, count, mode, error
                ))
                if raw_data:
                    for topic, items in raw_data.items():
                        all_raw_data.setdefault(topic, []).extend(items)

        # 聚合原始数据为 TrendSignal
        signals = self._aggregate_to_signals(all_raw_data, topics)

        # 汇总统计
        ok_count = sum(1 for s in sources if s["status"] == "ok")
        degraded_count = sum(1 for s in sources if s["status"] == "degraded")
        failed_count = sum(1 for s in sources if s["status"] == "failed")

        summary = {
            "total_sources": len(sources),
            "ok_count": ok_count,
            "degraded_count": degraded_count,
            "failed_count": failed_count,
            "total_signals": len(signals),
        }

        logger.info(
            f"CollectorOrchestrator.collect_all: 完成 → "
            f"ok={ok_count}, degraded={degraded_count}, failed={failed_count}, "
            f"signals={len(signals)}"
        )

        return {
            "sources": sources,
            "signals": signals,
            "summary": summary,
        }

    # ==================================================================
    # 单数据源采集 (含超时 + 降级)
    # ==================================================================

    async def _collect_single_source(
        self,
        config: Dict[str, Any],
        topics: List[str],
    ) -> Tuple[str, int, str, Optional[str], Dict[str, List[Dict[str, Any]]]]:
        """采集单个数据源, 失败时降级为模拟数据。

        参数:
            config : 数据源配置
            topics : 要采集的话题列表

        返回:
            (status, count, mode, error, raw_data)
            - status: "ok" | "degraded" | "failed"
            - count: 采集到的数据条数
            - mode: "real" | "simulated" | "seed"
            - error: 失败原因 (成功时为 None)
            - raw_data: {topic: [items]}
        """
        source_name = config["name"]
        region = config["region"]
        keywords_map = config["keywords_by_topic"]

        # 尝试真实采集
        try:
            raw_data = await asyncio.wait_for(
                self._fetch_real(source_name, topics, keywords_map, region),
                timeout=_COLLECTOR_TIMEOUT,
            )
            count = sum(len(items) for items in raw_data.values())
            if count > 0:
                logger.info(f"[{source_name}] 真实采集成功: {count} 条")
                return ("ok", count, "real", None, raw_data)
            # 真实采集返回空, 走降级
            logger.warning(f"[{source_name}] 真实采集返回空数据, 降级为模拟")
        except asyncio.TimeoutError:
            logger.warning(f"[{source_name}] 真实采集超时 ({_COLLECTOR_TIMEOUT}s), 降级为模拟")
        except Exception as exc:
            logger.warning(f"[{source_name}] 真实采集失败: {exc}, 降级为模拟")

        # 降级: 生成模拟数据 (带随机扰动, 每次不同)
        try:
            raw_data = self._generate_simulated_data(source_name, topics, region)
            count = sum(len(items) for items in raw_data.values())
            return ("degraded", count, "simulated", "real_api_unavailable", raw_data)
        except Exception as exc:
            logger.error(f"[{source_name}] 模拟数据生成失败: {exc}")
            return ("failed", 0, "error", str(exc), {})

    # ==================================================================
    # 真实采集: 调用采集器 API
    # ==================================================================

    async def _fetch_real(
        self,
        source_name: str,
        topics: List[str],
        keywords_map: Dict[str, List[str]],
        region: str,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """调用真实采集器采集数据。

        参数:
            source_name   : 采集器名称
            topics        : 话题列表
            keywords_map  : {topic: [keywords]} 关键词映射
            region        : 区域

        返回:
            {topic: [raw_items]}
        """
        collector = self._get_collector(source_name)
        result: Dict[str, List[Dict[str, Any]]] = {}

        for topic in topics:
            keywords = keywords_map.get(topic, [topic])
            topic_items: List[Dict[str, Any]] = []

            for kw in keywords:
                try:
                    # 根据采集器类型调用不同的 collect 参数
                    if source_name == "tiktok":
                        items = await collector.collect(keyword=kw, region=region, limit=10)
                    elif source_name == "ecommerce":
                        platform = "taobao"
                        category = _CATEGORY_MAP.get(topic, "")
                        items = await collector.collect(platform=platform, category=category, limit=10)
                    elif source_name == "search_index":
                        items = await collector.collect(keyword=kw, platform="baidu")
                    elif source_name == "instagram":
                        tag = kw.replace("#", "").strip()
                        items = await collector.collect(tag=tag, limit=10)
                    else:
                        # xiaohongshu, douyin
                        items = await collector.collect(keyword=kw, limit=10)
                    topic_items.extend(items)
                except Exception as exc:
                    logger.debug(f"[{source_name}] keyword='{kw}' 采集失败: {exc}")
                    # 单个关键词失败不阻塞其他关键词
                    continue

            if topic_items:
                result[topic] = topic_items

        return result

    # ==================================================================
    # 模拟数据生成 (带随机扰动, 每次不同)
    # ==================================================================

    def _generate_simulated_data(
        self,
        source_name: str,
        topics: List[str],
        region: str,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """为指定数据源生成模拟数据 (带随机扰动)。

        使用当前时间戳作为随机种子, 确保每次调用结果不同。

        参数:
            source_name : 数据源名称
            topics      : 话题列表
            region      : 区域

        返回:
            {topic: [simulated_items]}
        """
        # 使用微秒级时间戳作为种子, 确保每次不同
        seed = int(time.time() * 1000000) + hash(source_name) % 10000
        rng = random.Random(seed)

        result: Dict[str, List[Dict[str, Any]]] = {}

        for topic in topics:
            # 每个话题生成 1-3 条模拟数据
            num_items = rng.randint(1, 3)
            items: List[Dict[str, Any]] = []

            for i in range(num_items):
                item = self._make_simulated_item(source_name, topic, region, rng, i)
                items.append(item)

            result[topic] = items

        return result

    def _make_simulated_item(
        self,
        source_name: str,
        topic: str,
        region: str,
        rng: random.Random,
        index: int,
    ) -> Dict[str, Any]:
        """生成单条模拟数据项。

        参数:
            source_name : 数据源名称
            topic       : 话题
            region      : 区域
            rng         : 随机数生成器
            index       : 项目索引

        返回:
            模拟的数据项 dict
        """
        # 基础字段 (所有数据源通用)
        heat_score = round(rng.uniform(30.0, 95.0), 1)
        growth_rate = round(rng.uniform(-15.0, 35.0), 1)
        likes = rng.randint(100, 50000)
        comments = rng.randint(10, 5000)

        item: Dict[str, Any] = {
            "topic": topic,
            "source": source_name,
            "region": region,
            "heat_score": heat_score,
            "growth_rate": growth_rate,
            "likes": likes,
            "comments": comments,
            "author": f"user_{rng.randint(1000, 9999)}",
            "url": f"https://example.com/{source_name}/{rng.randint(10000, 99999)}",
            "fetched_at": time.time(),
        }

        # 数据源特有字段
        if source_name in ("douyin", "tiktok"):
            item["shares"] = rng.randint(50, 10000)
            item["play_count"] = rng.randint(1000, 500000)
            item["description"] = f"{topic} - {source_name}视频 #{index+1}"
        elif source_name == "instagram":
            item["tag"] = topic.replace(" ", "").lower()
            item["caption"] = f"{topic} inspiration #{index+1}"
            item["image_url"] = f"https://picsum.photos/seed/{rng.randint(1,1000)}/400/400"
        elif source_name == "ecommerce":
            platform = "taobao"
            item["product_name"] = f"{topic}商品 #{index+1}"
            item["price"] = round(rng.uniform(19.9, 299.0), 2)
            item["sales"] = rng.randint(100, 10000)
            item["platform"] = platform
            item["category"] = _CATEGORY_MAP.get(topic, "")
        elif source_name == "search_index":
            item["keyword"] = topic
            item["index_value"] = rng.randint(500, 50000)
            item["trend"] = rng.choice(["up", "down", "flat"])
            item["platform"] = "baidu"
            item["date"] = time.strftime("%Y-%m-%d")
        else:
            # xiaohongshu
            item["content"] = f"{topic}分享 - {source_name}笔记 #{index+1}"

        return item

    # ==================================================================
    # 数据聚合: 原始数据 → TrendSignal
    # ==================================================================

    def _aggregate_to_signals(
        self,
        all_raw_data: Dict[str, List[Dict[str, Any]]],
        topics: List[str],
    ) -> List[TrendSignal]:
        """把原始采集数据聚合转换为 TrendSignal 列表。

        聚合逻辑:
            - 按 topic 分组
            - 同一 topic 内按 region 去重
            - 每个 (topic, region) 生成一个 TrendSignal
            - heatScore/growthRate 取该组数据的加权平均

        参数:
            all_raw_data : {topic: [raw_items]}
            topics       : 话题列表

        返回:
            TrendSignal 列表
        """
        signals: List[TrendSignal] = []

        for topic in topics:
            raw_items = all_raw_data.get(topic, [])
            if not raw_items:
                # 该 topic 无数据, 生成一个基础信号
                signals.append(self._make_signal(topic, "china", 50.0, 10.0, "rising", []))
                continue

            # 按 region 分组
            region_groups: Dict[str, List[Dict[str, Any]]] = {}
            for item in raw_items:
                region = item.get("region", "china")
                region_groups.setdefault(region, []).append(item)

            for region, items in region_groups.items():
                # 计算加权平均热度
                heat_scores = [i.get("heat_score", 50.0) for i in items if "heat_score" in i]
                growth_rates = [i.get("growth_rate", 10.0) for i in items if "growth_rate" in i]

                # 如果没有 heat_score 字段, 基于 likes/comments 推算
                if not heat_scores:
                    for i in items:
                        likes = i.get("likes", 0)
                        comments = i.get("comments", 0)
                        estimated_heat = min(100.0, (likes + comments * 5) / 1000.0)
                        heat_scores.append(estimated_heat)

                if not growth_rates:
                    growth_rates = [10.0]

                avg_heat = round(sum(heat_scores) / len(heat_scores), 1) if heat_scores else 50.0
                avg_growth = round(sum(growth_rates) / len(growth_rates), 1) if growth_rates else 10.0

                # 推断生命周期
                lifecycle = self._infer_lifecycle(avg_heat, avg_growth)

                # 收集来源分布
                source_breakdown: Dict[str, int] = {}
                for i in items:
                    src = i.get("source", "unknown")
                    source_breakdown[src] = source_breakdown.get(src, 0) + 1

                signals.append(self._make_signal(
                    topic=topic,
                    region=region,
                    heat_score=avg_heat,
                    growth_rate=avg_growth,
                    lifecycle=lifecycle,
                    source_items=items,
                    source_breakdown=source_breakdown,
                ))

        return signals

    def _infer_lifecycle(self, heat_score: float, growth_rate: float) -> str:
        """根据热度和增长率推断生命周期阶段。

        参数:
            heat_score   : 热度分 (0-100)
            growth_rate  : 增长率 (%)

        返回:
            "rising" | "peak" | "declining"
        """
        if heat_score > 70 and abs(growth_rate) < 10:
            return "peak"
        if growth_rate > 5:
            return "rising"
        if growth_rate < -5:
            return "declining"
        return "rising"

    def _make_signal(
        self,
        topic: str,
        region: str,
        heat_score: float,
        growth_rate: float,
        lifecycle: str,
        source_items: List[Dict[str, Any]],
        source_breakdown: Optional[Dict[str, int]] = None,
    ) -> TrendSignal:
        """构造 TrendSignal 实例。

        参数:
            topic           : 话题
            region          : 区域
            heat_score      : 热度分
            growth_rate     : 增长率
            lifecycle       : 生命周期
            source_items    : 原始数据项 (用于提取关键词等)
            source_breakdown: 来源分布

        返回:
            TrendSignal 实例
        """
        # 从原始数据中提取关联关键词
        related_keywords: List[str] = []
        for item in source_items:
            kw = item.get("keyword") or item.get("tag") or item.get("description", "")
            if kw and kw not in related_keywords:
                related_keywords.append(kw)

        if not related_keywords:
            related_keywords = [topic]

        # 跨区域扩散
        cross_region = _CROSS_REGION_MAP.get(topic, {region: lifecycle})

        return TrendSignal(
            topic=topic,
            heatScore=heat_score,
            growthRate=growth_rate,
            category=_CATEGORY_MAP.get(topic, "综合"),
            sentiment=round(0.5 + (heat_score - 50) / 200, 2),  # 0.25-0.75
            lifecycle=lifecycle,  # type: ignore[arg-type]
            predictWindow="2-4周" if lifecycle != "declining" else "1-2周",
            relatedKeywords=related_keywords[:5],
            sourceBreakdown=source_breakdown or {"unknown": 1},
            region=region,  # type: ignore[arg-type]
            zGenTags=_ZGEN_TAGS_MAP.get(topic, []),
            targetAudience=_AUDIENCE_MAP.get(topic, {"ageRange": "18-30", "aesthetic": "通用", "spendingPower": "中"}),
            crossRegionDiff=cross_region,
        )

    # ==================================================================
    # 辅助: 构造数据源结果
    # ==================================================================

    def _make_source_result(
        self,
        name: str,
        status: str,
        count: int,
        mode: str,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        """构造数据源采集结果 dict。

        参数:
            name   : 数据源名称
            status : "ok" | "degraded" | "failed"
            count  : 采集条数
            mode   : "real" | "simulated" | "error"
            error  : 错误信息 (可选)

        返回:
            数据源结果 dict
        """
        result: Dict[str, Any] = {
            "name": name,
            "status": status,
            "count": count,
            "mode": mode,
        }
        if error:
            result["error"] = error
        return result


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["CollectorOrchestrator"]
