# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - SQLAlchemy 2.0 ORM 模型
# ==============================================================================
# 对应 spec:
#   §3.4 TrendSignal       - 数据感知层输出 (持久化趋势信号)
#   §4.4 ProductIdeaCard   - 决策推理层输出 (持久化产品创意卡)
#   §5   MarketProbe       - 验证反馈层输出 (持久化测试计划/模拟/分析结果)
#
# 技术栈: SQLAlchemy 2.0 (Mapped[] / mapped_column 风格)
# 数据库: PostgreSQL (使用 JSON 兼容 JSONB, UUID 主键, 时区感知时间戳)
#
# 设计要点:
#   - 继承 shared.database.Base (DeclarativeBase)
#   - 主键统一使用 UUID (PostgreSQL 原生 UUID 类型)
#   - JSON 字段使用 sqlalchemy.JSON (PostgreSQL 自动映射为 JSONB)
#   - 时间戳使用 DateTime(timezone=True) 带时区
#   - 高频查询字段建立索引 (topic / region / concept_id / hit_score / step ...)
#   - ORM 模型与 shared.models 中的 Pydantic 模型字段对齐
#     (Pydantic 模型不做修改, 由 repositories 层完成转换)
# ==============================================================================

"""
SQLAlchemy 2.0 ORM 模型模块。

定义三张核心持久化表:
    1. trend_signals        - 趋势信号 (对应 Pydantic TrendSignal, 13 业务字段)
    2. product_idea_cards   - 产品创意卡 (对应 Pydantic ProductIdeaCard, 16 业务字段)
    3. marketprobe_results  - MarketProbe 验证结果 (test_plan / simulation / analysis)

使用方式:
    - 由 Alembic 自动生成迁移 (target_metadata = Base.metadata)
    - 由 shared.repositories 仓储层进行 CRUD 操作
    - 由 shared.database.init_db() 在开发环境创建表

注意:
    - 本模块仅定义 ORM 模型, 不修改 shared.models 中的 Pydantic 模型
    - Pydantic 模型 -> ORM 模型的转换由 repositories.py 完成
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.database import Base


# ==============================================================================
# 模型 1: TrendSignalORM (表 trend_signals)
# ==============================================================================
# 对应 Pydantic TrendSignal (spec §3.4, 13 业务字段)
# 用途: 持久化 TrendPulse 数据感知层输出的趋势信号
# ==============================================================================


class TrendSignalORM(Base):
    """趋势信号 ORM 模型 (表名: trend_signals)。

    对应 Pydantic TrendSignal, 持久化多区域趋势信号数据。
    同一 topic 可含多个区域的信号 (跨区域对比的基础)。
    """

    __tablename__ = "trend_signals"

    # --- 主键 ---
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="主键 UUID",
    )

    # --- 基础趋势字段 (对齐 TrendSignal) ---
    topic: Mapped[str] = mapped_column(
        String(256),
        index=True,
        nullable=False,
        comment="话题名, 如 '侘寂风家居'",
    )
    heat_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="0-100 热度分",
    )
    growth_rate: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="周环比增长率, 如 +34.2 表示 +34.2%",
    )
    category: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="品类, 如 '家居/装饰'",
    )
    sentiment: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="-1~1 情感倾向",
    )
    lifecycle: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="生命周期阶段: rising | peak | declining",
    )
    predict_window: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="预计窗口期, 如 '2-4周'",
    )
    related_keywords: Mapped[List[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="关联关键词列表",
    )
    source_breakdown: Mapped[Dict[str, int]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="来源分布, 如 {xiaohongshu: 45, douyin: 30}",
    )

    # --- Task 2 重点扩展字段 ---
    region: Mapped[str] = mapped_column(
        String(32),
        index=True,
        nullable=False,
        comment="区域标识: china | sea | us | eu | global",
    )
    z_gen_tags: Mapped[List[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="Z 世代审美标签, 如 ['Y2K', '多巴胺']",
    )
    target_audience: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="受众画像 {ageRange, aesthetic, spendingPower}",
    )
    cross_region_diff: Mapped[Dict[str, str]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="跨区域热度差 {us: peak, cn: rising, sea: nascent}",
    )

    # --- 时间戳 ---
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )
    updated_at: Mapped[Optional[Any]] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
        comment="更新时间",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<TrendSignalORM(id={self.id}, topic='{self.topic}', "
            f"region='{self.region}', heat_score={self.heat_score})>"
        )


# ==============================================================================
# 模型 2: ProductIdeaCardORM (表 product_idea_cards)
# ==============================================================================
# 对应 Pydantic ProductIdeaCard (spec §4.4, 16 业务字段)
# 用途: 持久化 IdeaForge 决策推理层输出的产品创意卡
# ==============================================================================


class ProductIdeaCardORM(Base):
    """产品创意卡 ORM 模型 (表名: product_idea_cards)。

    对应 Pydantic ProductIdeaCard, 持久化完整的产品创意方案。
    包含 IP 匹配、爆品预测、区域适配与决策链路追溯。
    """

    __tablename__ = "product_idea_cards"

    # --- 主键 ---
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="主键 UUID",
    )

    # --- 产品基础信息 ---
    concept_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="创意 ID, 如 'CPT-2025-0001' (业务唯一键)",
    )
    product_name: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
        comment="产品名称",
    )
    category: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="品类, 如 '家居/香氛'",
    )
    design_desc: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="设计描述",
    )
    material: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="材质, 如 '大豆蜡 + 陶瓷'",
    )
    price_range: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="价格区间, 如 '59-89'",
    )

    # --- IP 匹配 (JSON 存储嵌套 IPMatch) ---
    ip_match: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="IP 联名匹配结果 (IPMatch 序列化)",
    )

    # --- 卖点与预测 ---
    selling_points: Mapped[List[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="核心卖点列表",
    )
    hit_score: Mapped[float] = mapped_column(
        Float,
        index=True,
        nullable=False,
        comment="爆品概率 0-1, 1 为确定爆品",
    )
    top_factors: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="Top-3 影响因子 (SHAP 值)",
    )
    concept_images: Mapped[List[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="概念图 URL 列表",
    )

    # --- 来源与匹配度 ---
    trend_source: Mapped[str] = mapped_column(
        String(256),
        index=True,
        nullable=False,
        comment="关联的 TrendSignal 话题名 (趋势来源引用)",
    )
    z_gen_match_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Z 世代匹配度 0-1",
    )
    target_audience: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="受众画像",
    )
    region_fit: Mapped[Dict[str, str]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="区域适配度 {china: high, sea: medium, us: low}",
    )
    agent_trace: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="决策链路可追溯 [{agent, step, output}]",
    )

    # --- 时间戳 ---
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )
    updated_at: Mapped[Optional[Any]] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
        comment="更新时间",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ProductIdeaCardORM(id={self.id}, concept_id='{self.concept_id}', "
            f"product_name='{self.product_name}', hit_score={self.hit_score})>"
        )


# ==============================================================================
# 模型 3: MarketProbeResultORM (表 marketprobe_results)
# ==============================================================================
# 对应 MarketProbeStore 中的 test_plan / simulation_data / analysis_result
# 用途: 持久化 MarketProbe 验证反馈层 4 步闭环的中间结果
# ==============================================================================


class MarketProbeResultORM(Base):
    """MarketProbe 验证结果 ORM 模型 (表名: marketprobe_results)。

    持久化 MarketProbe 4 步闭环的中间结果:
        - step='test_plan'   : TestDesigner 输出
        - step='simulation'  : SalesSimulator 输出
        - step='analysis'    : PerformanceAnalyzer 输出

    通过 (step, product_name) 联合定位某一产品的某一步骤结果。
    """

    __tablename__ = "marketprobe_results"

    # --- 主键 ---
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="主键 UUID",
    )

    # --- 业务键 ---
    step: Mapped[str] = mapped_column(
        String(32),
        index=True,
        nullable=False,
        comment="步骤标识: test_plan | simulation | analysis",
    )
    product_name: Mapped[str] = mapped_column(
        String(256),
        index=True,
        nullable=False,
        comment="产品名称 (业务关联键)",
    )

    # --- 载荷 (JSON 存储任意结构的结果) ---
    payload: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="步骤结果载荷 (JSON)",
    )

    # --- 时间戳 ---
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )
    updated_at: Mapped[Optional[Any]] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
        comment="更新时间",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<MarketProbeResultORM(id={self.id}, step='{self.step}', "
            f"product_name='{self.product_name}')>"
        )


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = [
    "TrendSignalORM",
    "ProductIdeaCardORM",
    "MarketProbeResultORM",
]
