# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - IP 联名匹配引擎测试 (Task 8)
# ==============================================================================
# 对应 Task 8: IP 联名匹配引擎（独立模块）
# 覆盖:
#   1. evaluate_ip        - IP 势能评分 (0-100) + 可用性 + 到期检测
#   2. match_category     - 品类匹配三级评分 (精确 1.0 / 部分 0.5 / 无 0.0)
#   3. full_match         - 完整 IPMatch 对象 (7 字段)
#   4. list_ips           - 列出所有 IP 名称
#   5. 区域热度图          - regionHeatMap 含 china/us 键
#   6. 边界场景            - IP 未找到 / 空品类 / 特殊字符
#
# 测试策略 (TDD):
#   Step 1: 编写测试 (本文件)
#   Step 2: 验证失败 (模块/数据库尚未创建)
#   Step 3: 创建 IP 数据库 JSON
#   Step 4: 实现 IPMatchEngine
#   Step 5: 验证通过
# ==============================================================================

"""
测试 IP 联名匹配引擎 (IPMatchEngine)。

测试覆盖 (TDD):
  - evaluate_ip: IP 势能评分 / 可用性 / 授权到期检测
  - match_category: 精确匹配 (1.0) / 部分匹配 (0.5) / 无匹配 (0.0)
  - full_match: 完整 IPMatch 对象 (7 字段全部填充)
  - list_ips: 返回数据库中全部 IP 名称
  - 区域热度图: regionHeatMap 含 china/us 键
  - 边界场景: IP 未找到 ValueError / 空品类 / 特殊字符

环境说明:
  - 使用真实 IP 数据库 (backend/data/ip_database.json) 进行主测试
  - 到期检测测试使用 tmp_path 构造临时数据库 (避免日期敏感)
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Dict, List

import pytest
from pydantic import ValidationError

from ideaforge.ip_engine import IPMatchEngine
from shared.models import IPMatch


# ==============================================================================
# 测试常量 - IP 数据库中已知 IP 的预期值
# ==============================================================================

_KUROMI = "三丽鸥·库洛米"
_LOTSO = "迪士尼·草莓熊"
_HARRY_POTTER = "华纳·哈利波特"
_CONAN = "青山刚昌·名侦探柯南"

_ALL_IP_NAMES = [_KUROMI, _LOTSO, _HARRY_POTTER, _CONAN]


# ==============================================================================
# 测试辅助 - 构造临时 IP 数据库 (用于到期检测等日期敏感测试)
# ==============================================================================


def _build_temp_ip_db(
    tmp_path, name: str = "测试IP", license_expiry: str = "2027-06-30"
) -> str:
    """构造一个仅含 1 个 IP 的临时数据库文件, 返回文件路径。

    用于到期检测等需要控制 licenseExpiry 的测试场景。
    """
    ip_entry = {
        "name": name,
        "powerScore": 70,
        "socialMentions": 500000,
        "searchHeat": 75,
        "merchandiseSales": 70,
        "topicGrowth": 10.0,
        "regionHeat": {"china": 80, "sea": 60, "us": 50, "eu": 40},
        "categories": ["美妆/个护"],
        "categoryMatchScores": {"美妆/个护": 0.90},
        "availability": "available",
        "exclusiveUntil": None,
        "licenseExpiry": license_expiry,
    }
    db_path = tmp_path / "test_ip_db.json"
    db_path.write_text(json.dumps([ip_entry], ensure_ascii=False), encoding="utf-8")
    return str(db_path)


# ==============================================================================
# 1. IP 势能评分 (evaluate_ip)
# ==============================================================================


class TestEvaluateIPPowerScore:
    """IP 势能评分测试 - 返回正确的 ipPowerScore (0-100)。"""

    def test_evaluate_ip_returns_power_score(self) -> None:
        """evaluate_ip 应返回 ipPowerScore 字段。"""
        engine = IPMatchEngine()
        result = engine.evaluate_ip(_KUROMI)
        assert "ipPowerScore" in result

    def test_power_score_in_valid_range(self) -> None:
        """ipPowerScore 应在 0-100 范围内。"""
        engine = IPMatchEngine()
        for ip_name in _ALL_IP_NAMES:
            result = engine.evaluate_ip(ip_name)
            score = result["ipPowerScore"]
            assert 0 <= score <= 100, f"{ip_name} 势能分 {score} 超出 0-100 范围"

    def test_power_score_matches_database_value(self) -> None:
        """库洛米的 ipPowerScore 应与数据库中 powerScore 一致 (85)。"""
        engine = IPMatchEngine()
        result = engine.evaluate_ip(_KUROMI)
        assert result["ipPowerScore"] == 85

    def test_evaluate_ip_returns_ip_name(self) -> None:
        """evaluate_ip 应返回 ipName 字段, 值与输入一致。"""
        engine = IPMatchEngine()
        result = engine.evaluate_ip(_KUROMI)
        assert result["ipName"] == _KUROMI

    def test_evaluate_ip_returns_availability(self) -> None:
        """evaluate_ip 应返回 availability 字段。"""
        engine = IPMatchEngine()
        result = engine.evaluate_ip(_KUROMI)
        assert "availability" in result
        assert result["availability"] in (
            "available",
            "exclusive",
            "expiring",
            "unavailable",
        )

    def test_evaluate_ip_returns_exclusive_until(self) -> None:
        """evaluate_ip 应返回 exclusiveUntil 字段。"""
        engine = IPMatchEngine()
        result = engine.evaluate_ip(_KUROMI)
        assert "exclusiveUntil" in result

    def test_evaluate_ip_returns_recommended_categories(self) -> None:
        """evaluate_ip 应返回 recommendedCategories 字段 (非空列表)。"""
        engine = IPMatchEngine()
        result = engine.evaluate_ip(_KUROMI)
        assert "recommendedCategories" in result
        assert isinstance(result["recommendedCategories"], list)
        assert len(result["recommendedCategories"]) > 0


# ==============================================================================
# 2. 区域热度图 (regionHeatMap)
# ==============================================================================


class TestRegionHeatMap:
    """区域热度图测试 - regionHeatMap 含 china/us 键。"""

    def test_region_heat_map_contains_china(self) -> None:
        """regionHeatMap 应包含 china 键。"""
        engine = IPMatchEngine()
        result = engine.evaluate_ip(_KUROMI)
        heat_map = result["regionHeatMap"]
        assert "china" in heat_map

    def test_region_heat_map_contains_us(self) -> None:
        """regionHeatMap 应包含 us 键。"""
        engine = IPMatchEngine()
        result = engine.evaluate_ip(_KUROMI)
        heat_map = result["regionHeatMap"]
        assert "us" in heat_map

    def test_region_heat_map_values_are_int(self) -> None:
        """regionHeatMap 的值应为 int 类型。"""
        engine = IPMatchEngine()
        result = engine.evaluate_ip(_KUROMI)
        heat_map = result["regionHeatMap"]
        for region, value in heat_map.items():
            assert isinstance(value, int), f"{region} 热度值应为 int"

    def test_region_heat_map_values_in_valid_range(self) -> None:
        """regionHeatMap 的值应在 0-100 范围内。"""
        engine = IPMatchEngine()
        result = engine.evaluate_ip(_KUROMI)
        heat_map = result["regionHeatMap"]
        for region, value in heat_map.items():
            assert 0 <= value <= 100, f"{region} 热度 {value} 超出 0-100"

    def test_region_heat_map_has_multiple_regions(self) -> None:
        """regionHeatMap 应包含多个区域 (至少 china/sea/us/eu)。"""
        engine = IPMatchEngine()
        result = engine.evaluate_ip(_KUROMI)
        heat_map = result["regionHeatMap"]
        assert len(heat_map) >= 4

    def test_kuromi_china_heat_higher_than_us(self) -> None:
        """库洛米在中国热度应高于美国 (IP 区域偏好)。"""
        engine = IPMatchEngine()
        result = engine.evaluate_ip(_KUROMI)
        heat_map = result["regionHeatMap"]
        assert heat_map["china"] > heat_map["us"]


# ==============================================================================
# 3. 品类匹配 - 精确匹配 (match_category exact match)
# ==============================================================================


class TestMatchCategoryExact:
    """品类精确匹配测试 - 返回 categoryMatchScores 中的高分。"""

    def test_exact_match_returns_high_score(self) -> None:
        """精确匹配应返回 categoryMatchScores 中的高分 (如 0.95)。"""
        engine = IPMatchEngine()
        # 库洛米 categories 含 "美妆/个护", categoryMatchScores["美妆/个护"]=0.95
        score = engine.match_category(_KUROMI, "美妆/个护")
        assert score == 0.95

    def test_exact_match_returns_score_in_valid_range(self) -> None:
        """精确匹配分数应在 0-1 范围内。"""
        engine = IPMatchEngine()
        score = engine.match_category(_KUROMI, "美妆/个护")
        assert 0 <= score <= 1

    def test_exact_match_for_home_fragrance(self) -> None:
        """库洛米 '家居/香氛' 精确匹配应返回 0.85。"""
        engine = IPMatchEngine()
        score = engine.match_category(_KUROMI, "家居/香氛")
        assert score == 0.85

    def test_exact_match_for_apparel(self) -> None:
        """库洛米 '服饰/穿搭' 精确匹配应返回 0.90。"""
        engine = IPMatchEngine()
        score = engine.match_category(_KUROMI, "服饰/穿搭")
        assert score == 0.90

    def test_exact_match_returns_explicit_score_not_default(self) -> None:
        """精确匹配应返回 categoryMatchScores 中的显式分数, 而非默认 1.0。"""
        engine = IPMatchEngine()
        # 库洛米所有精确匹配分数都不是 1.0, 验证使用了显式分数
        for cat in ["美妆/个护", "家居/香氛", "服饰/穿搭"]:
            score = engine.match_category(_KUROMI, cat)
            assert score != 1.0, f"{cat} 应使用 categoryMatchScores 显式分数"


# ==============================================================================
# 4. 品类匹配 - 部分匹配 (match_category partial match)
# ==============================================================================


class TestMatchCategoryPartial:
    """品类部分匹配测试 - 同顶级品类返回 0.5。"""

    def test_partial_match_same_top_level(self) -> None:
        """'美妆/口红' 与 '美妆/个护' 同顶级 '美妆' → 部分匹配 0.5。"""
        engine = IPMatchEngine()
        score = engine.match_category(_KUROMI, "美妆/口红")
        assert score == 0.5

    def test_partial_match_different_subcategory(self) -> None:
        """'服饰/外套' 与 '服饰/穿搭' 同顶级 '服饰' → 部分匹配 0.5。"""
        engine = IPMatchEngine()
        score = engine.match_category(_KUROMI, "服饰/外套")
        assert score == 0.5

    def test_partial_match_home_category(self) -> None:
        """'家居/装饰' 与 '家居/香氛' 同顶级 '家居' → 部分匹配 0.5。"""
        engine = IPMatchEngine()
        score = engine.match_category(_KUROMI, "家居/装饰")
        assert score == 0.5

    def test_partial_match_score_in_valid_range(self) -> None:
        """部分匹配分数应在 0-1 范围内。"""
        engine = IPMatchEngine()
        score = engine.match_category(_KUROMI, "美妆/口红")
        assert 0 <= score <= 1


# ==============================================================================
# 5. 品类匹配 - 无匹配 (match_category no match)
# ==============================================================================


class TestMatchCategoryNoMatch:
    """品类无匹配测试 - 完全不相关品类返回 0.0。"""

    def test_no_match_unrelated_category(self) -> None:
        """'食品/零食' 与库洛米品类无交集 → 0.0。"""
        engine = IPMatchEngine()
        score = engine.match_category(_KUROMI, "食品/零食")
        assert score == 0.0

    def test_no_match_completely_different(self) -> None:
        """'汽车/配件' 与库洛米品类完全无关 → 0.0。"""
        engine = IPMatchEngine()
        score = engine.match_category(_KUROMI, "汽车/配件")
        assert score == 0.0

    def test_no_match_score_in_valid_range(self) -> None:
        """无匹配分数应为 0.0 (在 0-1 范围内)。"""
        engine = IPMatchEngine()
        score = engine.match_category(_KUROMI, "汽车/配件")
        assert 0 <= score <= 1

    def test_no_match_for_conan_with_beauty(self) -> None:
        """柯南品类不含美妆类 → '美妆/个护' 无匹配 0.0。"""
        engine = IPMatchEngine()
        score = engine.match_category(_CONAN, "美妆/个护")
        assert score == 0.0


# ==============================================================================
# 6. full_match 完整 IPMatch 对象
# ==============================================================================


class TestFullMatch:
    """full_match 测试 - 返回完整 IPMatch 对象 (7 字段全部填充)。"""

    def test_full_match_returns_ipmatch_instance(self) -> None:
        """full_match 应返回 IPMatch 实例。"""
        engine = IPMatchEngine()
        result = engine.full_match(_KUROMI, "美妆/个护")
        assert isinstance(result, IPMatch)

    def test_full_match_has_ip_name(self) -> None:
        """IPMatch.ipName 应正确填充。"""
        engine = IPMatchEngine()
        result = engine.full_match(_KUROMI, "美妆/个护")
        assert result.ipName == _KUROMI

    def test_full_match_has_ip_power_score(self) -> None:
        """IPMatch.ipPowerScore 应正确填充 (0-100)。"""
        engine = IPMatchEngine()
        result = engine.full_match(_KUROMI, "美妆/个护")
        assert 0 <= result.ipPowerScore <= 100
        assert result.ipPowerScore == 85

    def test_full_match_has_match_score(self) -> None:
        """IPMatch.matchScore 应正确填充 (0-1)。"""
        engine = IPMatchEngine()
        result = engine.full_match(_KUROMI, "美妆/个护")
        assert 0 <= result.matchScore <= 1
        assert result.matchScore == 0.95

    def test_full_match_has_availability(self) -> None:
        """IPMatch.availability 应正确填充。"""
        engine = IPMatchEngine()
        result = engine.full_match(_KUROMI, "美妆/个护")
        assert result.availability in (
            "available",
            "exclusive",
            "expiring",
            "unavailable",
        )

    def test_full_match_has_exclusive_until(self) -> None:
        """IPMatch.exclusiveUntil 字段应存在。"""
        engine = IPMatchEngine()
        result = engine.full_match(_KUROMI, "美妆/个护")
        # exclusiveUntil 可为 None 或 str
        assert hasattr(result, "exclusiveUntil")

    def test_full_match_has_region_heat_map(self) -> None:
        """IPMatch.regionHeatMap 应正确填充, 含 china/us。"""
        engine = IPMatchEngine()
        result = engine.full_match(_KUROMI, "美妆/个护")
        assert "china" in result.regionHeatMap
        assert "us" in result.regionHeatMap

    def test_full_match_has_recommended_categories(self) -> None:
        """IPMatch.recommendedCategories 应正确填充 (非空列表)。"""
        engine = IPMatchEngine()
        result = engine.full_match(_KUROMI, "美妆/个护")
        assert isinstance(result.recommendedCategories, list)
        assert len(result.recommendedCategories) > 0

    def test_full_match_all_seven_fields_populated(self) -> None:
        """full_match 应填充全部 7 个字段 (ipName/ipPowerScore/matchScore/
        availability/exclusiveUntil/regionHeatMap/recommendedCategories)。"""
        engine = IPMatchEngine()
        result = engine.full_match(_KUROMI, "美妆/个护")
        # 验证 7 个字段全部存在且有值
        assert result.ipName
        assert result.ipPowerScore is not None
        assert result.matchScore is not None
        assert result.availability is not None
        assert result.regionHeatMap  # 非空字典
        assert result.recommendedCategories  # 非空列表

    def test_full_match_with_partial_category(self) -> None:
        """full_match 部分匹配品类时 matchScore 应为 0.5。"""
        engine = IPMatchEngine()
        result = engine.full_match(_KUROMI, "美妆/口红")
        assert result.matchScore == 0.5

    def test_full_match_with_no_match_category(self) -> None:
        """full_match 无匹配品类时 matchScore 应为 0.0。"""
        engine = IPMatchEngine()
        result = engine.full_match(_KUROMI, "汽车/配件")
        assert result.matchScore == 0.0


# ==============================================================================
# 7. 授权到期检测 (license expiry detection)
# ==============================================================================


class TestLicenseExpiry:
    """授权到期检测测试 - licenseExpiry 在 6 个月内 → availability='expiring'。"""

    def test_expiring_when_license_within_6_months(self, tmp_path) -> None:
        """licenseExpiry 在 6 个月内 → availability 应为 'expiring'。"""
        # 构造距今 3 个月后的到期日
        near_expiry = (date.today() + timedelta(days=90)).isoformat()
        db_path = _build_temp_ip_db(
            tmp_path, name="测试到期IP", license_expiry=near_expiry
        )
        engine = IPMatchEngine(db_path=db_path)
        result = engine.evaluate_ip("测试到期IP")
        assert result["availability"] == "expiring"

    def test_not_expiring_when_license_far_future(self, tmp_path) -> None:
        """licenseExpiry 在 6 个月以外 → availability 应保持数据库原值。"""
        # 构造距今 2 年后的到期日
        far_expiry = (date.today() + timedelta(days=730)).isoformat()
        db_path = _build_temp_ip_db(
            tmp_path, name="测试远期IP", license_expiry=far_expiry
        )
        engine = IPMatchEngine(db_path=db_path)
        result = engine.evaluate_ip("测试远期IP")
        # 数据库原值为 "available", 远期到期不应改变
        assert result["availability"] == "available"

    def test_expiring_boundary_just_under_6_months(self, tmp_path) -> None:
        """licenseExpiry 距今 5 个月 (150 天) → 应为 'expiring'。"""
        near_expiry = (date.today() + timedelta(days=150)).isoformat()
        db_path = _build_temp_ip_db(
            tmp_path, name="边界到期IP", license_expiry=near_expiry
        )
        engine = IPMatchEngine(db_path=db_path)
        result = engine.evaluate_ip("边界到期IP")
        assert result["availability"] == "expiring"

    def test_not_expiring_boundary_just_over_6_months(self, tmp_path) -> None:
        """licenseExpiry 距今 7 个月 (210 天) → 不应为 'expiring'。"""
        far_expiry = (date.today() + timedelta(days=210)).isoformat()
        db_path = _build_temp_ip_db(
            tmp_path, name="边界远期IP", license_expiry=far_expiry
        )
        engine = IPMatchEngine(db_path=db_path)
        result = engine.evaluate_ip("边界远期IP")
        assert result["availability"] != "expiring"

    def test_main_db_ips_not_expiring(self) -> None:
        """主数据库中 4 个 IP 的 licenseExpiry 均远期, 不应触发 expiring。"""
        engine = IPMatchEngine()
        for ip_name in _ALL_IP_NAMES:
            result = engine.evaluate_ip(ip_name)
            # 主数据库 IP 均远期到期, availability 不应为 expiring
            assert result["availability"] != "expiring", (
                f"{ip_name} 不应触发 expiring (主数据库远期到期)"
            )


# ==============================================================================
# 8. IP 未找到 (IP not found)
# ==============================================================================


class TestIPNotFound:
    """IP 未找到测试 - 未知 IP 名称应抛出 ValueError。"""

    def test_evaluate_ip_not_found_raises_value_error(self) -> None:
        """evaluate_ip 对未知 IP 应抛出 ValueError。"""
        engine = IPMatchEngine()
        with pytest.raises(ValueError):
            engine.evaluate_ip("不存在的IP")

    def test_match_category_not_found_raises_value_error(self) -> None:
        """match_category 对未知 IP 应抛出 ValueError。"""
        engine = IPMatchEngine()
        with pytest.raises(ValueError):
            engine.match_category("不存在的IP", "美妆/个护")

    def test_full_match_not_found_raises_value_error(self) -> None:
        """full_match 对未知 IP 应抛出 ValueError。"""
        engine = IPMatchEngine()
        with pytest.raises(ValueError):
            engine.full_match("不存在的IP", "美妆/个护")

    def test_value_error_message_contains_ip_name(self) -> None:
        """ValueError 消息应包含未知 IP 名称 (便于调试)。"""
        engine = IPMatchEngine()
        unknown_ip = "神秘IP_xyz"
        with pytest.raises(ValueError, match=unknown_ip):
            engine.evaluate_ip(unknown_ip)


# ==============================================================================
# 9. list_ips 列出所有 IP
# ==============================================================================


class TestListIPs:
    """list_ips 测试 - 返回数据库中全部 IP 名称。"""

    def test_list_ips_returns_list(self) -> None:
        """list_ips 应返回列表。"""
        engine = IPMatchEngine()
        result = engine.list_ips()
        assert isinstance(result, list)

    def test_list_ips_returns_all_four_ips(self) -> None:
        """list_ips 应返回 4 个 IP 名称。"""
        engine = IPMatchEngine()
        result = engine.list_ips()
        assert len(result) == 4

    def test_list_ips_contains_kuromi(self) -> None:
        """list_ips 应包含库洛米。"""
        engine = IPMatchEngine()
        result = engine.list_ips()
        assert _KUROMI in result

    def test_list_ips_contains_all_expected_names(self) -> None:
        """list_ips 应包含全部 4 个已知 IP 名称。"""
        engine = IPMatchEngine()
        result = engine.list_ips()
        for name in _ALL_IP_NAMES:
            assert name in result, f"list_ips 缺少 {name}"

    def test_list_ips_no_duplicates(self) -> None:
        """list_ips 返回的 IP 名称不应有重复。"""
        engine = IPMatchEngine()
        result = engine.list_ips()
        assert len(result) == len(set(result)), "IP 名称存在重复"


# ==============================================================================
# 10. 边界场景 (Edge Cases)
# ==============================================================================


class TestEdgeCases:
    """边界场景测试 - 空品类 / 特殊字符 / 默认路径加载。"""

    def test_empty_category_returns_no_match(self) -> None:
        """空字符串品类应返回 0.0 (无匹配)。"""
        engine = IPMatchEngine()
        score = engine.match_category(_KUROMI, "")
        assert score == 0.0

    def test_whitespace_category_returns_no_match(self) -> None:
        """纯空白品类应返回 0.0 (无匹配)。"""
        engine = IPMatchEngine()
        score = engine.match_category(_KUROMI, "   ")
        assert score == 0.0

    def test_category_with_special_characters(self) -> None:
        """含特殊字符的品类 (无匹配时) 应返回 0.0。"""
        engine = IPMatchEngine()
        score = engine.match_category(_KUROMI, "!!!@#$%")
        assert score == 0.0

    def test_category_without_slash_no_match(self) -> None:
        """无斜杠品类 '完全无关' 应返回 0.0。"""
        engine = IPMatchEngine()
        score = engine.match_category(_KUROMI, "完全无关")
        assert score == 0.0

    def test_category_without_slash_partial_match(self) -> None:
        """无斜杠品类 '美妆' 与 '美妆/个护' 同顶级 → 部分匹配 0.5。"""
        engine = IPMatchEngine()
        score = engine.match_category(_KUROMI, "美妆")
        assert score == 0.5

    def test_default_db_path_loads_successfully(self) -> None:
        """不传 db_path 时应使用默认路径成功加载数据库。"""
        engine = IPMatchEngine()
        ips = engine.list_ips()
        assert len(ips) > 0

    def test_custom_db_path_loads_successfully(self, tmp_path) -> None:
        """传入自定义 db_path 应成功加载临时数据库。"""
        db_path = _build_temp_ip_db(tmp_path, name="自定义路径IP")
        engine = IPMatchEngine(db_path=db_path)
        ips = engine.list_ips()
        assert "自定义路径IP" in ips

    def test_full_match_with_conan_and_tech_category(self) -> None:
        """柯南 + 数码/配件 → 完整 IPMatch (跨 IP 验证)。"""
        engine = IPMatchEngine()
        result = engine.full_match(_CONAN, "数码/配件")
        assert isinstance(result, IPMatch)
        assert result.ipName == _CONAN
        assert result.matchScore > 0  # 柯南支持数码/配件

    def test_full_match_with_harry_potter_global(self) -> None:
        """哈利波特 (全球强势 IP) + 服饰/穿搭 → 完整 IPMatch。"""
        engine = IPMatchEngine()
        result = engine.full_match(_HARRY_POTTER, "服饰/穿搭")
        assert isinstance(result, IPMatch)
        assert result.ipName == _HARRY_POTTER
        assert result.matchScore > 0

    def test_lotso_categories_include_food(self) -> None:
        """草莓熊推荐品类应包含 '食品/零食'。"""
        engine = IPMatchEngine()
        result = engine.evaluate_ip(_LOTSO)
        assert "食品/零食" in result["recommendedCategories"]
