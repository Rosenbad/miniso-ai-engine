# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - XGBoost 爆品预测模型测试 (Task 10)
# ==============================================================================
# 对应 Task 10: XGBoost 爆品预测模型
# 覆盖:
#   1. FeatureExtractor   - 19 维特征向量提取 (5类: 市场5+产品3+IP4+受众4+情感3)
#   2. train_model        - XGBoost 分类器训练 + AUC 评估 + 模型保存
#   3. HitPredictor       - 加载模型 + predict_proba + SHAP top-3 因子
#   4. SHAP / fallback    - topFactors 含 feature 名 + shap_value (或 importance)
#   5. 批量预测           - predict_batch 多产品预测
#   6. 边界场景           - 空数据 / 全零特征 / 极端值
#
# 测试策略 (TDD):
#   Step 1: 编写测试 (本文件)
#   Step 2: 验证失败 (features.py / train.py / predict.py 尚未创建)
#   Step 3: 实现 FeatureExtractor
#   Step 4: 实现 train_model
#   Step 5: 实现 HitPredictor
#   Step 6: 训练模型 + 验证通过
# ==============================================================================

"""
测试 XGBoost 爆品预测模型 (spec §4.5)。

测试覆盖 (TDD):
  - FeatureExtractor: 返回 19 维向量 / 正确顺序 / 缺失字段处理 / 类型转换
  - train_model: 训练成功 / AUC > 0 / 模型文件保存 / 返回指标字典
  - HitPredictor: hitScore ∈ [0,1] / topFactors 3 项 / 从文件加载
  - SHAP / fallback: topFactors 含 feature 名 + 数值
  - 批量预测: predict_batch 多产品
  - 边界场景: 空数据 / 全零特征 / 极端值

环境说明:
  - HitPredictor 测试使用预训练模型文件 (backend/data/xgboost_model.json)
  - train_model 测试使用临时输出路径 (tmp_path), 不污染仓库
  - SHAP 失败时自动降级为 feature_importances_ (fallback 必须可用)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

from ideaforge.models.features import FeatureExtractor
from ideaforge.models.predict import HitPredictor
from ideaforge.models.train import train_model


# ==============================================================================
# 常量 - 默认路径与特征定义
# ==============================================================================

# backend/ 目录 (conftest.py 已将其加入 sys.path)
_BACKEND_DIR: Path = Path(__file__).resolve().parent.parent.parent

# 预训练模型路径 (训练后提交, 测试可直接加载)
DEFAULT_MODEL_PATH: Path = _BACKEND_DIR / "data" / "xgboost_model.json"

# 模拟 SKU 数据路径
DEFAULT_CSV_PATH: Path = _BACKEND_DIR / "data" / "mock_skus.csv"

# 19 个特征名 (与 FeatureExtractor.FEATURE_NAMES 一致)
EXPECTED_FEATURE_NAMES: List[str] = [
    # 市场特征 (5)
    "category_heat",
    "trend_growth_rate",
    "seasonality_index",
    "competitor_density",
    "cross_region_diffusion_speed",
    # 产品特征 (3)
    "price_percentile",
    "material_cost_ratio",
    "design_novelty",
    # IP 特征 (4)
    "ip_power_score",
    "ip_category_match",
    "ip_license_urgency",
    "ip_region_heat_variance",
    # 受众特征 (4)
    "z_gen_match",
    "aesthetic_tag_heat",
    "audience_spending_power",
    "social_virality",
    # 情感特征 (3)
    "trend_sentiment",
    "social_mentions",
    "positive_review_ratio",
]

EXPECTED_FEATURE_COUNT: int = 19


# ==============================================================================
# 测试辅助 - 构造原始产品数据
# ==============================================================================


def _make_full_raw_data() -> Dict[str, Any]:
    """构造包含全部 19 特征的原始产品数据字典 (典型爆品)。

    返回:
        含 19 个特征键值 + 产品名/品类的字典, 值均为合理数值。
    """
    return {
        "product_name": "测试爆品A",
        "category": "美妆/个护",
        # 市场特征
        "category_heat": 85.0,
        "trend_growth_rate": 45.5,
        "seasonality_index": 0.72,
        "competitor_density": 0.35,
        "cross_region_diffusion_speed": 0.68,
        # 产品特征
        "price_percentile": 0.55,
        "material_cost_ratio": 0.28,
        "design_novelty": 0.82,
        # IP 特征
        "ip_power_score": 88.0,
        "ip_category_match": 0.92,
        "ip_license_urgency": 0.45,
        "ip_region_heat_variance": 55.0,
        # 受众特征
        "z_gen_match": 0.85,
        "aesthetic_tag_heat": 78.0,
        "audience_spending_power": 0.62,
        "social_virality": 0.73,
        # 情感特征
        "trend_sentiment": 0.65,
        "social_mentions": 45000.0,
        "positive_review_ratio": 0.88,
    }


def _make_minimal_raw_data() -> Dict[str, Any]:
    """构造仅含部分字段的原始数据 (测试缺失字段处理)。"""
    return {
        "product_name": "最小产品",
        "category": "家居/香氛",
        "category_heat": 60.0,
        "ip_power_score": 70.0,
        "z_gen_match": 0.5,
    }


# ==============================================================================
# 1. FeatureExtractor - 特征数量与顺序
# ==============================================================================


class TestFeatureExtractorDimensions:
    """FeatureExtractor 维度测试 - 返回 19 维向量, 顺序正确。"""

    def test_extract_returns_list(self) -> None:
        """extract 应返回 list 类型。"""
        extractor = FeatureExtractor()
        result = extractor.extract(_make_full_raw_data())
        assert isinstance(result, list)

    def test_extract_returns_exactly_19_features(self) -> None:
        """extract 应返回恰好 19 个特征值。"""
        extractor = FeatureExtractor()
        result = extractor.extract(_make_full_raw_data())
        assert len(result) == EXPECTED_FEATURE_COUNT

    def test_feature_names_has_19_entries(self) -> None:
        """FEATURE_NAMES 类属性应有 19 个条目。"""
        assert len(FeatureExtractor.FEATURE_NAMES) == EXPECTED_FEATURE_COUNT

    def test_feature_names_match_expected(self) -> None:
        """FEATURE_NAMES 应与 spec §4.5 定义的特征名完全一致 (顺序匹配)。"""
        assert FeatureExtractor.FEATURE_NAMES == EXPECTED_FEATURE_NAMES

    def test_extract_all_values_are_float(self) -> None:
        """extract 返回的所有值应为 float 类型。"""
        extractor = FeatureExtractor()
        result = extractor.extract(_make_full_raw_data())
        for i, val in enumerate(result):
            assert isinstance(val, float), f"特征 {i} 类型为 {type(val)}, 应为 float"

    def test_extract_values_match_input_order(self) -> None:
        """extract 返回值的顺序应与 FEATURE_NAMES 一致。"""
        extractor = FeatureExtractor()
        raw = _make_full_raw_data()
        result = extractor.extract(raw)
        for i, name in enumerate(FeatureExtractor.FEATURE_NAMES):
            expected = float(raw[name])
            assert result[i] == pytest.approx(expected), (
                f"特征 {name} (位置 {i}) 期望 {expected}, 实际 {result[i]}"
            )


# ==============================================================================
# 2. FeatureExtractor - 缺失字段处理
# ==============================================================================


class TestFeatureExtractorMissingFields:
    """FeatureExtractor 缺失字段测试 - 缺失字段填充默认值 (0)。"""

    def test_extract_with_missing_fields_returns_19(self) -> None:
        """仅含 5 个字段的原始数据仍应返回 19 维向量。"""
        extractor = FeatureExtractor()
        result = extractor.extract(_make_minimal_raw_data())
        assert len(result) == EXPECTED_FEATURE_COUNT

    def test_missing_field_filled_with_zero(self) -> None:
        """缺失字段应填充为 0.0。"""
        extractor = FeatureExtractor()
        result = extractor.extract(_make_minimal_raw_data())
        # trend_growth_rate 未提供 → 应为 0.0
        idx = FeatureExtractor.FEATURE_NAMES.index("trend_growth_rate")
        assert result[idx] == 0.0

    def test_provided_field_preserved(self) -> None:
        """已提供的字段值应正确保留。"""
        extractor = FeatureExtractor()
        result = extractor.extract(_make_minimal_raw_data())
        idx = FeatureExtractor.FEATURE_NAMES.index("category_heat")
        assert result[idx] == pytest.approx(60.0)

    def test_empty_dict_returns_19_zeros(self) -> None:
        """空字典应返回 19 个 0.0。"""
        extractor = FeatureExtractor()
        result = extractor.extract({})
        assert len(result) == EXPECTED_FEATURE_COUNT
        assert all(v == 0.0 for v in result)

    def test_none_value_filled_with_zero(self) -> None:
        """值为 None 的字段应填充为 0.0。"""
        extractor = FeatureExtractor()
        raw = _make_full_raw_data()
        raw["category_heat"] = None  # type: ignore[assignment]
        result = extractor.extract(raw)
        idx = FeatureExtractor.FEATURE_NAMES.index("category_heat")
        assert result[idx] == 0.0


# ==============================================================================
# 3. FeatureExtractor - 类型转换
# ==============================================================================


class TestFeatureExtractorTypeConversion:
    """FeatureExtractor 类型转换测试 - str/int → float。"""

    def test_string_numeric_value_converted(self) -> None:
        """字符串数字应正确转换为 float。"""
        extractor = FeatureExtractor()
        raw = _make_full_raw_data()
        raw["category_heat"] = "75.5"
        result = extractor.extract(raw)
        idx = FeatureExtractor.FEATURE_NAMES.index("category_heat")
        assert result[idx] == pytest.approx(75.5)

    def test_int_value_converted_to_float(self) -> None:
        """int 值应转换为 float。"""
        extractor = FeatureExtractor()
        raw = _make_full_raw_data()
        raw["category_heat"] = 80  # int
        result = extractor.extract(raw)
        idx = FeatureExtractor.FEATURE_NAMES.index("category_heat")
        assert isinstance(result[idx], float)
        assert result[idx] == pytest.approx(80.0)

    def test_invalid_string_filled_with_zero(self) -> None:
        """非数字字符串应填充为 0.0。"""
        extractor = FeatureExtractor()
        raw = _make_full_raw_data()
        raw["category_heat"] = "abc"
        result = extractor.extract(raw)
        idx = FeatureExtractor.FEATURE_NAMES.index("category_heat")
        assert result[idx] == 0.0


# ==============================================================================
# 4. FeatureExtractor - 批量提取
# ==============================================================================


class TestFeatureExtractorBatch:
    """FeatureExtractor 批量提取测试。"""

    def test_extract_batch_returns_list_of_lists(self) -> None:
        """extract_batch 应返回 list[list[float]]。"""
        extractor = FeatureExtractor()
        raw_list = [_make_full_raw_data(), _make_minimal_raw_data()]
        result = extractor.extract_batch(raw_list)
        assert isinstance(result, list)
        assert all(isinstance(row, list) for row in result)

    def test_extract_batch_correct_count(self) -> None:
        """extract_batch 返回行数应与输入一致。"""
        extractor = FeatureExtractor()
        raw_list = [_make_full_raw_data() for _ in range(5)]
        result = extractor.extract_batch(raw_list)
        assert len(result) == 5

    def test_extract_batch_each_row_19_features(self) -> None:
        """extract_batch 每行应有 19 个特征。"""
        extractor = FeatureExtractor()
        raw_list = [_make_full_raw_data(), _make_minimal_raw_data(), {}]
        result = extractor.extract_batch(raw_list)
        for row in result:
            assert len(row) == EXPECTED_FEATURE_COUNT

    def test_extract_batch_empty_list(self) -> None:
        """空列表应返回空列表。"""
        extractor = FeatureExtractor()
        result = extractor.extract_batch([])
        assert result == []


# ==============================================================================
# 5. train_model - 模型训练
# ==============================================================================


class TestTrainModel:
    """train_model 训练测试 - 训练成功 / AUC > 0 / 模型保存。"""

    def test_train_returns_dict(self, tmp_path) -> None:
        """train_model 应返回字典。"""
        model_path = tmp_path / "test_model.json"
        result = train_model(
            csv_path=str(DEFAULT_CSV_PATH), model_output_path=str(model_path)
        )
        assert isinstance(result, dict)

    def test_train_returns_auc_key(self, tmp_path) -> None:
        """返回字典应包含 auc 键。"""
        model_path = tmp_path / "test_model.json"
        result = train_model(
            csv_path=str(DEFAULT_CSV_PATH), model_output_path=str(model_path)
        )
        assert "auc" in result

    def test_train_auc_greater_than_zero(self, tmp_path) -> None:
        """AUC 应大于 0 (合理值)。"""
        model_path = tmp_path / "test_model.json"
        result = train_model(
            csv_path=str(DEFAULT_CSV_PATH), model_output_path=str(model_path)
        )
        assert result["auc"] > 0.0

    def test_train_auc_in_valid_range(self, tmp_path) -> None:
        """AUC 应在 0-1 范围内。"""
        model_path = tmp_path / "test_model.json"
        result = train_model(
            csv_path=str(DEFAULT_CSV_PATH), model_output_path=str(model_path)
        )
        assert 0.0 <= result["auc"] <= 1.0

    def test_train_returns_accuracy_key(self, tmp_path) -> None:
        """返回字典应包含 accuracy 键。"""
        model_path = tmp_path / "test_model.json"
        result = train_model(
            csv_path=str(DEFAULT_CSV_PATH), model_output_path=str(model_path)
        )
        assert "accuracy" in result

    def test_train_returns_model_path_key(self, tmp_path) -> None:
        """返回字典应包含 model_path 键。"""
        model_path = tmp_path / "test_model.json"
        result = train_model(
            csv_path=str(DEFAULT_CSV_PATH), model_output_path=str(model_path)
        )
        assert "model_path" in result

    def test_train_saves_model_file(self, tmp_path) -> None:
        """训练后模型文件应存在。"""
        model_path = tmp_path / "test_model.json"
        train_model(
            csv_path=str(DEFAULT_CSV_PATH), model_output_path=str(model_path)
        )
        assert model_path.exists()

    def test_train_model_path_in_result(self, tmp_path) -> None:
        """返回的 model_path 应与传入路径一致。"""
        model_path = tmp_path / "test_model.json"
        result = train_model(
            csv_path=str(DEFAULT_CSV_PATH), model_output_path=str(model_path)
        )
        assert result["model_path"] == str(model_path)

    def test_train_returns_feature_importance(self, tmp_path) -> None:
        """返回字典应包含 feature_importance。"""
        model_path = tmp_path / "test_model.json"
        result = train_model(
            csv_path=str(DEFAULT_CSV_PATH), model_output_path=str(model_path)
        )
        assert "feature_importance" in result
        assert isinstance(result["feature_importance"], dict)


# ==============================================================================
# 6. HitPredictor - 基础预测 (使用预训练模型)
# ==============================================================================


class TestHitPredictorBasic:
    """HitPredictor 基础预测测试 - hitScore / topFactors。"""

    def test_predict_returns_dict(self) -> None:
        """predict 应返回字典。"""
        predictor = HitPredictor(model_path=str(DEFAULT_MODEL_PATH))
        result = predictor.predict(_make_full_raw_data())
        assert isinstance(result, dict)

    def test_predict_returns_hit_score(self) -> None:
        """predict 应返回 hitScore 字段。"""
        predictor = HitPredictor(model_path=str(DEFAULT_MODEL_PATH))
        result = predictor.predict(_make_full_raw_data())
        assert "hitScore" in result

    def test_hit_score_in_valid_range(self) -> None:
        """hitScore 应在 0-1 范围内。"""
        predictor = HitPredictor(model_path=str(DEFAULT_MODEL_PATH))
        result = predictor.predict(_make_full_raw_data())
        assert 0.0 <= result["hitScore"] <= 1.0

    def test_predict_returns_top_factors(self) -> None:
        """predict 应返回 topFactors 字段。"""
        predictor = HitPredictor(model_path=str(DEFAULT_MODEL_PATH))
        result = predictor.predict(_make_full_raw_data())
        assert "topFactors" in result

    def test_top_factors_is_list(self) -> None:
        """topFactors 应为列表。"""
        predictor = HitPredictor(model_path=str(DEFAULT_MODEL_PATH))
        result = predictor.predict(_make_full_raw_data())
        assert isinstance(result["topFactors"], list)

    def test_top_factors_has_three_items(self) -> None:
        """topFactors 应包含恰好 3 项 (Top-3 影响因子)。"""
        predictor = HitPredictor(model_path=str(DEFAULT_MODEL_PATH))
        result = predictor.predict(_make_full_raw_data())
        assert len(result["topFactors"]) == 3

    def test_top_factors_contain_feature_name(self) -> None:
        """每个 topFactor 应含 feature 字段 (特征名)。"""
        predictor = HitPredictor(model_path=str(DEFAULT_MODEL_PATH))
        result = predictor.predict(_make_full_raw_data())
        for factor in result["topFactors"]:
            assert "feature" in factor
            assert isinstance(factor["feature"], str)

    def test_top_factors_contain_value(self) -> None:
        """每个 topFactor 应含数值字段 (shap_value 或 importance)。"""
        predictor = HitPredictor(model_path=str(DEFAULT_MODEL_PATH))
        result = predictor.predict(_make_full_raw_data())
        for factor in result["topFactors"]:
            # 含 shap_value 或 importance 之一
            assert "shap_value" in factor or "importance" in factor
            value = factor.get("shap_value", factor.get("importance"))
            assert isinstance(value, (int, float))

    def test_top_factors_feature_names_valid(self) -> None:
        """topFactors 中的 feature 名应在 19 个特征名范围内。"""
        predictor = HitPredictor(model_path=str(DEFAULT_MODEL_PATH))
        result = predictor.predict(_make_full_raw_data())
        valid_names = set(FeatureExtractor.FEATURE_NAMES)
        for factor in result["topFactors"]:
            assert factor["feature"] in valid_names


# ==============================================================================
# 7. HitPredictor - 从文件加载
# ==============================================================================


class TestHitPredictorLoading:
    """HitPredictor 模型加载测试。"""

    def test_load_from_default_path(self) -> None:
        """不传 model_path 时应使用默认路径加载。"""
        # 默认路径为 backend/data/xgboost_model.json
        predictor = HitPredictor()
        result = predictor.predict(_make_full_raw_data())
        assert "hitScore" in result

    def test_load_from_custom_path(self) -> None:
        """传入自定义 model_path 应成功加载。"""
        predictor = HitPredictor(model_path=str(DEFAULT_MODEL_PATH))
        result = predictor.predict(_make_full_raw_data())
        assert "hitScore" in result


# ==============================================================================
# 8. HitPredictor - 批量预测
# ==============================================================================


class TestHitPredictorBatch:
    """HitPredictor 批量预测测试。"""

    def test_predict_batch_returns_list(self) -> None:
        """predict_batch 应返回列表。"""
        predictor = HitPredictor(model_path=str(DEFAULT_MODEL_PATH))
        raw_list = [_make_full_raw_data(), _make_full_raw_data()]
        result = predictor.predict_batch(raw_list)
        assert isinstance(result, list)

    def test_predict_batch_correct_count(self) -> None:
        """predict_batch 返回数量应与输入一致。"""
        predictor = HitPredictor(model_path=str(DEFAULT_MODEL_PATH))
        raw_list = [_make_full_raw_data() for _ in range(4)]
        result = predictor.predict_batch(raw_list)
        assert len(result) == 4

    def test_predict_batch_each_item_has_hit_score(self) -> None:
        """predict_batch 每项应含 hitScore。"""
        predictor = HitPredictor(model_path=str(DEFAULT_MODEL_PATH))
        raw_list = [_make_full_raw_data(), _make_minimal_raw_data()]
        result = predictor.predict_batch(raw_list)
        for item in result:
            assert "hitScore" in item
            assert 0.0 <= item["hitScore"] <= 1.0

    def test_predict_batch_empty_list(self) -> None:
        """空列表应返回空列表。"""
        predictor = HitPredictor(model_path=str(DEFAULT_MODEL_PATH))
        result = predictor.predict_batch([])
        assert result == []


# ==============================================================================
# 9. HitPredictor - 边界场景
# ==============================================================================


class TestHitPredictorEdgeCases:
    """HitPredictor 边界场景测试 - 空数据 / 全零 / 极端值。"""

    def test_empty_dict_returns_valid_hit_score(self) -> None:
        """空字典应返回有效的 hitScore (0-1)。"""
        predictor = HitPredictor(model_path=str(DEFAULT_MODEL_PATH))
        result = predictor.predict({})
        assert 0.0 <= result["hitScore"] <= 1.0

    def test_empty_dict_returns_three_factors(self) -> None:
        """空字典应仍返回 3 个 topFactors。"""
        predictor = HitPredictor(model_path=str(DEFAULT_MODEL_PATH))
        result = predictor.predict({})
        assert len(result["topFactors"]) == 3

    def test_all_zero_features(self) -> None:
        """全零特征应返回有效的预测结果。"""
        predictor = HitPredictor(model_path=str(DEFAULT_MODEL_PATH))
        raw = {name: 0.0 for name in FeatureExtractor.FEATURE_NAMES}
        result = predictor.predict(raw)
        assert 0.0 <= result["hitScore"] <= 1.0
        assert len(result["topFactors"]) == 3

    def test_extreme_high_values(self) -> None:
        """极端高值特征应返回有效的预测结果。"""
        predictor = HitPredictor(model_path=str(DEFAULT_MODEL_PATH))
        raw = {
            "category_heat": 100.0,
            "trend_growth_rate": 100.0,
            "seasonality_index": 1.0,
            "competitor_density": 1.0,
            "cross_region_diffusion_speed": 1.0,
            "price_percentile": 1.0,
            "material_cost_ratio": 1.0,
            "design_novelty": 1.0,
            "ip_power_score": 100.0,
            "ip_category_match": 1.0,
            "ip_license_urgency": 1.0,
            "ip_region_heat_variance": 100.0,
            "z_gen_match": 1.0,
            "aesthetic_tag_heat": 100.0,
            "audience_spending_power": 1.0,
            "social_virality": 1.0,
            "trend_sentiment": 1.0,
            "social_mentions": 100000.0,
            "positive_review_ratio": 1.0,
        }
        result = predictor.predict(raw)
        assert 0.0 <= result["hitScore"] <= 1.0
        assert len(result["topFactors"]) == 3

    def test_extreme_low_values(self) -> None:
        """极端低值特征 (含负值) 应返回有效的预测结果。"""
        predictor = HitPredictor(model_path=str(DEFAULT_MODEL_PATH))
        raw = {
            "category_heat": 0.0,
            "trend_growth_rate": -50.0,
            "seasonality_index": 0.0,
            "competitor_density": 0.0,
            "cross_region_diffusion_speed": 0.0,
            "price_percentile": 0.0,
            "material_cost_ratio": 0.0,
            "design_novelty": 0.0,
            "ip_power_score": 0.0,
            "ip_category_match": 0.0,
            "ip_license_urgency": 0.0,
            "ip_region_heat_variance": 0.0,
            "z_gen_match": 0.0,
            "aesthetic_tag_heat": 0.0,
            "audience_spending_power": 0.0,
            "social_virality": 0.0,
            "trend_sentiment": -1.0,
            "social_mentions": 0.0,
            "positive_review_ratio": 0.0,
        }
        result = predictor.predict(raw)
        assert 0.0 <= result["hitScore"] <= 1.0
        assert len(result["topFactors"]) == 3

    def test_high_hit_product_scores_higher_than_low(self) -> None:
        """高爆品潜质产品的 hitScore 应高于低爆品潜质产品。"""
        predictor = HitPredictor(model_path=str(DEFAULT_MODEL_PATH))
        # 高潜质产品
        high_raw = _make_full_raw_data()
        # 低潜质产品 (低热度/无IP/低Z世代匹配)
        low_raw = {
            "product_name": "低潜质产品",
            "category": "食品/零食",
            "category_heat": 10.0,
            "trend_growth_rate": -30.0,
            "seasonality_index": 0.1,
            "competitor_density": 0.9,
            "cross_region_diffusion_speed": 0.05,
            "price_percentile": 0.1,
            "material_cost_ratio": 0.8,
            "design_novelty": 0.1,
            "ip_power_score": 0.0,
            "ip_category_match": 0.0,
            "ip_license_urgency": 0.0,
            "ip_region_heat_variance": 0.0,
            "z_gen_match": 0.1,
            "aesthetic_tag_heat": 5.0,
            "audience_spending_power": 0.1,
            "social_virality": 0.05,
            "trend_sentiment": -0.8,
            "social_mentions": 50.0,
            "positive_review_ratio": 0.2,
        }
        high_result = predictor.predict(high_raw)
        low_result = predictor.predict(low_raw)
        assert high_result["hitScore"] > low_result["hitScore"]


# ==============================================================================
# 10. HitPredictor - 预测一致性
# ==============================================================================


class TestHitPredictorConsistency:
    """HitPredictor 预测一致性测试。"""

    def test_same_input_same_output(self) -> None:
        """相同输入应产生相同输出 (确定性预测)。"""
        predictor = HitPredictor(model_path=str(DEFAULT_MODEL_PATH))
        raw = _make_full_raw_data()
        result1 = predictor.predict(raw)
        result2 = predictor.predict(raw)
        assert result1["hitScore"] == pytest.approx(result2["hitScore"])

    def test_predict_batch_consistent_with_predict(self) -> None:
        """predict_batch 单项结果应与 predict 一致。"""
        predictor = HitPredictor(model_path=str(DEFAULT_MODEL_PATH))
        raw = _make_full_raw_data()
        single = predictor.predict(raw)
        batch = predictor.predict_batch([raw])
        assert single["hitScore"] == pytest.approx(batch[0]["hitScore"])
