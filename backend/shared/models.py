# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 共享数据模型
# ==============================================================================
# 对应 spec:
#   §3.4 TrendSignal       - 数据感知层输出
#   §4.3 IPMatch           - IP 联名匹配输出
#   §4.4 ProductIdeaCard   - 决策推理层输出
#   Agent 1 ProductDirection - 产品方向
#   Agent 2 ProductConcept   - 产品概念
#
# 技术栈: Pydantic v2 (pydantic>=2.0)
# 所有模型继承 BaseModel，使用 Field() 约束 + Literal 枚举校验
# ==============================================================================

"""
共享 Pydantic 数据模型。

本模块定义跨服务 (TrendPulse / IdeaForge / MarketProbe) 共用的核心数据结构，
所有字段严格对齐设计文档 spec §3.4 / §4.3 / §4.4。

模型清单:
    1. TrendSignal        - 趋势信号 (13 字段, spec §3.4)
    2. IPMatch            - IP 联名匹配 (7 字段, spec §4.3)
    3. ProductIdeaCard    - 产品创意卡 (16 字段, spec §4.4)
    4. ProductDirection   - 产品方向 (6 字段, Agent 1 输出)
    5. ProductConcept     - 产品概念 (8 字段, Agent 2 输出)
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ==============================================================================
# 模型 1: TrendSignal (spec §3.4 - 数据感知层输出)
# ==============================================================================


class TrendSignal(BaseModel):
    """
    趋势信号 - 数据感知层 (TrendPulse) 的核心输出。

    描述一个市场趋势话题的热度、增长、情感、生命周期及跨区域差异。
    对应 spec §3.4，共 13 个字段。

    关键扩展字段 (Task 2 重点):
        - region          : 区域标识 (china | sea | us | eu | global)
        - zGenTags        : Z 世代审美标签
        - targetAudience  : 受众画像
        - crossRegionDiff : 跨区域热度差
    """

    model_config = ConfigDict(
        extra="forbid",  # 禁止未知字段，保证数据契约严格
        validate_assignment=True,  # 属性赋值时也触发校验
        populate_by_name=True,  # 允许按字段名 (而非别名) 填充
    )

    # --- 基础趋势字段 ---
    topic: str = Field(
        ...,
        description="话题名，如 '侘寂风家居'",
        min_length=1,
    )
    heatScore: float = Field(
        ...,
        ge=0,
        le=100,
        description="0-100 热度分",
    )
    growthRate: float = Field(
        ...,
        description="周环比增长率，如 +34.2 表示 +34.2%",
    )
    category: str = Field(
        ...,
        description="品类，如 '家居/装饰'",
        min_length=1,
    )
    sentiment: float = Field(
        ...,
        ge=-1,
        le=1,
        description="-1~1 情感倾向，-1 最负面，1 最正面",
    )
    lifecycle: Literal["rising", "peak", "declining"] = Field(
        ...,
        description="生命周期阶段: rising(上升) | peak(峰值) | declining(衰退)",
    )
    predictWindow: str = Field(
        ...,
        description="预计窗口期，如 '2-4周'",
        min_length=1,
    )
    relatedKeywords: List[str] = Field(
        default_factory=list,
        description="关联关键词列表",
    )
    sourceBreakdown: Dict[str, int] = Field(
        default_factory=dict,
        description="来源分布，如 {xiaohongshu: 45, douyin: 30}",
    )

    # --- Task 2 重点扩展字段 ---
    region: Literal["china", "sea", "us", "eu", "global"] = Field(
        ...,
        description="区域标识: china | sea | us | eu | global",
    )
    zGenTags: List[str] = Field(
        default_factory=list,
        description="Z 世代审美标签，如 ['Y2K', '多巴胺']",
    )
    targetAudience: Dict[str, Any] = Field(
        default_factory=dict,
        description="受众画像 {ageRange, aesthetic, spendingPower}",
    )
    crossRegionDiff: Dict[str, str] = Field(
        default_factory=dict,
        description="跨区域热度差 {us: peak, cn: rising, sea: nascent}",
    )


# ==============================================================================
# 模型 2: IPMatch (spec §4.3 - IP 联名匹配输出)
# ==============================================================================


class IPMatch(BaseModel):
    """
    IP 联名匹配结果 - IdeaForge 决策推理层的 IP 匹配输出。

    描述一个 IP 的势能、品类匹配度、可用性及区域热度分布。
    对应 spec §4.3，共 7 个字段。

    关键字段:
        - ipPowerScore  : IP 势能分 0-100
        - matchScore    : 品类匹配度 0-1
        - availability  : 可用性状态
        - regionHeatMap : 区域热度分布
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True,
    )

    ipName: str = Field(
        ...,
        description="IP 名称，如 '三丽鸥·库洛米'",
        min_length=1,
    )
    ipPowerScore: float = Field(
        ...,
        ge=0,
        le=100,
        description="IP 势能分 0-100，越高代表 IP 商业价值越大",
    )
    matchScore: float = Field(
        ...,
        ge=0,
        le=1,
        description="品类匹配度 0-1，1 为完美匹配",
    )
    availability: Literal["available", "exclusive", "expiring", "unavailable"] = (
        Field(
            ...,
            description=(
                "可用性状态: "
                "available(可用) | exclusive(独家期内) | "
                "expiring(即将到期) | unavailable(不可用)"
            ),
        )
    )
    exclusiveUntil: Optional[str] = Field(
        default=None,
        description="独家期截止日，如 '2025-12-31'；无独家期时为 None",
    )
    regionHeatMap: Dict[str, int] = Field(
        default_factory=dict,
        description="区域热度分布 {china: 92, sea: 78, us: 65, eu: 45}",
    )
    recommendedCategories: List[str] = Field(
        default_factory=list,
        description="该 IP 最适合的品类列表",
    )


# ==============================================================================
# 模型 3: ProductIdeaCard (spec §4.4 - 决策推理层输出)
# ==============================================================================


class ProductIdeaCard(BaseModel):
    """
    产品创意卡 - IdeaForge 决策推理层的最终输出。

    整合趋势信号、IP 匹配、爆品预测与区域适配，形成完整的产品创意方案。
    对应 spec §4.4，共 16 个字段。

    关键字段:
        - ipMatch         : IP 联名匹配结果 (嵌套 IPMatch)
        - hitScore        : 爆品概率 0-1
        - zGenMatchScore  : Z 世代匹配度 0-1
        - regionFit       : 区域适配度
        - agentTrace      : 决策链路可追溯
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True,
    )

    # --- 产品基础信息 ---
    conceptId: str = Field(
        ...,
        description="创意 ID，如 'CPT-2025-0001'",
        min_length=1,
    )
    productName: str = Field(
        ...,
        description="产品名称",
        min_length=1,
    )
    category: str = Field(
        ...,
        description="品类，如 '家居/香氛'",
        min_length=1,
    )
    designDesc: str = Field(
        ...,
        description="设计描述",
        min_length=1,
    )
    material: str = Field(
        ...,
        description="材质，如 '大豆蜡 + 陶瓷'",
        min_length=1,
    )
    priceRange: str = Field(
        ...,
        description="价格区间，如 '59-89'",
        min_length=1,
    )

    # --- IP 匹配 (嵌套模型) ---
    ipMatch: IPMatch = Field(
        ...,
        description="IP 联名匹配结果 (IPMatch 实例)",
    )

    # --- 卖点与预测 ---
    sellingPoints: List[str] = Field(
        default_factory=list,
        description="核心卖点列表",
    )
    hitScore: float = Field(
        ...,
        ge=0,
        le=1,
        description="爆品概率 0-1，1 为确定爆品",
    )
    topFactors: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Top-3 影响因子 (SHAP 值)，如 [{feature, shap}]",
    )
    conceptImages: List[str] = Field(
        default_factory=list,
        description="概念图 URL 列表 [url_front, url_scene]",
    )

    # --- 来源与匹配度 ---
    trendSource: str = Field(
        ...,
        description="关联的 TrendSignal 话题名 (趋势来源引用)",
        min_length=1,
    )
    zGenMatchScore: float = Field(
        ...,
        ge=0,
        le=1,
        description="Z 世代匹配度 0-1",
    )
    targetAudience: Dict[str, Any] = Field(
        default_factory=dict,
        description="受众画像 {ageRange, aesthetic, spendingPower}",
    )
    regionFit: Dict[str, str] = Field(
        default_factory=dict,
        description="区域适配度 {china: high, sea: medium, us: low}",
    )
    agentTrace: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="决策链路可追溯 [{agent, step, output}]",
    )


# ==============================================================================
# 模型 4: ProductDirection (Agent 1 输出 - 产品方向)
# ==============================================================================


class ProductDirection(BaseModel):
    """
    产品方向 - IdeaForge Agent 1 (ProductDirector) 的输出。

    在决策链路的第一步，根据趋势信号确定产品开发方向。
    共 6 个字段。

    字段:
        - category          : 目标品类
        - styleTone         : 风格基调
        - targetAudience    : 目标受众画像
        - priceRange        : 价格区间
        - zGenTags          : Z 世代审美标签
        - crossRegionAdvice : 跨区域推广建议
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True,
    )

    category: str = Field(
        ...,
        description="目标品类，如 '家居/香氛'",
        min_length=1,
    )
    styleTone: str = Field(
        ...,
        description="风格基调，如 '侘寂自然'",
        min_length=1,
    )
    targetAudience: Dict[str, Any] = Field(
        default_factory=dict,
        description="目标受众画像 {ageRange, aesthetic, spendingPower}",
    )
    priceRange: str = Field(
        ...,
        description="价格区间，如 '59-129'",
        min_length=1,
    )
    zGenTags: List[str] = Field(
        default_factory=list,
        description="Z 世代审美标签，如 ['Y2K', '多巴胺']",
    )
    crossRegionAdvice: Dict[str, str] = Field(
        default_factory=dict,
        description="跨区域推广建议 {china: 主推, sea: 次推, us: 观望}",
    )


# ==============================================================================
# 模型 5: ProductConcept (Agent 2 输出 - 产品概念)
# ==============================================================================


class ProductConcept(BaseModel):
    """
    产品概念 - IdeaForge Agent 2 (ConceptCreator) 的输出。

    在决策链路的第二步，基于产品方向生成具体的产品概念。
    共 8 个字段。

    字段:
        - productName     : 产品名称
        - category        : 品类
        - designDesc      : 设计描述
        - material        : 材质
        - priceRange      : 价格区间
        - ipDirection     : IP 方向建议
        - sellingPoints   : 核心卖点
        - targetAudience  : 目标受众画像
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True,
    )

    productName: str = Field(
        ...,
        description="产品名称",
        min_length=1,
    )
    category: str = Field(
        ...,
        description="品类，如 '家居/香氛'",
        min_length=1,
    )
    designDesc: str = Field(
        ...,
        description="设计描述",
        min_length=1,
    )
    material: str = Field(
        ...,
        description="材质，如 '大豆蜡 + 陶瓷'",
        min_length=1,
    )
    priceRange: str = Field(
        ...,
        description="价格区间，如 '59-89'",
        min_length=1,
    )
    ipDirection: str = Field(
        ...,
        description="IP 方向建议，如 '三丽鸥·库洛米'",
        min_length=1,
    )
    sellingPoints: List[str] = Field(
        default_factory=list,
        description="核心卖点列表",
    )
    targetAudience: Dict[str, Any] = Field(
        default_factory=dict,
        description="目标受众画像 {ageRange, aesthetic, spendingPower}",
    )


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = [
    "TrendSignal",
    "IPMatch",
    "ProductIdeaCard",
    "ProductDirection",
    "ProductConcept",
]
