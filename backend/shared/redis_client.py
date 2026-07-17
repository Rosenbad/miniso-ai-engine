# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - Redis 客户端 (异步)
# ==============================================================================
# 功能:
#   1. 从环境变量 REDIS_URL 读取 Redis 连接字符串
#   2. 创建异步 Redis 连接池 (redis.asyncio)
#   3. 提供 get_redis() 异步生成器，作为 FastAPI 依赖注入
#   4. 提供全局 Redis 客户端单例，供非依赖注入场景使用
# ==============================================================================

"""
异步 Redis 客户端模块。

核心导出:
    - get_redis()     : FastAPI 异步依赖，yield Redis 实例
    - get_redis_client() : 获取全局 Redis 客户端单例 (非依赖注入场景)
    - close_redis()   : 关闭连接池 (应用关闭时调用)
    - _redis_pool     : 底层连接池 (模块级单例)

设计要点:
    - 使用 redis.asyncio (Redis 5.x 内置异步支持)
    - 连接池配置可调 (max_connections)
    - 支持健康检查 ping
    - 自动解码 (decode_responses=True)，返回 str 而非 bytes
"""

from __future__ import annotations

import os
from typing import Optional

import redis.asyncio as aioredis
from redis.asyncio.connection import ConnectionPool

try:
    from loguru import logger
except ImportError:  # loguru 尚未安装时降级为标准 logging
    import logging

    logger = logging.getLogger(__name__)  # type: ignore[assignment]


# ==============================================================================
# 环境变量读取
# ==============================================================================

REDIS_URL: str = os.getenv(
    "REDIS_URL",
    "redis://localhost:6379/0",
)

# 连接池最大连接数
_REDIS_MAX_CONNECTIONS: int = int(os.getenv("REDIS_MAX_CONNECTIONS", "50"))
# 连接超时 (秒)
_REDIS_SOCKET_TIMEOUT: float = float(os.getenv("REDIS_SOCKET_TIMEOUT", "5.0"))
# 健康检查间隔 (秒)
_REDIS_HEALTH_CHECK_INTERVAL: int = int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30"))


# ==============================================================================
# 连接池 (模块级单例)
# ==============================================================================

_redis_pool: ConnectionPool = ConnectionPool.from_url(
    REDIS_URL,
    max_connections=_REDIS_MAX_CONNECTIONS,
    socket_timeout=_REDIS_SOCKET_TIMEOUT,
    socket_connect_timeout=_REDIS_SOCKET_TIMEOUT,
    health_check_interval=_REDIS_HEALTH_CHECK_INTERVAL,
    decode_responses=True,  # 自动解码为 str，避免手动 decode bytes
    encoding="utf-8",
)

logger.debug(
    f"Redis 连接池已创建: {REDIS_URL.split('@')[-1] if '@' in REDIS_URL else REDIS_URL}"
)


# ==============================================================================
# 全局 Redis 客户端单例
# ==============================================================================

# 模块级单例，延迟初始化
_redis_client: Optional[aioredis.Redis] = None


def get_redis_client() -> aioredis.Redis:
    """
    获取全局 Redis 客户端单例。

    适用于 Celery 任务、后台脚本等非 FastAPI 依赖注入场景。

    用法:
        from shared.redis_client import get_redis_client
        rds = get_redis_client()
        await rds.set("key", "value")
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.Redis(connection_pool=_redis_pool)
    return _redis_client


# ==============================================================================
# FastAPI 依赖注入: get_redis()
# ==============================================================================


async def get_redis() -> aioredis.Redis:
    """
    FastAPI 异步 Redis 依赖。

    用法:
        @app.get("/cache")
        async def get_cache(rds: Redis = Depends(get_redis)):
            value = await rds.get("my_key")
            return {"value": value}

    行为:
        - 复用模块级连接池 (不每次新建连接)
        - 返回 Redis 客户端实例
        - 连接由连接池统一管理，无需手动关闭
    """
    return get_redis_client()


# ==============================================================================
# 健康检查
# ==============================================================================


async def ping() -> bool:
    """
    Redis 连接健康检查。

    返回:
        True  - 连接正常
        False - 连接异常
    """
    try:
        client = get_redis_client()
        return await client.ping()
    except Exception as e:
        logger.error(f"Redis 健康检查失败: {e}")
        return False


# ==============================================================================
# 清理函数 (应用关闭时调用)
# ==============================================================================


async def close_redis() -> None:
    """关闭 Redis 连接池 (应用关闭时调用)。"""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
    await _redis_pool.disconnect()
    logger.info("Redis 连接池已关闭")


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = [
    "REDIS_URL",
    "get_redis",
    "get_redis_client",
    "ping",
    "close_redis",
    "_redis_pool",
]
