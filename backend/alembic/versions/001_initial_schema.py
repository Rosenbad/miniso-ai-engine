# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 初始数据库 Schema 迁移
# ==============================================================================
# 创建 3 张核心业务表:
#   1. trend_signals        - 趋势信号 (TrendPulse 数据感知层)
#   2. product_idea_cards   - 产品创意卡 (IdeaForge 决策推理层)
#   3. marketprobe_results  - MarketProbe 验证结果 (验证反馈层)
#
# 索引策略:
#   - trend_signals:        topic, region (高频查询 + 跨区域对比)
#   - product_idea_cards:   concept_id (唯一), hit_score (Top-N), trend_source (按趋势筛选)
#   - marketprobe_results:  step, product_name (按步骤+产品定位)
#
# 运行:
#   cd backend
#   alembic upgrade 001     # 升级到此版本
#   alembic downgrade 001   # 回滚到此版本 (从更高版本)
# ==============================================================================

"""初始数据库 schema: 创建 trend_signals / product_idea_cards / marketprobe_results 三张表。

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# ==============================================================================
# 版本标识
# ==============================================================================
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ==============================================================================
# 工具函数: 创建 PostgreSQL UUID 默认值表达式
# ==============================================================================
def _uuid_default() -> sa.text:
    """PostgreSQL 端 UUID 默认值表达式 (gen_random_uuid)。

    使用 gen_random_uuid() (PostgreSQL 13+ 内置),
    兼容性优于 uuid_generate_v4() (需 uuid-ossp 扩展)。
    """
    return sa.text("gen_random_uuid()")


# ==============================================================================
# 升级: 创建表与索引
# ==============================================================================
def upgrade() -> None:
    """创建 3 张核心业务表及相关索引。"""

    # ------------------------------------------------------------------
    # 表 1: trend_signals (趋势信号)
    # ------------------------------------------------------------------
    op.create_table(
        "trend_signals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=_uuid_default(),
            nullable=False,
            comment="主键 UUID",
        ),
        sa.Column("topic", sa.String(256), nullable=False, comment="话题名"),
        sa.Column("heat_score", sa.Float, nullable=False, comment="0-100 热度分"),
        sa.Column("growth_rate", sa.Float, nullable=False, comment="周环比增长率"),
        sa.Column("category", sa.String(128), nullable=False, comment="品类"),
        sa.Column("sentiment", sa.Float, nullable=False, comment="-1~1 情感倾向"),
        sa.Column("lifecycle", sa.String(32), nullable=False, comment="生命周期阶段"),
        sa.Column("predict_window", sa.String(64), nullable=False, comment="预计窗口期"),
        sa.Column(
            "related_keywords",
            sa.JSON,
            nullable=False,
            server_default=sa.text("'[]'"),
            comment="关联关键词列表",
        ),
        sa.Column(
            "source_breakdown",
            sa.JSON,
            nullable=False,
            server_default=sa.text("'{}'"),
            comment="来源分布",
        ),
        sa.Column("region", sa.String(32), nullable=False, comment="区域标识"),
        sa.Column(
            "z_gen_tags",
            sa.JSON,
            nullable=False,
            server_default=sa.text("'[]'"),
            comment="Z 世代审美标签",
        ),
        sa.Column(
            "target_audience",
            sa.JSON,
            nullable=False,
            server_default=sa.text("'{}'"),
            comment="受众画像",
        ),
        sa.Column(
            "cross_region_diff",
            sa.JSON,
            nullable=False,
            server_default=sa.text("'{}'"),
            comment="跨区域热度差",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="更新时间",
        ),
        comment="TrendPulse 趋势信号表",
    )

    # 索引: trend_signals
    op.create_index("ix_trend_signals_topic", "trend_signals", ["topic"])
    op.create_index("ix_trend_signals_region", "trend_signals", ["region"])
    # 复合索引: 按 topic + region 查询 (跨区域对比常用)
    op.create_index(
        "ix_trend_signals_topic_region",
        "trend_signals",
        ["topic", "region"],
    )

    # ------------------------------------------------------------------
    # 表 2: product_idea_cards (产品创意卡)
    # ------------------------------------------------------------------
    op.create_table(
        "product_idea_cards",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=_uuid_default(),
            nullable=False,
            comment="主键 UUID",
        ),
        sa.Column("concept_id", sa.String(64), nullable=False, comment="创意 ID (业务唯一键)"),
        sa.Column("product_name", sa.String(256), nullable=False, comment="产品名称"),
        sa.Column("category", sa.String(128), nullable=False, comment="品类"),
        sa.Column("design_desc", sa.Text, nullable=False, comment="设计描述"),
        sa.Column("material", sa.String(128), nullable=False, comment="材质"),
        sa.Column("price_range", sa.String(64), nullable=False, comment="价格区间"),
        sa.Column(
            "ip_match",
            sa.JSON,
            nullable=False,
            server_default=sa.text("'{}'"),
            comment="IP 联名匹配结果",
        ),
        sa.Column(
            "selling_points",
            sa.JSON,
            nullable=False,
            server_default=sa.text("'[]'"),
            comment="核心卖点列表",
        ),
        sa.Column("hit_score", sa.Float, nullable=False, comment="爆品概率 0-1"),
        sa.Column(
            "top_factors",
            sa.JSON,
            nullable=False,
            server_default=sa.text("'[]'"),
            comment="Top-3 影响因子",
        ),
        sa.Column(
            "concept_images",
            sa.JSON,
            nullable=False,
            server_default=sa.text("'[]'"),
            comment="概念图 URL 列表",
        ),
        sa.Column("trend_source", sa.String(256), nullable=False, comment="趋势来源引用"),
        sa.Column("z_gen_match_score", sa.Float, nullable=False, comment="Z 世代匹配度 0-1"),
        sa.Column(
            "target_audience",
            sa.JSON,
            nullable=False,
            server_default=sa.text("'{}'"),
            comment="受众画像",
        ),
        sa.Column(
            "region_fit",
            sa.JSON,
            nullable=False,
            server_default=sa.text("'{}'"),
            comment="区域适配度",
        ),
        sa.Column(
            "agent_trace",
            sa.JSON,
            nullable=False,
            server_default=sa.text("'[]'"),
            comment="决策链路可追溯",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="更新时间",
        ),
        comment="IdeaForge 产品创意卡表",
    )

    # 索引: product_idea_cards
    op.create_index(
        "ix_product_idea_cards_concept_id",
        "product_idea_cards",
        ["concept_id"],
        unique=True,
    )
    op.create_index("ix_product_idea_cards_hit_score", "product_idea_cards", ["hit_score"])
    op.create_index(
        "ix_product_idea_cards_trend_source",
        "product_idea_cards",
        ["trend_source"],
    )

    # ------------------------------------------------------------------
    # 表 3: marketprobe_results (MarketProbe 验证结果)
    # ------------------------------------------------------------------
    op.create_table(
        "marketprobe_results",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=_uuid_default(),
            nullable=False,
            comment="主键 UUID",
        ),
        sa.Column("step", sa.String(32), nullable=False, comment="步骤: test_plan|simulation|analysis"),
        sa.Column("product_name", sa.String(256), nullable=False, comment="产品名称"),
        sa.Column(
            "payload",
            sa.JSON,
            nullable=False,
            server_default=sa.text("'{}'"),
            comment="步骤结果载荷 (JSON)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="更新时间",
        ),
        comment="MarketProbe 验证结果表",
    )

    # 索引: marketprobe_results
    op.create_index("ix_marketprobe_results_step", "marketprobe_results", ["step"])
    op.create_index(
        "ix_marketprobe_results_product_name",
        "marketprobe_results",
        ["product_name"],
    )
    # 复合索引: 按 step + product_name 定位 (常用查询)
    op.create_index(
        "ix_marketprobe_results_step_product_name",
        "marketprobe_results",
        ["step", "product_name"],
    )


# ==============================================================================
# 降级: 回滚表与索引
# ==============================================================================
def downgrade() -> None:
    """回滚初始 schema: 删除 3 张表及相关索引。"""

    # 表 3: marketprobe_results
    op.drop_index("ix_marketprobe_results_step_product_name", table_name="marketprobe_results")
    op.drop_index("ix_marketprobe_results_product_name", table_name="marketprobe_results")
    op.drop_index("ix_marketprobe_results_step", table_name="marketprobe_results")
    op.drop_table("marketprobe_results")

    # 表 2: product_idea_cards
    op.drop_index("ix_product_idea_cards_trend_source", table_name="product_idea_cards")
    op.drop_index("ix_product_idea_cards_hit_score", table_name="product_idea_cards")
    op.drop_index("ix_product_idea_cards_concept_id", table_name="product_idea_cards")
    op.drop_table("product_idea_cards")

    # 表 1: trend_signals
    op.drop_index("ix_trend_signals_topic_region", table_name="trend_signals")
    op.drop_index("ix_trend_signals_region", table_name="trend_signals")
    op.drop_index("ix_trend_signals_topic", table_name="trend_signals")
    op.drop_table("trend_signals")
