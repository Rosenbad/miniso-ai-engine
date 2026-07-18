# ==============================================================================
# 共享模块 - CORS 跨域配置 (Phase 1 安全修复)
# ==============================================================================
# 对应评估报告 R1 风险修复: CORS 安全漏洞
#
# 问题: 三处 allow_origins=["*"] + allow_credentials=True 违反 CORS 规范
# 修复: 从环境变量 CORS_ORIGINS 读取白名单, 开发环境默认 localhost:3000
#
# 使用方式:
#   from shared.cors import setup_cors
#   setup_cors(app)
# ==============================================================================

"""
CORS 跨域配置工具。

提供统一的 CORS 中间件设置, 从环境变量 ``CORS_ORIGINS`` 读取允许的前端来源列表。

环境变量:
    CORS_ORIGINS : 逗号分隔的允许来源列表
                   开发默认: http://localhost:3000,http://127.0.0.1:3000
                   生产环境: 必须替换为具体域名

用法::

    from fastapi import FastAPI
    from shared.cors import setup_cors

    app = FastAPI()
    setup_cors(app)
"""

from __future__ import annotations

import os
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 开发环境默认允许的前端来源
_DEFAULT_DEV_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# 允许的 HTTP 方法
_ALLOW_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]

# 允许的请求头
_ALLOW_HEADERS = [
    "Content-Type",
    "Authorization",
    "X-Requested-With",
    "Accept",
    "Origin",
]


def _parse_origins(raw: str) -> List[str]:
    """解析环境变量中的来源列表, 去除空白和空项。

    参数:
        raw: 逗号分隔的来源字符串 (如 "http://a.com,http://b.com")

    返回:
        来源列表, 每项为完整的 URL 字符串
    """
    return [o.strip() for o in raw.split(",") if o.strip()]


def get_allowed_origins() -> List[str]:
    """从环境变量获取允许的 CORS 来源列表。

    读取 ``CORS_ORIGINS`` 环境变量 (逗号分隔)。
    若未设置或为空, 返回开发环境默认值 (localhost:3000)。

    返回:
        允许的前端来源 URL 列表
    """
    raw = os.environ.get("CORS_ORIGINS", "")
    if not raw.strip():
        return list(_DEFAULT_DEV_ORIGINS)
    return _parse_origins(raw)


def setup_cors(app: FastAPI) -> None:
    """为 FastAPI 应用配置安全的 CORS 中间件。

    从环境变量 ``CORS_ORIGINS`` 读取允许的前端来源列表,
    替代不安全的 ``allow_origins=["*"]`` 配置。

    参数:
        app: FastAPI 应用实例
    """
    origins = get_allowed_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=_ALLOW_METHODS,
        allow_headers=_ALLOW_HEADERS,
    )


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["setup_cors", "get_allowed_origins"]
