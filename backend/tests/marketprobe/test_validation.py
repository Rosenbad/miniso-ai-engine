# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - MarketProbe 验证反馈层 (Task 12)
# ==============================================================================
# 对应 Task 12: 4 步闭环验证 (反哺链路修复核心)
# 覆盖:
#   1. TestDesigner        - price×packaging×channel×region 组合矩阵
#   2. DataCollector       - 销量/转化率/退货率/Z世代互动率采集
#   3. PerformanceAnalyzer - 综合评分 + 置信度计算
#   4. ModelCalibrator     - 预测误差→权重调整 + 版本递增 + 策略优化建议
#   5. SalesSimulator      - 7-14 天加速模拟 (增长趋势 + 随机噪声)
#   6. FastAPI 路由        - test-plan/simulate/analyze/calibrate 4 端点
#   7. 边界场景            - 空数据/单组合/全部相同表现
#
# 测试策略 (TDD):
#   Step 1: 编写测试 (本文件)
#   Step 2: 验证失败 (模块尚未创建)
#   Step 3: 实现 4 步闭环 + Simulator + 路由
#   Step 4: 验证通过
# ==============================================================================

"""
测试 MarketProbe 验证反馈层 (Task 12)。

测试覆盖 (TDD):
  - TestDesigner: A/B 矩阵生成, 组合数 6-12, 样本量 50-100, 全因子覆盖
  - DataCollector: 逐日数据存储/检索, 多日采集
  - PerformanceAnalyzer: 赢家判定, 综合评分, 因子贡献, 置信度, 跨区域对比
  - ModelCalibrator: 版本递增, 权重调整, 策略建议, 预测误差
  - SalesSimulator: N 天数据, 增长趋势, 不同组合不同结果, 种子可复现
  - API 路由: 4 端点 + 健康检查
  - 边界场景: 空数据/单组合/全部相同表现

环境说明:
  - 纯 Python + numpy 模拟, 无需外部服务
  - 复用 ideaforge.models.features.FeatureExtractor.FEATURE_NAMES (19 特征)
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient


# ==============================================================================
# 测试辅助 - 构造测试计划与模拟数据
# ==============================================================================


def _make_test_plan(
    product_name: str = "原木杯香薰蜡烛",
    category: str = "家居/香氛",
    days: int = 7,
) -> Dict[str, Any]:
    """构造一个测试计划 (通过 TestDesigner 生成)。"""
    from marketprobe.test_designer import TestDesigner

    designer = TestDesigner()
    return designer.design_test_plan(
        product_name=product_name, category=category, days=days
    )


def _make_simulation_data(
    test_plan: Dict[str, Any] | None = None, days: int = 7, seed: int = 42
) -> Dict[str, Any]:
    """构造模拟销售数据。"""
    from marketprobe.simulator import SalesSimulator

    if test_plan is None:
        test_plan = _make_test_plan(days=days)
    simulator = SalesSimulator()
    return simulator.simulate(test_plan, days=days, seed=seed)


def _make_collected_data(simulation: Dict[str, Any]) -> Dict[str, List[Dict]]:
    """将模拟数据转换为 DataCollector 格式。"""
    from marketprobe.data_collector import DataCollector

    collector = DataCollector()
    for combo_id, daily_list in simulation["daily_data"].items():
        for record in daily_list:
            collector.collect_daily(
                combination_id=combo_id,
                day=record["day"],
                sales=record["sales"],
                conversion=record["conversion"],
                return_rate=record["return_rate"],
                z_gen_engagement=record["z_gen_engagement"],
            )
    return collector.get_all_data()


# ==============================================================================
# 1. TestDesigner 测试
# ==============================================================================


class TestTestDesigner:
    """TestDesigner (Step 1) 测试 - A/B 组合矩阵生成。"""

    def test_design_returns_dict(self) -> None:
        """design_test_plan 应返回字典。"""
        from marketprobe.test_designer import TestDesigner

        designer = TestDesigner()
        result = designer.design_test_plan(
            product_name="测试产品", category="家居/香氛"
        )
        assert isinstance(result, dict)

    def test_design_has_required_fields(self) -> None:
        """返回的测试计划应含必需字段。"""
        from marketprobe.test_designer import TestDesigner

        designer = TestDesigner()
        plan = designer.design_test_plan(
            product_name="测试产品", category="家居/香氛"
        )
        assert "product_name" in plan
        assert "category" in plan
        assert "combinations" in plan
        assert "test_days" in plan
        assert "kpi_baseline" in plan

    def test_combinations_count_in_range(self) -> None:
        """组合数应在 6-12 之间 (可管理子集)。"""
        from marketprobe.test_designer import TestDesigner

        designer = TestDesigner()
        plan = designer.design_test_plan(
            product_name="测试产品", category="家居/香氛"
        )
        combos = plan["combinations"]
        assert 6 <= len(combos) <= 12, f"组合数 {len(combos)} 不在 6-12 范围"

    def test_each_combination_has_required_fields(self) -> None:
        """每个组合应含 id/price/packaging/channel/region/sample_size。"""
        from marketprobe.test_designer import TestDesigner

        designer = TestDesigner()
        plan = designer.design_test_plan(
            product_name="测试产品", category="家居/香氛"
        )
        for combo in plan["combinations"]:
            assert "id" in combo, f"组合缺少 id: {combo}"
            assert "price" in combo, f"组合缺少 price: {combo}"
            assert "packaging" in combo, f"组合缺少 packaging: {combo}"
            assert "channel" in combo, f"组合缺少 channel: {combo}"
            assert "region" in combo, f"组合缺少 region: {combo}"
            assert "sample_size" in combo, f"组合缺少 sample_size: {combo}"

    def test_sample_size_in_range(self) -> None:
        """每个组合的样本量应在 50-100 之间。"""
        from marketprobe.test_designer import TestDesigner

        designer = TestDesigner()
        plan = designer.design_test_plan(
            product_name="测试产品", category="家居/香氛"
        )
        for combo in plan["combinations"]:
            assert 50 <= combo["sample_size"] <= 100, (
                f"样本量 {combo['sample_size']} 不在 50-100 范围"
            )

    def test_all_price_levels_covered(self) -> None:
        """所有价格水平 (high/medium/low) 都应出现。"""
        from marketprobe.test_designer import TestDesigner

        designer = TestDesigner()
        plan = designer.design_test_plan(
            product_name="测试产品", category="家居/香氛"
        )
        prices = {c["price"] for c in plan["combinations"]}
        assert prices == {"high", "medium", "low"}, f"价格覆盖不全: {prices}"

    def test_all_packaging_levels_covered(self) -> None:
        """所有包装水平 (minimalist/ip_collab) 都应出现。"""
        from marketprobe.test_designer import TestDesigner

        designer = TestDesigner()
        plan = designer.design_test_plan(
            product_name="测试产品", category="家居/香氛"
        )
        packaging = {c["packaging"] for c in plan["combinations"]}
        assert packaging == {"minimalist", "ip_collab"}, f"包装覆盖不全: {packaging}"

    def test_all_channel_levels_covered(self) -> None:
        """所有渠道 (online/store) 都应出现。"""
        from marketprobe.test_designer import TestDesigner

        designer = TestDesigner()
        plan = designer.design_test_plan(
            product_name="测试产品", category="家居/香氛"
        )
        channels = {c["channel"] for c in plan["combinations"]}
        assert channels == {"online", "store"}, f"渠道覆盖不全: {channels}"

    def test_all_region_levels_covered(self) -> None:
        """所有区域 (china/sea/us) 都应出现。"""
        from marketprobe.test_designer import TestDesigner

        designer = TestDesigner()
        plan = designer.design_test_plan(
            product_name="测试产品", category="家居/香氛"
        )
        regions = {c["region"] for c in plan["combinations"]}
        assert regions == {"china", "sea", "us"}, f"区域覆盖不全: {regions}"

    def test_combination_ids_unique(self) -> None:
        """组合 ID 应互不相同。"""
        from marketprobe.test_designer import TestDesigner

        designer = TestDesigner()
        plan = designer.design_test_plan(
            product_name="测试产品", category="家居/香氛"
        )
        ids = [c["id"] for c in plan["combinations"]]
        assert len(ids) == len(set(ids)), "组合 ID 存在重复"

    def test_kpi_baseline_has_expected_fields(self) -> None:
        """KPI 基线应含预期指标。"""
        from marketprobe.test_designer import TestDesigner

        designer = TestDesigner()
        plan = designer.design_test_plan(
            product_name="测试产品", category="家居/香氛"
        )
        baseline = plan["kpi_baseline"]
        assert isinstance(baseline, dict)
        assert len(baseline) >= 2, "KPI 基线字段过少"

    def test_test_days_matches_input(self) -> None:
        """test_days 应与输入一致。"""
        from marketprobe.test_designer import TestDesigner

        designer = TestDesigner()
        plan = designer.design_test_plan(
            product_name="测试产品", category="家居/香氛", days=14
        )
        assert plan["test_days"] == 14

    def test_design_with_ip_name(self) -> None:
        """传入 ip_name 时应正常生成。"""
        from marketprobe.test_designer import TestDesigner

        designer = TestDesigner()
        plan = designer.design_test_plan(
            product_name="测试产品", category="家居/香氛", ip_name="三丽鸥·库洛米"
        )
        assert plan["product_name"] == "测试产品"


# ==============================================================================
# 2. DataCollector 测试
# ==============================================================================


class TestDataCollector:
    """DataCollector (Step 2) 测试 - 实时数据采集。"""

    def test_collect_daily_returns_dict(self) -> None:
        """collect_daily 应返回存储的记录字典。"""
        from marketprobe.data_collector import DataCollector

        collector = DataCollector()
        record = collector.collect_daily(
            combination_id="C001",
            day=1,
            sales=50,
            conversion=0.05,
            return_rate=0.02,
            z_gen_engagement=0.3,
        )
        assert isinstance(record, dict)

    def test_collect_daily_record_has_fields(self) -> None:
        """存储的记录应含全部指标字段。"""
        from marketprobe.data_collector import DataCollector

        collector = DataCollector()
        record = collector.collect_daily(
            combination_id="C001",
            day=1,
            sales=50,
            conversion=0.05,
            return_rate=0.02,
            z_gen_engagement=0.3,
        )
        assert record["day"] == 1
        assert record["sales"] == 50
        assert record["conversion"] == 0.05
        assert record["return_rate"] == 0.02
        assert record["z_gen_engagement"] == 0.3

    def test_get_data_returns_list(self) -> None:
        """get_data 应返回列表。"""
        from marketprobe.data_collector import DataCollector

        collector = DataCollector()
        collector.collect_daily("C001", 1, 50, 0.05, 0.02, 0.3)
        data = collector.get_data("C001")
        assert isinstance(data, list)
        assert len(data) == 1

    def test_get_data_empty_for_unknown(self) -> None:
        """未知组合应返回空列表。"""
        from marketprobe.data_collector import DataCollector

        collector = DataCollector()
        data = collector.get_data("UNKNOWN")
        assert data == []

    def test_get_all_data_returns_dict(self) -> None:
        """get_all_data 应返回字典。"""
        from marketprobe.data_collector import DataCollector

        collector = DataCollector()
        collector.collect_daily("C001", 1, 50, 0.05, 0.02, 0.3)
        collector.collect_daily("C002", 1, 60, 0.06, 0.01, 0.4)
        all_data = collector.get_all_data()
        assert isinstance(all_data, dict)
        assert "C001" in all_data
        assert "C002" in all_data

    def test_collect_multiple_days(self) -> None:
        """多日采集应按顺序存储。"""
        from marketprobe.data_collector import DataCollector

        collector = DataCollector()
        for day in range(1, 8):
            collector.collect_daily("C001", day, 50 + day, 0.05, 0.02, 0.3)
        data = collector.get_data("C001")
        assert len(data) == 7
        assert data[0]["day"] == 1
        assert data[6]["day"] == 7

    def test_collect_multiple_combinations(self) -> None:
        """多组合数据应独立存储。"""
        from marketprobe.data_collector import DataCollector

        collector = DataCollector()
        collector.collect_daily("C001", 1, 50, 0.05, 0.02, 0.3)
        collector.collect_daily("C002", 1, 80, 0.08, 0.01, 0.5)
        assert len(collector.get_data("C001")) == 1
        assert len(collector.get_data("C002")) == 1


# ==============================================================================
# 3. PerformanceAnalyzer 测试
# ==============================================================================


class TestPerformanceAnalyzer:
    """PerformanceAnalyzer (Step 3) 测试 - 表现分析。"""

    def test_analyze_returns_dict(self) -> None:
        """analyze 应返回字典。"""
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)

        analyzer = PerformanceAnalyzer()
        result = analyzer.analyze(plan, collected)
        assert isinstance(result, dict)

    def test_analyze_has_required_fields(self) -> None:
        """分析结果应含 winner/rankings/factor_contribution/confidence。"""
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)

        analyzer = PerformanceAnalyzer()
        result = analyzer.analyze(plan, collected)
        assert "winner" in result
        assert "rankings" in result
        assert "factor_contribution" in result
        assert "confidence" in result

    def test_winner_has_highest_score(self) -> None:
        """赢家应为综合评分最高的组合。"""
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)

        analyzer = PerformanceAnalyzer()
        result = analyzer.analyze(plan, collected)
        winner_score = result["winner"]["composite_score"]
        for rank in result["rankings"]:
            assert rank["score"] <= winner_score, (
                f"排名 {rank['combination_id']} 分数 {rank['score']} "
                f"高于赢家 {winner_score}"
            )

    def test_rankings_sorted_descending(self) -> None:
        """排名应按分数降序排列。"""
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)

        analyzer = PerformanceAnalyzer()
        result = analyzer.analyze(plan, collected)
        scores = [r["score"] for r in result["rankings"]]
        assert scores == sorted(scores, reverse=True), (
            f"排名未降序: {scores}"
        )

    def test_factor_contribution_has_four_factors(self) -> None:
        """因子贡献应含 price/packaging/channel/region。"""
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)

        analyzer = PerformanceAnalyzer()
        result = analyzer.analyze(plan, collected)
        factors = result["factor_contribution"]
        assert "price" in factors
        assert "packaging" in factors
        assert "channel" in factors
        assert "region" in factors

    def test_confidence_in_valid_range(self) -> None:
        """置信度应在 [0, 1] 范围内。"""
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)

        analyzer = PerformanceAnalyzer()
        result = analyzer.analyze(plan, collected)
        assert 0.0 <= result["confidence"] <= 1.0, (
            f"置信度越界: {result['confidence']}"
        )

    def test_cross_region_comparison_present(self) -> None:
        """应包含跨区域对比。"""
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)

        analyzer = PerformanceAnalyzer()
        result = analyzer.analyze(plan, collected)
        assert "cross_region_comparison" in result
        cross = result["cross_region_comparison"]
        assert isinstance(cross, dict)
        assert len(cross) >= 1

    def test_rankings_cover_all_combinations(self) -> None:
        """排名应覆盖所有有数据的组合。"""
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)

        analyzer = PerformanceAnalyzer()
        result = analyzer.analyze(plan, collected)
        combo_ids_in_plan = {c["id"] for c in plan["combinations"]}
        ranked_ids = {r["combination_id"] for r in result["rankings"]}
        assert combo_ids_in_plan == ranked_ids, (
            f"排名未覆盖所有组合: 缺少 {combo_ids_in_plan - ranked_ids}"
        )

    def test_winner_combination_id_in_rankings(self) -> None:
        """赢家的 combination_id 应出现在排名第一。"""
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)

        analyzer = PerformanceAnalyzer()
        result = analyzer.analyze(plan, collected)
        assert result["winner"]["combination_id"] == result["rankings"][0][
            "combination_id"
        ]


# ==============================================================================
# 4. ModelCalibrator 测试
# ==============================================================================


class TestModelCalibrator:
    """ModelCalibrator (Step 4) 测试 - 模型校准 (反哺链路修复核心)。"""

    def test_initial_version(self) -> None:
        """初始版本应为 1.0.0。"""
        from marketprobe.model_calibrator import ModelCalibrator

        calibrator = ModelCalibrator()
        assert calibrator._version == "1.0.0"

    def test_feature_weights_count_19(self) -> None:
        """特征权重应覆盖 19 个特征。"""
        from marketprobe.model_calibrator import ModelCalibrator

        calibrator = ModelCalibrator()
        assert len(calibrator._feature_weights) == 19

    def test_calibrate_returns_dict(self) -> None:
        """calibrate 应返回字典。"""
        from marketprobe.model_calibrator import ModelCalibrator
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)
        analyzer = PerformanceAnalyzer()
        test_result = analyzer.analyze(plan, collected)

        # 构造预测与实际
        predicted_hits = {
            c["id"]: 0.75 for c in plan["combinations"]
        }
        actual_results = {
            c["id"]: 0.80 for c in plan["combinations"]
        }

        calibrator = ModelCalibrator()
        result = calibrator.calibrate(test_result, predicted_hits, actual_results)
        assert isinstance(result, dict)

    def test_calibrate_has_required_fields(self) -> None:
        """校准结果应含 new_version/weight_changes/strategy_suggestions/prediction_errors。"""
        from marketprobe.model_calibrator import ModelCalibrator
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)
        analyzer = PerformanceAnalyzer()
        test_result = analyzer.analyze(plan, collected)

        predicted_hits = {c["id"]: 0.75 for c in plan["combinations"]}
        actual_results = {c["id"]: 0.80 for c in plan["combinations"]}

        calibrator = ModelCalibrator()
        result = calibrator.calibrate(test_result, predicted_hits, actual_results)
        assert "new_version" in result
        assert "weight_changes" in result
        assert "strategy_suggestions" in result
        assert "prediction_errors" in result

    def test_calibrate_increments_version(self) -> None:
        """校准后版本号应递增。"""
        from marketprobe.model_calibrator import ModelCalibrator
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)
        analyzer = PerformanceAnalyzer()
        test_result = analyzer.analyze(plan, collected)

        predicted_hits = {c["id"]: 0.75 for c in plan["combinations"]}
        actual_results = {c["id"]: 0.80 for c in plan["combinations"]}

        calibrator = ModelCalibrator()
        old_version = calibrator._version
        result = calibrator.calibrate(test_result, predicted_hits, actual_results)
        assert result["new_version"] != old_version, "版本号未递增"

    def test_calibrate_version_format_semver(self) -> None:
        """版本号应为 semver 格式 (x.y.z)。"""
        from marketprobe.model_calibrator import ModelCalibrator
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)
        analyzer = PerformanceAnalyzer()
        test_result = analyzer.analyze(plan, collected)

        predicted_hits = {c["id"]: 0.75 for c in plan["combinations"]}
        actual_results = {c["id"]: 0.80 for c in plan["combinations"]}

        calibrator = ModelCalibrator()
        result = calibrator.calibrate(test_result, predicted_hits, actual_results)
        parts = result["new_version"].split(".")
        assert len(parts) == 3, f"版本号格式异常: {result['new_version']}"

    def test_weight_changes_present(self) -> None:
        """权重变更列表应非空。"""
        from marketprobe.model_calibrator import ModelCalibrator
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)
        analyzer = PerformanceAnalyzer()
        test_result = analyzer.analyze(plan, collected)

        predicted_hits = {c["id"]: 0.50 for c in plan["combinations"]}
        actual_results = {c["id"]: 0.90 for c in plan["combinations"]}

        calibrator = ModelCalibrator()
        result = calibrator.calibrate(test_result, predicted_hits, actual_results)
        assert isinstance(result["weight_changes"], list)
        assert len(result["weight_changes"]) >= 1, "权重变更为空"

    def test_weight_change_has_fields(self) -> None:
        """每条权重变更应含 feature/old_weight/new_weight/change_reason。"""
        from marketprobe.model_calibrator import ModelCalibrator
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)
        analyzer = PerformanceAnalyzer()
        test_result = analyzer.analyze(plan, collected)

        predicted_hits = {c["id"]: 0.50 for c in plan["combinations"]}
        actual_results = {c["id"]: 0.90 for c in plan["combinations"]}

        calibrator = ModelCalibrator()
        result = calibrator.calibrate(test_result, predicted_hits, actual_results)
        for change in result["weight_changes"]:
            assert "feature" in change
            assert "old_weight" in change
            assert "new_weight" in change
            assert "change_reason" in change

    def test_strategy_suggestions_present(self) -> None:
        """策略建议列表应非空。"""
        from marketprobe.model_calibrator import ModelCalibrator
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)
        analyzer = PerformanceAnalyzer()
        test_result = analyzer.analyze(plan, collected)

        predicted_hits = {c["id"]: 0.75 for c in plan["combinations"]}
        actual_results = {c["id"]: 0.80 for c in plan["combinations"]}

        calibrator = ModelCalibrator()
        result = calibrator.calibrate(test_result, predicted_hits, actual_results)
        assert isinstance(result["strategy_suggestions"], list)
        assert len(result["strategy_suggestions"]) >= 1, "策略建议为空"

    def test_prediction_errors_present(self) -> None:
        """预测误差列表应非空。"""
        from marketprobe.model_calibrator import ModelCalibrator
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)
        analyzer = PerformanceAnalyzer()
        test_result = analyzer.analyze(plan, collected)

        predicted_hits = {c["id"]: 0.75 for c in plan["combinations"]}
        actual_results = {c["id"]: 0.80 for c in plan["combinations"]}

        calibrator = ModelCalibrator()
        result = calibrator.calibrate(test_result, predicted_hits, actual_results)
        assert isinstance(result["prediction_errors"], list)
        assert len(result["prediction_errors"]) >= 1, "预测误差为空"

    def test_prediction_error_has_fields(self) -> None:
        """每条预测误差应含 product/predicted/actual/error。"""
        from marketprobe.model_calibrator import ModelCalibrator
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)
        analyzer = PerformanceAnalyzer()
        test_result = analyzer.analyze(plan, collected)

        predicted_hits = {c["id"]: 0.75 for c in plan["combinations"]}
        actual_results = {c["id"]: 0.80 for c in plan["combinations"]}

        calibrator = ModelCalibrator()
        result = calibrator.calibrate(test_result, predicted_hits, actual_results)
        for err in result["prediction_errors"]:
            assert "product" in err
            assert "predicted" in err
            assert "actual" in err
            assert "error" in err

    def test_prediction_error_value_correct(self) -> None:
        """预测误差值应等于 |predicted - actual|。"""
        from marketprobe.model_calibrator import ModelCalibrator
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)
        analyzer = PerformanceAnalyzer()
        test_result = analyzer.analyze(plan, collected)

        predicted_hits = {c["id"]: 0.75 for c in plan["combinations"]}
        actual_results = {c["id"]: 0.80 for c in plan["combinations"]}

        calibrator = ModelCalibrator()
        result = calibrator.calibrate(test_result, predicted_hits, actual_results)
        for err in result["prediction_errors"]:
            expected_error = abs(err["predicted"] - err["actual"])
            assert abs(err["error"] - expected_error) < 1e-9, (
                f"误差值不正确: {err['error']} != {expected_error}"
            )

    def test_calibrate_updates_internal_version(self) -> None:
        """校准后内部版本号应更新。"""
        from marketprobe.model_calibrator import ModelCalibrator
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)
        analyzer = PerformanceAnalyzer()
        test_result = analyzer.analyze(plan, collected)

        predicted_hits = {c["id"]: 0.75 for c in plan["combinations"]}
        actual_results = {c["id"]: 0.80 for c in plan["combinations"]}

        calibrator = ModelCalibrator()
        calibrator.calibrate(test_result, predicted_hits, actual_results)
        assert calibrator._version != "1.0.0", "内部版本号未更新"

    def test_multiple_calibrations_increment_version(self) -> None:
        """多次校准版本号应持续递增。"""
        from marketprobe.model_calibrator import ModelCalibrator
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)
        analyzer = PerformanceAnalyzer()
        test_result = analyzer.analyze(plan, collected)

        predicted_hits = {c["id"]: 0.75 for c in plan["combinations"]}
        actual_results = {c["id"]: 0.80 for c in plan["combinations"]}

        calibrator = ModelCalibrator()
        v1 = calibrator.calibrate(test_result, predicted_hits, actual_results)[
            "new_version"
        ]
        v2 = calibrator.calibrate(test_result, predicted_hits, actual_results)[
            "new_version"
        ]
        assert v1 != v2, "多次校准版本号未递增"


# ==============================================================================
# 5. SalesSimulator 测试
# ==============================================================================


class TestSalesSimulator:
    """SalesSimulator 测试 - 7-14 天加速模拟。"""

    def test_simulate_returns_dict(self) -> None:
        """simulate 应返回字典。"""
        from marketprobe.simulator import SalesSimulator

        plan = _make_test_plan()
        simulator = SalesSimulator()
        result = simulator.simulate(plan)
        assert isinstance(result, dict)

    def test_simulate_has_required_fields(self) -> None:
        """模拟结果应含 days/daily_data/summary。"""
        from marketprobe.simulator import SalesSimulator

        plan = _make_test_plan()
        simulator = SalesSimulator()
        result = simulator.simulate(plan)
        assert "days" in result
        assert "daily_data" in result
        assert "summary" in result

    def test_days_matches_input(self) -> None:
        """days 应与输入一致。"""
        from marketprobe.simulator import SalesSimulator

        plan = _make_test_plan()
        simulator = SalesSimulator()
        result = simulator.simulate(plan, days=10)
        assert result["days"] == 10

    def test_daily_data_has_all_combinations(self) -> None:
        """daily_data 应覆盖所有组合。"""
        from marketprobe.simulator import SalesSimulator

        plan = _make_test_plan()
        simulator = SalesSimulator()
        result = simulator.simulate(plan)
        combo_ids = {c["id"] for c in plan["combinations"]}
        simulated_ids = set(result["daily_data"].keys())
        assert combo_ids == simulated_ids, (
            f"模拟未覆盖所有组合: 缺少 {combo_ids - simulated_ids}"
        )

    def test_daily_data_length_matches_days(self) -> None:
        """每个组合的日数据长度应等于 days。"""
        from marketprobe.simulator import SalesSimulator

        plan = _make_test_plan()
        simulator = SalesSimulator()
        result = simulator.simulate(plan, days=7)
        for combo_id, daily_list in result["daily_data"].items():
            assert len(daily_list) == 7, (
                f"组合 {combo_id} 日数据长度 {len(daily_list)} != 7"
            )

    def test_daily_record_has_required_fields(self) -> None:
        """每日记录应含 day/sales/conversion/return_rate/z_gen_engagement。"""
        from marketprobe.simulator import SalesSimulator

        plan = _make_test_plan()
        simulator = SalesSimulator()
        result = simulator.simulate(plan)
        for combo_id, daily_list in result["daily_data"].items():
            for record in daily_list:
                assert "day" in record
                assert "sales" in record
                assert "conversion" in record
                assert "return_rate" in record
                assert "z_gen_engagement" in record

    def test_sales_are_non_negative(self) -> None:
        """销量应为非负整数。"""
        from marketprobe.simulator import SalesSimulator

        plan = _make_test_plan()
        simulator = SalesSimulator()
        result = simulator.simulate(plan)
        for combo_id, daily_list in result["daily_data"].items():
            for record in daily_list:
                assert record["sales"] >= 0, (
                    f"组合 {combo_id} 第 {record['day']} 天销量为负: {record['sales']}"
                )

    def test_conversion_in_valid_range(self) -> None:
        """转化率应在 [0, 1] 范围内。"""
        from marketprobe.simulator import SalesSimulator

        plan = _make_test_plan()
        simulator = SalesSimulator()
        result = simulator.simulate(plan)
        for combo_id, daily_list in result["daily_data"].items():
            for record in daily_list:
                assert 0.0 <= record["conversion"] <= 1.0, (
                    f"组合 {combo_id} 转化率越界: {record['conversion']}"
                )

    def test_growth_trend_present(self) -> None:
        """数据应体现增长趋势 (后半段均值 >= 前半段均值)。"""
        from marketprobe.simulator import SalesSimulator

        plan = _make_test_plan()
        simulator = SalesSimulator()
        result = simulator.simulate(plan, days=14, seed=42)
        # 取第一个组合验证增长趋势
        combo_id = plan["combinations"][0]["id"]
        daily_list = result["daily_data"][combo_id]
        first_half = daily_list[:7]
        second_half = daily_list[7:]
        avg_first = sum(r["sales"] for r in first_half) / len(first_half)
        avg_second = sum(r["sales"] for r in second_half) / len(second_half)
        assert avg_second >= avg_first * 0.9, (
            f"增长趋势不明显: 前半段均值 {avg_first:.1f}, "
            f"后半段均值 {avg_second:.1f}"
        )

    def test_different_combinations_different_results(self) -> None:
        """不同组合应有不同的总销量。"""
        from marketprobe.simulator import SalesSimulator

        plan = _make_test_plan()
        simulator = SalesSimulator()
        result = simulator.simulate(plan)
        total_sales = {
            combo_id: sum(r["sales"] for r in daily_list)
            for combo_id, daily_list in result["daily_data"].items()
        }
        unique_totals = set(total_sales.values())
        assert len(unique_totals) >= 2, (
            f"所有组合总销量相同: {total_sales}"
        )

    def test_seed_reproducibility(self) -> None:
        """相同种子应产生相同结果。"""
        from marketprobe.simulator import SalesSimulator

        plan = _make_test_plan()
        simulator = SalesSimulator()
        result1 = simulator.simulate(plan, seed=42)
        result2 = simulator.simulate(plan, seed=42)
        # 比较第一个组合的第一天数据
        combo_id = plan["combinations"][0]["id"]
        assert result1["daily_data"][combo_id][0] == result2["daily_data"][
            combo_id
        ][0], "相同种子结果不一致"

    def test_different_seeds_different_results(self) -> None:
        """不同种子应产生不同结果。"""
        from marketprobe.simulator import SalesSimulator

        plan = _make_test_plan()
        simulator = SalesSimulator()
        result1 = simulator.simulate(plan, seed=42)
        result2 = simulator.simulate(plan, seed=99)
        combo_id = plan["combinations"][0]["id"]
        # 至少有一天的数据不同
        differ = any(
            result1["daily_data"][combo_id][i]["sales"]
            != result2["daily_data"][combo_id][i]["sales"]
            for i in range(len(result1["daily_data"][combo_id]))
        )
        assert differ, "不同种子结果完全相同"

    def test_summary_has_required_fields(self) -> None:
        """summary 应含 total_sales/avg_conversion 等字段。"""
        from marketprobe.simulator import SalesSimulator

        plan = _make_test_plan()
        simulator = SalesSimulator()
        result = simulator.simulate(plan)
        for combo_id, summary in result["summary"].items():
            assert "total_sales" in summary
            assert "avg_conversion" in summary

    def test_summary_total_sales_correct(self) -> None:
        """summary 的 total_sales 应等于日数据销量之和。"""
        from marketprobe.simulator import SalesSimulator

        plan = _make_test_plan()
        simulator = SalesSimulator()
        result = simulator.simulate(plan)
        for combo_id, daily_list in result["daily_data"].items():
            expected_total = sum(r["sales"] for r in daily_list)
            actual_total = result["summary"][combo_id]["total_sales"]
            assert actual_total == expected_total, (
                f"组合 {combo_id} total_sales {actual_total} != {expected_total}"
            )

    def test_simulate_14_days(self) -> None:
        """模拟 14 天应正常工作。"""
        from marketprobe.simulator import SalesSimulator

        plan = _make_test_plan(days=14)
        simulator = SalesSimulator()
        result = simulator.simulate(plan, days=14)
        assert result["days"] == 14
        for combo_id, daily_list in result["daily_data"].items():
            assert len(daily_list) == 14


# ==============================================================================
# 6. API 路由测试
# ==============================================================================


class TestAPIRoutes:
    """MarketProbe FastAPI 路由测试。"""

    def test_health_endpoint(self) -> None:
        """GET /health 应返回 200 + healthy 状态。"""
        from marketprobe.main import create_app

        app = create_app()
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "marketprobe"

    def test_test_plan_endpoint(self) -> None:
        """POST /test-plan 应返回测试计划。"""
        from marketprobe.main import create_app

        app = create_app()
        client = TestClient(app)
        response = client.post(
            "/test-plan",
            json={"product_name": "测试产品", "category": "家居/香氛", "days": 7},
        )
        assert response.status_code == 200
        data = response.json()
        assert "combinations" in data
        assert 6 <= len(data["combinations"]) <= 12

    def test_simulate_endpoint(self) -> None:
        """POST /simulate 应返回模拟数据。"""
        from marketprobe.main import create_app

        app = create_app()
        client = TestClient(app)
        # 先生成测试计划
        plan_resp = client.post(
            "/test-plan",
            json={"product_name": "测试产品", "category": "家居/香氛"},
        )
        plan = plan_resp.json()
        # 模拟
        response = client.post(
            "/simulate",
            json={"test_plan": plan, "days": 7, "seed": 42},
        )
        assert response.status_code == 200
        data = response.json()
        assert "daily_data" in data
        assert "summary" in data

    def test_analyze_endpoint(self) -> None:
        """POST /analyze 应返回分析结果。"""
        from marketprobe.main import create_app

        app = create_app()
        client = TestClient(app)
        # 先生成测试计划
        plan_resp = client.post(
            "/test-plan",
            json={"product_name": "测试产品", "category": "家居/香氛"},
        )
        plan = plan_resp.json()
        # 模拟
        sim_resp = client.post(
            "/simulate",
            json={"test_plan": plan, "days": 7, "seed": 42},
        )
        simulation = sim_resp.json()
        # 分析
        response = client.post(
            "/analyze",
            json={"test_plan": plan, "simulation_data": simulation},
        )
        assert response.status_code == 200
        data = response.json()
        assert "winner" in data
        assert "rankings" in data

    def test_calibrate_endpoint(self) -> None:
        """POST /calibrate 应返回模型更新。"""
        from marketprobe.main import create_app

        app = create_app()
        client = TestClient(app)
        # 完整链路: test-plan → simulate → analyze → calibrate
        plan = client.post(
            "/test-plan",
            json={"product_name": "测试产品", "category": "家居/香氛"},
        ).json()
        simulation = client.post(
            "/simulate",
            json={"test_plan": plan, "days": 7, "seed": 42},
        ).json()
        analysis = client.post(
            "/analyze",
            json={"test_plan": plan, "simulation_data": simulation},
        ).json()
        # 构造预测与实际
        predicted_hits = {c["id"]: 0.75 for c in plan["combinations"]}
        actual_results = {c["id"]: 0.80 for c in plan["combinations"]}
        response = client.post(
            "/calibrate",
            json={
                "test_result": analysis,
                "predicted_hits": predicted_hits,
                "actual_results": actual_results,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "new_version" in data
        assert "weight_changes" in data
        assert "strategy_suggestions" in data
        assert "prediction_errors" in data

    def test_full_chain_via_stored_state(self) -> None:
        """通过存储状态串联完整链路 (不显式传参)。"""
        from marketprobe.main import create_app

        app = create_app()
        client = TestClient(app)
        # Step 1: 生成测试计划 (存储)
        resp1 = client.post(
            "/test-plan",
            json={"product_name": "链路测试", "category": "美妆/个护"},
        )
        assert resp1.status_code == 200
        # Step 2: 模拟 (使用存储的测试计划)
        resp2 = client.post("/simulate", json={})
        assert resp2.status_code == 200
        assert "daily_data" in resp2.json()
        # Step 3: 分析 (使用存储的数据)
        resp3 = client.post("/analyze", json={})
        assert resp3.status_code == 200
        assert "winner" in resp3.json()
        # Step 4: 校准 (使用存储的分析结果)
        resp4 = client.post(
            "/calibrate",
            json={
                "predicted_hits": {},
                "actual_results": {},
            },
        )
        assert resp4.status_code == 200
        assert "new_version" in resp4.json()


# ==============================================================================
# 7. 边界场景测试
# ==============================================================================


class TestEdgeCases:
    """边界场景测试 - 空数据/单组合/全部相同表现。"""

    def test_analyze_empty_data(self) -> None:
        """空数据分析应不报错, 返回空排名或合理默认值。"""
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        analyzer = PerformanceAnalyzer()
        result = analyzer.analyze(plan, {})
        # 空数据应返回空排名
        assert isinstance(result["rankings"], list)
        assert len(result["rankings"]) == 0

    def test_analyze_single_combination(self) -> None:
        """单组合数据分析应正常工作。"""
        from marketprobe.data_collector import DataCollector
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        collector = DataCollector()
        # 只为一个组合采集数据
        combo_id = plan["combinations"][0]["id"]
        for day in range(1, 8):
            collector.collect_daily(combo_id, day, 50, 0.05, 0.02, 0.3)
        result = analyzer_result = PerformanceAnalyzer().analyze(
            plan, collector.get_all_data()
        )
        assert len(result["rankings"]) == 1
        assert result["winner"]["combination_id"] == combo_id

    def test_analyze_all_same_performance(self) -> None:
        """全部组合表现相同时应正常选出赢家。"""
        from marketprobe.data_collector import DataCollector
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        collector = DataCollector()
        # 所有组合用相同数据
        for combo in plan["combinations"]:
            for day in range(1, 8):
                collector.collect_daily(
                    combo["id"], day, 50, 0.05, 0.02, 0.3
                )
        result = PerformanceAnalyzer().analyze(plan, collector.get_all_data())
        assert "winner" in result
        assert len(result["rankings"]) == len(plan["combinations"])

    def test_calibrate_no_prediction_error(self) -> None:
        """预测与实际完全一致时仍应正常工作。"""
        from marketprobe.model_calibrator import ModelCalibrator
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)
        analyzer = PerformanceAnalyzer()
        test_result = analyzer.analyze(plan, collected)

        # 预测 = 完全一致
        predicted_hits = {c["id"]: 0.80 for c in plan["combinations"]}
        actual_results = {c["id"]: 0.80 for c in plan["combinations"]}

        calibrator = ModelCalibrator()
        result = calibrator.calibrate(test_result, predicted_hits, actual_results)
        assert "new_version" in result
        # 误差为 0
        for err in result["prediction_errors"]:
            assert err["error"] == 0.0 or abs(err["error"]) < 1e-9

    def test_calibrate_empty_predictions(self) -> None:
        """空预测字典应不报错。"""
        from marketprobe.model_calibrator import ModelCalibrator
        from marketprobe.performance_analyzer import PerformanceAnalyzer

        plan = _make_test_plan()
        simulation = _make_simulation_data(plan)
        collected = _make_collected_data(simulation)
        analyzer = PerformanceAnalyzer()
        test_result = analyzer.analyze(plan, collected)

        calibrator = ModelCalibrator()
        result = calibrator.calibrate(test_result, {}, {})
        assert "new_version" in result
        assert isinstance(result["prediction_errors"], list)

    def test_simulator_min_days(self) -> None:
        """模拟最少 7 天应正常工作。"""
        from marketprobe.simulator import SalesSimulator

        plan = _make_test_plan(days=7)
        simulator = SalesSimulator()
        result = simulator.simulate(plan, days=7)
        assert result["days"] == 7

    def test_simulator_max_days(self) -> None:
        """模拟 14 天应正常工作。"""
        from marketprobe.simulator import SalesSimulator

        plan = _make_test_plan(days=14)
        simulator = SalesSimulator()
        result = simulator.simulate(plan, days=14)
        assert result["days"] == 14

    def test_designer_default_days(self) -> None:
        """不传 days 时应使用默认值 7。"""
        from marketprobe.test_designer import TestDesigner

        designer = TestDesigner()
        plan = designer.design_test_plan(
            product_name="默认天数测试", category="家居/香氛"
        )
        assert plan["test_days"] == 7

    def test_ip_collab_outperforms_minimalist(self) -> None:
        """IP 联名包装整体表现应优于极简包装 (模拟模型验证)。"""
        from marketprobe.simulator import SalesSimulator

        plan = _make_test_plan()
        simulator = SalesSimulator()
        result = simulator.simulate(plan, days=14, seed=42)
        # 按 packaging 分组计算平均总销量
        ip_sales: List[float] = []
        min_sales: List[float] = []
        for combo in plan["combinations"]:
            total = result["summary"][combo["id"]]["total_sales"]
            if combo["packaging"] == "ip_collab":
                ip_sales.append(total)
            else:
                min_sales.append(total)
        avg_ip = sum(ip_sales) / len(ip_sales) if ip_sales else 0
        avg_min = sum(min_sales) / len(min_sales) if min_sales else 0
        assert avg_ip > avg_min, (
            f"IP 联名 {avg_ip:.1f} 未优于极简 {avg_min:.1f}"
        )

    def test_low_price_higher_volume(self) -> None:
        """低价应有更高销量 (模拟模型验证)。"""
        from marketprobe.simulator import SalesSimulator

        plan = _make_test_plan()
        simulator = SalesSimulator()
        result = simulator.simulate(plan, days=14, seed=42)
        # 按 price 分组计算平均总销量
        price_sales: Dict[str, List[float]] = {"high": [], "medium": [], "low": []}
        for combo in plan["combinations"]:
            total = result["summary"][combo["id"]]["total_sales"]
            price_sales[combo["price"]].append(total)
        avg_low = sum(price_sales["low"]) / len(price_sales["low"])
        avg_high = sum(price_sales["high"]) / len(price_sales["high"])
        assert avg_low > avg_high, (
            f"低价 {avg_low:.1f} 未高于高价 {avg_high:.1f}"
        )
