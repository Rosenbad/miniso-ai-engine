# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - MarketProbe 数据采集器 (Task 12)
# ==============================================================================
# 对应 spec §5 验证反馈层 · Step 2: DataCollector
#
# DataCollector 设计要点:
#   - 采集指标: 销量 / 转化率 / AOV / 退货率 / 评分 / 收藏率 / Z世代互动率
#   - 按日增量采集
#   - 存储: 按 test combination 分组 (demo 使用内存 dict)
#
# 存储结构:
#   {combination_id: [{day, sales, conversion, return_rate, z_gen_engagement, ...}, ...]}
# ==============================================================================

"""
数据采集器 (spec §5 Step 2)。

按 test combination 分组, 逐日采集销售指标。

采集指标:
    - sales             : 日销量
    - conversion        : 转化率 (0-1)
    - return_rate       : 退货率 (0-1)
    - z_gen_engagement  : Z世代互动率 (0-1)

存储结构 (内存 dict, demo 模式)::

    {
        "C001": [
            {"day": 1, "sales": 50, "conversion": 0.05, ...},
            {"day": 2, "sales": 55, "conversion": 0.06, ...},
            ...
        ],
        "C002": [...],
    }

用法::

    collector = DataCollector()
    collector.collect_daily("C001", 1, 50, 0.05, 0.02, 0.3)
    data = collector.get_data("C001")  # → [{day: 1, sales: 50, ...}]
"""

from __future__ import annotations

from typing import Any, Dict, List

from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# DataCollector 数据采集器
# ==============================================================================


class DataCollector:
    """数据采集器 (spec §5 Step 2)。

    按 test combination 分组, 逐日采集销售指标 (demo 内存存储)。

    采集指标:
        - sales             : 日销量
        - conversion        : 转化率 (0-1)
        - return_rate       : 退货率 (0-1)
        - z_gen_engagement  : Z世代互动率 (0-1)

    用法::

        collector = DataCollector()
        collector.collect_daily("C001", 1, 50, 0.05, 0.02, 0.3)
        data = collector.get_data("C001")
    """

    def __init__(self) -> None:
        """初始化数据采集器, 创建空内存存储。"""
        self._storage: Dict[str, List[Dict[str, Any]]] = {}

    # ==================================================================
    # collect_daily - 采集单日数据
    # ==================================================================

    def collect_daily(
        self,
        combination_id: str,
        day: int,
        sales: int,
        conversion: float,
        return_rate: float,
        z_gen_engagement: float,
    ) -> Dict[str, Any]:
        """存储某个测试组合的单日指标数据。

        参数:
            combination_id:   测试组合 ID (如 "C001")
            day:              天数 (1-based)
            sales:            日销量
            conversion:       转化率 (0-1)
            return_rate:      退货率 (0-1)
            z_gen_engagement: Z世代互动率 (0-1)

        返回:
            存储的记录字典 (含 day/sales/conversion/return_rate/z_gen_engagement)。
        """
        record: Dict[str, Any] = {
            "day": day,
            "sales": sales,
            "conversion": conversion,
            "return_rate": return_rate,
            "z_gen_engagement": z_gen_engagement,
        }

        self._storage.setdefault(combination_id, []).append(record)

        logger.debug(
            f"DataCollector.collect_daily: {combination_id} day={day} "
            f"sales={sales} conversion={conversion:.4f}"
        )

        return record

    # ==================================================================
    # get_data - 获取单组合全部数据
    # ==================================================================

    def get_data(self, combination_id: str) -> List[Dict[str, Any]]:
        """获取指定测试组合的全部日数据。

        参数:
            combination_id: 测试组合 ID

        返回:
            日数据列表 (按采集顺序), 未知组合返回空列表。
        """
        return list(self._storage.get(combination_id, []))

    # ==================================================================
    # get_all_data - 获取全部数据
    # ==================================================================

    def get_all_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取全部存储数据 (按组合分组)。

        返回:
            {combination_id: [daily_records]} 的字典 (浅拷贝)。
        """
        return {k: list(v) for k, v in self._storage.items()}

    # ==================================================================
    # clear - 清空存储
    # ==================================================================

    def clear(self) -> None:
        """清空所有存储数据。"""
        self._storage.clear()
        logger.info("DataCollector: 存储已清空")


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["DataCollector"]
