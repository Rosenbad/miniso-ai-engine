# ==============================================================================
# 共享模块 - 全局异常处理器 (异常处理收窄改进)
# ==============================================================================
# 将 AppError 及未捕获的 Exception 转换为统一 JSON 响应格式, 配合
# shared.exceptions 统一异常体系使用, 实现:
#   1. 统一 JSON 响应格式 { "error": { code, message, status, details? } }
#   2. 4xx 业务错误记 info, 5xx 系统错误记 error + 完整 traceback
#   3. 未捕获的 Exception 兜底为 500, 不暴露内部细节 (安全)
#
# 注册方式:
#   from shared.error_handler import register_error_handlers
#   register_error_handlers(app)
#
# 注意: 必须在 app.include_router(...) 之前调用, 以确保异常处理器注册到位。
# ==============================================================================

"""
全局异常处理 — 将 AppError 转换为统一 JSON 响应格式。

注册方式::

    from fastapi import FastAPI
    from shared.error_handler import register_error_handlers

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router)

统一响应格式::

    {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "heatScore 必须在 0-100 之间",
            "status": 422,
            "details": { ... }   # 可选, 仅当 extra 非空时
        }
    }
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from shared.exceptions import AppError
from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """为 FastAPI 应用注册全局异常处理器。

    注册两个异常处理器:
        1. ``AppError`` 处理器: 将业务异常转换为统一 JSON 响应
           - 4xx (BusinessError 子类): 记 info 级别日志
           - 5xx (InternalError / ServiceUnavailableError): 记 error + traceback
        2. ``Exception`` 兜底处理器: 未捕获的异常统一返回 500 + 通用消息
           - 不暴露内部细节 (安全)
           - 记 error + 完整 traceback (调试)

    参数:
        app: FastAPI 应用实例

    注意:
        必须在 ``app.include_router(...)`` 之前调用, 以确保异常处理器
        优先于路由层生效。
    """

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        """处理 AppError 及其子类, 返回统一 JSON 响应。

        - 5xx 错误记 error + 完整 traceback
        - 4xx 错误记 info
        - 响应体含 error.code / message / status, 可选 details
        """
        # BusinessError (4xx) 记录 info 级别
        # InternalError / ServiceUnavailableError (5xx) 记录 error 级别 (含完整 traceback)
        if exc.status_code >= 500:
            logger.error(
                f"[{request.method} {request.url.path}] "
                f"{exc.error_code}: {exc.detail}",
                exc_info=True,
            )
        else:
            logger.info(
                f"[{request.method} {request.url.path}] "
                f"{exc.error_code}: {exc.detail}"
            )

        body: dict = {
            "error": {
                "code": exc.error_code,
                "message": exc.detail,
                "status": exc.status_code,
            }
        }
        if exc.extra:
            body["error"]["details"] = exc.extra
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """兜底处理未捕获的 Exception, 返回 500 + 通用消息。

        - 不暴露内部异常信息 (安全)
        - 记录 error + 完整 traceback (调试)
        """
        logger.error(
            f"[{request.method} {request.url.path}] 未捕获异常: {exc}",
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "内部服务器错误",
                    "status": 500,
                }
            },
        )


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["register_error_handlers"]
