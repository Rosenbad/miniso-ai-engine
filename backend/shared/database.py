# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 数据库连接 (SQLAlchemy 异步)
# ==============================================================================
# 功能:
#   1. 从环境变量 DATABASE_URL 读取数据库连接字符串
#   2. 自动将同步 URL (postgresql://) 转为异步 URL (postgresql+asyncpg://)
#   3. 创建异步引擎 (AsyncEngine) 与异步会话工厂 (async_sessionmaker)
#   4. 提供 get_db() 异步生成器，作为 FastAPI 依赖注入
#   5. 提供 Base 声明式基类，供后续 ORM 模型继承
# ==============================================================================

"""
SQLAlchemy 异步数据库连接模块。

核心导出:
    - engine            : AsyncEngine 实例
    - AsyncSessionLocal : async_sessionmaker 会话工厂
    - Base              : DeclarativeBase 声明式基类
    - get_db()          : FastAPI 异步依赖，yield AsyncSession
    - init_db()         : 异步初始化数据库 (创建所有表)

设计要点:
    - 使用 asyncpg 驱动 (PostgreSQL 异步驱动)
    - 连接池参数可调 (pool_size / max_overflow / pool_recycle)
    - 自动 URL 协议转换，兼容 .env 中写同步 URL 的场景
"""

from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

try:
    from loguru import logger
except ImportError:  # loguru 尚未安装时降级为标准 logging
    import logging

    logger = logging.getLogger(__name__)  # type: ignore[assignment]


# ==============================================================================
# 环境变量读取
# ==============================================================================

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://miniso:miniso@localhost:5432/miniso_ai",
)


# ==============================================================================
# URL 协议转换: 同步 -> 异步
# ==============================================================================
# .env.example 中 DATABASE_URL=postgresql://...
# SQLAlchemy 异步引擎需要 postgresql+asyncpg://...


def _convert_to_async_url(url: str) -> str:
    """
    将同步 PostgreSQL URL 转为异步 asyncpg URL。

    转换规则:
        postgresql://      -> postgresql+asyncpg://
        postgresql+psycopg2:// -> postgresql+asyncpg://
        postgresql+asyncpg://  -> (保持不变)
    """
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    # 非 PostgreSQL URL 原样返回 (如 SQLite 测试场景)
    return url


ASYNC_DATABASE_URL: str = _convert_to_async_url(DATABASE_URL)

logger.debug(f"数据库连接 URL (脱敏): {ASYNC_DATABASE_URL.split('@')[-1] if '@' in ASYNC_DATABASE_URL else 'N/A'}")


# ==============================================================================
# 异步引擎与会话工厂
# ==============================================================================

# 连接池配置 (生产环境可按需调整)
_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "10"))
_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))
_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "3600"))  # 秒
_POOL_PRE_PING: bool = os.getenv("DB_POOL_PRE_PING", "true").lower() == "true"

engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,  # 生产环境关闭 SQL 日志；调试时设为 True
    pool_size=_POOL_SIZE,
    max_overflow=_MAX_OVERFLOW,
    pool_recycle=_POOL_RECYCLE,
    pool_pre_ping=_POOL_PRE_PING,
    future=True,
)

# 异步会话工厂
# expire_on_commit=False: 提交后不过期，避免异步会话中访问属性触发隐式 IO
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ==============================================================================
# 声明式基类
# ==============================================================================


class Base(DeclarativeBase):
    """
    SQLAlchemy 2.0 声明式基类。

    所有 ORM 模型应继承此类:
        class TrendSignalORM(Base):
            __tablename__ = "trend_signals"
            ...
    """

    pass


# ==============================================================================
# FastAPI 依赖注入: get_db()
# ==============================================================================


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 异步数据库依赖。

    用法:
        @app.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()

    行为:
        - 每次请求创建一个独立 AsyncSession
        - 请求结束后自动关闭会话
        - 发生异常时自动回滚
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            # 由业务层决定是否 commit (调用 await db.commit())
        except Exception:
            await session.rollback()
            raise
        # 注意: 无需在此显式调用 session.close()。
        # `async with AsyncSessionLocal() as session:` 上下文管理器退出时
        # 会自动关闭会话 (调用 session.close())，重复调用是冗余的。


# ==============================================================================
# 数据库初始化 (开发/测试用)
# ==============================================================================


async def init_db() -> None:
    """
    初始化数据库 - 创建 Base.metadata 中定义的所有表。

    注意: 此函数仅用于开发/测试环境。
    生产环境应使用 Alembic 迁移 (alembic upgrade head)。
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("数据库表已创建 (dev/test 模式)")


async def close_db() -> None:
    """关闭数据库引擎连接池 (应用关闭时调用)。"""
    await engine.dispose()
    logger.info("数据库连接池已关闭")


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = [
    "DATABASE_URL",
    "ASYNC_DATABASE_URL",
    "engine",
    "AsyncSessionLocal",
    "Base",
    "get_db",
    "init_db",
    "close_db",
]
