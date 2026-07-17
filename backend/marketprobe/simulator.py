# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - MarketProbe 销售模拟器 (Task 12)
# ==============================================================================
# 对应 spec §5 验证反馈层 · SalesSimulator (验证模拟)
#
# SalesSimulator 设计要点:
#   - 模拟 7-14 天销售数据 (加速模拟)
#   - 增长趋势 + 随机噪声 (种子可复现)
#   - 为每个测试组合生成日数据
#   - 展示 hitScore 预测 vs 实际结果
#
# 模拟模型:
#   base_sales[price] × packaging_boost × region_factor × channel_factor
#   × (1 + growth_rate × day/days) × (1 + noise)
#   - 高价 → 低销量, 低价 → 高销量
#   - IP 联名包装 → 销量提升
#   - 不同区域 → 不同表现
# ==============================================================================

"""
销售模拟器 (spec §5 SalesSimulator)。

模拟 7-14 天加速销售数据, 为每个测试组合生成日数据。

模拟模型:
    daily_sales = base_sales[price]
                  × packaging_boost[packaging]
                  × region_factor[region]
                  × channel_factor[channel]
                  × (1 + growth_rate × day / days)   # 增长趋势
                  × (1 + noise)                       # 随机噪声

模型假设:
    - 高价 → 低销量, 低价 → 高销量
    - IP 联名包装 → 销量 + 转化率提升
    - 不同区域 → 不同表现 (中国 > 欧美 > 东南亚)
    - 线上渠道 → 略高于门店

用法::

    simulator = SalesSimulator()
    result = simulator.simulate(test_plan, days=7, seed=42)
    # result = {days, daily_data, summary}
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# 常量 - 模拟模型参数
# ==============================================================================

# 基础日销量 (按价格水平)
_BASE_SALES: Dict[str, float] = {
    "high": 30.0,
    "medium": 50.0,
    "low": 80.0,
}
"""基础日销量: 高价低量, 低价高量。"""

# 包装加成系数
_PACKAGING_BOOST: Dict[str, float] = {
    "ip_collab": 1.35,
    "minimalist": 1.0,
}
"""IP 联名包装销量加成 1.35x。"""

# 区域系数
_REGION_FACTOR: Dict[str, float] = {
    "china": 1.20,
    "us": 1.00,
    "sea": 0.85,
}
"""区域系数: 中国 > 欧美 > 东南亚。"""

# 渠道系数
_CHANNEL_FACTOR: Dict[str, float] = {
    "online": 1.10,
    "store": 0.90,
}
"""渠道系数: 线上略高于门店。"""

# 基础转化率 (按价格水平)
_BASE_CONVERSION: Dict[str, float] = {
    "high": 0.03,
    "medium": 0.05,
    "low": 0.08,
}
"""基础转化率: 低价高转化, 高价低转化。"""

# 转化率包装加成
_CONVERSION_PACKAGING_BOOST: Dict[str, float] = {
    "ip_collab": 1.20,
    "minimalist": 1.0,
}
"""IP 联名包装转化率加成 1.20x。"""

# 基础退货率 (按价格水平)
_BASE_RETURN_RATE: Dict[str, float] = {
    "high": 0.02,
    "medium": 0.03,
    "low": 0.05,
}
"""基础退货率: 低价高退货 (冲动消费)。"""

# 基础 Z 世代互动率 (按包装)
_BASE_Z_GEN_ENGAGEMENT: Dict[str, float] = {
    "ip_collab": 0.40,
    "minimalist": 0.20,
}
"""IP 联名包装 Z 世代互动率 0.40, 极简 0.20。"""

# Z 世代区域系数
_Z_GEN_REGION_FACTOR: Dict[str, float] = {
    "china": 1.15,
    "us": 0.90,
    "sea": 0.75,
}
"""Z 世代互动区域系数: 中国最高。"""

# 增长率 (每日)
_GROWTH_RATE: float = 0.03
"""每日增长率 3% (增长趋势)。"""

# 噪声幅度
_NOISE_AMPLITUDE: float = 0.15
"""随机噪声幅度 ±15%。"""


# ==============================================================================
# SalesSimulator 销售模拟器
# ==============================================================================


class SalesSimulator:
    """销售模拟器 (spec §5 SalesSimulator)。

    模拟 7-14 天加速销售数据, 为每个测试组合生成日数据。

    模拟模型:
        - 基础销量受价格水平影响 (高价低量, 低价高量)
        - IP 联名包装提升销量 + 转化率
        - 不同区域不同表现
        - 增长趋势 (每日 +3%)
        - 随机噪声 (±15%, 种子可复现)

    用法::

        simulator = SalesSimulator()
        result = simulator.simulate(test_plan, days=7, seed=42)
    """

    # ==================================================================
    # simulate - 模拟销售数据
    # ==================================================================

    def simulate(
        self,
        test_plan: Dict[str, Any],
        days: int = 7,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """为测试计划中的所有组合模拟日销售数据。

        参数:
            test_plan: TestDesigner.design_test_plan() 的输出
            days:      模拟天数 (默认 7)
            seed:      随机种子 (确保可复现, 默认 42)

        返回:
            模拟结果字典::

                {
                    "days": int,
                    "daily_data": {
                        "C001": [
                            {"day": 1, "sales": 50, "conversion": 0.05,
                             "return_rate": 0.02, "z_gen_engagement": 0.3},
                            ...
                        ],
                        ...
                    },
                    "summary": {
                        "C001": {
                            "total_sales": 400,
                            "avg_conversion": 0.055,
                            "avg_return_rate": 0.025,
                            "avg_z_gen_engagement": 0.32
                        },
                        ...
                    }
                }
        """
        # 约束天数到 7-14
        sim_days = max(7, min(14, days))
        rng = np.random.RandomState(seed)

        combinations: List[Dict[str, Any]] = test_plan.get("combinations", [])
        daily_data: Dict[str, List[Dict[str, Any]]] = {}
        summary: Dict[str, Dict[str, Any]] = {}

        for combo in combinations:
            combo_id = combo["id"]
            price = combo["price"]
            packaging = combo["packaging"]
            channel = combo["channel"]
            region = combo["region"]

            # 计算基础参数
            base_sales = _BASE_SALES.get(price, 50.0)
            packaging_boost = _PACKAGING_BOOST.get(packaging, 1.0)
            region_factor = _REGION_FACTOR.get(region, 1.0)
            channel_factor = _CHANNEL_FACTOR.get(channel, 1.0)

            base_conversion = _BASE_CONVERSION.get(price, 0.05)
            conv_packaging_boost = _CONVERSION_PACKAGING_BOOST.get(packaging, 1.0)

            base_return = _BASE_RETURN_RATE.get(price, 0.03)
            base_z_gen = _BASE_Z_GEN_ENGAGEMENT.get(packaging, 0.25)
            z_gen_region = _Z_GEN_REGION_FACTOR.get(region, 1.0)

            # 基础日销量 (不含增长和噪声)
            base_daily = (
                base_sales * packaging_boost * region_factor * channel_factor
            )

            # 基础转化率
            base_conv = base_conversion * conv_packaging_boost

            # 基础 Z 世代互动率
            base_z_gen_value = base_z_gen * z_gen_region

            daily_records: List[Dict[str, Any]] = []
            total_sales = 0
            total_conversion = 0.0
            total_return = 0.0
            total_z_gen = 0.0

            for day in range(1, sim_days + 1):
                # 增长趋势: 每日 +growth_rate
                growth = 1.0 + _GROWTH_RATE * (day - 1) / max(sim_days - 1, 1)

                # 随机噪声 (±noise_amplitude)
                noise = 1.0 + rng.uniform(
                    -_NOISE_AMPLITUDE, _NOISE_AMPLITUDE
                )

                # 日销量 = base × growth × noise (取整)
                sales = max(0, int(round(base_daily * growth * noise)))

                # 转化率 (含小噪声, 裁剪到 [0, 1])
                conv_noise = 1.0 + rng.uniform(-0.10, 0.10)
                conversion = max(
                    0.0, min(1.0, base_conv * growth * conv_noise)
                )

                # 退货率 (含小噪声, 裁剪到 [0, 1])
                return_noise = 1.0 + rng.uniform(-0.20, 0.20)
                return_rate = max(
                    0.0, min(1.0, base_return * return_noise)
                )

                # Z 世代互动率 (含小噪声, 裁剪到 [0, 1])
                z_gen_noise = 1.0 + rng.uniform(-0.15, 0.15)
                z_gen_engagement = max(
                    0.0, min(1.0, base_z_gen_value * z_gen_noise)
                )

                record: Dict[str, Any] = {
                    "day": day,
                    "sales": sales,
                    "conversion": round(conversion, 6),
                    "return_rate": round(return_rate, 6),
                    "z_gen_engagement": round(z_gen_engagement, 6),
                }
                daily_records.append(record)

                total_sales += sales
                total_conversion += conversion
                total_return += return_rate
                total_z_gen += z_gen_engagement

            daily_data[combo_id] = daily_records

            # 计算汇总
            n = sim_days
            summary[combo_id] = {
                "total_sales": total_sales,
                "avg_conversion": round(total_conversion / n, 6),
                "avg_return_rate": round(total_return / n, 6),
                "avg_z_gen_engagement": round(total_z_gen / n, 6),
            }

        result: Dict[str, Any] = {
            "days": sim_days,
            "daily_data": daily_data,
            "summary": summary,
        }

        logger.info(
            f"SalesSimulator: 模拟 {sim_days} 天, "
            f"{len(combinations)} 组合, seed={seed}"
        )

        return result


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["SalesSimulator"]
