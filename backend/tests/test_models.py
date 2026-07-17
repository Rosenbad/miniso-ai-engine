# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 共享数据模型单元测试
# ==============================================================================
# 对应 Task 2: 共享数据模型 + 数据库连接
# 覆盖: TrendSignal / IPMatch / ProductIdeaCard / ProductDirection / ProductConcept
# ==============================================================================

"""
测试共享数据模型的字段完整性与校验逻辑。

测试策略 (TDD):
  1. 字段完整性 - 每个模型按 spec §3.4 / §4.3 / §4.4 定义全部字段
  2. 字段校验器 - heatScore 0-100 / sentiment -1~1 / hitScore 0-1 等
  3. 序列化往返 - model_dump -> model_validate 可无损还原
  4. 嵌套模型 - ProductIdeaCard.ipMatch 为 IPMatch 实例
  5. 默认值与可选字段
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest
from pydantic import ValidationError

from shared.models import (
    IPMatch,
    ProductConcept,
    ProductDirection,
    ProductIdeaCard,
    TrendSignal,
)


# ==============================================================================
# 测试夹具 - 构造合法的模型数据
# ==============================================================================


@pytest.fixture
def trend_signal_data() -> Dict[str, Any]:
    """构造一份合法的 TrendSignal 数据 (spec §3.4 全部 13 字段)。"""
    return {
        "topic": "侘寂风家居",
        "heatScore": 87.5,
        "growthRate": 34.2,
        "category": "家居/装饰",
        "sentiment": 0.62,
        "lifecycle": "rising",
        "predictWindow": "2-4周",
        "relatedKeywords": ["侘寂", "原木", "极简", "手作"],
        "sourceBreakdown": {
            "xiaohongshu": 45,
            "douyin": 30,
            "weibo": 15,
            "others": 10,
        },
        "region": "china",
        "zGenTags": ["Y2K", "多巴胺"],
        "targetAudience": {
            "ageRange": "18-25",
            "aesthetic": "极简自然",
            "spendingPower": "中",
        },
        "crossRegionDiff": {
            "us": "peak",
            "cn": "rising",
            "sea": "nascent",
        },
    }


@pytest.fixture
def ip_match_data() -> Dict[str, Any]:
    """构造一份合法的 IPMatch 数据 (spec §4.3 全部 7 字段)。"""
    return {
        "ipName": "三丽鸥·库洛米",
        "ipPowerScore": 92.0,
        "matchScore": 0.85,
        "availability": "available",
        "exclusiveUntil": "2025-12-31",
        "regionHeatMap": {
            "china": 92,
            "sea": 78,
            "us": 65,
            "eu": 45,
        },
        "recommendedCategories": ["美妆", "文具", "家居饰品"],
    }


@pytest.fixture
def product_idea_card_data(ip_match_data: Dict[str, Any]) -> Dict[str, Any]:
    """构造一份合法的 ProductIdeaCard 数据 (spec §4.4 全字段)。"""
    return {
        "conceptId": "CPT-2025-0001",
        "productName": "库洛米侘寂风香薰蜡烛",
        "category": "家居/香氛",
        "designDesc": "库洛米形象结合侘寂风原木底座，哑光釉面陶瓷杯身",
        "material": "大豆蜡 + 陶瓷",
        "priceRange": "59-89",
        "ipMatch": ip_match_data,
        "sellingPoints": [
            "IP 联名限量款",
            "天然大豆蜡 48h 持久燃烧",
            "侘寂风设计百搭家居场景",
        ],
        "hitScore": 0.78,
        "topFactors": [
            {"feature": "ip_power_score", "shap": 0.32},
            {"feature": "trend_heat", "shap": 0.24},
            {"feature": "z_gen_match", "shap": 0.18},
        ],
        "conceptImages": [
            "https://cdn.miniso.com/concepts/cpt-2025-0001-front.png",
            "https://cdn.miniso.com/concepts/cpt-2025-0001-scene.png",
        ],
        "trendSource": "侘寂风家居",
        "zGenMatchScore": 0.82,
        "targetAudience": {
            "ageRange": "18-25",
            "aesthetic": "侘寂自然",
            "spendingPower": "中",
        },
        "regionFit": {
            "china": "high",
            "sea": "medium",
            "us": "low",
        },
        "agentTrace": [
            {"agent": "ProductDirector", "step": "direction", "output": "家居/香氛"},
            {"agent": "ConceptCreator", "step": "concept", "output": "香薰蜡烛"},
            {"agent": "HitPredictor", "step": "score", "output": 0.78},
        ],
    }


@pytest.fixture
def product_direction_data() -> Dict[str, Any]:
    """构造一份合法的 ProductDirection 数据 (Agent 1 输出, 6 字段)。"""
    return {
        "category": "家居/香氛",
        "styleTone": "侘寂自然",
        "targetAudience": {
            "ageRange": "18-25",
            "aesthetic": "极简自然",
            "spendingPower": "中",
        },
        "priceRange": "59-129",
        "zGenTags": ["Y2K", "多巴胺", "侘寂"],
        "crossRegionAdvice": {
            "china": "主推",
            "sea": "次推",
            "us": "观望",
        },
    }


@pytest.fixture
def product_concept_data() -> Dict[str, Any]:
    """构造一份合法的 ProductConcept 数据 (Agent 2 输出, 8 字段)。"""
    return {
        "productName": "库洛米侘寂风香薰蜡烛",
        "category": "家居/香氛",
        "designDesc": "库洛米形象结合侘寂风原木底座，哑光釉面陶瓷杯身",
        "material": "大豆蜡 + 陶瓷",
        "priceRange": "59-89",
        "ipDirection": "三丽鸥·库洛米",
        "sellingPoints": [
            "IP 联名限量款",
            "天然大豆蜡 48h 持久燃烧",
        ],
        "targetAudience": {
            "ageRange": "18-25",
            "aesthetic": "侘寂自然",
            "spendingPower": "中",
        },
    }


# ==============================================================================
# TrendSignal 测试 (spec §3.4 - 数据感知层输出)
# ==============================================================================


class TestTrendSignal:
    """TrendSignal 模型测试 - 验证 13 字段完整性及校验器。"""

    def test_create_with_all_fields(self, trend_signal_data: Dict[str, Any]) -> None:
        """验证 TrendSignal 能以 spec §3.4 全部 13 字段成功创建。"""
        signal = TrendSignal(**trend_signal_data)

        assert signal.topic == "侘寂风家居"
        assert signal.heatScore == 87.5
        assert signal.growthRate == 34.2
        assert signal.category == "家居/装饰"
        assert signal.sentiment == 0.62
        assert signal.lifecycle == "rising"
        assert signal.predictWindow == "2-4周"
        assert signal.relatedKeywords == ["侘寂", "原木", "极简", "手作"]
        assert signal.sourceBreakdown == {
            "xiaohongshu": 45,
            "douyin": 30,
            "weibo": 15,
            "others": 10,
        }
        # 重点验证 Task 2 强调的扩展字段
        assert signal.region == "china"
        assert signal.zGenTags == ["Y2K", "多巴胺"]
        assert signal.targetAudience == {
            "ageRange": "18-25",
            "aesthetic": "极简自然",
            "spendingPower": "中",
        }
        assert signal.crossRegionDiff == {
            "us": "peak",
            "cn": "rising",
            "sea": "nascent",
        }

    def test_field_count(self, trend_signal_data: Dict[str, Any]) -> None:
        """验证 TrendSignal 字段数量与 spec 一致 (13 字段)。"""
        signal = TrendSignal(**trend_signal_data)
        # model_fields 是 Pydantic v2 的类属性
        assert len(TrendSignal.model_fields) == 13
        assert set(signal.model_dump().keys()) == set(trend_signal_data.keys())

    def test_required_fields(self) -> None:
        """验证缺失必填字段会抛出 ValidationError。

        TrendSignal 有 7 个必填字段 (无默认值):
            heatScore / growthRate / category / sentiment /
            lifecycle / predictWindow / region
        其余 5 个 list/dict 字段有默认值 (空集合)，不报缺失。
        """
        with pytest.raises(ValidationError) as exc_info:
            TrendSignal(topic="测试")  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors}
        # 7 个必填字段应报缺失 (topic 已提供)
        assert len(missing_fields) == 7
        assert "heatScore" in missing_fields
        assert "growthRate" in missing_fields
        assert "category" in missing_fields
        assert "sentiment" in missing_fields
        assert "lifecycle" in missing_fields
        assert "predictWindow" in missing_fields
        assert "region" in missing_fields
        # 有默认值的字段不应报缺失
        assert "zGenTags" not in missing_fields
        assert "targetAudience" not in missing_fields
        assert "crossRegionDiff" not in missing_fields
        assert "relatedKeywords" not in missing_fields
        assert "sourceBreakdown" not in missing_fields

    def test_heat_score_validator_upper_bound(self, trend_signal_data: Dict[str, Any]) -> None:
        """heatScore > 100 应被拒绝。"""
        trend_signal_data["heatScore"] = 101.0
        with pytest.raises(ValidationError) as exc_info:
            TrendSignal(**trend_signal_data)
        assert any(e["loc"][-1] == "heatScore" for e in exc_info.value.errors())

    def test_heat_score_validator_lower_bound(self, trend_signal_data: Dict[str, Any]) -> None:
        """heatScore < 0 应被拒绝。"""
        trend_signal_data["heatScore"] = -0.1
        with pytest.raises(ValidationError) as exc_info:
            TrendSignal(**trend_signal_data)
        assert any(e["loc"][-1] == "heatScore" for e in exc_info.value.errors())

    def test_heat_score_boundary_values(self, trend_signal_data: Dict[str, Any]) -> None:
        """heatScore 边界值 0 和 100 应通过。"""
        for boundary in (0.0, 100.0):
            trend_signal_data["heatScore"] = boundary
            signal = TrendSignal(**trend_signal_data)
            assert signal.heatScore == boundary

    def test_sentiment_validator_upper_bound(self, trend_signal_data: Dict[str, Any]) -> None:
        """sentiment > 1 应被拒绝。"""
        trend_signal_data["sentiment"] = 1.5
        with pytest.raises(ValidationError) as exc_info:
            TrendSignal(**trend_signal_data)
        assert any(e["loc"][-1] == "sentiment" for e in exc_info.value.errors())

    def test_sentiment_validator_lower_bound(self, trend_signal_data: Dict[str, Any]) -> None:
        """sentiment < -1 应被拒绝。"""
        trend_signal_data["sentiment"] = -1.1
        with pytest.raises(ValidationError) as exc_info:
            TrendSignal(**trend_signal_data)
        assert any(e["loc"][-1] == "sentiment" for e in exc_info.value.errors())

    def test_sentiment_boundary_values(self, trend_signal_data: Dict[str, Any]) -> None:
        """sentiment 边界值 -1 和 1 应通过。"""
        for boundary in (-1.0, 1.0):
            trend_signal_data["sentiment"] = boundary
            signal = TrendSignal(**trend_signal_data)
            assert signal.sentiment == boundary

    def test_lifecycle_invalid_value(self, trend_signal_data: Dict[str, Any]) -> None:
        """lifecycle 非法值应被拒绝 (仅允许 rising/peak/declining)。"""
        trend_signal_data["lifecycle"] = "unknown"
        with pytest.raises(ValidationError) as exc_info:
            TrendSignal(**trend_signal_data)
        assert any(e["loc"][-1] == "lifecycle" for e in exc_info.value.errors())

    def test_lifecycle_valid_values(self, trend_signal_data: Dict[str, Any]) -> None:
        """lifecycle 合法枚举值应通过。"""
        for value in ("rising", "peak", "declining"):
            trend_signal_data["lifecycle"] = value
            signal = TrendSignal(**trend_signal_data)
            assert signal.lifecycle == value

    def test_region_invalid_value(self, trend_signal_data: Dict[str, Any]) -> None:
        """region 非法值应被拒绝 (仅允许 china/sea/us/eu/global)。"""
        trend_signal_data["region"] = "japan"
        with pytest.raises(ValidationError) as exc_info:
            TrendSignal(**trend_signal_data)
        assert any(e["loc"][-1] == "region" for e in exc_info.value.errors())

    def test_serialization_roundtrip(self, trend_signal_data: Dict[str, Any]) -> None:
        """验证 model_dump -> model_validate 可无损往返。"""
        signal = TrendSignal(**trend_signal_data)
        dumped = signal.model_dump()
        restored = TrendSignal.model_validate(dumped)
        assert restored == signal

    def test_json_serialization_roundtrip(self, trend_signal_data: Dict[str, Any]) -> None:
        """验证 model_dump_json -> model_validate_json 可无损往返。"""
        signal = TrendSignal(**trend_signal_data)
        json_str = signal.model_dump_json()
        restored = TrendSignal.model_validate_json(json_str)
        assert restored == signal


# ==============================================================================
# IPMatch 测试 (spec §4.3 - IP 联名匹配输出)
# ==============================================================================


class TestIPMatch:
    """IPMatch 模型测试 - 验证 7 字段完整性及校验器。"""

    def test_create_with_all_fields(self, ip_match_data: Dict[str, Any]) -> None:
        """验证 IPMatch 能以 spec §4.3 全部 7 字段成功创建。"""
        match = IPMatch(**ip_match_data)

        assert match.ipName == "三丽鸥·库洛米"
        assert match.ipPowerScore == 92.0
        assert match.matchScore == 0.85
        assert match.availability == "available"
        assert match.exclusiveUntil == "2025-12-31"
        assert match.regionHeatMap == {
            "china": 92,
            "sea": 78,
            "us": 65,
            "eu": 45,
        }
        assert match.recommendedCategories == ["美妆", "文具", "家居饰品"]

    def test_field_count(self, ip_match_data: Dict[str, Any]) -> None:
        """验证 IPMatch 字段数量与 spec 一致 (7 字段)。"""
        IPMatch(**ip_match_data)
        assert len(IPMatch.model_fields) == 7

    def test_ip_power_score_validator_upper_bound(self, ip_match_data: Dict[str, Any]) -> None:
        """ipPowerScore > 100 应被拒绝。"""
        ip_match_data["ipPowerScore"] = 100.1
        with pytest.raises(ValidationError) as exc_info:
            IPMatch(**ip_match_data)
        assert any(e["loc"][-1] == "ipPowerScore" for e in exc_info.value.errors())

    def test_ip_power_score_validator_lower_bound(self, ip_match_data: Dict[str, Any]) -> None:
        """ipPowerScore < 0 应被拒绝。"""
        ip_match_data["ipPowerScore"] = -1.0
        with pytest.raises(ValidationError) as exc_info:
            IPMatch(**ip_match_data)
        assert any(e["loc"][-1] == "ipPowerScore" for e in exc_info.value.errors())

    def test_match_score_validator_upper_bound(self, ip_match_data: Dict[str, Any]) -> None:
        """matchScore > 1 应被拒绝。"""
        ip_match_data["matchScore"] = 1.1
        with pytest.raises(ValidationError) as exc_info:
            IPMatch(**ip_match_data)
        assert any(e["loc"][-1] == "matchScore" for e in exc_info.value.errors())

    def test_match_score_validator_lower_bound(self, ip_match_data: Dict[str, Any]) -> None:
        """matchScore < 0 应被拒绝。"""
        ip_match_data["matchScore"] = -0.01
        with pytest.raises(ValidationError) as exc_info:
            IPMatch(**ip_match_data)
        assert any(e["loc"][-1] == "matchScore" for e in exc_info.value.errors())

    def test_availability_invalid_value(self, ip_match_data: Dict[str, Any]) -> None:
        """availability 非法值应被拒绝 (仅允许 available/exclusive/expiring/unavailable)。"""
        ip_match_data["availability"] = "maybe"
        with pytest.raises(ValidationError) as exc_info:
            IPMatch(**ip_match_data)
        assert any(e["loc"][-1] == "availability" for e in exc_info.value.errors())

    def test_availability_valid_values(self, ip_match_data: Dict[str, Any]) -> None:
        """availability 合法枚举值应通过。"""
        for value in ("available", "exclusive", "expiring", "unavailable"):
            ip_match_data["availability"] = value
            match = IPMatch(**ip_match_data)
            assert match.availability == value

    def test_serialization_roundtrip(self, ip_match_data: Dict[str, Any]) -> None:
        """验证 model_dump -> model_validate 可无损往返。"""
        match = IPMatch(**ip_match_data)
        dumped = match.model_dump()
        restored = IPMatch.model_validate(dumped)
        assert restored == match


# ==============================================================================
# ProductIdeaCard 测试 (spec §4.4 - 决策推理层输出)
# ==============================================================================


class TestProductIdeaCard:
    """ProductIdeaCard 模型测试 - 验证全字段完整性、嵌套模型及校验器。"""

    def test_create_with_all_fields(
        self, product_idea_card_data: Dict[str, Any]
    ) -> None:
        """验证 ProductIdeaCard 能以 spec §4.4 全字段成功创建。"""
        card = ProductIdeaCard(**product_idea_card_data)

        assert card.conceptId == "CPT-2025-0001"
        assert card.productName == "库洛米侘寂风香薰蜡烛"
        assert card.category == "家居/香氛"
        assert card.designDesc.startswith("库洛米形象")
        assert card.material == "大豆蜡 + 陶瓷"
        assert card.priceRange == "59-89"
        # 重点验证 Task 2 强调的嵌套与评分字段
        assert isinstance(card.ipMatch, IPMatch)
        assert card.ipMatch.ipName == "三丽鸥·库洛米"
        assert card.zGenMatchScore == 0.82
        assert card.regionFit == {
            "china": "high",
            "sea": "medium",
            "us": "low",
        }
        assert card.hitScore == 0.78
        assert len(card.sellingPoints) == 3
        assert len(card.topFactors) == 3
        assert len(card.conceptImages) == 2
        assert card.trendSource == "侘寂风家居"
        assert card.agentTrace[0]["agent"] == "ProductDirector"

    def test_field_count(self, product_idea_card_data: Dict[str, Any]) -> None:
        """验证 ProductIdeaCard 字段数量与 spec 一致 (16 字段)。"""
        ProductIdeaCard(**product_idea_card_data)
        assert len(ProductIdeaCard.model_fields) == 16

    def test_ip_match_nested_model(self, product_idea_card_data: Dict[str, Any]) -> None:
        """验证 ipMatch 字段被正确解析为 IPMatch 嵌套实例。"""
        card = ProductIdeaCard(**product_idea_card_data)
        assert isinstance(card.ipMatch, IPMatch)
        assert card.ipMatch.matchScore == 0.85
        # 嵌套模型也应能独立序列化
        nested_dump = card.ipMatch.model_dump()
        assert nested_dump["ipName"] == "三丽鸥·库洛米"

    def test_ip_match_dict_input_coerced(
        self, product_idea_card_data: Dict[str, Any], ip_match_data: Dict[str, Any]
    ) -> None:
        """验证传入 dict 会被自动强转为 IPMatch 实例。"""
        product_idea_card_data["ipMatch"] = ip_match_data  # dict 形式
        card = ProductIdeaCard(**product_idea_card_data)
        assert isinstance(card.ipMatch, IPMatch)

    def test_hit_score_validator_upper_bound(
        self, product_idea_card_data: Dict[str, Any]
    ) -> None:
        """hitScore > 1 应被拒绝。"""
        product_idea_card_data["hitScore"] = 1.01
        with pytest.raises(ValidationError) as exc_info:
            ProductIdeaCard(**product_idea_card_data)
        assert any(e["loc"][-1] == "hitScore" for e in exc_info.value.errors())

    def test_hit_score_validator_lower_bound(
        self, product_idea_card_data: Dict[str, Any]
    ) -> None:
        """hitScore < 0 应被拒绝。"""
        product_idea_card_data["hitScore"] = -0.01
        with pytest.raises(ValidationError) as exc_info:
            ProductIdeaCard(**product_idea_card_data)
        assert any(e["loc"][-1] == "hitScore" for e in exc_info.value.errors())

    def test_z_gen_match_score_validator(
        self, product_idea_card_data: Dict[str, Any]
    ) -> None:
        """zGenMatchScore 超出 [0, 1] 应被拒绝。"""
        for invalid_value in (-0.1, 1.5):
            product_idea_card_data["zGenMatchScore"] = invalid_value
            with pytest.raises(ValidationError) as exc_info:
                ProductIdeaCard(**product_idea_card_data)
            assert any(e["loc"][-1] == "zGenMatchScore" for e in exc_info.value.errors())

    def test_serialization_roundtrip(
        self, product_idea_card_data: Dict[str, Any]
    ) -> None:
        """验证 model_dump -> model_validate 可无损往返 (含嵌套模型)。"""
        card = ProductIdeaCard(**product_idea_card_data)
        dumped = card.model_dump()
        restored = ProductIdeaCard.model_validate(dumped)
        assert restored == card
        # 嵌套模型类型应保持
        assert isinstance(restored.ipMatch, IPMatch)

    def test_json_serialization_roundtrip(
        self, product_idea_card_data: Dict[str, Any]
    ) -> None:
        """验证 model_dump_json -> model_validate_json 可无损往返。"""
        card = ProductIdeaCard(**product_idea_card_data)
        json_str = card.model_dump_json()
        restored = ProductIdeaCard.model_validate_json(json_str)
        assert restored == card


# ==============================================================================
# ProductDirection 测试 (Agent 1 输出)
# ==============================================================================


class TestProductDirection:
    """ProductDirection 模型测试 - 验证 6 字段完整性。"""

    def test_create_with_all_fields(
        self, product_direction_data: Dict[str, Any]
    ) -> None:
        """验证 ProductDirection 能以全部 6 字段成功创建。"""
        direction = ProductDirection(**product_direction_data)

        assert direction.category == "家居/香氛"
        assert direction.styleTone == "侘寂自然"
        assert direction.targetAudience == {
            "ageRange": "18-25",
            "aesthetic": "极简自然",
            "spendingPower": "中",
        }
        assert direction.priceRange == "59-129"
        assert direction.zGenTags == ["Y2K", "多巴胺", "侘寂"]
        assert direction.crossRegionAdvice == {
            "china": "主推",
            "sea": "次推",
            "us": "观望",
        }

    def test_field_count(self, product_direction_data: Dict[str, Any]) -> None:
        """验证 ProductDirection 字段数量 (6 字段)。"""
        ProductDirection(**product_direction_data)
        assert len(ProductDirection.model_fields) == 6

    def test_required_fields(self) -> None:
        """验证缺失必填字段会抛出 ValidationError。"""
        with pytest.raises(ValidationError):
            ProductDirection(category="测试")  # type: ignore[call-arg]

    def test_serialization_roundtrip(
        self, product_direction_data: Dict[str, Any]
    ) -> None:
        """验证 model_dump -> model_validate 可无损往返。"""
        direction = ProductDirection(**product_direction_data)
        dumped = direction.model_dump()
        restored = ProductDirection.model_validate(dumped)
        assert restored == direction


# ==============================================================================
# ProductConcept 测试 (Agent 2 输出)
# ==============================================================================


class TestProductConcept:
    """ProductConcept 模型测试 - 验证 8 字段完整性。"""

    def test_create_with_all_fields(
        self, product_concept_data: Dict[str, Any]
    ) -> None:
        """验证 ProductConcept 能以全部 8 字段成功创建。"""
        concept = ProductConcept(**product_concept_data)

        assert concept.productName == "库洛米侘寂风香薰蜡烛"
        assert concept.category == "家居/香氛"
        assert concept.designDesc.startswith("库洛米形象")
        assert concept.material == "大豆蜡 + 陶瓷"
        assert concept.priceRange == "59-89"
        assert concept.ipDirection == "三丽鸥·库洛米"
        assert len(concept.sellingPoints) == 2
        assert concept.targetAudience == {
            "ageRange": "18-25",
            "aesthetic": "侘寂自然",
            "spendingPower": "中",
        }

    def test_field_count(self, product_concept_data: Dict[str, Any]) -> None:
        """验证 ProductConcept 字段数量 (8 字段)。"""
        ProductConcept(**product_concept_data)
        assert len(ProductConcept.model_fields) == 8

    def test_required_fields(self) -> None:
        """验证缺失必填字段会抛出 ValidationError。"""
        with pytest.raises(ValidationError):
            ProductConcept(productName="测试")  # type: ignore[call-arg]

    def test_serialization_roundtrip(
        self, product_concept_data: Dict[str, Any]
    ) -> None:
        """验证 model_dump -> model_validate 可无损往返。"""
        concept = ProductConcept(**product_concept_data)
        dumped = concept.model_dump()
        restored = ProductConcept.model_validate(dumped)
        assert restored == concept


# ==============================================================================
# 数据库连接模块导入测试 (shared/database.py + shared/redis_client.py)
# ==============================================================================


class TestDatabaseModule:
    """验证 shared/database.py 可正常导入并暴露关键对象。"""

    def test_database_module_imports(self) -> None:
        """验证 database 模块暴露 engine / session / Base / get_db。"""
        from shared import database

        assert hasattr(database, "engine")
        assert hasattr(database, "AsyncSessionLocal")
        assert hasattr(database, "Base")
        assert hasattr(database, "get_db")
        # get_db 应为可调用 (FastAPI 依赖)
        assert callable(database.get_db)

    def test_base_is_declarative(self) -> None:
        """验证 Base 是 SQLAlchemy DeclarativeBase 子类。"""
        from sqlalchemy.orm import DeclarativeBase

        from shared.database import Base

        assert isinstance(Base, type)
        assert issubclass(Base, DeclarativeBase)


class TestRedisModule:
    """验证 shared/redis_client.py 可正常导入并暴露关键对象。"""

    def test_redis_module_imports(self) -> None:
        """验证 redis_client 模块暴露 get_redis。"""
        from shared import redis_client

        assert hasattr(redis_client, "get_redis")
        assert callable(redis_client.get_redis)

    def test_redis_pool_configured(self) -> None:
        """验证 Redis 连接池已配置。"""
        from shared.redis_client import _redis_pool

        assert _redis_pool is not None


# ==============================================================================
# _convert_to_async_url() 单元测试 (shared/database.py - I1)
# ==============================================================================
# 该函数为纯函数，无需真实数据库连接即可测试。
# 覆盖四类输入: 同步 URL / psycopg2 URL / 已是 asyncpg URL / 非 PostgreSQL URL
# ==============================================================================


class TestConvertToAsyncUrl:
    """测试 database._convert_to_async_url() 的 URL 协议转换逻辑。"""

    def test_plain_postgresql_to_asyncpg(self) -> None:
        """postgresql:// 应被转换为 postgresql+asyncpg://"""
        from shared.database import _convert_to_async_url

        url = "postgresql://miniso:miniso@localhost:5432/miniso_ai"
        expected = "postgresql+asyncpg://miniso:miniso@localhost:5432/miniso_ai"
        assert _convert_to_async_url(url) == expected

    def test_postgresql_no_credentials_to_asyncpg(self) -> None:
        """无凭证的 postgresql:// 也应正确转换。"""
        from shared.database import _convert_to_async_url

        url = "postgresql://localhost:5432/db"
        expected = "postgresql+asyncpg://localhost:5432/db"
        assert _convert_to_async_url(url) == expected

    def test_psycopg2_to_asyncpg(self) -> None:
        """postgresql+psycopg2:// 应被转换为 postgresql+asyncpg://"""
        from shared.database import _convert_to_async_url

        url = "postgresql+psycopg2://user:pass@localhost:5432/db"
        expected = "postgresql+asyncpg://user:pass@localhost:5432/db"
        assert _convert_to_async_url(url) == expected

    def test_asyncpg_url_unchanged(self) -> None:
        """postgresql+asyncpg:// 应保持不变 (幂等)。"""
        from shared.database import _convert_to_async_url

        url = "postgresql+asyncpg://user:pass@localhost:5432/db"
        assert _convert_to_async_url(url) == url

    def test_non_postgresql_url_unchanged(self) -> None:
        """非 PostgreSQL URL (如 SQLite) 应原样返回。"""
        from shared.database import _convert_to_async_url

        url = "sqlite:///./test.db"
        assert _convert_to_async_url(url) == url

    def test_sqlite_in_memory_unchanged(self) -> None:
        """SQLite 内存数据库 URL 应原样返回。"""
        from shared.database import _convert_to_async_url

        url = "sqlite:///:memory:"
        assert _convert_to_async_url(url) == url

    def test_mysql_url_unchanged(self) -> None:
        """MySQL URL 应原样返回 (仅转换 PostgreSQL)。"""
        from shared.database import _convert_to_async_url

        url = "mysql://user:pass@localhost:3306/db"
        assert _convert_to_async_url(url) == url


# ==============================================================================
# Redis 客户端行为测试 (shared/redis_client.py - I2)
# ==============================================================================
# 覆盖: 单例行为 / ping 成功与失败路径 / close_redis 重置单例
# ==============================================================================


class TestRedisClient:
    """测试 redis_client 模块的单例行为与健康检查。"""

    def test_get_redis_client_singleton(self, mocker: Any) -> None:
        """两次调用 get_redis_client() 应返回同一实例 (单例)。"""
        import shared.redis_client as redis_module

        # 重置单例为 None 确保干净起点 (mocker 会在测试后自动恢复原值)
        mocker.patch.object(redis_module, "_redis_client", None)
        client1 = redis_module.get_redis_client()
        client2 = redis_module.get_redis_client()
        assert client1 is client2
        # 再次调用仍应返回同一实例
        assert redis_module.get_redis_client() is client1

    def test_get_redis_client_caches_after_first_call(self, mocker: Any) -> None:
        """单例建立后，get_redis_client 不应再重复构造新实例。"""
        import shared.redis_client as redis_module

        mocker.patch.object(redis_module, "_redis_client", None)
        # 用 spy 监视 Redis 构造，验证只被调用一次
        spy = mocker.patch(
            "redis.asyncio.Redis", wraps=redis_module.aioredis.Redis
        )
        redis_module.get_redis_client()
        redis_module.get_redis_client()
        redis_module.get_redis_client()
        assert spy.call_count == 1

    async def test_ping_success(self, mocker: Any) -> None:
        """ping() 在连接正常时应返回 True。"""
        import shared.redis_client as redis_module

        mock_client = mocker.AsyncMock()
        mock_client.ping.return_value = True
        mocker.patch.object(redis_module, "get_redis_client", return_value=mock_client)

        result = await redis_module.ping()

        assert result is True
        mock_client.ping.assert_awaited_once()

    async def test_ping_failure_returns_false(self, mocker: Any) -> None:
        """ping() 在连接异常时应返回 False (捕获异常而非抛出)。"""
        import shared.redis_client as redis_module

        mock_client = mocker.AsyncMock()
        mock_client.ping.side_effect = ConnectionError("connection refused")
        mocker.patch.object(redis_module, "get_redis_client", return_value=mock_client)

        result = await redis_module.ping()

        assert result is False
        mock_client.ping.assert_awaited_once()

    async def test_ping_timeout_returns_false(self, mocker: Any) -> None:
        """ping() 在超时异常时也应返回 False。"""
        import shared.redis_client as redis_module

        mock_client = mocker.AsyncMock()
        mock_client.ping.side_effect = TimeoutError("request timed out")
        mocker.patch.object(redis_module, "get_redis_client", return_value=mock_client)

        result = await redis_module.ping()

        assert result is False

    async def test_close_redis_resets_singleton(self, mocker: Any) -> None:
        """close_redis() 应重置单例为 None 并关闭客户端。"""
        import shared.redis_client as redis_module

        mock_client = mocker.AsyncMock()
        mocker.patch.object(redis_module, "_redis_client", mock_client)
        # 屏蔽真实连接池 disconnect，避免触碰真实 Redis
        mocker.patch.object(redis_module._redis_pool, "disconnect", new=mocker.AsyncMock())

        await redis_module.close_redis()

        assert redis_module._redis_client is None
        mock_client.aclose.assert_awaited_once()

    async def test_close_redis_when_already_none(self, mocker: Any) -> None:
        """单例已为 None 时 close_redis() 不应报错。"""
        import shared.redis_client as redis_module

        mocker.patch.object(redis_module, "_redis_client", None)
        mocker.patch.object(redis_module._redis_pool, "disconnect", new=mocker.AsyncMock())

        # 不应抛出异常
        await redis_module.close_redis()
        assert redis_module._redis_client is None


# ==============================================================================
# extra="forbid" 数据契约测试 (I3)
# ==============================================================================
# 所有模型均配置 extra="forbid"，传入未知字段应抛出 ValidationError。
# ==============================================================================


class TestExtraForbid:
    """验证模型的 extra='forbid' 数据契约 - 未知字段应被拒绝。"""

    def test_trend_signal_rejects_unknown_field(
        self, trend_signal_data: Dict[str, Any]
    ) -> None:
        """TrendSignal 传入未知字段应抛出 ValidationError。"""
        trend_signal_data["unknownField"] = "rogue"
        with pytest.raises(ValidationError) as exc_info:
            TrendSignal(**trend_signal_data)
        errors = exc_info.value.errors()
        assert any(e["type"] == "extra_forbidden" for e in errors)
        assert any("unknownField" in str(e["loc"]) for e in errors)

    def test_ip_match_rejects_unknown_field(
        self, ip_match_data: Dict[str, Any]
    ) -> None:
        """IPMatch 传入未知字段应抛出 ValidationError。"""
        ip_match_data["unknownField"] = "rogue"
        with pytest.raises(ValidationError) as exc_info:
            IPMatch(**ip_match_data)
        errors = exc_info.value.errors()
        assert any(e["type"] == "extra_forbidden" for e in errors)
        assert any("unknownField" in str(e["loc"]) for e in errors)

    def test_product_idea_card_rejects_unknown_field(
        self, product_idea_card_data: Dict[str, Any]
    ) -> None:
        """ProductIdeaCard 传入未知字段应抛出 ValidationError。"""
        product_idea_card_data["unknownField"] = "rogue"
        with pytest.raises(ValidationError) as exc_info:
            ProductIdeaCard(**product_idea_card_data)
        errors = exc_info.value.errors()
        assert any(e["type"] == "extra_forbidden" for e in errors)
        assert any("unknownField" in str(e["loc"]) for e in errors)

    def test_product_direction_rejects_unknown_field(
        self, product_direction_data: Dict[str, Any]
    ) -> None:
        """ProductDirection 传入未知字段应抛出 ValidationError。"""
        product_direction_data["unknownField"] = "rogue"
        with pytest.raises(ValidationError) as exc_info:
            ProductDirection(**product_direction_data)
        assert any(e["type"] == "extra_forbidden" for e in exc_info.value.errors())

    def test_product_concept_rejects_unknown_field(
        self, product_concept_data: Dict[str, Any]
    ) -> None:
        """ProductConcept 传入未知字段应抛出 ValidationError。"""
        product_concept_data["unknownField"] = "rogue"
        with pytest.raises(ValidationError) as exc_info:
            ProductConcept(**product_concept_data)
        assert any(e["type"] == "extra_forbidden" for e in exc_info.value.errors())


# ==============================================================================
# validate_assignment=True 行为测试 (I4)
# ==============================================================================
# 所有模型均配置 validate_assignment=True，
# 赋值非法值时应抛出 ValidationError，且原值保持不变。
# ==============================================================================


class TestValidateAssignment:
    """验证模型的 validate_assignment=True - 赋值非法值应抛出 ValidationError。"""

    def test_trend_signal_heat_score_assignment_upper_bound(
        self, trend_signal_data: Dict[str, Any]
    ) -> None:
        """赋值 heatScore = 101 (>100) 应抛出 ValidationError。"""
        signal = TrendSignal(**trend_signal_data)
        original = signal.heatScore

        with pytest.raises(ValidationError) as exc_info:
            signal.heatScore = 101  # type: ignore[assignment]
        assert any(e["loc"][-1] == "heatScore" for e in exc_info.value.errors())
        # 赋值失败后原值应保持不变
        assert signal.heatScore == original

    def test_trend_signal_heat_score_assignment_lower_bound(
        self, trend_signal_data: Dict[str, Any]
    ) -> None:
        """赋值 heatScore = -1 (<0) 应抛出 ValidationError。"""
        signal = TrendSignal(**trend_signal_data)

        with pytest.raises(ValidationError) as exc_info:
            signal.heatScore = -1  # type: ignore[assignment]
        assert any(e["loc"][-1] == "heatScore" for e in exc_info.value.errors())

    def test_trend_signal_sentiment_assignment_invalid(
        self, trend_signal_data: Dict[str, Any]
    ) -> None:
        """赋值 sentiment = 1.5 (>1) 应抛出 ValidationError。"""
        signal = TrendSignal(**trend_signal_data)

        with pytest.raises(ValidationError) as exc_info:
            signal.sentiment = 1.5  # type: ignore[assignment]
        assert any(e["loc"][-1] == "sentiment" for e in exc_info.value.errors())

    def test_trend_signal_lifecycle_assignment_invalid(
        self, trend_signal_data: Dict[str, Any]
    ) -> None:
        """赋值 lifecycle 非法枚举值应抛出 ValidationError。"""
        signal = TrendSignal(**trend_signal_data)

        with pytest.raises(ValidationError) as exc_info:
            signal.lifecycle = "unknown"  # type: ignore[assignment]
        assert any(e["loc"][-1] == "lifecycle" for e in exc_info.value.errors())

    def test_trend_signal_valid_assignment_succeeds(
        self, trend_signal_data: Dict[str, Any]
    ) -> None:
        """赋值合法值应成功更新 (对照组，验证正常路径)。"""
        signal = TrendSignal(**trend_signal_data)
        signal.heatScore = 50.0
        assert signal.heatScore == 50.0

    def test_ip_match_match_score_assignment_lower_bound(
        self, ip_match_data: Dict[str, Any]
    ) -> None:
        """赋值 matchScore = -0.1 (<0) 应抛出 ValidationError。"""
        match = IPMatch(**ip_match_data)
        original = match.matchScore

        with pytest.raises(ValidationError) as exc_info:
            match.matchScore = -0.1  # type: ignore[assignment]
        assert any(e["loc"][-1] == "matchScore" for e in exc_info.value.errors())
        # 原值保持不变
        assert match.matchScore == original

    def test_ip_match_match_score_assignment_upper_bound(
        self, ip_match_data: Dict[str, Any]
    ) -> None:
        """赋值 matchScore = 1.1 (>1) 应抛出 ValidationError。"""
        match = IPMatch(**ip_match_data)

        with pytest.raises(ValidationError) as exc_info:
            match.matchScore = 1.1  # type: ignore[assignment]
        assert any(e["loc"][-1] == "matchScore" for e in exc_info.value.errors())

    def test_ip_match_ip_power_score_assignment_invalid(
        self, ip_match_data: Dict[str, Any]
    ) -> None:
        """赋值 ipPowerScore = 101 (>100) 应抛出 ValidationError。"""
        match = IPMatch(**ip_match_data)

        with pytest.raises(ValidationError) as exc_info:
            match.ipPowerScore = 101  # type: ignore[assignment]
        assert any(e["loc"][-1] == "ipPowerScore" for e in exc_info.value.errors())

    def test_ip_match_availability_assignment_invalid(
        self, ip_match_data: Dict[str, Any]
    ) -> None:
        """赋值 availability 非法枚举值应抛出 ValidationError。"""
        match = IPMatch(**ip_match_data)

        with pytest.raises(ValidationError) as exc_info:
            match.availability = "maybe"  # type: ignore[assignment]
        assert any(e["loc"][-1] == "availability" for e in exc_info.value.errors())

    def test_product_idea_card_hit_score_assignment_invalid(
        self, product_idea_card_data: Dict[str, Any]
    ) -> None:
        """赋值 hitScore = 1.5 (>1) 应抛出 ValidationError。"""
        card = ProductIdeaCard(**product_idea_card_data)

        with pytest.raises(ValidationError) as exc_info:
            card.hitScore = 1.5  # type: ignore[assignment]
        assert any(e["loc"][-1] == "hitScore" for e in exc_info.value.errors())
