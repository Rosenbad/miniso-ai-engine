# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 后端 Dockerfile
# ==============================================================================
# 支持三个微服务: TrendPulse / IdeaForge / MarketProbe
# 通过 SERVICE_NAME 环境变量区分服务
# ==============================================================================

FROM python:3.11-slim

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONSEED=42 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 先复制依赖文件以利用 Docker 缓存层
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Playwright 浏览器（用于数据采集）
RUN playwright install --with-deps chromium || true

# 复制项目代码
COPY . .

# 暴露端口
EXPOSE 8000

# 默认启动命令（各服务可通过 docker-compose 覆盖）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
