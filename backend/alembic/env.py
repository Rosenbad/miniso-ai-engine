# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - Alembic 迁移环境
# ==============================================================================
# 功能:
#   1. 从环境变量 DATABASE_URL 读取连接串 (与运行时一致)
#   2. 将异步 URL (postgresql+asyncpg://) 转为同步 URL (postgresql://)
#      以便使用 psycopg2 同步驱动执行迁移
#   3. 导入 shared.orm_models 以便 Alembic autogenerate 检测到 ORM 模型
#   4. 设置 target_metadata = Base.metadata 用于 autogenerate 对比
#
# 运行迁移:
#   cd backend
#   export DATABASE_URL=postgresql://miniso:miniso@localhost:5432/miniso_ai
#   alembic upgrade head
# ==============================================================================

"""
Alembic 迁移环境配置。

从环境变量 DATABASE_URL 读取连接串, 使用 psycopg2 同步驱动执行迁移。
导入 shared.orm_models 以便 autogenerate 能检测到所有 ORM 模型。
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# ==============================================================================
# 将 backend/ 目录加入 sys.path, 使 shared.* 等绝对导入可用
# ==============================================================================
# env.py 位于 backend/alembic/env.py, 需要回退一级到 backend/
_BACKEND_DIR = str(Path(__file__).resolve().parent.parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# ==============================================================================
# 导入 ORM 模型, 确保 Base.metadata 中注册了所有表
# ==============================================================================
# 必须在设置 target_metadata 之前导入, 否则 autogenerate 检测不到表
from shared.database import Base  # noqa: E402
from shared import orm_models  # noqa: F401, E402  # 导入即注册 ORM 模型到 Base.metadata

try:
    from loguru import logger
except ImportError:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)  # type: ignore[assignment]


# ==============================================================================
# Alembic 配置对象
# ==============================================================================
config = context.config

# 日志配置 (若 alembic.ini 中存在 [loggers] 段)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# ==============================================================================
# 从环境变量注入同步数据库 URL
# ==============================================================================
def _resolve_sync_url() -> str:
    """从环境变量 DATABASE_URL 读取并转为 psycopg2 同步 URL。

    转换规则:
        - postgresql+asyncpg://  -> postgresql://  (异步 -> 同步)
        - postgresql+psycopg2:// -> 保持不变
        - postgresql://          -> 保持不变
        - 其他                   -> 原样返回

    若环境变量未设置, 使用默认本地连接串。
    """
    url = os.getenv(
        "DATABASE_URL",
        "postgresql://miniso:miniso@localhost:5432/miniso_ai",
    )

    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    # psycopg2 同步驱动: postgresql:// 即可 (psycopg2 是默认驱动)

    return url


SYNC_DATABASE_URL = _resolve_sync_url()
config.set_main_option("sqlalchemy.url", SYNC_DATABASE_URL)

logger.debug(
    f"Alembic 使用同步 URL (脱敏): "
    f"{SYNC_DATABASE_URL.split('@')[-1] if '@' in SYNC_DATABASE_URL else 'N/A'}"
)


# ==============================================================================
# target_metadata - 用于 autogenerate 对比
# ==============================================================================
target_metadata = Base.metadata


# ==============================================================================
# 离线模式 (offline) - 生成 SQL 脚本而不连接数据库
# ==============================================================================
def run_migrations_offline() -> None:
    """离线模式: 生成 SQL 脚本, 不连接数据库。

    适用于 CI/CD 环境, 将 SQL 脚本交给 DBA 执行。
    """
    context.configure(
        url=SYNC_DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ==============================================================================
# 在线模式 (online) - 连接数据库执行迁移
# ==============================================================================
def run_migrations_online() -> None:
    """在线模式: 连接数据库执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


# ==============================================================================
# 入口: 根据模式选择离线/在线
# ==============================================================================
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
