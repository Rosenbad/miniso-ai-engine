# ==============================================================================
# 共享模块 - 跨服务通用工具、配置、数据库连接池等。
# ==============================================================================
# 子模块:
#   - models       : Pydantic 数据模型 (TrendSignal / IPMatch / ProductIdeaCard 等)
#   - database     : SQLAlchemy 异步数据库连接
#   - redis_client : 异步 Redis 客户端
# ==============================================================================

"""共享模块包。

提供跨服务 (TrendPulse / IdeaForge / MarketProbe) 共用的:
    - 数据模型 (shared.models)
    - 数据库连接 (shared.database)
    - Redis 客户端 (shared.redis_client)
"""

__version__ = "0.2.0"

# 延迟导入避免循环依赖，同时提供便捷访问入口
# 使用方仍推荐显式导入: from shared.models import TrendSignal
