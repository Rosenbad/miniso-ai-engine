# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 规模化漏斗过滤器 (Task 11)
# ==============================================================================
# 对应 spec §4.3 规模化漏斗:
#   万级趋势信号 → 千级概念 → 百级 ProductIdeaCard → Top100 爆品候选
#
# FunnelFilter 设计要点 (Phase 2 修复 — 动态阈值):
#   - filter_top100: 使用分位数动态阈值过滤, 按 hitScore 降序, 取前 100
#   - batch_run:     批量处理多条趋势, 逐条编排后合并过滤
#   - 阈值策略:      默认使用 P70 分位数 (前 30% 进入 Top100)
#                    最低保底阈值 0.01 (避免全零数据导致阈值过低)
#                    可通过环境变量 HIT_SCORE_PERCENTILE 调整分位数
#   - 上限:          TOP_N = 100
#
# 规模化漏斗 (spec §4.3):
#   Level 1 (万级): 全量趋势信号 (TrendSignal[])           ~10,000+
#   Level 2 (千级): TrendAnalyst + ProductPlanner 产出概念   ~1,000+
#   Level 3 (百级): AgentOrchestrator 产出 ProductIdeaCard  ~100+
#   Level 4 (Top100): FunnelFilter 动态阈值过滤               ≤100
# ==============================================================================

"""
规模化漏斗过滤器模块 (spec §4.3)。

实现万级→千级→百级→Top100 的漏斗筛选流程。

核心方法:
    - filter_top100: 使用分位数动态阈值过滤, 按 hitScore 降序, 取前 100
    - batch_run:     批量处理多条趋势信号, 逐条编排后合并过滤

阈值策略 (Phase 2 修复):
    原实现使用固定 0.7 阈值, 但 XGBoost 模型输出的 hitScore 均值约 0.04,
    导致几乎所有卡片被过滤掉。现改为分位数动态阈值:
    - 计算所有卡片 hitScore 的 P70 分位数 (前 30% 通过)
    - 最低保底阈值 0.01, 避免全零数据
    - 可通过参数或环境变量 HIT_SCORE_PERCENTILE 调整

用法::

    funnel = FunnelFilter()
    orchestrator = AgentOrchestrator()

    # 单批过滤
    filtered = funnel.filter_top100(all_cards)

    # 批量处理
    final_cards = funnel.batch_run(trend_list, orchestrator)
"""

from __future__ import annotations

import os
from typing import List, Optional

from shared.models import ProductIdeaCard, TrendSignal
from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# 常量
# ==============================================================================

# 默认分位数 (P70 = 前 30% 的卡片通过阈值)
DEFAULT_PERCENTILE: float = 70.0

# 最低保底阈值 (避免全零数据导致阈值过低)
MIN_THRESHOLD: float = 0.01

# 旧版固定阈值 (向后兼容, 仅用于日志对比)
LEGACY_FIXED_THRESHOLD: float = 0.7

# 最终保留的卡片数量上限
TOP_N: int = 100

# 向后兼容: 保留模块级常量 (旧代码可能直接引用 funnel.HIT_SCORE_THRESHOLD)
HIT_SCORE_THRESHOLD: float = LEGACY_FIXED_THRESHOLD


def _get_percentile_from_env() -> float:
    """从环境变量 HIT_SCORE_PERCENTILE 读取分位数 (默认 70)。"""
    raw = os.environ.get("HIT_SCORE_PERCENTILE", "")
    try:
        val = float(raw)
        if 0 < val < 100:
            return val
    except (ValueError, TypeError):
        pass
    return DEFAULT_PERCENTILE


def _compute_quantile_threshold(
    cards: List[ProductIdeaCard],
    percentile: float,
) -> float:
    """计算 hitScore 的分位数阈值。

    参数:
        cards:      ProductIdeaCard 列表
        percentile: 分位数 (0-100), 如 70 表示 P70

    返回:
        分位数阈值, 不低于 MIN_THRESHOLD
    """
    if not cards:
        return MIN_THRESHOLD

    scores = sorted([c.hitScore for c in cards])
    n = len(scores)

    # 计算分位数索引 (线性插值)
    rank = (percentile / 100.0) * (n - 1)
    lower = int(rank)
    upper = min(lower + 1, n - 1)
    frac = rank - lower
    threshold = scores[lower] + frac * (scores[upper] - scores[lower])

    # 保底阈值
    return max(threshold, MIN_THRESHOLD)


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
        Level 4 (Top100): FunnelFilter 动态阈值过滤

    阈值策略:
        使用分位数动态阈值 (默认 P70), 替代原固定 0.7 阈值。
        可通过构造函数 percentile 参数或环境变量 HIT_SCORE_PERCENTILE 调整。

    核心方法:
        - filter_top100(cards): 动态阈值过滤 + 排序 + 截断
        - batch_run(trends, orchestrator): 批量编排 + 过滤

    用法::

        funnel = FunnelFilter()
        filtered = funnel.filter_top100(all_cards)
        # filtered: hitScore > 动态阈值, 按 hitScore 降序, 最多 100 条
    """

    # 最终保留的卡片数量上限
    TOP_N: int = TOP_N

    # 最低保底阈值
    MIN_THRESHOLD: float = MIN_THRESHOLD

    def __init__(self, percentile: Optional[float] = None):
        """初始化漏斗过滤器。

        参数:
            percentile: 分位数 (0-100), 如 70 表示 P70 (前 30% 通过)。
                        None 时从环境变量 HIT_SCORE_PERCENTILE 读取, 默认 70。
        """
        self.percentile = percentile if percentile is not None else _get_percentile_from_env()
        # 上次过滤使用的动态阈值 (供外部读取, 如 API 返回)
        self._last_threshold: float = LEGACY_FIXED_THRESHOLD

    @property
    def HIT_SCORE_THRESHOLD(self) -> float:
        """向后兼容: 返回上次过滤使用的动态阈值。"""
        return self._last_threshold

    # ==================================================================
    # filter_top100 - 动态阈值过滤, 排序, 截断
    # ==================================================================

    def filter_top100(
        self, cards: List[ProductIdeaCard]
    ) -> List[ProductIdeaCard]:
        """使用动态分位数阈值过滤卡片, 按 hitScore 降序排列, 取前 100。

        对应 spec §4.3 Level 4 (Top100)。

        三步操作:
            1. 计算阈值: hitScore 的 P{percentile} 分位数 (不低于 0.01)
            2. 过滤+排序: 仅保留 hitScore > 阈值, 按 hitScore 降序排列
            3. 截断: 取前 TOP_N (100) 条

        参数:
            cards: ProductIdeaCard 列表 (AgentOrchestrator 输出)

        返回:
            过滤后的 ProductIdeaCard 列表:
            - 每张卡 hitScore > 动态阈值
            - 按 hitScore 降序排列
            - 长度 ≤ 100
        """
        # 1. 计算动态阈值
        threshold = _compute_quantile_threshold(cards, self.percentile)
        self._last_threshold = threshold

        # 2. 过滤: hitScore > 阈值 (严格大于)
        filtered = [
            card for card in cards if card.hitScore > threshold
        ]

        # 边界情况: 如果过滤后为空但输入非空, 取 top_n 条 (避免全被过滤)
        if not filtered and cards:
            filtered = list(cards)
            logger.warning(
                f"FunnelFilter.filter_top100: 动态阈值 {threshold:.4f} 过滤后为空, "
                f"保留全部 {len(cards)} 张卡"
            )

        # 3. 排序: 按 hitScore 降序
        filtered.sort(key=lambda c: c.hitScore, reverse=True)

        # 4. 截断: 取前 TOP_N 条
        result = filtered[: self.TOP_N]

        logger.info(
            f"FunnelFilter.filter_top100: 输入 {len(cards)} 张卡 → "
            f"动态阈值={threshold:.4f} (P{self.percentile:.0f}) → "
            f"过滤后 {len(filtered)} 张 → 截断至 {len(result)} 张 "
            f"(旧固定阈值={LEGACY_FIXED_THRESHOLD}, 上限={self.TOP_N})"
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
            过滤后的 ProductIdeaCard 列表 (动态阈值, 降序, ≤100)
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

__all__ = [
    "FunnelFilter",
    "HIT_SCORE_THRESHOLD",
    "TOP_N",
    "DEFAULT_PERCENTILE",
    "MIN_THRESHOLD",
    "LEGACY_FIXED_THRESHOLD",
]
