# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 全局异常处理器测试 (异常处理收窄改进)
# ==============================================================================
# 测试 shared.error_handler.register_error_handlers 注册的全局异常处理器:
#   1. BusinessError (4xx) 返回正确 status_code + error_code + message
#   2. InternalError (500) 不暴露底层 detail (安全)
#   3. 未捕获 Exception 兜底为 500 + 通用消息
#   4. extra 字段正确透传到响应 details
#   5. ServiceUnavailableError (503) 返回正确状态码
#
# 测试策略:
#   - 构造独立的 FastAPI 测试应用, 注册异常处理器 + 注入触发异常的路由
#   - 使用 fastapi.testclient.TestClient 发起请求, 校验响应状态码与 JSON 体
#   - 不依赖真实业务服务 (TrendPulse / IdeaForge / MarketProbe), 隔离测试
# ==============================================================================

"""
测试全局异常处理器 (shared.error_handler)。

覆盖:
    - BusinessError 子类 (ValidationError / NotFoundError / ConflictError) → 4xx
    - InternalError → 500, 不暴露 detail
    - ServiceUnavailableError → 503
    - 未捕获 Exception → 500 + 通用消息
    - extra 字段透传
    - 异常链 (raise ... from exc) 保留底层异常
"""

from __future__ import annotations

from typing import Any, Dict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.error_handler import register_error_handlers
from shared.exceptions import (
    AppError,
    BusinessError,
    ConflictError,
    InternalError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)


# ==============================================================================
# 测试辅助 - 构造独立的 FastAPI 测试应用
# ==============================================================================


def _make_test_app() -> FastAPI:
    """构造一个注册了异常处理器的测试 FastAPI 应用。

    注入若干触发各类异常的测试路由, 用于验证异常处理器的行为。
    路由设计:
        - GET /raise/validation-error    → raise ValidationError
        - GET /raise/not-found           → raise NotFoundError
        - GET /raise/conflict            → raise ConflictError
        - GET /raise/business            → raise BusinessError
        - GET /raise/internal            → raise InternalError
        - GET /raise/service-unavailable → raise ServiceUnavailableError
        - GET /raise/internal-from       → raise InternalError from RuntimeError
        - GET /raise/unexpected          → raise RuntimeError (未捕获)
        - GET /raise/extra               → raise ValidationError with extra
        - GET /ok                        → 正常返回 200
    """
    app = FastAPI()

    # 注册全局异常处理器 (必须在 include_router 之前)
    register_error_handlers(app)

    @app.get("/ok")
    async def ok() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/raise/validation-error")
    async def raise_validation_error() -> Dict[str, Any]:
        raise ValidationError(detail="heatScore 必须在 0-100 之间")

    @app.get("/raise/not-found")
    async def raise_not_found() -> Dict[str, Any]:
        raise NotFoundError(detail="趋势信号 T-001 不存在")

    @app.get("/raise/conflict")
    async def raise_conflict() -> Dict[str, Any]:
        raise ConflictError(detail="产品已存在, 无法重复创建")

    @app.get("/raise/business")
    async def raise_business() -> Dict[str, Any]:
        raise BusinessError(detail="业务处理失败: 库存不足")

    @app.get("/raise/internal")
    async def raise_internal() -> Dict[str, Any]:
        raise InternalError(detail="处理请求时发生内部错误")

    @app.get("/raise/service-unavailable")
    async def raise_service_unavailable() -> Dict[str, Any]:
        raise ServiceUnavailableError(detail="Redis 连接失败")

    @app.get("/raise/internal-from")
    async def raise_internal_from() -> Dict[str, Any]:
        try:
            # 模拟底层异常
            _ = {"a": 1}["b"]  # KeyError
        except KeyError as exc:
            raise InternalError(detail="处理请求时发生内部错误") from exc

    @app.get("/raise/unexpected")
    async def raise_unexpected() -> Dict[str, Any]:
        # 未被路由层捕获的裸异常, 应被 Exception 兜底处理器捕获
        raise RuntimeError("数据库连接断开: connection refused")

    @app.get("/raise/extra")
    async def raise_extra() -> Dict[str, Any]:
        raise ValidationError(
            detail="输入参数校验失败",
            extra={"fields": ["heatScore", "growthRate"], "reason": "越界"},
        )

    return app


# ==============================================================================
# 1. BusinessError (4xx) 测试
# ==============================================================================


class TestBusinessErrors:
    """业务错误 (4xx) 测试 - 应返回正确状态码与 error_code。"""

    def test_validation_error_returns_422(self) -> None:
        """ValidationError 应返回 422 + VALIDATION_ERROR。"""
        client = TestClient(_make_test_app())
        response = client.get("/raise/validation-error")

        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert body["error"]["status"] == 422
        assert "heatScore" in body["error"]["message"]

    def test_not_found_error_returns_404(self) -> None:
        """NotFoundError 应返回 404 + NOT_FOUND。"""
        client = TestClient(_make_test_app())
        response = client.get("/raise/not-found")

        assert response.status_code == 404
        body = response.json()
        assert body["error"]["code"] == "NOT_FOUND"
        assert body["error"]["status"] == 404
        assert "T-001" in body["error"]["message"]

    def test_conflict_error_returns_409(self) -> None:
        """ConflictError 应返回 409 + CONFLICT。"""
        client = TestClient(_make_test_app())
        response = client.get("/raise/conflict")

        assert response.status_code == 409
        body = response.json()
        assert body["error"]["code"] == "CONFLICT"
        assert body["error"]["status"] == 409
        assert "重复创建" in body["error"]["message"]

    def test_business_error_returns_400(self) -> None:
        """BusinessError 基类应返回 400 + BUSINESS_ERROR。"""
        client = TestClient(_make_test_app())
        response = client.get("/raise/business")

        assert response.status_code == 400
        body = response.json()
        assert body["error"]["code"] == "BUSINESS_ERROR"
        assert body["error"]["status"] == 400
        assert "库存不足" in body["error"]["message"]


# ==============================================================================
# 2. InternalError (500) 测试 - 不暴露底层细节
# ==============================================================================


class TestInternalError:
    """内部错误 (500) 测试 - 应返回通用消息, 不暴露底层异常。"""

    def test_internal_error_returns_500(self) -> None:
        """InternalError 应返回 500 + INTERNAL_ERROR。"""
        client = TestClient(_make_test_app())
        response = client.get("/raise/internal")

        assert response.status_code == 500
        body = response.json()
        assert body["error"]["code"] == "INTERNAL_ERROR"
        assert body["error"]["status"] == 500

    def test_internal_error_message_is_generic(self) -> None:
        """InternalError 响应 message 应为通用提示, 不含底层细节。

        注意: InternalError 的 detail 是开发者显式传入的面向用户消息
        (如 "处理请求时发生内部错误"), 而非底层 str(exc)。
        本测试验证 message 不包含底层异常的敏感信息。
        """
        client = TestClient(_make_test_app())
        response = client.get("/raise/internal-from")

        assert response.status_code == 500
        body = response.json()
        message = body["error"]["message"]
        # 响应体不应包含底层 KeyError 的细节
        assert "KeyError" not in message
        assert "'b'" not in message
        # 应为通用提示
        assert message == "处理请求时发生内部错误"

    def test_internal_error_response_has_unified_format(self) -> None:
        """InternalError 响应应遵循统一 JSON 格式 { error: {code, message, status} }。"""
        client = TestClient(_make_test_app())
        response = client.get("/raise/internal")

        body = response.json()
        assert "error" in body
        error = body["error"]
        assert set(error.keys()) >= {"code", "message", "status"}
        # 不应有 details 字段 (extra 为空)
        assert "details" not in error


# ==============================================================================
# 3. 未捕获 Exception 兜底测试
# ==============================================================================
#
# 注意: FastAPI 将 @app.exception_handler(Exception) 注册的处理器挂载到
# ServerErrorMiddleware 上, 而该中间件在调用处理器发送响应后会 re-raise
# 异常 (便于 TestClient 捕获服务端错误)。因此测试未捕获异常时需设置
# raise_server_exceptions=False, 以便检查实际返回的 JSON 响应体。
# ==============================================================================


class TestUnexpectedException:
    """未捕获的 Exception 应被兜底处理器捕获, 返回 500 + 通用消息。"""

    def test_unexpected_exception_returns_500(self) -> None:
        """未捕获 RuntimeError 应返回 500。"""
        client = TestClient(_make_test_app(), raise_server_exceptions=False)
        response = client.get("/raise/unexpected")

        assert response.status_code == 500

    def test_unexpected_exception_does_not_leak_detail(self) -> None:
        """未捕获异常的响应不应暴露底层异常信息 (安全)。

        底层异常消息 "数据库连接断开: connection refused" 不应出现在响应中。
        """
        client = TestClient(_make_test_app(), raise_server_exceptions=False)
        response = client.get("/raise/unexpected")

        body = response.json()
        message = body["error"]["message"]
        # 不应包含底层异常的敏感信息
        assert "数据库连接断开" not in message
        assert "connection refused" not in message
        assert "RuntimeError" not in message
        # 应为通用提示
        assert message == "内部服务器错误"

    def test_unexpected_exception_has_correct_code(self) -> None:
        """未捕获异常应返回 INTERNAL_ERROR code。"""
        client = TestClient(_make_test_app(), raise_server_exceptions=False)
        response = client.get("/raise/unexpected")

        body = response.json()
        assert body["error"]["code"] == "INTERNAL_ERROR"
        assert body["error"]["status"] == 500


# ==============================================================================
# 4. extra 字段透传测试
# ==============================================================================


class TestExtraField:
    """异常的 extra 字段应正确透传到响应 details。"""

    def test_extra_field_passed_to_response(self) -> None:
        """ValidationError 携带 extra 时, 响应应含 details 字段。"""
        client = TestClient(_make_test_app())
        response = client.get("/raise/extra")

        assert response.status_code == 422
        body = response.json()
        assert "details" in body["error"]
        details = body["error"]["details"]
        assert details["fields"] == ["heatScore", "growthRate"]
        assert details["reason"] == "越界"

    def test_no_details_when_extra_empty(self) -> None:
        """extra 为空时, 响应不应含 details 字段。"""
        client = TestClient(_make_test_app())
        response = client.get("/raise/validation-error")

        body = response.json()
        assert "details" not in body["error"]


# ==============================================================================
# 5. ServiceUnavailableError (503) 测试
# ==============================================================================


class TestServiceUnavailableError:
    """依赖服务不可用 (503) 测试。"""

    def test_service_unavailable_returns_503(self) -> None:
        """ServiceUnavailableError 应返回 503 + SERVICE_UNAVAILABLE。"""
        client = TestClient(_make_test_app())
        response = client.get("/raise/service-unavailable")

        assert response.status_code == 503
        body = response.json()
        assert body["error"]["code"] == "SERVICE_UNAVAILABLE"
        assert body["error"]["status"] == 503
        assert "Redis" in body["error"]["message"]


# ==============================================================================
# 6. 正常请求不受影响测试
# ==============================================================================


class TestNormalRequest:
    """注册异常处理器后, 正常请求应不受影响。"""

    def test_normal_request_returns_200(self) -> None:
        """正常路由应返回 200, 不被异常处理器拦截。"""
        client = TestClient(_make_test_app())
        response = client.get("/ok")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


# ==============================================================================
# 7. 异常类属性测试 (单元测试, 不依赖 FastAPI)
# ==============================================================================


class TestExceptionClasses:
    """异常类属性测试 - 验证默认值与构造参数覆盖。"""

    def test_app_error_defaults(self) -> None:
        """AppError 默认 status_code=500, error_code=INTERNAL_ERROR。"""
        exc = AppError()
        assert exc.status_code == 500
        assert exc.error_code == "INTERNAL_ERROR"
        assert exc.detail == "内部服务器错误"
        assert exc.extra == {}

    def test_validation_error_defaults(self) -> None:
        """ValidationError 默认 status_code=422。"""
        exc = ValidationError()
        assert exc.status_code == 422
        assert exc.error_code == "VALIDATION_ERROR"

    def test_not_found_error_defaults(self) -> None:
        """NotFoundError 默认 status_code=404。"""
        exc = NotFoundError()
        assert exc.status_code == 404
        assert exc.error_code == "NOT_FOUND"

    def test_conflict_error_defaults(self) -> None:
        """ConflictError 默认 status_code=409。"""
        exc = ConflictError()
        assert exc.status_code == 409
        assert exc.error_code == "CONFLICT"

    def test_service_unavailable_defaults(self) -> None:
        """ServiceUnavailableError 默认 status_code=503。"""
        exc = ServiceUnavailableError()
        assert exc.status_code == 503
        assert exc.error_code == "SERVICE_UNAVAILABLE"

    def test_internal_error_defaults(self) -> None:
        """InternalError 默认 status_code=500。"""
        exc = InternalError()
        assert exc.status_code == 500
        assert exc.error_code == "INTERNAL_ERROR"

    def test_business_error_is_app_error_subclass(self) -> None:
        """BusinessError 应是 AppError 的子类。"""
        assert issubclass(BusinessError, AppError)
        assert issubclass(ValidationError, BusinessError)
        assert issubclass(NotFoundError, BusinessError)
        assert issubclass(ConflictError, BusinessError)

    def test_internal_error_is_app_error_subclass(self) -> None:
        """InternalError 应是 AppError 的子类。"""
        assert issubclass(InternalError, AppError)
        assert issubclass(ServiceUnavailableError, AppError)

    def test_custom_detail_overrides_default(self) -> None:
        """构造时传入 detail 应覆盖默认值。"""
        exc = InternalError(detail="自定义错误消息")
        assert exc.detail == "自定义错误消息"

    def test_custom_error_code_overrides_default(self) -> None:
        """构造时传入 error_code 应覆盖默认值。"""
        exc = InternalError(error_code="CUSTOM_CODE")
        assert exc.error_code == "CUSTOM_CODE"

    def test_custom_status_code_overrides_default(self) -> None:
        """构造时传入 status_code 应覆盖默认值。"""
        exc = InternalError(status_code=501)
        assert exc.status_code == 501

    def test_extra_passed_through(self) -> None:
        """构造时传入 extra 应存储在 extra 属性。"""
        extra = {"field": "heatScore", "max": 100}
        exc = ValidationError(extra=extra)
        assert exc.extra == extra

    def test_exception_chain_preserved(self) -> None:
        """raise InternalError from exc 应保留异常链。"""
        try:
            try:
                raise ValueError("底层原因")
            except ValueError as exc:
                raise InternalError(detail="处理失败") from exc
        except InternalError as exc:
            assert exc.__cause__ is not None
            assert isinstance(exc.__cause__, ValueError)
            assert str(exc.__cause__) == "底层原因"
