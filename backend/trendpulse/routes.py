# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - TrendPulse API 路由 (Task 7)
# ==============================================================================
# 对应 spec §3.3 跨区域趋势对比引擎 + TrendPulse 微服务 API
#
# 本模块提供 TrendPulse 数据感知层的 REST API:
#   GET  /health                - 健康检查
#   GET  /trends                - 趋势列表 (按 topic 去重, 聚合多区域)
#   GET  /trends/{topic}        - 趋势详情 (含多区域信号)
#   GET  /cross-region/{topic}  - 跨区域对比 (扩散路径/跟进窗口/热度图/本地化)
#   POST /collect               - 触发数据采集 (返回采集摘要)
#
# 设计要点:
#   - TrendStore: 内存存储 (demo 模式), 结构对齐真实数据接入
#   - 通过 FastAPI 依赖注入 (Depends) 暴露 store, 便于测试与替换
#   - demo 数据在 seed_demo_data() 中种子化, 覆盖多 topic × 多区域 × 多 lifecycle
#   - POST /collect 在 demo 模式重载种子数据并返回采集摘要
#     (生产环境可替换为调用真实 collectors)
# ==============================================================================

"""
TrendPulse API 路由模块。

核心组件:
    - TrendStore : 内存趋势信号存储 (demo 模式, 可替换为真实数据源)
    - router     : FastAPI APIRouter, 暴露 /trends /cross-region /collect /health
    - get_store  : 依赖注入函数, 从 app.state 获取 TrendStore

用法 (在 main.py 中)::

    app = FastAPI(...)
    app.state.trend_store = TrendStore()
    app.state.trend_store.seed_demo_data()
    app.include_router(router)
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, status

from shared.models import TrendSignal
from trendpulse.collectors.utils import setup_logger
from trendpulse.cross_region import CrossRegionComparator

logger = setup_logger(__name__)


# ==============================================================================
# TrendStore - 内存趋势信号存储 (demo 模式)
# ==============================================================================


class TrendStore:
    """TrendPulse 趋势信号内存存储 (demo 模式)。

    以 topic 为键存储多区域 TrendSignal 列表, 提供:
        - add_signal / add_signals : 写入信号
        - get_signals              : 按 topic 读取信号列表
        - get_topics               : 获取所有 topic (去重)
        - get_all_signals          : 获取全部信号
        - clear / seed_demo_data   : 清空 / 种子化 demo 数据

    设计说明:
        - demo 模式使用内存存储, 重启即丢失
        - 结构对齐真实数据接入: 替换 seed_demo_data/collect 即可对接 collectors
        - 同一 topic 可含多个区域的信号 (跨区域对比的基础)
    """

    def __init__(self) -> None:
        self._signals: Dict[str, List[TrendSignal]] = {}

    def add_signal(self, signal: TrendSignal) -> None:
        """写入单条趋势信号。"""
        self._signals.setdefault(signal.topic, []).append(signal)

    def add_signals(self, signals: List[TrendSignal]) -> None:
        """写入多条趋势信号。"""
        for s in signals:
            self.add_signal(s)

    def get_signals(self, topic: str) -> List[TrendSignal]:
        """读取指定 topic 的全部区域信号 (无则返回空列表)。"""
        return list(self._signals.get(topic, []))

    def get_topics(self) -> List[str]:
        """获取所有 topic (按插入顺序, 已天然去重)。"""
        return list(self._signals.keys())

    def get_all_signals(self) -> List[TrendSignal]:
        """获取全部信号 (扁平化)。"""
        flat: List[TrendSignal] = []
        for sigs in self._signals.values():
            flat.extend(sigs)
        return flat

    def clear(self) -> None:
        """清空存储。"""
        self._signals.clear()

    def seed_demo_data(self) -> int:
        """种子化 demo 数据 (覆盖多 topic × 多区域 × 多 lifecycle)。

        Returns:
            种子化的信号总数
        """
        self.clear()
        self.add_signals(_build_demo_signals())
        count = len(self.get_all_signals())
        logger.info(f"TrendStore: demo 数据已种子化, 共 {count} 条信号")
        return count


# ==============================================================================
# Demo 数据构造 (覆盖跨区域扩散场景)
# ==============================================================================


def _build_demo_signals() -> List[TrendSignal]:
    """构造 demo 趋势信号 (覆盖跨区域扩散 / 跟进窗口 / 本地化场景)。

    包含 3 个 topic:
        1. 侘寂风家居   : eu declining + us peak + china rising (典型扩散+本地化)
        2. Y2K千禧风穿搭 : us peak + sea rising (海外→东南亚扩散)
        3. 多巴胺彩色配色: china peak + us rising (中国领先海外)
    """
    signals: List[TrendSignal] = []

    # --- topic 1: 侘寂风家居 (eu declining → us peak → china rising) ---
    topic1 = "侘寂风家居"
    signals.append(
        TrendSignal(
            topic=topic1,
            heatScore=32.0,
            growthRate=-12.5,
            category="家居/装饰",
            sentiment=0.4,
            lifecycle="declining",
            predictWindow="1-2周",
            relatedKeywords=["侘寂", "极简", "自然质感"],
            sourceBreakdown={"instagram": 60, "tiktok": 40},
            region="eu",
            zGenTags=["侘寂"],
            targetAudience={"ageRange": "25-35", "aesthetic": "侘寂", "spendingPower": "中"},
            crossRegionDiff={"eu": "declining", "us": "peak", "china": "rising"},
        )
    )
    signals.append(
        TrendSignal(
            topic=topic1,
            heatScore=88.0,
            growthRate=6.2,
            category="家居/装饰",
            sentiment=0.7,
            lifecycle="peak",
            predictWindow="2-4周",
            relatedKeywords=["wabi-sabi", "minimalist", "natural"],
            sourceBreakdown={"tiktok": 70, "instagram": 30},
            region="us",
            zGenTags=["侘寂"],
            targetAudience={"ageRange": "22-30", "aesthetic": "侘寂", "spendingPower": "中"},
            crossRegionDiff={"eu": "declining", "us": "peak", "china": "rising"},
        )
    )
    signals.append(
        TrendSignal(
            topic=topic1,
            heatScore=45.0,
            growthRate=34.2,
            category="家居/装饰",
            sentiment=0.6,
            lifecycle="rising",
            predictWindow="2-4周",
            relatedKeywords=["侘寂风", "极简家居", "自然质感"],
            sourceBreakdown={"xiaohongshu": 55, "douyin": 45},
            region="china",
            zGenTags=["侘寂", "新中式"],
            targetAudience={"ageRange": "18-28", "aesthetic": "侘寂", "spendingPower": "中"},
            crossRegionDiff={"eu": "declining", "us": "peak", "china": "rising"},
        )
    )

    # --- topic 2: Y2K千禧风穿搭 (us peak → sea rising) ---
    topic2 = "Y2K千禧风穿搭"
    signals.append(
        TrendSignal(
            topic=topic2,
            heatScore=82.0,
            growthRate=8.5,
            category="服饰/穿搭",
            sentiment=0.65,
            lifecycle="peak",
            predictWindow="2-4周",
            relatedKeywords=["Y2K", "千禧风", "低腰"],
            sourceBreakdown={"tiktok": 80, "instagram": 20},
            region="us",
            zGenTags=["Y2K"],
            targetAudience={"ageRange": "16-24", "aesthetic": "Y2K", "spendingPower": "中"},
            crossRegionDiff={"us": "peak", "sea": "rising"},
        )
    )
    signals.append(
        TrendSignal(
            topic=topic2,
            heatScore=38.0,
            growthRate=28.7,
            category="服饰/穿搭",
            sentiment=0.55,
            lifecycle="rising",
            predictWindow="3-6周",
            relatedKeywords=["Y2K", "复古", "金属"],
            sourceBreakdown={"tiktok": 60, "instagram": 40},
            region="sea",
            zGenTags=["Y2K"],
            targetAudience={"ageRange": "16-24", "aesthetic": "Y2K", "spendingPower": "低"},
            crossRegionDiff={"us": "peak", "sea": "rising"},
        )
    )

    # --- topic 3: 多巴胺彩色配色 (china peak, us rising - 中国领先) ---
    topic3 = "多巴胺彩色配色"
    signals.append(
        TrendSignal(
            topic=topic3,
            heatScore=90.0,
            growthRate=4.1,
            category="美妆/个护",
            sentiment=0.8,
            lifecycle="peak",
            predictWindow="2-4周",
            relatedKeywords=["多巴胺", "彩色", "撞色"],
            sourceBreakdown={"xiaohongshu": 50, "douyin": 50},
            region="china",
            zGenTags=["多巴胺"],
            targetAudience={"ageRange": "18-25", "aesthetic": "多巴胺", "spendingPower": "中"},
            crossRegionDiff={"china": "peak", "us": "rising"},
        )
    )
    signals.append(
        TrendSignal(
            topic=topic3,
            heatScore=42.0,
            growthRate=22.3,
            category="美妆/个护",
            sentiment=0.7,
            lifecycle="rising",
            predictWindow="3-6周",
            relatedKeywords=["dopamine", "colorful", "bright"],
            sourceBreakdown={"tiktok": 70, "instagram": 30},
            region="us",
            zGenTags=["多巴胺"],
            targetAudience={"ageRange": "18-25", "aesthetic": "多巴胺", "spendingPower": "中"},
            crossRegionDiff={"china": "peak", "us": "rising"},
        )
    )

    return signals


# ==============================================================================
# 数据源清单 (POST /collect 摘要用)
# ==============================================================================

_DATA_SOURCES = [
    "xiaohongshu",
    "douyin",
    "ecommerce",
    "search_index",
    "tiktok",
    "instagram",
]


# ==============================================================================
# FastAPI 路由
# ==============================================================================

router = APIRouter(tags=["trendpulse"])


def get_store(request: Request) -> TrendStore:
    """依赖注入: 从 app.state 获取 TrendStore。"""
    return request.app.state.trend_store  # type: ignore[no-any-return]


def _signal_to_dict(signal: TrendSignal) -> Dict[str, Any]:
    """将 TrendSignal 序列化为 JSON 友好的 dict。"""
    return signal.model_dump()


# ------------------------------------------------------------------------------
# GET /health
# ------------------------------------------------------------------------------


@router.get("/health")
async def health() -> Dict[str, str]:
    """健康检查端点。"""
    return {"status": "healthy", "service": "trendpulse"}


# ------------------------------------------------------------------------------
# GET /trends
# ------------------------------------------------------------------------------


@router.get("/trends")
async def list_trends(
    store: TrendStore = Depends(get_store),
) -> List[Dict[str, Any]]:
    """列出所有趋势 (按 topic 去重, 聚合多区域信号)。

    每条返回:
        ``{topic, region_count, regions, max_heat, lifecycle_summary}``
    """
    comparator = CrossRegionComparator()
    topics = store.get_topics()
    result: List[Dict[str, Any]] = []
    for topic in topics:
        signals = store.get_signals(topic)
        heat_map = comparator.generate_heat_map(signals)
        max_heat = max(heat_map.values()) if heat_map else 0.0
        # lifecycle 汇总: {region: lifecycle}
        lifecycle_summary = {s.region: s.lifecycle for s in signals}
        result.append(
            {
                "topic": topic,
                "region_count": len(signals),
                "regions": [s.region for s in signals],
                "max_heat": max_heat,
                "lifecycle_summary": lifecycle_summary,
            }
        )
    return result


# ------------------------------------------------------------------------------
# GET /trends/{topic}
# ------------------------------------------------------------------------------


@router.get("/trends/{topic}")
async def get_trend(
    topic: str,
    store: TrendStore = Depends(get_store),
) -> Dict[str, Any]:
    """获取指定 topic 的趋势详情 (含多区域信号列表)。"""
    signals = store.get_signals(topic)
    if not signals:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"趋势话题 '{topic}' 不存在",
        )
    return {
        "topic": topic,
        "region_count": len(signals),
        "signals": [_signal_to_dict(s) for s in signals],
    }


# ------------------------------------------------------------------------------
# GET /cross-region/{topic}
# ------------------------------------------------------------------------------


@router.get("/cross-region/{topic}")
async def cross_region_compare(
    topic: str,
    store: TrendStore = Depends(get_store),
) -> Dict[str, Any]:
    """跨区域趋势对比 (扩散路径/跟进窗口/热度图/本地化建议)。"""
    signals = store.get_signals(topic)
    if not signals:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"趋势话题 '{topic}' 不存在",
        )
    comparator = CrossRegionComparator()
    return comparator.compare(signals)


# ------------------------------------------------------------------------------
# POST /collect
# ------------------------------------------------------------------------------


@router.post("/collect")
async def collect(
    store: TrendStore = Depends(get_store),
) -> Dict[str, Any]:
    """触发数据采集 (demo 模式: 重载种子数据并返回采集摘要)。

    生产环境可替换为调用各 collectors (xiaohongshu/douyin/tiktok/...),
    此处保持接口契约一致, demo 模式同步返回完成摘要。
    """
    logger.info("POST /collect: 触发数据采集 (demo 模式重载种子数据)")

    # demo 模式: 重载种子数据 (模拟一次完整采集)
    total = store.seed_demo_data()

    # 构造采集摘要: 每个数据源的采集状态与计数
    all_signals = store.get_all_signals()
    source_counts: Dict[str, int] = {}
    for s in all_signals:
        for src in s.sourceBreakdown:
            source_counts[src] = source_counts.get(src, 0) + 1

    sources: List[Dict[str, Any]] = []
    for name in _DATA_SOURCES:
        sources.append(
            {
                "name": name,
                "status": "ok",
                "count": source_counts.get(name, 0),
            }
        )

    return {
        "status": "completed",
        "sources": sources,
        "total_signals": total,
    }


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["TrendStore", "router", "get_store"]
