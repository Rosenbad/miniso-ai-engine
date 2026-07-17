# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - MarketProbe 模型校准器 (Task 12)
# ==============================================================================
# 对应 spec §5 验证反馈层 · Step 4: ModelCalibrator (反哺链路修复核心)
#
# ModelCalibrator 设计要点:
#   - Data 回流: 验证结果 (实际 hit/non-hit) 自动写入训练集
#   - 特征校准: 根据验证偏差调整特征权重
#   - 策略优化: 根据赢家特征生成策略调整建议
#   - 输出: ModelUpdate (新模型版本 + 特征权重变更 + 策略建议)
#
# 权重调整逻辑:
#   1. 对比预测 hitScore vs 实际结果, 计算预测误差
#   2. 若模型整体高估 (predicted > actual), 降低高贡献因子相关特征权重
#   3. 若模型整体低估 (predicted < actual), 提升高贡献因子相关特征权重
#   4. 版本号递增 (patch 版本 +1)
#
# 因子→特征映射:
#   price     → price_percentile, material_cost_ratio
#   packaging → design_novelty, ip_power_score, ip_category_match
#   channel   → social_virality, social_mentions
#   region    → cross_region_diffusion_speed, ip_region_heat_variance
# ==============================================================================

"""
模型校准器 (spec §5 Step 4 - 反哺链路修复核心)。

根据验证结果校准爆品预测模型: 预测误差 → 权重调整 + 版本递增 + 策略优化建议。

核心流程:
    1. 对比预测 hitScore vs 实际结果 → 计算预测误差
    2. 根据误差方向调整因子相关特征权重
    3. 版本号递增 (patch +1)
    4. 根据赢家特征生成策略优化建议

因子→特征映射::
    price     → price_percentile, material_cost_ratio
    packaging → design_novelty, ip_power_score, ip_category_match
    channel   → social_virality, social_mentions
    region    → cross_region_diffusion_speed, ip_region_heat_variance

用法::

    calibrator = ModelCalibrator()
    update = calibrator.calibrate(test_result, predicted_hits, actual_results)
    # update = {new_version, weight_changes, strategy_suggestions, prediction_errors}
"""

from __future__ import annotations

from typing import Any, Dict, List

from ideaforge.models.features import FeatureExtractor
from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# 常量 - 因子→特征映射
# ==============================================================================

# A/B 测试因子 → XGBoost 特征映射
_FACTOR_TO_FEATURES: Dict[str, List[str]] = {
    "price": ["price_percentile", "material_cost_ratio"],
    "packaging": ["design_novelty", "ip_power_score", "ip_category_match"],
    "channel": ["social_virality", "social_mentions"],
    "region": ["cross_region_diffusion_speed", "ip_region_heat_variance"],
}
"""A/B 因子到 XGBoost 19 特征的映射。"""

# 权重调整幅度 (每次校准的最大调整比例)
_WEIGHT_ADJUSTMENT_RATE: float = 0.10
"""权重调整幅度: ±10%。"""

# 权重上下限
_WEIGHT_MIN: float = 0.10
_WEIGHT_MAX: float = 5.00


# ==============================================================================
# ModelCalibrator 模型校准器
# ==============================================================================


class ModelCalibrator:
    """模型校准器 (spec §5 Step 4 - 反哺链路修复核心)。

    根据验证结果校准爆品预测模型:
        1. 预测误差 → 权重调整
        2. 版本递增
        3. 策略优化建议

    属性:
        _version:          当前模型版本 (semver, 初始 "1.0.0")
        _feature_weights:  19 个特征的权重 (初始全 1.0)

    用法::

        calibrator = ModelCalibrator()
        update = calibrator.calibrate(test_result, predicted_hits, actual_results)
    """

    def __init__(self) -> None:
        """初始化模型校准器。

        设置初始版本 "1.0.0", 19 个特征权重全为 1.0。
        """
        self._version: str = "1.0.0"
        self._feature_weights: Dict[str, float] = {
            feature: 1.0 for feature in FeatureExtractor.FEATURE_NAMES
        }

    # ==================================================================
    # calibrate - 校准模型
    # ==================================================================

    def calibrate(
        self,
        test_result: Dict[str, Any],
        predicted_hits: Dict[str, float],
        actual_results: Dict[str, float],
    ) -> Dict[str, Any]:
        """根据验证结果校准模型。

        流程:
            1. 对比预测 vs 实际 → 计算预测误差
            2. 根据误差方向 + 因子贡献调整特征权重
            3. 版本号递增 (patch +1)
            4. 根据赢家特征生成策略优化建议

        参数:
            test_result:     PerformanceAnalyzer.analyze() 的输出
            predicted_hits:  {combination_id: predicted_hitScore}
            actual_results:  {combination_id: actual_hit_result (0-1)}

        返回:
            ModelUpdate 字典::

                {
                    "new_version": "1.0.1",
                    "weight_changes": [
                        {
                            "feature": "price_percentile",
                            "old_weight": 1.0,
                            "new_weight": 1.05,
                            "change_reason": "模型低估, 提升 price 相关特征权重"
                        },
                        ...
                    ],
                    "strategy_suggestions": [
                        "扩大 IP 联名产品线 (赢家为 ip_collab 包装)",
                        ...
                    ],
                    "prediction_errors": [
                        {"product": "C001", "predicted": 0.75, "actual": 0.80, "error": 0.05},
                        ...
                    ]
                }
        """
        # --- 1. 计算预测误差 ---
        prediction_errors: List[Dict[str, Any]] = []
        all_combo_ids = set(predicted_hits.keys()) | set(actual_results.keys())

        total_error = 0.0
        error_count = 0
        for combo_id in all_combo_ids:
            predicted = predicted_hits.get(combo_id, 0.0)
            actual = actual_results.get(combo_id, 0.0)
            error = abs(predicted - actual)
            prediction_errors.append(
                {
                    "product": combo_id,
                    "predicted": round(predicted, 6),
                    "actual": round(actual, 6),
                    "error": round(error, 6),
                }
            )
            total_error += error
            error_count += 1

        avg_error = total_error / error_count if error_count > 0 else 0.0

        # --- 2. 调整特征权重 ---
        weight_changes: List[Dict[str, Any]] = []
        factor_contribution = test_result.get("factor_contribution", {})
        winner = test_result.get("winner")

        # 判断模型整体偏差方向
        # 计算预测均值 vs 实际均值
        if predicted_hits and actual_results:
            common_ids = set(predicted_hits.keys()) & set(actual_results.keys())
            if common_ids:
                pred_mean = sum(predicted_hits[cid] for cid in common_ids) / len(
                    common_ids
                )
                actual_mean = sum(actual_results[cid] for cid in common_ids) / len(
                    common_ids
                )
                bias = pred_mean - actual_mean  # 正=高估, 负=低估
            else:
                bias = 0.0
        else:
            bias = 0.0

        # 根据因子贡献 + 偏差方向调整权重
        # 贡献大的因子, 权重调整幅度也大
        for factor, features in _FACTOR_TO_FEATURES.items():
            contribution = factor_contribution.get(factor, 0.0)
            if contribution <= 0:
                continue

            # 调整幅度 = 基础调整率 × 因子贡献占比 × 偏差方向
            # 高估 (bias > 0) → 降低权重; 低估 (bias < 0) → 提升权重
            adjustment = -_WEIGHT_ADJUSTMENT_RATE * contribution * (
                1 if bias > 0 else -1 if bias < 0 else 0
            )

            if abs(adjustment) < 1e-9:
                continue

            for feature in features:
                if feature not in self._feature_weights:
                    continue
                old_weight = self._feature_weights[feature]
                new_weight = old_weight * (1.0 + adjustment)
                # 裁剪到 [min, max]
                new_weight = max(_WEIGHT_MIN, min(_WEIGHT_MAX, new_weight))

                if abs(new_weight - old_weight) < 1e-9:
                    continue

                direction = "降低" if bias > 0 else "提升"
                reason = (
                    f"模型{'高估' if bias > 0 else '低估'} (偏差={bias:+.4f}), "
                    f"{direction} {factor} 相关特征权重 "
                    f"(因子贡献={contribution:.4f})"
                )

                self._feature_weights[feature] = new_weight
                weight_changes.append(
                    {
                        "feature": feature,
                        "old_weight": round(old_weight, 6),
                        "new_weight": round(new_weight, 6),
                        "change_reason": reason,
                    }
                )

        # --- 3. 版本号递增 (patch +1) ---
        old_version = self._version
        self._version = self._increment_version(old_version)

        # --- 4. 策略优化建议 ---
        strategy_suggestions = self._generate_strategy_suggestions(
            test_result, avg_error
        )

        result: Dict[str, Any] = {
            "new_version": self._version,
            "weight_changes": weight_changes,
            "strategy_suggestions": strategy_suggestions,
            "prediction_errors": prediction_errors,
        }

        logger.info(
            f"ModelCalibrator: 版本 {old_version} → {self._version}, "
            f"权重变更 {len(weight_changes)} 项, "
            f"策略建议 {len(strategy_suggestions)} 条, "
            f"平均预测误差 {avg_error:.4f}"
        )

        return result

    # ==================================================================
    # 内部辅助 - 版本号递增
    # ==================================================================

    def _increment_version(self, version: str) -> str:
        """递增版本号 (patch +1)。

        参数:
            version: 当前版本号 (semver "x.y.z")

        返回:
            递增后的版本号 (patch +1)。
        """
        parts = version.split(".")
        if len(parts) != 3:
            return "1.0.1"
        major, minor, patch = parts
        return f"{major}.{minor}.{int(patch) + 1}"

    # ==================================================================
    # 内部辅助 - 策略优化建议
    # ==================================================================

    def _generate_strategy_suggestions(
        self, test_result: Dict[str, Any], avg_error: float
    ) -> List[str]:
        """根据赢家特征生成策略优化建议。

        参数:
            test_result: PerformanceAnalyzer.analyze() 的输出
            avg_error:   平均预测误差

        返回:
            策略建议字符串列表。
        """
        suggestions: List[str] = []
        winner = test_result.get("winner")
        factor_contribution = test_result.get("factor_contribution", {})

        if winner:
            # 基于赢家特征的策略建议
            if winner.get("packaging") == "ip_collab":
                suggestions.append(
                    "扩大 IP 联名产品线 (赢家为 IP 联名包装, 表现显著优于极简)"
                )
            elif winner.get("packaging") == "minimalist":
                suggestions.append(
                    "优化极简包装设计 (赢家为极简包装, IP 联名未显优势)"
                )

            if winner.get("price") == "low":
                suggestions.append(
                    "主推低价高性价比产品 (赢家为低价区间, 销量优势明显)"
                )
            elif winner.get("price") == "high":
                suggestions.append(
                    "聚焦高端溢价产品 (赢家为高价区间, 利润率优势显著)"
                )

            if winner.get("channel") == "online":
                suggestions.append(
                    "加大线上渠道投入 (赢家为线上渠道, 转化率更高)"
                )
            elif winner.get("channel") == "store":
                suggestions.append(
                    "强化门店体验营销 (赢家为门店渠道, 线下转化优势明显)"
                )

            if winner.get("region") == "china":
                suggestions.append(
                    "优先投放中国市场 (赢家为中国区域, 市场响应最佳)"
                )
            elif winner.get("region") == "us":
                suggestions.append(
                    "拓展欧美市场 (赢家为欧美区域, 高利润率优势)"
                )
            elif winner.get("region") == "sea":
                suggestions.append(
                    "深耕东南亚市场 (赢家为东南亚区域, 增长潜力大)"
                )

        # 基于因子贡献的建议
        if factor_contribution:
            # 找到贡献最大的因子
            max_factor = max(factor_contribution, key=factor_contribution.get)
            max_contrib = factor_contribution[max_factor]
            if max_contrib > 0.4:
                suggestions.append(
                    f"重点优化 {max_factor} 策略 "
                    f"(因子贡献最大: {max_contrib:.2%})"
                )

        # 基于预测误差的建议
        if avg_error > 0.15:
            suggestions.append(
                f"模型预测偏差较大 (平均误差={avg_error:.4f}), "
                f"建议增加验证样本量以提升校准精度"
            )
        elif avg_error > 0.05:
            suggestions.append(
                f"模型预测存在一定偏差 (平均误差={avg_error:.4f}), "
                f"建议持续监控预测准确率"
            )

        # 确保至少有一条建议
        if not suggestions:
            suggestions.append(
                "验证结果与预测基本一致, 维持当前策略, 持续采集数据优化模型"
            )

        return suggestions


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["ModelCalibrator"]
