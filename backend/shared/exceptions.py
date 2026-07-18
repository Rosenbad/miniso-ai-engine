# ==============================================================================
# 共享模块 - 统一异常体系 (异常处理收窄改进)
# ==============================================================================
# 为三服务 (TrendPulse / IdeaForge / MarketProbe) 提供统一的异常基类与
# 业务异常子类, 配合 shared.error_handler 全局异常处理器, 实现:
#   1. 路由层不再将底层 str(exc) 直接暴露给客户端 (安全)
#   2. 统一 JSON 响应格式 { "error": { code, message, status, details? } }
#   3. 4xx 业务错误记 info, 5xx 系统错误记 error + traceback
#
# 异常层级:
#     AppError (基类)
#     ├── BusinessError (4xx, 可预期业务错误)
#     │   ├── ValidationError (422, 输入校验失败)
#     │   ├── NotFoundError (404, 资源不存在)
#     │   └── ConflictError (409, 状态冲突)
#     ├── ServiceUnavailableError (503, 依赖服务不可用)
#     └── InternalError (500, 不可预期系统错误)
# ==============================================================================

"""
统一异常体系 — MINISO AI 引擎。

异常层级::

    AppError (基类)
    ├── BusinessError (4xx, 可预期业务错误)
    │   ├── ValidationError (422, 输入校验失败)
    │   ├── NotFoundError (404, 资源不存在)
    │   └── ConflictError (409, 状态冲突)
    ├── ServiceUnavailableError (503, 依赖服务不可用)
    └── InternalError (500, 不可预期系统错误)

用法::

    from shared.exceptions import InternalError, ValidationError

    # 路由层捕获底层异常后包装为 InternalError
    try:
        ...
    except Exception as exc:
        raise InternalError(detail="处理请求时发生内部错误") from exc

    # 业务校验失败
    if not valid:
        raise ValidationError(detail="heatScore 必须在 0-100 之间")
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class AppError(Exception):
    """所有应用异常的基类。

    属性:
        status_code : HTTP 状态码 (子类覆盖)
        error_code  : 业务错误码字符串 (子类覆盖)
        detail      : 面向用户的错误描述 (子类覆盖)
        extra       : 附加细节字典 (可选, 透传到响应 details 字段)

    参数:
        detail      : 覆盖默认 detail
        error_code  : 覆盖默认 error_code
        status_code : 覆盖默认 status_code
        extra       : 附加细节 (如字段级错误信息)
    """

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    detail: str = "内部服务器错误"

    def __init__(
        self,
        detail: Optional[str] = None,
        error_code: Optional[str] = None,
        status_code: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.detail = detail or self.__class__.detail
        self.error_code = error_code or self.__class__.error_code
        self.status_code = status_code or self.__class__.status_code
        self.extra = extra or {}
        super().__init__(self.detail)


class BusinessError(AppError):
    """业务错误 (4xx)，可预期的客户端错误。

    用于输入校验、资源不存在、状态冲突等业务可预期场景。
    日志级别: info (不打扰运维)。
    """

    status_code = 400
    error_code = "BUSINESS_ERROR"
    detail = "业务处理失败"


class ValidationError(BusinessError):
    """输入校验失败 (422)。

    用于请求参数不合法、字段缺失、值越界等场景。
    """

    status_code = 422
    error_code = "VALIDATION_ERROR"
    detail = "输入参数校验失败"


class NotFoundError(BusinessError):
    """资源不存在 (404)。

    用于请求的资源 ID 在系统中不存在时。
    """

    status_code = 404
    error_code = "NOT_FOUND"
    detail = "请求的资源不存在"


class ConflictError(BusinessError):
    """状态冲突 (409)。

    用于资源状态不允许当前操作时 (如重复创建、状态机非法迁移)。
    """

    status_code = 409
    error_code = "CONFLICT"
    detail = "资源状态冲突"


class ServiceUnavailableError(AppError):
    """依赖服务不可用 (503)。

    用于下游依赖 (Redis / DB / 第三方 API) 不可用时。
    区别于 InternalError: 503 表示临时性故障, 客户端可重试。
    """

    status_code = 503
    error_code = "SERVICE_UNAVAILABLE"
    detail = "依赖服务暂时不可用"


class InternalError(AppError):
    """不可预期系统错误 (500)，不应暴露内部细节。

    用于路由层捕获底层未知异常后的统一包装。
    ``detail`` 应为面向用户的通用提示, 底层异常信息通过 ``from exc`` 保留在
    异常链中, 仅供日志查看, 不会进入响应体。
    """

    status_code = 500
    error_code = "INTERNAL_ERROR"
    detail = "内部服务器错误"


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = [
    "AppError",
    "BusinessError",
    "ValidationError",
    "NotFoundError",
    "ConflictError",
    "ServiceUnavailableError",
    "InternalError",
]
