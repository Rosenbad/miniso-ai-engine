# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 采集器公共工具 (Task 4 修复)
# ==============================================================================
# 本模块抽取各数据源采集器 (xiaohongshu / douyin / ecommerce / search_index)
# 重复定义的公共辅助函数与日志初始化逻辑, 消除代码重复 (DRY)。
#
# 提供内容:
#   1. safe_int(value, default=0)    - 安全 int 转换 (处理 None / "" / 非数字)
#   2. safe_float(value, default=0.0) - 安全 float 转换
#   3. setup_logger(name)            - 统一 loguru / logging 降级导入模式
# ==============================================================================

"""
采集器公共工具模块。

抽取自 4 个采集器中重复定义的辅助函数与日志初始化模式,
统一维护, 避免代码漂移。

函数:
    safe_int     - 安全 int 转换, 失败返回 default
    safe_float   - 安全 float 转换, 失败返回 default
    setup_logger - loguru 优先, 缺失时降级为标准 logging
"""

from __future__ import annotations

from typing import Any


# ==============================================================================
# 安全类型转换
# ==============================================================================


def safe_int(value: Any, default: int = 0) -> int:
    """安全转换为 int, 失败时返回 default。

    处理 None / 空字符串 / 非数字字符串等异常输入。

    参数:
        value   : 待转换的值
        default : 转换失败时的默认返回值

    返回:
        转换后的 int, 或 default

    用例::

        >>> safe_int("100")
        100
        >>> safe_int(None)
        0
        >>> safe_int("", default=-1)
        -1
        >>> safe_int("abc")
        0
    """
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """安全转换为 float, 失败时返回 default。

    处理 None / 空字符串 / 非数字字符串等异常输入。

    参数:
        value   : 待转换的值
        default : 转换失败时的默认返回值

    返回:
        转换后的 float, 或 default

    用例::

        >>> safe_float("29.9")
        29.9
        >>> safe_float(None)
        0.0
        >>> safe_float("abc", default=-1.0)
        -1.0
    """
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


# ==============================================================================
# 日志初始化
# ==============================================================================


def setup_logger(name: str) -> Any:
    """初始化日志器, 优先使用 loguru, 缺失时降级为标准 logging。

    抽取自 4 个采集器中重复出现的 try/except import 模式::

        try:
            from loguru import logger
        except ImportError:
            import logging
            logger = logging.getLogger(__name__)

    参数:
        name : 日志器名称 (通常传 ``__name__``), 仅在 loguru 缺失时
               降级路径中使用, loguru 全局单例忽略该参数

    返回:
        loguru.logger 或 logging.Logger 实例
    """
    try:
        from loguru import logger

        return logger
    except ImportError:  # pragma: no cover - loguru 缺失时降级
        import logging

        return logging.getLogger(name)


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["safe_int", "safe_float", "setup_logger"]
