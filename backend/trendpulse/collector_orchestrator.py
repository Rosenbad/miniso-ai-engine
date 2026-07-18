# ==============================================================================
# 采集器编排器 - 使用免费公开数据源获取真实数据
# ==============================================================================
# 替代需要鉴权的采集器, 改用 3 个免费公开 API:
#   1. B站热门   - Z世代视频趋势 (bilibili.com)
#   2. 头条热榜   - 大众关注热点 (toutiao.com)
#   3. 豆瓣热门   - 影视文化消费 (douban.com)
#
# 工作流程:
#   1. 并发调用 3 个免费采集器获取真实热榜数据
#   2. 基于采集到的真实数据, 提取 Top N 热门话题作为趋势信号
#   3. 按 (topic, source) 聚合为 TrendSignal, 更新 TrendStore
#   4. 返回每个数据源的采集状态 (ok/failed) + 真实数据
#
# 降级策略:
#   - 真实采集: 调用免费公开 API (无需凭证)
#   - 模拟降级: 仅当免费 API 也不可用时才降级 (极端网络故障)
# ==============================================================================

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

from shared.models import TrendSignal
from trendpulse.collectors.free_sources import (
    BilibiliHotCollector,
    DoubanHotCollector,
    ToutiaoHotCollector,
)
from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# 常量
# ==============================================================================

_COLLECTOR_TIMEOUT: float = 10.0


# ==============================================================================
# CollectorOrchestrator 采集器编排器
# ==============================================================================


class CollectorOrchestrator:
    """采集器编排器。

    并发调用 3 个免费公开数据源采集器, 获取真实趋势数据。

    用法::

        orchestrator = CollectorOrchestrator()
        result = await orchestrator.collect_all()
        # result = {sources, signals, summary}
    """

    def __init__(self) -> None:
        """初始化编排器, 创建 3 个免费采集器实例。"""
        self._collectors: Dict[str, Any] = {
            "bilibili": BilibiliHotCollector(),
            "toutiao": ToutiaoHotCollector(),
            "douban": DoubanHotCollector(),
        }
        logger.info("CollectorOrchestrator: 初始化完成 (3 个免费数据源: B站/头条/豆瓣)")

    # ==================================================================
    # collect_all - 主入口: 并发采集所有数据源
    # ==================================================================

    async def collect_all(
        self,
        keywords: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """并发采集所有免费数据源, 返回真实趋势数据。

        参数:
            keywords : 保留参数 (免费数据源返回全站热榜, 不按关键词搜索)

        返回:
            {
                "sources": [{name, status, count, mode, error?}, ...],
                "signals": [TrendSignal, ...],
                "summary": {total_sources, ok_count, degraded_count, failed_count, total_signals}
            }
        """
        logger.info("CollectorOrchestrator.collect_all: 开始采集真实数据 (3 个免费源)")

        # 并发采集所有数据源
        tasks = []
        for name, collector in self._collectors.items():
            tasks.append(self._collect_single(name, collector))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        sources: List[Dict[str, Any]] = []
        all_raw_data: List[Dict[str, Any]] = []

        for i, result in enumerate(results):
            name = list(self._collectors.keys())[i]

            if isinstance(result, Exception):
                logger.error(f"[{name}] 编排层异常: {result}")
                sources.append(self._make_source_result(name, "failed", 0, "error", str(result)))
            else:
                status, count, mode, error, raw_data = result
                sources.append(self._make_source_result(name, status, count, mode, error))
                if raw_data:
                    all_raw_data.extend(raw_data)

        # 聚合原始数据为 TrendSignal
        signals = self._aggregate_to_signals(all_raw_data)

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
    # 单数据源采集 (含超时)
    # ==================================================================

    async def _collect_single(
        self,
        name: str,
        collector: Any,
    ) -> Tuple[str, int, str, Optional[str], List[Dict[str, Any]]]:
        """采集单个数据源。

        参数:
            name      : 数据源名称
            collector : 采集器实例

        返回:
            (status, count, mode, error, raw_data)
        """
        try:
            raw_data = await asyncio.wait_for(
                collector.collect(limit=15),
                timeout=_COLLECTOR_TIMEOUT,
            )
            count = len(raw_data)
            if count > 0:
                logger.info(f"[{name}] 真实采集成功: {count} 条")
                return ("ok", count, "real", None, raw_data)
            logger.warning(f"[{name}] 采集返回空数据")
            return ("degraded", 0, "simulated", "empty_result", [])
        except asyncio.TimeoutError:
            logger.warning(f"[{name}] 采集超时 ({_COLLECTOR_TIMEOUT}s)")
            return ("failed", 0, "error", f"timeout_{_COLLECTOR_TIMEOUT}s", [])
        except Exception as exc:
            logger.warning(f"[{name}] 采集失败: {exc}")
            return ("failed", 0, "error", str(exc), [])

    # ==================================================================
    # 数据聚合: 原始数据 → TrendSignal
    # ==================================================================

    def _aggregate_to_signals(
        self,
        all_raw_data: List[Dict[str, Any]],
    ) -> List[TrendSignal]:
        """把原始采集数据聚合转换为 TrendSignal 列表。

        聚合逻辑:
            - 每条原始数据项转换为一个 TrendSignal
            - 按热度排序, 取 Top 10
            - 为每个话题分配品类和标签

        参数:
            all_raw_data : 所有数据源的原始数据列表

        返回:
            TrendSignal 列表 (按热度降序, 最多 10 条)
        """
        if not all_raw_data:
            return []

        # 按热度排序
        sorted_data = sorted(
            all_raw_data,
            key=lambda x: x.get("heat_score", 0),
            reverse=True,
        )

        # 取 Top 10
        top_data = sorted_data[:10]

        signals: List[TrendSignal] = []
        for item in top_data:
            signal = self._make_signal_from_raw(item)
            if signal:
                signals.append(signal)

        return signals

    def _make_signal_from_raw(self, item: Dict[str, Any]) -> Optional[TrendSignal]:
        """从原始数据项构造 TrendSignal。

        参数:
            item : 原始数据项

        返回:
            TrendSignal 实例 (或 None)
        """
        topic = item.get("topic", "").strip()
        if not topic:
            return None

        source = item.get("source", "unknown")
        heat_score = float(item.get("heat_score", 50.0))
        growth_rate = float(item.get("growth_rate", 10.0))

        # 推断生命周期
        lifecycle = self._infer_lifecycle(heat_score, growth_rate)

        # 推断品类
        category = self._infer_category(topic, source)

        # 构造来源分布
        source_breakdown = {source: 100}

        return TrendSignal(
            topic=topic,
            heatScore=heat_score,
            growthRate=growth_rate,
            category=category,
            sentiment=round(0.5 + (heat_score - 50) / 200, 2),
            lifecycle=lifecycle,  # type: ignore[arg-type]
            predictWindow="2-4周" if lifecycle != "declining" else "1-2周",
            relatedKeywords=[topic],
            sourceBreakdown=source_breakdown,
            region="china",  # type: ignore[arg-type]
            zGenTags=self._infer_zgen_tags(source, category),
            targetAudience={"ageRange": "18-30", "aesthetic": "通用", "spendingPower": "中"},
            crossRegionDiff={"china": lifecycle},
        )

    def _infer_lifecycle(self, heat_score: float, growth_rate: float) -> str:
        """根据热度和增长率推断生命周期阶段。"""
        if heat_score > 70 and abs(growth_rate) < 10:
            return "peak"
        if growth_rate > 5:
            return "rising"
        if growth_rate < -5:
            return "declining"
        return "rising"

    def _infer_category(self, topic: str, source: str) -> str:
        """根据来源和话题推断品类。"""
        if source == "douban":
            return "影视/文化"
        if source == "bilibili":
            return "视频/娱乐"
        if source == "toutiao":
            return "社会/热点"
        return "综合"

    def _infer_zgen_tags(self, source: str, category: str) -> List[str]:
        """根据来源推断 Z 世代标签。"""
        if source == "bilibili":
            return ["Z世代", "视频原生"]
        if source == "douban":
            return ["文青", "品质消费"]
        if source == "toutiao":
            return ["大众趋势"]
        return []

    # ==================================================================
    # 辅助
    # ==================================================================

    def _make_source_result(
        self,
        name: str,
        status: str,
        count: int,
        mode: str,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        """构造数据源采集结果 dict。"""
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
