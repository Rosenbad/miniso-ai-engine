# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - IP 联名匹配引擎 (Task 8)
# ==============================================================================
# 对应 spec §4.3 IP 联名匹配引擎:
#   IP 是独立决策模块 (非产品字段), 含 4 个子模块:
#     1. IP 势能评估   - 评估 IP 当前热度与商业价值 (ipPowerScore 0-100)
#     2. 品类匹配     - IP 风格 × 品类契合度 (matchScore 0-1)
#     3. 授权窗口     - 检查 IP 授权可用性与时效 (availability)
#     4. 区域偏好     - IP 在各国热度差异 (regionHeatMap)
#
# IPMatchEngine 设计要点:
#   - 独立模块: 从 backend/data/ip_database.json 加载 IP 档案
#   - evaluate_ip: 势能评分 + 可用性 + 到期检测 (6 个月内到期 → expiring)
#   - match_category: 三级评分 (精确=显式分 / 部分=0.5 / 无=0.0)
#   - full_match: 聚合 evaluate_ip + match_category → 返回完整 IPMatch 对象
#   - list_ips: 列出数据库中全部 IP 名称
# ==============================================================================

"""
IP 联名匹配引擎模块 (spec §4.3)。

IP 是名创优品「全球 IP 运营平台」定位的核心独立决策模块, 不作为产品字段,
而是独立的决策引擎, 含 4 个子模块:

    1. IP 势能评估   - socialMentions / searchHeat / merchandiseSales / topicGrowth
    2. 品类匹配     - IP 风格 × 品类调性矩阵 (精确/部分/无 三级评分)
    3. 授权窗口     - available / exclusive / expiring / unavailable
    4. 区域偏好     - 112 国 IP 热度排名 (regionHeatMap)

核心组件:
    IPMatchEngine - IP 势能评估 / 品类匹配 / 授权窗口 / 区域偏好

用法::

    engine = IPMatchEngine()
    # 评估 IP 势能
    result = engine.evaluate_ip("三丽鸥·库洛米")
    # 品类匹配
    score = engine.match_category("三丽鸥·库洛米", "美妆/个护")  # → 0.95
    # 完整匹配 (返回 IPMatch 对象)
    ip_match = engine.full_match("三丽鸥·库洛米", "美妆/个护")
"""

from __future__ import annotations

import calendar
import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.models import IPMatch

logger = logging.getLogger(__name__)


# ==============================================================================
# 常量
# ==============================================================================

# 默认 IP 数据库路径 (相对于本文件: backend/ideaforge/ → backend/data/)
DEFAULT_DB_PATH: Path = (
    Path(__file__).resolve().parent.parent / "data" / "ip_database.json"
)
"""默认 IP 数据库 JSON 路径, 使用 pathlib 相对于引擎文件解析。"""

# 授权到期检测阈值 (月)
_LICENSE_EXPIRY_THRESHOLD_MONTHS = 6
"""licenseExpiry 在当前日期 N 个月内时, 标记 availability 为 'expiring'。"""

# 品类匹配三级评分常量
_PARTIAL_MATCH_SCORE = 0.5
"""部分匹配分数 (同顶级品类, 不同子品类)。"""

_NO_MATCH_SCORE = 0.0
"""无匹配分数 (品类与 IP 无任何交集)。"""

_DEFAULT_EXACT_MATCH_SCORE = 1.0
"""精确匹配默认分数 (品类在 categories 中但无 categoryMatchScores 时)。"""


# ==============================================================================
# IPMatchEngine IP 联名匹配引擎
# ==============================================================================


class IPMatchEngine:
    """IP 联名匹配引擎 (spec §4.3)。

    独立决策模块, 整合 IP 势能评估、品类匹配、授权窗口与区域偏好 4 个子模块。

    数据来源: ``backend/data/ip_database.json`` (JSON 数组, 每个 IP 含
    powerScore / socialMentions / regionHeat / categories / categoryMatchScores /
    availability / licenseExpiry 等字段)。

    用法::

        engine = IPMatchEngine()
        # 1. IP 势能评估
        result = engine.evaluate_ip("三丽鸥·库洛米")
        # → {ipName, ipPowerScore, availability, exclusiveUntil,
        #    regionHeatMap, recommendedCategories}

        # 2. 品类匹配 (三级评分)
        score = engine.match_category("三丽鸥·库洛米", "美妆/个护")  # → 0.95
        score = engine.match_category("三丽鸥·库洛米", "美妆/口红")  # → 0.5
        score = engine.match_category("三丽鸥·库洛米", "汽车/配件")  # → 0.0

        # 3. 完整匹配 (返回 IPMatch 对象)
        ip_match = engine.full_match("三丽鸥·库洛米", "美妆/个护")
    """

    # ==================================================================
    # __init__ - 加载 IP 数据库
    # ==================================================================

    def __init__(self, db_path: Optional[str] = None) -> None:
        """初始化 IP 联名匹配引擎, 加载 IP 数据库。

        参数:
            db_path: IP 数据库 JSON 文件路径。
                     为 None 时使用默认路径 ``backend/data/ip_database.json``。
                     路径通过 pathlib 解析, 支持 str / Path 类型。

        异常:
            FileNotFoundError: 数据库文件不存在时抛出
            json.JSONDecodeError: JSON 格式无效时抛出
            KeyError: IP 条目缺少 ``name`` 字段时抛出
        """
        resolved_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        logger.debug(f"IPMatchEngine: 加载数据库 path={resolved_path}")

        with open(resolved_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        # 构建 {name: ip_entry} 字典, 实现 O(1) 查找
        self._ip_db: Dict[str, Dict[str, Any]] = {}
        for entry in raw_data:
            name = entry["name"]
            self._ip_db[name] = entry

        logger.info(f"IPMatchEngine: 已加载 {len(self._ip_db)} 个 IP")

    # ==================================================================
    # evaluate_ip - IP 势能评估 + 可用性 + 到期检测
    # ==================================================================

    def evaluate_ip(self, ip_name: str) -> Dict[str, Any]:
        """评估 IP 势能分、可用性与授权到期状态。

        对应 spec §4.3 子模块 1 (势能评估) + 子模块 3 (授权窗口) +
        子模块 4 (区域偏好)。

        评估内容:
            1. ipPowerScore       : 从数据库 powerScore 读取 (0-100)
            2. availability       : 从数据库读取, 并检查 licenseExpiry
                                    若 6 个月内到期 → 覆盖为 "expiring"
            3. exclusiveUntil     : 从数据库 exclusiveUntil 读取
            4. regionHeatMap      : 从数据库 regionHeat 读取
            5. recommendedCategories: 从数据库 categories 读取

        参数:
            ip_name: IP 名称, 如 "三丽鸥·库洛米"

        返回:
            ``{ipName, ipPowerScore, availability, exclusiveUntil,
               regionHeatMap, recommendedCategories}``

        异常:
            ValueError: IP 名称在数据库中不存在时抛出
        """
        ip_entry = self._lookup_ip(ip_name)

        # 势能分 (0-100)
        power_score = float(ip_entry.get("powerScore", 0))

        # 可用性 (检查授权到期)
        availability = self._check_availability(ip_entry)

        # 独家期截止日
        exclusive_until = ip_entry.get("exclusiveUntil")

        # 区域热度图
        region_heat_map = dict(ip_entry.get("regionHeat", {}))

        # 推荐品类
        recommended_categories = list(ip_entry.get("categories", []))

        logger.info(
            f"evaluate_ip: ip='{ip_name}', powerScore={power_score}, "
            f"availability={availability}"
        )

        return {
            "ipName": ip_name,
            "ipPowerScore": power_score,
            "availability": availability,
            "exclusiveUntil": exclusive_until,
            "regionHeatMap": region_heat_map,
            "recommendedCategories": recommended_categories,
        }

    # ==================================================================
    # match_category - 品类匹配 (三级评分)
    # ==================================================================

    def match_category(self, ip_name: str, category: str) -> float:
        """计算 IP 与品类的匹配度 (0-1), 三级评分机制。

        对应 spec §4.3 子模块 2 (品类匹配)。

        三级评分逻辑:
            1. 精确匹配: 品类在 IP 的 categories 列表中
               → 返回 categoryMatchScores 中的显式分数 (如 0.95)
               → 若无显式分数, 返回默认 1.0
            2. 部分匹配: 品类与 IP 某品类同顶级前缀 (如 "美妆/口红" vs "美妆/个护")
               → 返回 0.5
            3. 无匹配: 品类与 IP 所有品类无任何交集
               → 返回 0.0

        顶级前缀提取: 按 "/" 分割取第一段 (如 "美妆/个护" → "美妆")。
        无 "/" 的品类整体作为前缀。

        参数:
            ip_name : IP 名称, 如 "三丽鸥·库洛米"
            category: 品类名, 如 "美妆/个护" / "美妆/口红" / "汽车/配件"

        返回:
            匹配分数 0-1 (精确=显式分/1.0, 部分=0.5, 无=0.0)

        异常:
            ValueError: IP 名称在数据库中不存在时抛出
        """
        ip_entry = self._lookup_ip(ip_name)

        # 空品类/纯空白 → 无匹配
        if not category or not category.strip():
            return _NO_MATCH_SCORE
        category = category.strip()

        categories: List[str] = ip_entry.get("categories", [])
        match_scores: Dict[str, float] = ip_entry.get("categoryMatchScores", {})

        # 1. 精确匹配: 品类在 IP categories 列表中
        if category in categories:
            # 优先使用 categoryMatchScores 中的显式分数, 缺失时默认 1.0
            return float(match_scores.get(category, _DEFAULT_EXACT_MATCH_SCORE))

        # 2. 部分匹配: 同顶级品类前缀
        category_prefix = category.split("/")[0]
        for ip_cat in categories:
            ip_prefix = ip_cat.split("/")[0]
            if category_prefix == ip_prefix:
                return _PARTIAL_MATCH_SCORE

        # 3. 无匹配
        return _NO_MATCH_SCORE

    # ==================================================================
    # full_match - 完整 IP 匹配 (返回 IPMatch 对象)
    # ==================================================================

    def full_match(self, ip_name: str, category: str) -> IPMatch:
        """完整 IP 匹配 — 聚合势能评估与品类匹配, 返回 IPMatch 对象。

        整合 evaluate_ip() (势能+可用性+区域热度) 与 match_category() (品类匹配度),
        构造 spec §4.3 定义的 IPMatch 模型实例 (7 个字段全部填充)。

        参数:
            ip_name : IP 名称, 如 "三丽鸥·库洛米"
            category: 品类名, 如 "美妆/个护"

        返回:
            IPMatch 实例, 含 ipName / ipPowerScore / matchScore / availability /
            exclusiveUntil / regionHeatMap / recommendedCategories

        异常:
            ValueError: IP 名称在数据库中不存在时抛出
        """
        eval_result = self.evaluate_ip(ip_name)
        match_score = self.match_category(ip_name, category)

        ip_match = IPMatch(
            ipName=eval_result["ipName"],
            ipPowerScore=eval_result["ipPowerScore"],
            matchScore=match_score,
            availability=eval_result["availability"],  # type: ignore[arg-type]
            exclusiveUntil=eval_result["exclusiveUntil"],
            regionHeatMap=eval_result["regionHeatMap"],
            recommendedCategories=eval_result["recommendedCategories"],
        )

        logger.info(
            f"full_match: ip='{ip_name}', category='{category}', "
            f"matchScore={match_score}, availability={eval_result['availability']}"
        )

        return ip_match

    # ==================================================================
    # list_ips - 列出所有 IP 名称
    # ==================================================================

    def list_ips(self) -> List[str]:
        """列出数据库中全部 IP 名称。

        返回:
            IP 名称列表 (保持数据库顺序)
        """
        return list(self._ip_db.keys())

    # ==================================================================
    # 内部辅助方法
    # ==================================================================

    def _lookup_ip(self, ip_name: str) -> Dict[str, Any]:
        """在数据库中查找 IP, 不存在时抛出 ValueError。

        参数:
            ip_name: IP 名称

        返回:
            IP 数据库条目 (dict)

        异常:
            ValueError: IP 名称不存在时抛出, 消息含 ip_name 便于调试
        """
        if ip_name not in self._ip_db:
            raise ValueError(f"IP 未找到: '{ip_name}' 不在 IP 数据库中")
        return self._ip_db[ip_name]

    def _check_availability(self, ip_entry: Dict[str, Any]) -> str:
        """检查 IP 可用性, 包含授权到期检测。

        逻辑:
            1. 读取数据库 availability 字段作为基线
            2. 检查 licenseExpiry: 若在当前日期 6 个月内 → 覆盖为 "expiring"
               (无论数据库原值, 即将到期优先级最高)
            3. 返回最终 availability

        参数:
            ip_entry: IP 数据库条目

        返回:
            可用性状态: "available" | "exclusive" | "expiring" | "unavailable"
        """
        availability: str = ip_entry.get("availability", "available")
        license_expiry_str = ip_entry.get("licenseExpiry")

        # 授权到期检测: 6 个月内到期 → "expiring"
        if license_expiry_str and self._is_expiring(license_expiry_str):
            availability = "expiring"

        return availability

    @staticmethod
    def _is_expiring(license_expiry_str: str) -> bool:
        """判断 licenseExpiry 是否在当前日期 6 个月内 (即将到期)。

        判定: today <= expiry <= today + 6 months → True

        6 个月计算使用日历月精度 (非固定天数), 处理月末溢出
        (如 1月31日 + 6个月 = 7月31日, 2月末 + 6个月 = 8月末)。

        参数:
            license_expiry_str: 到期日 ISO 字符串, 如 "2027-06-30"

        返回:
            True 如果到期日在 6 个月内, False 否则
        """
        try:
            expiry = date.fromisoformat(license_expiry_str)
        except (ValueError, TypeError):
            # 日期解析失败, 不触发 expiring
            return False

        today = date.today()

        # 已过期的不算 "即将到期" (expiring 仅针对未来到期)
        if expiry < today:
            return False

        # 计算 6 个月后的日期
        six_months_later = IPMatchEngine._add_months(today, _LICENSE_EXPIRY_THRESHOLD_MONTHS)

        return expiry <= six_months_later

    @staticmethod
    def _add_months(d: date, months: int) -> date:
        """将日期增加指定月数, 处理年末溢出与月末天数。

        参数:
            d      : 基准日期
            months : 增加的月数 (正整数)

        返回:
            增加月数后的日期, 若目标月天数不足则取月末
            (如 1月31日 + 1个月 = 2月28/29日)
        """
        new_month = d.month + months
        new_year = d.year + (new_month - 1) // 12
        new_month = ((new_month - 1) % 12) + 1

        # 处理月末天数溢出 (如 31日在 2 月不存在)
        max_day = calendar.monthrange(new_year, new_month)[1]
        new_day = min(d.day, max_day)

        return date(new_year, new_month, new_day)


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["IPMatchEngine"]
