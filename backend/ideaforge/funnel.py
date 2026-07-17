# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 规模化漏斗过滤器 (Task 11)
# ==============================================================================
# 对应 spec §4.3 规模化漏斗:
#   万级趋势信号 → 千级概念 → 百级 ProductIdeaCard → Top100 爆品候选
#
# FunnelFilter 设计要点:
#   - filter_top100: 过滤 hitScore > 0.7, 按 hitScore 降序, 取前 100
#   - batch_run:     批量处理多条趋势, 逐条编排后合并过滤
#   - 阈值:          HIT_SCORE_THRESHOLD = 0.7 (严格大于)
#   - 上限:          TOP_N = 100
#
# 规模化漏斗 (spec §4.3):
#   Level 1 (万级): 全量趋势信号 (TrendSignal[])           ~10,000+
#   Level 2 (千级): TrendAnalyst + ProductPlanner 产出概念   ~1,000+
#   Level 3 (百级): AgentOrchestrator 产出 ProductIdeaCard  ~100+
#   Level 4 (Top100): FunnelFilter 过滤 hitScore > 0.7       ≤100
# ==============================================================================

"""
规模化漏斗过滤器模块 (spec §4.3)。

实现万级→千级→百级→Top100 的漏斗筛选流程。

核心方法:
    - filter_top100: 过滤 hitScore > 0.7, 按 hitScore 降序, 取前 100
    - batch_run:     批量处理多条趋势信号, 逐条编排后合并过滤

用法::

    funnel = FunnelFilter()
    orchestrator = AgentOrchestrator()

    # 单批过滤
    filtered = funnel.filter_top100(all_cards)

    # 批量处理
    final_cards = funnel.batch_run(trend_list, orchestrator)
"""

from __future__ import annotations

from typing import List

from shared.models import ProductIdeaCard, TrendSignal
from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# 常量
# ==============================================================================

# 爆品阈值: hitScore 严格大于此值才保留
HIT_SCORE_THRESHOLD: float = 0.7

# 最终保留的卡片数量上限
TOP_N: int = 100


# ==============================================================================
# FunnelFilter 规模化漏斗过滤器
# ==============================================================================


class FunnelFilter:
    """规模化漏斗过滤器 (spec §4.3)。

    实现万级→千级→百级→Top100 的漏斗筛选流程。

    漏斗阶段:
        Level 1 (万级): 全量趋势信号 (TrendSignal[])
        Level 2 (千级): TrendAnalyst + ProductPlanner 产出概念
        Level 3 (百级): AgentOrchestrator 产出 ProductIdeaCard
        Level 4 (Top100): FunnelFilter 过滤 hitScore > 0.7

    核心方法:
        - filter_top100(cards): 过滤 + 排序 + 截断
        - batch_run(trends, orchestrator): 批量编排 + 过滤

    用法::

        funnel = FunnelFilter()
        filtered = funnel.filter_top100(all_cards)
        # filtered: hitScore > 0.7, 按 hitScore 降序, 最多 100 条
    """

    # 爆品阈值 (hitScore 严格大于此值)
    HIT_SCORE_THRESHOLD: float = HIT_SCORE_THRESHOLD

    # 最终保留的卡片数量上限
    TOP_N: int = TOP_N

    # ==================================================================
    # filter_top100 - 过滤 hitScore > 0.7, 排序, 截断
    # ==================================================================

    def filter_top100(
        self, cards: List[ProductIdeaCard]
    ) -> List[ProductIdeaCard]:
        """过滤 hitScore > 0.7 的卡片, 按 hitScore 降序排列, 取前 100。

        对应 spec §4.3 Level 4 (Top100)。

        三步操作:
            1. 过滤: 仅保留 hitScore > 0.7 (严格大于)
            2. 排序: 按 hitScore 降序排列
            3. 截断: 取前 TOP_N (100) 条

        参数:
            cards: ProductIdeaCard 列表 (AgentOrchestrator 输出)

        返回:
            过滤后的 ProductIdeaCard 列表:
            - 每张卡 hitScore > 0.7
            - 按 hitScore 降序排列
            - 长度 ≤ 100
        """
        # 1. 过滤: hitScore > 阈值 (严格大于)
        filtered = [
            card for card in cards if card.hitScore > self.HIT_SCORE_THRESHOLD
        ]

        # 2. 排序: 按 hitScore 降序
        filtered.sort(key=lambda c: c.hitScore, reverse=True)

        # 3. 截断: 取前 TOP_N 条
        result = filtered[: self.TOP_N]

        logger.info(
            f"FunnelFilter.filter_top100: 输入 {len(cards)} 张卡 → "
            f"过滤后 {len(filtered)} 张 → 截断至 {len(result)} 张 "
            f"(阈值={self.HIT_SCORE_THRESHOLD}, 上限={self.TOP_N})"
        )

        return result

    # ==================================================================
    # batch_run - 批量处理多条趋势信号
    # ==================================================================

    def batch_run(
        self,
        trends: List[TrendSignal],
        orchestrator: "AgentOrchestrator",  # noqa: F821 (前向引用)
    ) -> List[ProductIdeaCard]:
        """批量处理多条趋势信号, 逐条编排后合并过滤。

        对应 spec §4.3 规模化漏斗完整流程:
            1. 对每条趋势信号调用 orchestrator.orchestrate()
            2. 合并所有趋势产出的 ProductIdeaCard
            3. 调用 filter_top100 进行过滤 + 排序 + 截断

        参数:
            trends:       趋势信号列表
            orchestrator: Agent 编排器实例

        返回:
            过滤后的 ProductIdeaCard 列表 (hitScore > 0.7, 降序, ≤100)
        """
        if not trends:
            logger.info("FunnelFilter.batch_run: 空趋势列表, 返回空列表")
            return []

        all_cards: List[ProductIdeaCard] = []

        # 逐条编排, 合并所有卡片
        for idx, trend in enumerate(trends, start=1):
            logger.info(
                f"FunnelFilter.batch_run: 处理趋势 {idx}/{len(trends)} "
                f"(topic='{trend.topic}')"
            )
            cards = orchestrator.orchestrate(trend)
            all_cards.extend(cards)

        logger.info(
            f"FunnelFilter.batch_run: {len(trends)} 条趋势 → "
            f"合计 {len(all_cards)} 张卡, 开始漏斗过滤"
        )

        # 合并后过滤
        result = self.filter_top100(all_cards)

        logger.info(
            f"FunnelFilter.batch_run: 最终产出 {len(result)} 张爆品候选卡"
        )

        return result


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["FunnelFilter", "HIT_SCORE_THRESHOLD", "TOP_N"]
