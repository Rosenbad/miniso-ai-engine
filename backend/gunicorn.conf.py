"""Gunicorn 生产配置 — MINISO AI 引擎三服务共享。

环境变量:
    GUNICORN_WORKERS: worker 数量 (默认 4)
    GUNICORN_WORKER_CLASS: worker 类 (默认 uvicorn.workers.UvicornWorker)
    GUNICORN_TIMEOUT: 请求超时秒数 (默认 120)
    GUNICORN_GRACEFUL_TIMEOUT: 优雅关闭超时 (默认 30)
    GUNICORN_KEEPALIVE: keep-alive 秒数 (默认 5)
    GUNICORN_MAX_REQUESTS: 每 worker 最大请求数后重启 (默认 1000)
    GUNICORN_MAX_REQUESTS_JITTER: 随机抖动 (默认 50)
"""
import os
import multiprocessing

# 绑定地址 (由 docker-compose command 覆盖)
bind = "0.0.0.0:8000"

# worker 配置
workers = int(os.getenv("GUNICORN_WORKERS", str(min(multiprocessing.cpu_count() * 2 + 1, 8))))
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "uvicorn.workers.UvicornWorker")
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))

# 优雅重启: 处理完当前请求后重启 worker
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "1000"))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "50"))

# 日志
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
accesslog = os.getenv("GUNICORN_ACCESS_LOG", "-")  # stdout
errorlog = os.getenv("GUNICORN_ERROR_LOG", "-")    # stderr
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sms'

# 进程管理
preload_app = True       # 预加载应用，节省内存
daemon = False           # 前台运行 (Docker 需要)
pidfile = "/tmp/gunicorn.pid"
tmp_upload_dir = "/tmp"

# 安全
limit_request_line = 8190
limit_request_fields = 100
