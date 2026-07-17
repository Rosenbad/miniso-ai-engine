# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 爆品预测特征提取器 (Task 10)
# ==============================================================================
# 对应 spec §4.5 爆品预测模型 · XGBoost 特征工程:
#   19 个特征分 5 类, 从原始产品数据字典提取为 19 维特征向量。
#
# 特征清单 (19 个):
#   市场特征 (5): category_heat / trend_growth_rate / seasonality_index /
#                 competitor_density / cross_region_diffusion_speed
#   产品特征 (3): price_percentile / material_cost_ratio / design_novelty
#   IP 特征  (4): ip_power_score / ip_category_match / ip_license_urgency /
#                 ip_region_heat_variance
#   受众特征 (4): z_gen_match / aesthetic_tag_heat / audience_spending_power /
#                 social_virality
#   情感特征 (3): trend_sentiment / social_mentions / positive_review_ratio
#
# FeatureExtractor 设计要点:
#   - FEATURE_NAMES: 19 个特征名 (snake_case), 顺序固定, 匹配 spec §4.5
#   - extract: 单条原始数据 → 19 维 float 向量
#   - extract_batch: 批量提取
#   - 缺失字段填充 0.0, 非数字字符串填充 0.0, None 填充 0.0
#   - 所有返回值强制 float 类型
# ==============================================================================

"""
爆品预测特征提取器 (spec §4.5)。

将原始产品数据字典 (含市场/产品/IP/受众/情感 5 类指标) 提取为
19 维特征向量, 供 XGBoost 爆品预测模型使用。

特征分 5 类 (共 19 个):
    1. 市场特征 (5) - 品类热度 / 趋势增长 / 季节性 / 竞品密度 / 跨区域扩散
    2. 产品特征 (3) - 价格分位 / 材质成本比 / 设计新颖度
    3. IP 特征  (4) - IP 势能 / 品类匹配 / 授权紧迫 / 区域热度方差
    4. 受众特征 (4) - Z世代匹配 / 审美热度 / 消费力 / 社交传播
    5. 情感特征 (3) - 趋势情感 / 社交提及 / 正面评价比

用法::

    extractor = FeatureExtractor()
    # 单条提取
    features = extractor.extract({"category_heat": 85.0, ...})  # → [float, ...]
    assert len(features) == 19
    # 批量提取
    batch = extractor.extract_batch([raw1, raw2])  # → [[float, ...], [float, ...]]
"""

from __future__ import annotations

from typing import Any, Dict, List

from trendpulse.collectors.utils import safe_float

# ==============================================================================
# 常量 - 19 个特征名 (匹配 spec §4.5, 顺序固定)
# ==============================================================================


class FeatureExtractor:
    """爆品预测特征提取器 (spec §4.5)。

    从原始产品数据字典提取 19 维特征向量, 分 5 类:
    市场 (5) + 产品 (3) + IP (4) + 受众 (4) + 情感 (3) = 19。

    特征顺序固定, 与 ``FEATURE_NAMES`` 一致, 确保模型输入一致性。

    设计要点:
        - 缺失字段填充 0.0 (非破坏性默认值)
        - None / 空字符串 / 非数字字符串均安全转换为 0.0
        - 所有返回值强制 float 类型 (XGBoost 要求数值输入)
    """

    FEATURE_NAMES: List[str] = [
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
    """19 个特征名 (snake_case), 顺序匹配 spec §4.5。

    顺序: 市场(5) → 产品(3) → IP(4) → 受众(4) → 情感(3)。
    """

    # ==================================================================
    # extract - 单条特征提取
    # ==================================================================

    def extract(self, raw_data: Dict[str, Any]) -> List[float]:
        """从原始产品数据字典提取 19 维特征向量。

        按 ``FEATURE_NAMES`` 顺序提取对应字段值, 缺失或无效值填充 0.0。
        所有值强制转换为 float 类型。

        参数:
            raw_data: 原始产品数据字典, 键为特征名 (snake_case),
                      值为数值或可转换为数值的类型。
                      允许缺失字段 (填充 0.0)。
                      允许 None / 空字符串 / 非数字字符串 (填充 0.0)。

        返回:
            长度 19 的 float 列表, 顺序与 ``FEATURE_NAMES`` 一致。

        用例::

            >>> extractor = FeatureExtractor()
            >>> features = extractor.extract({"category_heat": 85.0})
            >>> len(features)
            19
            >>> features[0]  # category_heat
            85.0
            >>> features[1]  # trend_growth_rate (缺失 → 0.0)
            0.0
        """
        if not raw_data:
            return [0.0] * len(self.FEATURE_NAMES)

        return [
            safe_float(raw_data.get(name, 0.0), default=0.0)
            for name in self.FEATURE_NAMES
        ]

    # ==================================================================
    # extract_batch - 批量特征提取
    # ==================================================================

    def extract_batch(self, raw_data_list: List[Dict[str, Any]]) -> List[List[float]]:
        """批量提取特征向量。

        对 ``raw_data_list`` 中每条原始数据调用 ``extract()``, 返回特征矩阵。

        参数:
            raw_data_list: 原始产品数据字典列表

        返回:
            特征向量列表 (list[list[float]]), 每个内层列表长度为 19。
            空输入返回空列表。

        用例::

            >>> extractor = FeatureExtractor()
            >>> batch = extractor.extract_batch([{"category_heat": 85.0}, {}])
            >>> len(batch)
            2
            >>> len(batch[0])
            19
        """
        return [self.extract(raw) for raw in raw_data_list]


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["FeatureExtractor"]
