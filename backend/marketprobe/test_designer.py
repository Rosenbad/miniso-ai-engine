# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - MarketProbe 测试方案设计器 (Task 12)
# ==============================================================================
# 对应 spec §5 验证反馈层 · Step 1: TestDesigner
#
# TestDesigner 设计要点:
#   - 为高潜力创意 (hitScore > 0.7) 生成小批量测试方案
#   - A/B 维度: price(高/中/低) × packaging(极简/IP联名) × channel(线上/门店) × region(中国/东南亚/欧美)
#   - 规模: 每组合 50-100 件, 测试周期 7-14 天
#   - 输出: TestPlan (组合矩阵 + KPI 基线)
#
# 组合生成策略:
#   全量 3×2×2×3 = 36 组合过多, 采用代表性子集 (8 组合),
#   覆盖所有因子的所有水平, 确保因子贡献可分析。
# ==============================================================================

"""
测试方案设计器 (spec §5 Step 1)。

为高潜力产品创意生成 A/B 测试组合矩阵。

A/B 维度:
    - price     : high / medium / low
    - packaging : minimalist / ip_collab
    - channel   : online / store
    - region    : china / sea / us

组合生成策略:
    全量 36 组合过多, 采用代表性子集 (8 组合),
    覆盖所有因子的所有水平。

用法::

    designer = TestDesigner()
    plan = designer.design_test_plan("原木杯香薰蜡烛", "家居/香氛", days=7)
    # plan = {product_name, category, combinations, test_days, kpi_baseline}
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# 常量 - A/B 测试维度
# ==============================================================================

_PRICES: List[str] = ["high", "medium", "low"]
"""价格水平: high(高) / medium(中) / low(低)。"""

_PACKAGING: List[str] = ["minimalist", "ip_collab"]
"""包装水平: minimalist(极简) / ip_collab(IP联名)。"""

_CHANNELS: List[str] = ["online", "store"]
"""渠道: online(线上) / store(门店)。"""

_REGIONS: List[str] = ["china", "sea", "us"]
"""区域: china(中国) / sea(东南亚) / us(欧美)。"""

# 代表性子集: 8 组合, 覆盖所有因子的所有水平
_REPRESENTATIVE_COMBOS: List[tuple] = [
    # --- china (3 组合: 覆盖 3 价格 × 2 包装 × 2 渠道) ---
    ("low", "ip_collab", "online", "china"),
    ("low", "minimalist", "store", "china"),
    ("medium", "ip_collab", "online", "china"),
    # --- sea (3 组合: 覆盖中高价格) ---
    ("medium", "minimalist", "store", "sea"),
    ("high", "ip_collab", "online", "sea"),
    # --- us (2 组合: 覆盖高价 + 低价门店) ---
    ("high", "minimalist", "store", "us"),
    ("high", "ip_collab", "online", "us"),
    ("low", "ip_collab", "store", "us"),
]
"""代表性组合子集 (8 组合), 覆盖 price×packaging×channel×region 全水平。"""


# ==============================================================================
# TestDesigner 测试方案设计器
# ==============================================================================


class TestDesigner:
    """测试方案设计器 (spec §5 Step 1)。

    为高潜力产品创意生成 A/B 测试组合矩阵。

    A/B 维度:
        - price(高/中/低) × packaging(极简/IP联名) × channel(线上/门店) × region(中国/东南亚/欧美)

    组合生成策略:
        采用代表性子集 (8 组合), 覆盖所有因子的所有水平,
        确保因子贡献可分析 (非全量 36 组合)。

    用法::

        designer = TestDesigner()
        plan = designer.design_test_plan("原木杯香薰蜡烛", "家居/香氛", days=7)
    """

    PRICES: List[str] = _PRICES
    PACKAGING: List[str] = _PACKAGING
    CHANNELS: List[str] = _CHANNELS
    REGIONS: List[str] = _REGIONS

    # ==================================================================
    # design_test_plan - 生成 A/B 测试方案
    # ==================================================================

    def design_test_plan(
        self,
        product_name: str,
        category: str,
        ip_name: Optional[str] = None,
        days: int = 7,
    ) -> Dict[str, Any]:
        """为产品生成 A/B 测试组合矩阵。

        生成代表性子集 (8 组合), 每组合 50-100 件样本,
        测试周期 7-14 天, 含 KPI 基线。

        参数:
            product_name: 产品名称
            category:     品类 (如 "家居/香氛")
            ip_name:      IP 名称 (可选, 用于 IP 联名组合)
            days:         测试天数 (7-14, 默认 7)

        返回:
            测试计划字典::

                {
                    "product_name": str,
                    "category": str,
                    "ip_name": str | None,
                    "combinations": [
                        {
                            "id": "C001",
                            "price": "low",
                            "packaging": "ip_collab",
                            "channel": "online",
                            "region": "china",
                            "sample_size": 80
                        },
                        ...
                    ],
                    "test_days": int,
                    "kpi_baseline": {
                        "expected_sales": int,
                        "expected_conversion": float,
                        "expected_return_rate": float,
                        "expected_z_gen_engagement": float
                    }
                }
        """
        # 约束测试天数到 7-14 范围
        test_days = max(7, min(14, days))

        # 使用固定随机种子确保组合样本量可复现
        rng = random.Random(42)

        # 生成代表性组合子集
        combinations: List[Dict[str, Any]] = []
        for idx, (price, packaging, channel, region) in enumerate(
            _REPRESENTATIVE_COMBOS, start=1
        ):
            combo_id = f"C{idx:03d}"
            # 样本量 50-100, 随机但可复现
            sample_size = rng.randint(50, 100)
            combinations.append(
                {
                    "id": combo_id,
                    "price": price,
                    "packaging": packaging,
                    "channel": channel,
                    "region": region,
                    "sample_size": sample_size,
                }
            )

        # 生成 KPI 基线 (预期指标, 用于后续对比)
        kpi_baseline: Dict[str, Any] = {
            "expected_sales": 50 * test_days,
            "expected_conversion": 0.05,
            "expected_return_rate": 0.03,
            "expected_z_gen_engagement": 0.25,
            "expected_aov": 59.0,
        }

        plan: Dict[str, Any] = {
            "product_name": product_name,
            "category": category,
            "ip_name": ip_name,
            "combinations": combinations,
            "test_days": test_days,
            "kpi_baseline": kpi_baseline,
        }

        logger.info(
            f"TestDesigner: 为 '{product_name}' 生成 {len(combinations)} 组合, "
            f"测试周期 {test_days} 天"
        )

        return plan


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["TestDesigner"]
