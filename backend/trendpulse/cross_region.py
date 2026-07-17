# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 跨区域趋势对比引擎 (Task 7)
# ==============================================================================
# 对应 spec §3.3 跨区域趋势对比引擎:
#   1. 趋势扩散检测 - 比较同一趋势在不同区域的 lifecycle 阶段
#      (TikTok US 已 peak, 小红书 CN 刚 rising → 中国有跟进窗口)
#   2. 区域热度差 - 比较各国热度分, 输出趋势扩散路径图
#   3. 本地化适配 - 海外趋势进入中国的价格/材质/文化适配建议
#
# CrossRegionComparator 设计要点:
#   - 输入: 同一 topic 来自不同区域的 TrendSignal 列表
#   - lifecycle 扩散排序: declining(0) < peak(1) < rising(2)
#     趋势发源于某区域 (rising→peak→declining), 其他区域滞后跟进
#     故 declining 最前端 (origin), rising 最后端 (follower)
#   - 跟进窗口: 当某区域处于 peak/declining, 另一区域处于 rising 时,
#     rising 区域存在跟进窗口 (趋势尚未达峰, 仍可捕捉)
#   - 本地化建议: 海外 (us/eu) 领先中国 (china 落后) 时, 给出适配建议
# ==============================================================================

"""
跨区域趋势对比引擎模块。

核心组件:
    CrossRegionComparator - 趋势扩散检测 / 跟进窗口 / 区域热度图 / 本地化建议

设计思路 (spec §3.3):
    趋势在起源区域经历 rising → peak → declining 生命周期, 随后扩散至其他区域。
    通过比较同一趋势在不同区域的 lifecycle 阶段, 可识别扩散方向与跟进机会:
        - declining 区域: 趋势最早发源, 现已衰退 (origin)
        - peak 区域: 趋势正处于峰值
        - rising 区域: 趋势刚到达, 处于跟进窗口 (follower)

用法::

    comparator = CrossRegionComparator()
    result = comparator.compare(signals)
    # result: {topic, region_count, diffusion_path, follow_up_windows,
    #          heat_map, localization_suggestions, ...}
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from shared.models import TrendSignal
from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# 常量: lifecycle 扩散排序与角色映射
# ==============================================================================

# lifecycle → 扩散序号 (越小越靠前 = 趋势越早到达该区域)
# declining: 趋势已衰退 = 最早到达 (origin)
# peak: 趋势正峰值 = 中间
# rising: 趋势刚起步 = 最晚到达 (follower)
LIFECYCLE_DIFFUSION_ORDER: Dict[str, int] = {
    "declining": 0,
    "peak": 1,
    "rising": 2,
}
"""lifecycle 阶段扩散序号。

排序含义: 趋势从 origin 区域扩散到 follower 区域。
- declining(0): 趋势在该区域最早出现, 现已衰退 → origin (最前端)
- peak(1): 趋势在该区域正处于峰值 → 中间
- rising(2): 趋势在该区域刚起步 → follower (最后端, 跟进窗口)

扩散路径按此序号升序排列: origin → peak → follower。
"""

# lifecycle → 角色语义 (用于扩散路径节点标注)
LIFECYCLE_ROLE: Dict[str, str] = {
    "declining": "origin",
    "peak": "peak",
    "rising": "follower",
}
"""lifecycle → 角色映射。

- declining → origin: 趋势发源区域 (现已衰退)
- peak → peak: 趋势峰值区域
- rising → follower: 趋势跟进区域 (跟进窗口)
"""

# 海外区域集合 (用于本地化建议判定)
_OVERSEAS_REGIONS = {"us", "eu"}

# 本地化目标区域
_TARGET_REGION = "china"


# ==============================================================================
# 品类本地化适配档案 (spec §3.3 本地化适配)
# ==============================================================================

# 品类 → {priceRange, material, culturalAdaptation}
# 价格区间为「中等消费力」基线, 后续按 spendingPower 调整
_LOCALIZATION_PROFILES: Dict[str, Dict[str, str]] = {
    "家居/装饰": {
        "priceRange": "39-129",
        "material": "陶瓷/原木/棉麻",
        "culturalAdaptation": "融入新中式留白美学与东方意境, "
        "材质偏好天然质感 (原木/陶瓷/棉麻), 适配国内中小户型家居场景",
    },
    "家居/香氛": {
        "priceRange": "39-99",
        "material": "大豆蜡/陶瓷/玻璃",
        "culturalAdaptation": "结合东方香韵 (茶香/木质/草本), "
        "适配国人对淡香与疗愈场景的偏好, 包装融入国风元素",
    },
    "美妆/个护": {
        "priceRange": "29-99",
        "material": "植物提取/温和配方",
        "culturalAdaptation": "适配中国肤质与审美偏好, "
        "强调成分透明与功效验证, 包装融入国风或极简设计",
    },
    "服饰/穿搭": {
        "priceRange": "59-199",
        "material": "棉/麻/混纺",
        "culturalAdaptation": "结合亚洲版型与国潮元素, "
        "适配国内季节与多场景穿搭需求, 融入本土 IP 联名",
    },
    "数码/配件": {
        "priceRange": "59-299",
        "material": "ABS/硅胶/金属",
        "culturalAdaptation": "适配国内使用习惯与审美, "
        "融入本土 IP 联名与社交分享功能, 兼顾性价比",
    },
    "食品/零食": {
        "priceRange": "19-59",
        "material": "原装进口/本土化配方",
        "culturalAdaptation": "适配中国口味偏好 (茶/果/轻甜), "
        "符合国内食品合规要求, 包装融入节庆与社交属性",
    },
}

# 默认本地化档案 (品类未匹配时)
_DEFAULT_PROFILE: Dict[str, str] = {
    "priceRange": "39-129",
    "material": "通用材质",
    "culturalAdaptation": "结合中国消费者审美与使用习惯进行本地化适配, "
    "兼顾性价比与社交分享属性",
}

# spendingPower → 价格区间倍率 (作用于上限)
# 高消费力上调, 低消费力下调, 中等不变
_SPENDING_POWER_MULTIPLIER: Dict[str, float] = {
    "高": 1.4,
    "中": 1.0,
    "低": 0.7,
}


# ==============================================================================
# CrossRegionComparator 跨区域趋势对比引擎
# ==============================================================================


class CrossRegionComparator:
    """跨区域趋势对比引擎 (spec §3.3)。

    比较同一趋势在不同区域的 lifecycle 阶段, 识别:
        1. 趋势扩散路径 (origin → peak → follower)
        2. 跟进窗口 (rising 区域可捕捉的跟进机会)
        3. 区域热度图 ({region: heatScore})
        4. 本地化适配建议 (海外趋势进入中国)

    用法::

        comparator = CrossRegionComparator()
        result = comparator.compare(signals)
        # result["follow_up_windows"]: [{from_region, to_region, ...}]
    """

    # 扩散序号 (类常量, 便于外部引用)
    LIFECYCLE_DIFFUSION_ORDER: Dict[str, int] = LIFECYCLE_DIFFUSION_ORDER

    # ==================================================================
    # compare() - 主入口 (聚合全部跨区域分析)
    # ==================================================================

    def compare(self, signals: List[TrendSignal]) -> Dict[str, Any]:
        """跨区域对比主入口 — 聚合扩散路径/跟进窗口/热度图/本地化建议。

        参数:
            signals: 同一 topic 来自不同区域的 TrendSignal 列表
                     (允许空列表, 返回安全默认值)

        返回:
            ``{topic, region_count, regions, diffusion_path,
               follow_up_windows, heat_map, localization_suggestions,
               leading_region, max_heat_region}``
            - topic                  : 趋势话题 (空输入时为 None)
            - region_count           : 参与对比的区域数
            - regions                : 区域代码列表
            - diffusion_path         : 扩散路径 (按 lifecycle 排序)
            - follow_up_windows      : 跟进窗口列表
            - heat_map               : {region: heatScore}
            - localization_suggestions: 本地化建议
            - leading_region         : 扩散最前端区域 (origin)
            - max_heat_region        : 热度最高区域
        """
        diffusion_path = self.detect_diffusion_path(signals)
        follow_up_windows = self.detect_follow_up_windows(signals)
        heat_map = self.generate_heat_map(signals)
        localization = self.generate_localization_suggestions(signals)

        regions = [s.region for s in signals]
        topic: Optional[str] = signals[0].topic if signals else None

        # leading_region: 扩散路径首个节点 (lifecycle 最前端)
        leading_region = diffusion_path[0]["region"] if diffusion_path else None

        # max_heat_region: 热度最高区域
        max_heat_region: Optional[str] = None
        if heat_map:
            max_heat_region = max(heat_map, key=lambda r: heat_map[r])

        logger.info(
            f"CrossRegionComparator: topic='{topic}', 区域数={len(regions)}, "
            f"跟进窗口={len(follow_up_windows)}, 本地化适用={localization['applicable']}"
        )

        return {
            "topic": topic,
            "region_count": len(signals),
            "regions": regions,
            "diffusion_path": diffusion_path,
            "follow_up_windows": follow_up_windows,
            "heat_map": heat_map,
            "localization_suggestions": localization,
            "leading_region": leading_region,
            "max_heat_region": max_heat_region,
        }

    # ==================================================================
    # detect_diffusion_path - 扩散路径检测
    # ==================================================================

    def detect_diffusion_path(self, signals: List[TrendSignal]) -> List[Dict[str, Any]]:
        """检测趋势扩散路径 — 按 lifecycle 阶段排序输出。

        排序规则:
            1. 主排序: lifecycle 扩散序号升序 (declining=0 → peak=1 → rising=2)
               origin (趋势最早到达, 现已衰退) 排最前, follower 排最后
            2. 次排序: 同 lifecycle 时按 heatScore 降序 (热度高优先)

        每个节点结构:
            ``{region, lifecycle, heatScore, role}``
            - role: origin (declining) / peak (peak) / follower (rising)

        参数:
            signals: TrendSignal 列表

        返回:
            扩散路径节点列表 (空输入返回空列表)
        """
        if not signals:
            return []

        # 按 (扩散序号升序, heatScore 降序) 排序
        sorted_signals = sorted(
            signals,
            key=lambda s: (
                LIFECYCLE_DIFFUSION_ORDER.get(s.lifecycle, 99),
                -s.heatScore,
            ),
        )

        path: List[Dict[str, Any]] = []
        for s in sorted_signals:
            path.append(
                {
                    "region": s.region,
                    "lifecycle": s.lifecycle,
                    "heatScore": s.heatScore,
                    "role": LIFECYCLE_ROLE.get(s.lifecycle, "unknown"),
                }
            )
        return path

    # ==================================================================
    # detect_follow_up_windows - 跟进窗口识别
    # ==================================================================

    def detect_follow_up_windows(self, signals: List[TrendSignal]) -> List[Dict[str, Any]]:
        """识别跟进窗口 — rising 区域可捕捉的跟进机会。

        判定逻辑:
            对每个处于 ``rising`` 的区域 (follower), 寻找处于 ``peak`` 或
            ``declining`` 的区域 (趋势已成熟), 形成 (ahead → rising) 跟进窗口。
            该 rising 区域存在跟进窗口 (趋势尚未达峰, 仍可捕捉)。

        窗口结构:
            ``{from_region, to_region, from_lifecycle, to_lifecycle, window}``
            - from_region    : 趋势已成熟区域 (peak/declining)
            - to_region      : 跟进区域 (rising), 拥有跟进窗口
            - from_lifecycle : from_region 的 lifecycle
            - to_lifecycle   : "rising"
            - window         : to_region 的 predictWindow (窗口时长)

        参数:
            signals: TrendSignal 列表

        返回:
            跟进窗口列表 (无跟进机会时返回空列表)
        """
        if not signals:
            return []

        # 按区域分组, 同区域取最后一条信号 (与热度图一致)
        region_signal: Dict[str, TrendSignal] = {}
        for s in signals:
            region_signal[s.region] = s

        # ahead 区域: lifecycle 为 peak 或 declining (趋势已成熟)
        ahead_regions = [
            (r, s)
            for r, s in region_signal.items()
            if s.lifecycle in ("peak", "declining")
        ]
        # rising 区域: 跟进窗口持有者
        rising_regions = [
            (r, s) for r, s in region_signal.items() if s.lifecycle == "rising"
        ]

        windows: List[Dict[str, Any]] = []
        for ahead_region, ahead_signal in ahead_regions:
            for rising_region, rising_signal in rising_regions:
                windows.append(
                    {
                        "from_region": ahead_region,
                        "to_region": rising_region,
                        "from_lifecycle": ahead_signal.lifecycle,
                        "to_lifecycle": "rising",
                        "window": rising_signal.predictWindow,
                    }
                )

        logger.debug(
            f"跟进窗口识别: {len(windows)} 个 "
            f"(ahead={len(ahead_regions)}, rising={len(rising_regions)})"
        )
        return windows

    # ==================================================================
    # generate_heat_map - 区域热度图
    # ==================================================================

    def generate_heat_map(self, signals: List[TrendSignal]) -> Dict[str, float]:
        """生成区域热度图 — {region: heatScore}。

        同区域多条信号时, 取最后一条的 heatScore (调用方可按需去重)。

        参数:
            signals: TrendSignal 列表

        返回:
            ``{region: heatScore}`` 字典 (空输入返回空字典)
        """
        heat_map: Dict[str, float] = {}
        for s in signals:
            heat_map[s.region] = s.heatScore
        return heat_map

    # ==================================================================
    # generate_localization_suggestions - 本地化适配建议
    # ==================================================================

    def generate_localization_suggestions(
        self, signals: List[TrendSignal]
    ) -> Dict[str, Any]:
        """生成本地化适配建议 — 海外趋势进入中国时的价格/材质/文化建议。

        适用条件 (applicable=True):
            存在海外区域 (us/eu) 处于 peak/declining (趋势已成熟),
            且中国 (china) 处于 rising (趋势刚到达, 正在进入中国)。

        建议内容:
            - priceRange         : 价格区间 (按品类 + spendingPower 调整)
            - material           : 材质偏好 (按品类)
            - culturalAdaptation : 文化适配建议 (按品类)
            - zGenTags           : 聚合海外信号的 Z 世代审美标签
            - source_regions     : 领先中国的海外区域列表

        参数:
            signals: TrendSignal 列表

        返回:
            ``{applicable, source_regions, priceRange, material,
               culturalAdaptation, zGenTags}``
            不适用时 applicable=False, 其余字段为空/默认。
        """
        not_applicable = {
            "applicable": False,
            "source_regions": [],
            "priceRange": "",
            "material": "",
            "culturalAdaptation": "",
            "zGenTags": [],
        }

        if not signals:
            return not_applicable

        # 按区域分组 (同区域取最后一条)
        region_signal: Dict[str, TrendSignal] = {}
        for s in signals:
            region_signal[s.region] = s

        china_signal = region_signal.get(_TARGET_REGION)
        # 中国不存在或非 rising → 不属于「进入中国」场景
        if china_signal is None or china_signal.lifecycle != "rising":
            return not_applicable

        # 海外领先区域: us/eu 处于 peak/declining
        ahead_overseas = [
            r
            for r, s in region_signal.items()
            if r in _OVERSEAS_REGIONS and s.lifecycle in ("peak", "declining")
        ]
        if not ahead_overseas:
            return not_applicable

        # 取品类 (优先用中国信号, 其次任一海外信号)
        category = china_signal.category
        profile = _LOCALIZATION_PROFILES.get(category, _DEFAULT_PROFILE)

        # 聚合海外信号的 Z 世代标签 (去重, 保序)
        z_gen_tags: List[str] = []
        seen_tags = set()
        for r in ahead_overseas:
            for tag in region_signal[r].zGenTags:
                if tag not in seen_tags:
                    seen_tags.add(tag)
                    z_gen_tags.append(tag)

        # 按 spendingPower 调整价格区间
        spending_power = self._extract_spending_power(china_signal)
        price_range = self._adjust_price_range(profile["priceRange"], spending_power)

        logger.info(
            f"本地化建议适用: 品类='{category}', 来源区域={ahead_overseas}, "
            f"消费力='{spending_power}', 价格区间='{price_range}'"
        )

        return {
            "applicable": True,
            "source_regions": ahead_overseas,
            "priceRange": price_range,
            "material": profile["material"],
            "culturalAdaptation": profile["culturalAdaptation"],
            "zGenTags": z_gen_tags,
        }

    # ==================================================================
    # 辅助方法
    # ==================================================================

    @staticmethod
    def _extract_spending_power(signal: Any) -> str:
        """从 TrendSignal.targetAudience 提取 spendingPower。

        参数:
            signal: TrendSignal 实例

        返回:
            spendingPower 值 ("高"/"中"/"低"), 缺失时默认 "中"
        """
        audience = signal.targetAudience or {}
        power = audience.get("spendingPower", "中")
        if power in _SPENDING_POWER_MULTIPLIER:
            return power
        return "中"

    @staticmethod
    def _adjust_price_range(base_range: str, spending_power: str) -> str:
        """按 spendingPower 调整价格区间。

        解析 "39-129" 格式, 对上下限同乘倍率 (向上取整)。

        参数:
            base_range     : 基线价格区间 (如 "39-129")
            spending_power : 消费力 ("高"/"中"/"低")

        返回:
            调整后的价格区间 (如 "55-181")
        """
        multiplier = _SPENDING_POWER_MULTIPLIER.get(spending_power, 1.0)
        if multiplier == 1.0:
            return base_range

        parts = base_range.split("-")
        if len(parts) != 2:
            return base_range

        try:
            lower = math.ceil(float(parts[0]) * multiplier)
            upper = math.ceil(float(parts[1]) * multiplier)
            return f"{lower}-{upper}"
        except (ValueError, TypeError):
            return base_range


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = [
    "CrossRegionComparator",
    "LIFECYCLE_DIFFUSION_ORDER",
    "LIFECYCLE_ROLE",
]
