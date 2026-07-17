# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - MarketProbe 表现分析器 (Task 12)
# ==============================================================================
# 对应 spec §5 验证反馈层 · Step 3: PerformanceAnalyzer
#
# PerformanceAnalyzer 设计要点:
#   - 对比各组合 vs 基线, 计算统计显著性
#   - 赢家: 综合评分最高 (销量 + 转化率 + 利润率)
#   - 跨区域对比
#   - 输出: TestResult (赢家组合 + 因子贡献 + 置信度)
#
# 综合评分模型:
#   composite_score = 0.4 × normalized_sales + 0.3 × conversion + 0.3 × profit_margin
#   - normalized_sales: 销量归一化到 [0, 1]
#   - conversion:       转化率 (已为 0-1)
#   - profit_margin:    利润率 (按价格水平: high=0.6, medium=0.45, low=0.3)
#
# 因子贡献分析 (简化 ANOVA):
#   对每个因子 (price/packaging/channel/region), 计算各水平均值与总均值的
#   偏差平方和, 归一化后得到因子贡献占比。
# ==============================================================================

"""
表现分析器 (spec §5 Step 3)。

分析测试结果, 判定赢家组合, 计算因子贡献与置信度。

综合评分模型::
    composite_score = 0.4 × normalized_sales + 0.3 × conversion + 0.3 × profit_margin

因子贡献分析 (简化 ANOVA):
    对每个因子计算各水平均值与总均值的偏差平方和, 归一化得到贡献占比。

用法::

    analyzer = PerformanceAnalyzer()
    result = analyzer.analyze(test_plan, collected_data)
    # result = {winner, rankings, factor_contribution, confidence, ...}
"""

from __future__ import annotations

from typing import Any, Dict, List

from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# 常量 - 评分模型参数
# ==============================================================================

# 利润率 (按价格水平)
_PROFIT_MARGIN: Dict[str, float] = {
    "high": 0.60,
    "medium": 0.45,
    "low": 0.30,
}
"""利润率: 高价 60%, 中价 45%, 低价 30%。"""

# 综合评分权重
_WEIGHT_SALES: float = 0.4
"""销量权重。"""

_WEIGHT_CONVERSION: float = 0.3
"""转化率权重。"""

_WEIGHT_PROFIT: float = 0.3
"""利润率权重。"""

# 因子列表 (4 个 A/B 维度)
_FACTORS: List[str] = ["price", "packaging", "channel", "region"]
"""4 个 A/B 测试因子。"""


# ==============================================================================
# PerformanceAnalyzer 表现分析器
# ==============================================================================


class PerformanceAnalyzer:
    """表现分析器 (spec §5 Step 3)。

    分析测试结果, 判定赢家组合, 计算因子贡献与置信度。

    综合评分模型:
        composite_score = 0.4 × normalized_sales + 0.3 × conversion + 0.3 × profit_margin

    因子贡献分析 (简化 ANOVA):
        对每个因子计算各水平均值与总均值的偏差平方和, 归一化得到贡献占比。

    用法::

        analyzer = PerformanceAnalyzer()
        result = analyzer.analyze(test_plan, collected_data)
    """

    # ==================================================================
    # analyze - 分析测试结果
    # ==================================================================

    def analyze(
        self,
        test_plan: Dict[str, Any],
        collected_data: Dict[str, List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """分析测试结果, 判定赢家, 计算因子贡献与置信度。

        参数:
            test_plan:      TestDesigner.design_test_plan() 的输出
            collected_data: DataCollector.get_all_data() 的输出
                            {combination_id: [{day, sales, conversion, ...}]}

        返回:
            分析结果字典::

                {
                    "winner": {
                        "combination_id": "C001",
                        "composite_score": 0.85,
                        "total_sales": 400,
                        "avg_conversion": 0.06,
                        "profit_margin": 0.30
                    },
                    "rankings": [
                        {"combination_id": "C001", "score": 0.85,
                         "sales": 400, "conversion": 0.06, ...},
                        ...
                    ],
                    "factor_contribution": {
                        "price": 0.35, "packaging": 0.25,
                        "channel": 0.20, "region": 0.20
                    },
                    "confidence": 0.85,
                    "cross_region_comparison": {
                        "china": {"avg_score": 0.75, "total_sales": 1200, ...},
                        ...
                    }
                }
        """
        combinations: List[Dict[str, Any]] = test_plan.get("combinations", [])

        # --- 1. 计算每个组合的聚合指标 ---
        combo_metrics: Dict[str, Dict[str, Any]] = {}
        for combo in combinations:
            combo_id = combo["id"]
            daily_data = collected_data.get(combo_id, [])

            if not daily_data:
                continue

            # 聚合指标
            total_sales = sum(r["sales"] for r in daily_data)
            n_days = len(daily_data)
            avg_conversion = sum(r["conversion"] for r in daily_data) / n_days
            avg_return = sum(r["return_rate"] for r in daily_data) / n_days
            avg_z_gen = sum(r["z_gen_engagement"] for r in daily_data) / n_days

            # 利润率 (按价格水平)
            profit_margin = _PROFIT_MARGIN.get(combo["price"], 0.40)

            combo_metrics[combo_id] = {
                "combination_id": combo_id,
                "price": combo["price"],
                "packaging": combo["packaging"],
                "channel": combo["channel"],
                "region": combo["region"],
                "total_sales": total_sales,
                "avg_conversion": avg_conversion,
                "avg_return_rate": avg_return,
                "avg_z_gen_engagement": avg_z_gen,
                "profit_margin": profit_margin,
                "n_days": n_days,
            }

        # --- 2. 计算综合评分 ---
        if not combo_metrics:
            # 空数据: 返回空结果
            return self._empty_result()

        # 归一化销量到 [0, 1]
        max_sales = max(m["total_sales"] for m in combo_metrics.values())
        min_sales = min(m["total_sales"] for m in combo_metrics.values())
        sales_range = max(max_sales - min_sales, 1)  # 避免除零

        for metrics in combo_metrics.values():
            normalized_sales = (metrics["total_sales"] - min_sales) / sales_range
            if max_sales == min_sales:
                # 所有组合销量相同: 归一化为 0.5
                normalized_sales = 0.5
            metrics["normalized_sales"] = normalized_sales
            metrics["composite_score"] = (
                _WEIGHT_SALES * normalized_sales
                + _WEIGHT_CONVERSION * metrics["avg_conversion"]
                + _WEIGHT_PROFIT * metrics["profit_margin"]
            )

        # --- 3. 排名 (按综合评分降序) ---
        rankings: List[Dict[str, Any]] = []
        for combo_id, metrics in combo_metrics.items():
            rankings.append(
                {
                    "combination_id": combo_id,
                    "score": round(metrics["composite_score"], 6),
                    "sales": metrics["total_sales"],
                    "conversion": round(metrics["avg_conversion"], 6),
                    "return_rate": round(metrics["avg_return_rate"], 6),
                    "z_gen_engagement": round(metrics["avg_z_gen_engagement"], 6),
                    "profit_margin": metrics["profit_margin"],
                    "price": metrics["price"],
                    "packaging": metrics["packaging"],
                    "channel": metrics["channel"],
                    "region": metrics["region"],
                }
            )
        rankings.sort(key=lambda r: r["score"], reverse=True)

        # --- 4. 赢家 ---
        winner_rank = rankings[0]
        winner: Dict[str, Any] = {
            "combination_id": winner_rank["combination_id"],
            "composite_score": winner_rank["score"],
            "total_sales": winner_rank["sales"],
            "avg_conversion": winner_rank["conversion"],
            "profit_margin": winner_rank["profit_margin"],
            "price": winner_rank["price"],
            "packaging": winner_rank["packaging"],
            "channel": winner_rank["channel"],
            "region": winner_rank["region"],
        }

        # --- 5. 因子贡献分析 (简化 ANOVA) ---
        factor_contribution = self._compute_factor_contribution(
            combo_metrics, combinations
        )

        # --- 6. 置信度计算 ---
        confidence = self._compute_confidence(rankings, combo_metrics)

        # --- 7. 跨区域对比 ---
        cross_region = self._compute_cross_region_comparison(
            combo_metrics, combinations
        )

        result: Dict[str, Any] = {
            "winner": winner,
            "rankings": rankings,
            "factor_contribution": factor_contribution,
            "confidence": round(confidence, 6),
            "cross_region_comparison": cross_region,
        }

        logger.info(
            f"PerformanceAnalyzer: 分析 {len(rankings)} 组合, "
            f"赢家={winner['combination_id']} "
            f"(score={winner['composite_score']:.4f}, "
            f"confidence={confidence:.4f})"
        )

        return result

    # ==================================================================
    # 内部辅助 - 因子贡献分析
    # ==================================================================

    def _compute_factor_contribution(
        self,
        combo_metrics: Dict[str, Dict[str, Any]],
        combinations: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        """计算各因子对综合评分的贡献占比 (简化 ANOVA)。

        对每个因子, 计算各水平均值与总均值的偏差平方和 (SS_between),
        归一化后得到因子贡献占比。

        参数:
            combo_metrics: 组合指标字典
            combinations:  测试计划中的组合列表

        返回:
            {factor: contribution_ratio}, 所有值之和约为 1.0。
        """
        if not combo_metrics:
            return {f: 0.0 for f in _FACTORS}

        # 总均值
        all_scores = [m["composite_score"] for m in combo_metrics.values()]
        grand_mean = sum(all_scores) / len(all_scores)

        # 构建组合查找表
        combo_lookup = {c["id"]: c for c in combinations}

        ss_between: Dict[str, float] = {}
        for factor in _FACTORS:
            # 按因子水平分组
            level_scores: Dict[str, List[float]] = {}
            for combo_id, metrics in combo_metrics.items():
                combo = combo_lookup.get(combo_id, {})
                level = combo.get(factor, "unknown")
                level_scores.setdefault(level, []).append(
                    metrics["composite_score"]
                )

            # 计算 SS_between = Σ n_level × (mean_level - grand_mean)²
            ss = 0.0
            for level, scores in level_scores.items():
                level_mean = sum(scores) / len(scores)
                ss += len(scores) * (level_mean - grand_mean) ** 2
            ss_between[factor] = ss

        # 归一化
        total_ss = sum(ss_between.values())
        if total_ss > 0:
            contribution = {
                factor: round(ss_between[factor] / total_ss, 6)
                for factor in _FACTORS
            }
        else:
            # 所有因子贡献相同 (无差异)
            contribution = {factor: 0.25 for factor in _FACTORS}

        return contribution

    # ==================================================================
    # 内部辅助 - 置信度计算
    # ==================================================================

    def _compute_confidence(
        self,
        rankings: List[Dict[str, Any]],
        combo_metrics: Dict[str, Dict[str, Any]],
    ) -> float:
        """计算分析结果的置信度 (0-1)。

        置信度因素:
            1. 数据量: 采集天数越多 → 置信度越高
            2. 效果量: 赢家与均值的差距越大 → 置信度越高
            3. 组合数: 测试组合越多 → 置信度越高

        参数:
            rankings:      排名列表
            combo_metrics: 组合指标字典

        返回:
            置信度 [0, 1]。
        """
        if not rankings or not combo_metrics:
            return 0.0

        # 因素 1: 数据量 (平均天数, 7天=0.7, 14天=1.0)
        avg_days = sum(m["n_days"] for m in combo_metrics.values()) / len(
            combo_metrics
        )
        data_factor = min(1.0, avg_days / 14.0)

        # 因素 2: 效果量 (赢家分数 vs 均值)
        all_scores = [r["score"] for r in rankings]
        mean_score = sum(all_scores) / len(all_scores)
        winner_score = all_scores[0]
        score_range = max(all_scores) - min(all_scores)
        if score_range > 0:
            effect_size = (winner_score - mean_score) / score_range
        else:
            effect_size = 0.0
        effect_factor = min(1.0, max(0.0, effect_size * 2))

        # 因素 3: 组合数 (8组合=0.8, 更多=1.0)
        combo_factor = min(1.0, len(rankings) / 10.0)

        # 综合置信度
        confidence = 0.4 * data_factor + 0.35 * effect_factor + 0.25 * combo_factor

        return min(1.0, max(0.0, confidence))

    # ==================================================================
    # 内部辅助 - 跨区域对比
    # ==================================================================

    def _compute_cross_region_comparison(
        self,
        combo_metrics: Dict[str, Dict[str, Any]],
        combinations: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """计算跨区域表现对比。

        参数:
            combo_metrics: 组合指标字典
            combinations:  测试计划中的组合列表

        返回:
            {region: {avg_score, total_sales, avg_conversion, combo_count}}。
        """
        combo_lookup = {c["id"]: c for c in combinations}

        region_data: Dict[str, List[Dict[str, Any]]] = {}
        for combo_id, metrics in combo_metrics.items():
            combo = combo_lookup.get(combo_id, {})
            region = combo.get("region", "unknown")
            region_data.setdefault(region, []).append(metrics)

        cross: Dict[str, Dict[str, Any]] = {}
        for region, metrics_list in region_data.items():
            n = len(metrics_list)
            cross[region] = {
                "avg_score": round(
                    sum(m["composite_score"] for m in metrics_list) / n, 6
                ),
                "total_sales": sum(m["total_sales"] for m in metrics_list),
                "avg_conversion": round(
                    sum(m["avg_conversion"] for m in metrics_list) / n, 6
                ),
                "combo_count": n,
            }

        return cross

    # ==================================================================
    # 内部辅助 - 空结果
    # ==================================================================

    def _empty_result(self) -> Dict[str, Any]:
        """返回空分析结果 (无数据时)。"""
        return {
            "winner": None,
            "rankings": [],
            "factor_contribution": {f: 0.0 for f in _FACTORS},
            "confidence": 0.0,
            "cross_region_comparison": {},
        }


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["PerformanceAnalyzer"]
