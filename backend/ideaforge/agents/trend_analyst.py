# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - Agent 1 趋势分析师 (Task 9)
# ==============================================================================
# 对应 spec §4.2 Agent 1: TrendAnalyst (趋势分析师)
#   职责: 解读趋势信号, 提取产品方向 (含 Z 世代审美标签 + 跨区域适配建议)
#   输入: TrendSignal (13 字段, 数据感知层输出)
#   输出: ProductDirection (6 字段, 产品方向)
#
# TrendAnalyst 设计要点:
#   - 规则/模板生成 (Demo 原型, 无需 LLM API 调用)
#   - analyze() 方法结构化, 未来可替换为 LLM 调用 (GPT-4 / 通义千问 / 飞书 AI)
#   - 品类 → 价格带映射 (与跨区域引擎本地化档案保持一致)
#   - Z 世代审美标签 → 风格调性映射 (侘寂/Y2K/多巴胺/极简等)
#   - 跨区域建议: lifecycle (rising/peak/declining) + crossRegionDiff → 主推/次推/观望
#
# 工具 (未来集成, 当前 stub):
#   - 趋势数据库查询
#   - 品类知识库
#   - 飞书 Wiki RAG (历史爆品案例检索)
# ==============================================================================

"""
Agent 1: 趋势分析师 (TrendAnalyst)。

决策推理层第一步: 解读趋势信号, 提取产品方向。

将数据感知层 (TrendPulse) 输出的 TrendSignal 转化为产品开发方向
ProductDirection, 含品类方向、风格调性、目标人群、价格带区间、
Z 世代审美标签与跨区域适配建议。

当前实现采用规则/模板生成 (Demo 原型), 结构设计支持未来替换为
LLM few-shot 生成 (GPT-4 / 通义千问 / 飞书 AI)。

用法::

    analyst = TrendAnalyst()
    direction = analyst.analyze(trend_signal)
    # direction: ProductDirection(category, styleTone, targetAudience,
    #                             priceRange, zGenTags, crossRegionAdvice)
"""

from __future__ import annotations

from typing import Any, Dict

from shared.models import ProductDirection, TrendSignal
from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# 常量: 品类 → 价格带映射 (与 cross_region._LOCALIZATION_PROFILES 保持一致)
# ==============================================================================

# 品类 → 价格区间 (中等消费力基线, 名创优品主力价格带)
_CATEGORY_PRICE_RANGE: Dict[str, str] = {
    "家居/装饰": "39-129",
    "家居/香氛": "39-99",
    "美妆/个护": "29-99",
    "服饰/穿搭": "59-199",
    "数码/配件": "59-299",
    "食品/零食": "19-59",
    "玩具/文创": "19-99",
}
"""品类 → 价格带映射。

与跨区域引擎本地化档案 (cross_region._LOCALIZATION_PROFILES) 保持一致,
确保趋势分析师与产品策划师的价格带判断同源。
"""

# 默认价格带 (品类未匹配时)
_DEFAULT_PRICE_RANGE: str = "39-129"

# 默认受众画像 (trend.targetAudience 缺失键时补全)
_DEFAULT_AUDIENCE: Dict[str, Any] = {
    "ageRange": "18-30",
    "aesthetic": "自然",
    "spendingPower": "中",
}

# Z 世代审美标签关键词 → 风格调性映射
# 按标签关键词匹配 (子串包含), 命中即采用对应风格调性
_ZGEN_TAG_STYLE_MAP: Dict[str, str] = {
    "侘寂": "侘寂自然",
    "自然系": "侘寂自然",
    "Y2K": "Y2K复古",
    "多巴胺": "多巴胺鲜艳",
    "极简": "极简留白",
    "简约": "极简留白",
    "复古": "复古怀旧",
    "国潮": "国潮新中式",
    "新中式": "国潮新中式",
    "赛博": "赛博朋克",
    "废土": "废土机能",
    "甜妹": "甜美少女",
    "少女": "甜美少女",
    "治愈": "治愈温暖",
    "森系": "森系自然",
}
"""Z 世代审美标签关键词 → 风格调性映射。

匹配方式: 遍历 zGenTags, 若某标签包含映射中的关键词 (子串匹配),
则采用对应风格调性。优先匹配第一个命中的关键词。
"""

# 默认风格调性 (无 zGenTags 或无匹配时, 基于品类推断)
_DEFAULT_STYLE_TONE: str = "现代简约"

# 品类 → 默认风格调性 (无 zGenTags 匹配时的回退)
_CATEGORY_DEFAULT_STYLE: Dict[str, str] = {
    "家居/香氛": "疗愈自然",
    "家居/装饰": "现代简约",
    "美妆/个护": "少女心",
    "服饰/穿搭": "潮流休闲",
    "数码/配件": "科技简约",
    "食品/零食": "趣味活泼",
    "玩具/文创": "趣味萌系",
}

# lifecycle → 跨区域建议 (当前区域)
_LIFECYCLE_ADVICE: Dict[str, str] = {
    "rising": "主推",
    "peak": "主推",
    "declining": "观望",
}
"""lifecycle 阶段 → 当前区域推广建议。

- rising (上升): 趋势增长中, 存在跟进窗口 → 主推
- peak (峰值): 趋势正热, 抢占窗口 → 主推
- declining (衰退): 趋势下行, 风险升高 → 观望
"""

# crossRegionDiff 值 (lifecycle 描述符) → 跨区域建议
_REGION_DIFF_ADVICE: Dict[str, str] = {
    "peak": "主推",
    "rising": "主推",
    "declining": "观望",
    "nascent": "次推",
}
"""crossRegionDiff 值 → 该区域推广建议。

crossRegionDiff 的值为各区域的 lifecycle 描述符 (如 peak/rising/
declining/nascent), 映射为推广建议:
- peak/rising → 主推 (趋势热度高或增长中)
- declining → 观望 (趋势衰退)
- nascent → 次推 (萌芽期, 潜力待验证)
- 未知描述符 → 次推 (保守策略)
"""

# crossRegionDiff 未知值时的默认建议
_DEFAULT_REGION_ADVICE: str = "次推"


# ==============================================================================
# TrendAnalyst 趋势分析师
# ==============================================================================


class TrendAnalyst:
    """趋势分析师 (Agent 1, spec §4.2)。

    解读 TrendSignal 趋势信号, 提取产品开发方向 ProductDirection。

    当前采用规则/模板生成:
        1. category          : 透传 trend.category
        2. styleTone         : 基于 zGenTags 关键词映射, 回退至品类默认风格
        3. targetAudience    : 透传 trend.targetAudience, 缺失键补全默认值
        4. priceRange        : 品类 → 价格带映射, 未知品类用默认价格带
        5. zGenTags          : 透传 trend.zGenTags
        6. crossRegionAdvice : lifecycle + crossRegionDiff → 主推/次推/观望

    设计支持未来替换为 LLM 调用: analyze() 方法可改为调用 GPT-4 /
    通义千问 / 飞书 AI, 输入 TrendSignal, 输出 ProductDirection。

    用法::

        analyst = TrendAnalyst()
        direction = analyst.analyze(trend_signal)
        # direction.category == trend_signal.category
        # direction.zGenTags == trend_signal.zGenTags
        # direction.crossRegionAdvice == {"china": "主推", "us": "主推"}
    """

    # ==================================================================
    # analyze() - 主入口: TrendSignal → ProductDirection
    # ==================================================================

    def analyze(self, trend: TrendSignal) -> ProductDirection:
        """解读趋势信号, 提取产品方向。

        对应 spec §4.2 Agent 1 核心职责。将 TrendSignal 转化为
        ProductDirection, 含品类/风格/受众/价格带/Z世代标签/跨区域建议。

        参数:
            trend: 趋势信号 (TrendSignal 实例, 数据感知层输出)

        返回:
            ProductDirection 实例, 6 个字段全部填充:
            - category          : 透传 trend.category
            - styleTone         : 基于 zGenTags 映射的风格调性
            - targetAudience    : 透传并补全的受众画像
            - priceRange        : 品类对应价格带
            - zGenTags          : 透传 trend.zGenTags
            - crossRegionAdvice : 跨区域推广建议
        """
        logger.info(
            f"TrendAnalyst.analyze: topic='{trend.topic}', "
            f"category='{trend.category}', lifecycle='{trend.lifecycle}', "
            f"region='{trend.region}'"
        )

        # 1. 品类: 透传
        category = trend.category

        # 2. 风格调性: 基于 zGenTags 映射, 回退至品类默认
        style_tone = self._derive_style_tone(trend)

        # 3. 目标受众: 透传并补全缺失键
        target_audience = self._build_target_audience(trend)

        # 4. 价格带: 品类映射, 未知品类用默认
        price_range = _CATEGORY_PRICE_RANGE.get(category, _DEFAULT_PRICE_RANGE)

        # 5. Z 世代标签: 透传
        z_gen_tags = list(trend.zGenTags)

        # 6. 跨区域建议: lifecycle + crossRegionDiff
        cross_region_advice = self._build_cross_region_advice(trend)

        direction = ProductDirection(
            category=category,
            styleTone=style_tone,
            targetAudience=target_audience,
            priceRange=price_range,
            zGenTags=z_gen_tags,
            crossRegionAdvice=cross_region_advice,
        )

        logger.info(
            f"TrendAnalyst.analyze: 完成 → category='{direction.category}', "
            f"styleTone='{direction.styleTone}', priceRange='{direction.priceRange}', "
            f"advice={direction.crossRegionAdvice}"
        )

        return direction

    # ==================================================================
    # 内部辅助: 风格调性推导
    # ==================================================================

    def _derive_style_tone(self, trend: TrendSignal) -> str:
        """基于 zGenTags 与 topic 推导风格调性。

        优先级:
            1. zGenTags 关键词匹配 (子串包含) → 对应风格调性
            2. topic 关键词匹配 → 对应风格调性
            3. 品类默认风格调性
            4. 全局默认风格调性 (_DEFAULT_STYLE_TONE)

        参数:
            trend: 趋势信号

        返回:
            风格调性字符串 (非空)
        """
        # 1. zGenTags 关键词匹配
        for tag in trend.zGenTags:
            matched = self._match_style_keyword(tag)
            if matched:
                return matched

        # 2. topic 关键词匹配
        matched_topic = self._match_style_keyword(trend.topic)
        if matched_topic:
            return matched_topic

        # 3. 品类默认风格
        category_style = _CATEGORY_DEFAULT_STYLE.get(trend.category)
        if category_style:
            return category_style

        # 4. 全局默认
        return _DEFAULT_STYLE_TONE

    @staticmethod
    def _match_style_keyword(text: str) -> str:
        """在文本中匹配风格关键词, 返回对应风格调性。

        遍历 _ZGEN_TAG_STYLE_MAP, 返回第一个关键词被 text 包含的映射值。

        参数:
            text: 待匹配文本 (zGenTag 或 topic)

        返回:
            匹配到的风格调性; 无匹配返回空字符串
        """
        if not text:
            return ""
        for keyword, style in _ZGEN_TAG_STYLE_MAP.items():
            if keyword in text:
                return style
        return ""

    # ==================================================================
    # 内部辅助: 目标受众画像构建
    # ==================================================================

    def _build_target_audience(self, trend: TrendSignal) -> Dict[str, Any]:
        """透传 trend.targetAudience, 缺失键补全默认值。

        确保 targetAudience 含 ageRange/aesthetic/spendingPower 三个键,
        缺失的键用 _DEFAULT_AUDIENCE 中的默认值补全。

        参数:
            trend: 趋势信号

        返回:
            补全后的受众画像字典
        """
        audience: Dict[str, Any] = {}
        # 透传原始值
        for key, value in trend.targetAudience.items():
            audience[key] = value
        # 补全缺失键
        for key, default_value in _DEFAULT_AUDIENCE.items():
            if key not in audience:
                audience[key] = default_value
        return audience

    # ==================================================================
    # 内部辅助: 跨区域建议构建
    # ==================================================================

    def _build_cross_region_advice(self, trend: TrendSignal) -> Dict[str, str]:
        """基于 lifecycle + crossRegionDiff 构建跨区域推广建议。

        逻辑:
            1. 当前区域 (trend.region): 基于 trend.lifecycle 映射
               - rising/peak → 主推
               - declining → 观望
            2. crossRegionDiff 中各区域: 基于其 lifecycle 描述符映射
               - peak/rising → 主推
               - declining → 观望
               - nascent → 次推
               - 未知 → 次推
            3. 当前区域的建议以 trend.lifecycle 为准 (权威), 不被
               crossRegionDiff 覆盖 (若 crossRegionDiff 也含当前区域)

        参数:
            trend: 趋势信号

        返回:
            跨区域推广建议 {region: 主推|次推|观望}
        """
        advice: Dict[str, str] = {}

        # 1. 当前区域: 基于 trend.lifecycle (权威来源)
        current_advice = _LIFECYCLE_ADVICE.get(trend.lifecycle, _DEFAULT_REGION_ADVICE)
        advice[trend.region] = current_advice

        # 2. crossRegionDiff 中各区域: 基于其 lifecycle 描述符
        for region, lifecycle_desc in trend.crossRegionDiff.items():
            # 跳过当前区域 (已用权威 lifecycle 设置)
            if region == trend.region:
                continue
            region_advice = _REGION_DIFF_ADVICE.get(
                lifecycle_desc, _DEFAULT_REGION_ADVICE
            )
            advice[region] = region_advice

        return advice


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["TrendAnalyst"]
