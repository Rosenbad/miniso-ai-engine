# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 数据库仓储层
# ==============================================================================
# 实现 3 个异步仓储类, 封装 ORM 模型的 CRUD 操作:
#   1. TrendRepository        - 趋势信号仓储 (TrendSignalORM)
#   2. IdeaCardRepository     - 产品创意卡仓储 (ProductIdeaCardORM)
#   3. MarketProbeRepository  - MarketProbe 结果仓储 (MarketProbeResultORM)
#
# 设计要点:
#   - 基于 AsyncSession, 与 FastAPI 依赖注入 (get_db) 配合使用
#   - 仓储方法接收 Pydantic 模型, 内部完成 -> ORM 转换
#   - save_* 方法执行 upsert 语义 (存在则更新, 不存在则插入)
#   - 查询方法返回 ORM 实例列表, 由调用方按需序列化
#   - 不在此处调用 commit, 由调用方 (或 FastAPI 依赖) 决定提交时机
#
# 用法:
#   async with AsyncSessionLocal() as session:
#       repo = TrendRepository(session)
#       orm = await repo.save_signal(signal)
#       await session.commit()
# ==============================================================================

"""
数据库仓储层模块。

提供三个仓储类, 封装 TrendSignalORM / ProductIdeaCardORM / MarketProbeResultORM
的持久化与查询操作。所有方法均为异步, 基于 SQLAlchemy AsyncSession。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from shared.models import ProductIdeaCard, TrendSignal
from shared.orm_models import (
    MarketProbeResultORM,
    ProductIdeaCardORM,
    TrendSignalORM,
)

try:
    from loguru import logger
except ImportError:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)  # type: ignore[assignment]


# ==============================================================================
# 仓储 1: TrendRepository - 趋势信号仓储
# ==============================================================================


class TrendRepository:
    """趋势信号仓储 - 封装 TrendSignalORM 的持久化与查询。

    方法:
        - save_signal(signal)         : 保存一条趋势信号 (Pydantic -> ORM)
        - get_signals_by_topic(topic) : 按 topic 查询信号列表
        - get_all_signals()           : 查询全部信号
        - get_topics()                : 获取所有 topic (去重)

    用法:
        async with AsyncSessionLocal() as session:
            repo = TrendRepository(session)
            orm = await repo.save_signal(signal)
            await session.commit()
    """

    def __init__(self, session: AsyncSession) -> None:
        """初始化仓储。

        参数:
            session: SQLAlchemy 异步会话
        """
        self.session = session

    async def save_signal(self, signal: TrendSignal) -> TrendSignalORM:
        """保存一条趋势信号 (Pydantic -> ORM)。

        采用追加插入语义 (与 TrendStore.add_signal 行为一致):
        每次调用都插入一条新记录, 同一 topic 可含多个区域信号。
        同一 (topic, region) 的去重由调用方决定 (如 collect 时先清理)。

        参数:
            signal: Pydantic TrendSignal 实例

        返回:
            持久化后的 TrendSignalORM 实例 (含 id / created_at 等)
        """
        data = signal.model_dump()

        orm = TrendSignalORM(
            topic=data["topic"],
            heat_score=data["heatScore"],
            growth_rate=data["growthRate"],
            category=data["category"],
            sentiment=data["sentiment"],
            lifecycle=data["lifecycle"],
            predict_window=data["predictWindow"],
            related_keywords=data["relatedKeywords"],
            source_breakdown=data["sourceBreakdown"],
            region=data["region"],
            z_gen_tags=data["zGenTags"],
            target_audience=data["targetAudience"],
            cross_region_diff=data["crossRegionDiff"],
        )
        self.session.add(orm)
        await self.session.flush()  # 获取 id / created_at 而不提交

        logger.debug(
            f"TrendRepository.save_signal: topic='{signal.topic}', "
            f"region='{signal.region}', id={orm.id}"
        )
        return orm

    async def get_signals_by_topic(self, topic: str) -> List[TrendSignalORM]:
        """按 topic 查询趋势信号列表 (含多区域信号)。

        参数:
            topic: 话题名

        返回:
            TrendSignalORM 列表 (按 created_at 升序)
        """
        stmt = (
            select(TrendSignalORM)
            .where(TrendSignalORM.topic == topic)
            .order_by(TrendSignalORM.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_signals(self) -> List[TrendSignalORM]:
        """查询全部趋势信号。

        返回:
            TrendSignalORM 列表 (按 created_at 升序)
        """
        stmt = select(TrendSignalORM).order_by(TrendSignalORM.created_at.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_topics(self) -> List[str]:
        """获取所有 topic (去重, 保持顺序)。

        返回:
            topic 字符串列表
        """
        stmt = select(TrendSignalORM.topic).distinct().order_by(
            TrendSignalORM.created_at.asc()
        )
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]


# ==============================================================================
# 仓储 2: IdeaCardRepository - 产品创意卡仓储
# ==============================================================================


class IdeaCardRepository:
    """产品创意卡仓储 - 封装 ProductIdeaCardORM 的持久化与查询。

    方法:
        - save_card(card)                  : 保存一张创意卡 (Pydantic -> ORM, upsert)
        - get_cards_by_trend(trend_source) : 按趋势来源查询创意卡
        - get_top_cards(limit=100)         : 按 hit_score 降序获取 Top-N 创意卡
    """

    def __init__(self, session: AsyncSession) -> None:
        """初始化仓储。

        参数:
            session: SQLAlchemy 异步会话
        """
        self.session = session

    async def save_card(self, card: ProductIdeaCard) -> ProductIdeaCardORM:
        """保存一张产品创意卡 (Pydantic -> ORM, upsert)。

        采用 upsert 语义: concept_id 冲突时更新, 否则插入。

        参数:
            card: Pydantic ProductIdeaCard 实例

        返回:
            持久化后的 ProductIdeaCardORM 实例
        """
        data = card.model_dump()

        # ipMatch 为嵌套 IPMatch, 序列化为 dict
        ip_match_dict: Dict[str, Any] = (
            data["ipMatch"] if isinstance(data["ipMatch"], dict) else card.ipMatch.model_dump()
        )

        stmt = (
            pg_insert(ProductIdeaCardORM)
            .values(
                concept_id=data["conceptId"],
                product_name=data["productName"],
                category=data["category"],
                design_desc=data["designDesc"],
                material=data["material"],
                price_range=data["priceRange"],
                ip_match=ip_match_dict,
                selling_points=data["sellingPoints"],
                hit_score=data["hitScore"],
                top_factors=data["topFactors"],
                concept_images=data["conceptImages"],
                trend_source=data["trendSource"],
                z_gen_match_score=data["zGenMatchScore"],
                target_audience=data["targetAudience"],
                region_fit=data["regionFit"],
                agent_trace=data["agentTrace"],
            )
            .on_conflict_do_update(
                index_elements=["concept_id"],
                set_=dict(
                    product_name=data["productName"],
                    category=data["category"],
                    design_desc=data["designDesc"],
                    material=data["material"],
                    price_range=data["priceRange"],
                    ip_match=ip_match_dict,
                    selling_points=data["sellingPoints"],
                    hit_score=data["hitScore"],
                    top_factors=data["topFactors"],
                    concept_images=data["conceptImages"],
                    trend_source=data["trendSource"],
                    z_gen_match_score=data["zGenMatchScore"],
                    target_audience=data["targetAudience"],
                    region_fit=data["regionFit"],
                    agent_trace=data["agentTrace"],
                ),
            )
            .returning(ProductIdeaCardORM)
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one()

        logger.debug(
            f"IdeaCardRepository.save_card: concept_id='{card.conceptId}', "
            f"hit_score={card.hitScore}, id={row.id}"
        )
        return row

    async def get_cards_by_trend(self, trend_source: str) -> List[ProductIdeaCardORM]:
        """按趋势来源查询创意卡列表。

        参数:
            trend_source: 关联的 TrendSignal 话题名

        返回:
            ProductIdeaCardORM 列表 (按 hit_score 降序)
        """
        stmt = (
            select(ProductIdeaCardORM)
            .where(ProductIdeaCardORM.trend_source == trend_source)
            .order_by(ProductIdeaCardORM.hit_score.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_top_cards(self, limit: int = 100) -> List[ProductIdeaCardORM]:
        """按 hit_score 降序获取 Top-N 创意卡。

        参数:
            limit: 返回的最大数量 (默认 100)

        返回:
            ProductIdeaCardORM 列表 (按 hit_score 降序)
        """
        stmt = (
            select(ProductIdeaCardORM)
            .order_by(ProductIdeaCardORM.hit_score.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


# ==============================================================================
# 仓储 3: MarketProbeRepository - MarketProbe 结果仓储
# ==============================================================================


class MarketProbeRepository:
    """MarketProbe 验证结果仓储 - 封装 MarketProbeResultORM 的持久化与查询。

    方法:
        - save_result(step, product_name, payload) : 保存步骤结果 (upsert)
        - get_result(step, product_name)           : 按步骤+产品查询结果
        - get_all_results(step)                    : 按步骤查询全部结果

    step 取值:
        - 'test_plan'  : 测试计划
        - 'simulation' : 模拟数据
        - 'analysis'   : 分析结果
    """

    def __init__(self, session: AsyncSession) -> None:
        """初始化仓储。

        参数:
            session: SQLAlchemy 异步会话
        """
        self.session = session

    async def save_result(
        self, step: str, product_name: str, payload: Dict[str, Any]
    ) -> MarketProbeResultORM:
        """保存 MarketProbe 步骤结果 (upsert 语义)。

        采用 check-then-update-or-insert 语义 (与 MarketProbeStore 覆盖行为一致):
        (step, product_name) 已存在则更新 payload, 否则插入新记录。

        参数:
            step: 步骤标识 (test_plan | simulation | analysis)
            product_name: 产品名称
            payload: 步骤结果载荷 (JSON 可序列化 dict)

        返回:
            持久化后的 MarketProbeResultORM 实例
        """
        # 先查询是否已存在
        sel = select(MarketProbeResultORM).where(
            MarketProbeResultORM.step == step,
            MarketProbeResultORM.product_name == product_name,
        )
        existing_result = await self.session.execute(sel)
        existing = existing_result.scalar_one_or_none()

        if existing is not None:
            # 已存在: 更新 payload
            existing.payload = payload
            await self.session.flush()
            logger.debug(
                f"MarketProbeRepository.save_result (update): step='{step}', "
                f"product_name='{product_name}', id={existing.id}"
            )
            return existing

        # 不存在: 插入新记录
        orm = MarketProbeResultORM(
            step=step,
            product_name=product_name,
            payload=payload,
        )
        self.session.add(orm)
        await self.session.flush()

        logger.debug(
            f"MarketProbeRepository.save_result (insert): step='{step}', "
            f"product_name='{product_name}', id={orm.id}"
        )
        return orm

    async def get_result(
        self, step: str, product_name: str
    ) -> Optional[MarketProbeResultORM]:
        """按步骤+产品查询结果。

        参数:
            step: 步骤标识
            product_name: 产品名称

        返回:
            MarketProbeResultORM 实例, 不存在时返回 None
        """
        stmt = select(MarketProbeResultORM).where(
            MarketProbeResultORM.step == step,
            MarketProbeResultORM.product_name == product_name,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_results(self, step: str) -> List[MarketProbeResultORM]:
        """按步骤查询全部结果。

        参数:
            step: 步骤标识

        返回:
            MarketProbeResultORM 列表 (按 created_at 升序)
        """
        stmt = (
            select(MarketProbeResultORM)
            .where(MarketProbeResultORM.step == step)
            .order_by(MarketProbeResultORM.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = [
    "TrendRepository",
    "IdeaCardRepository",
    "MarketProbeRepository",
]
