# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - Makefile 快捷命令
# ==============================================================================
# 使用方法: make <target>
# 常用命令:
#   make up          - 启动所有服务（后台）
#   make down        - 停止所有服务
#   make build       - 构建所有镜像
#   make logs        - 查看实时日志
#   make ps          - 查看服务状态
#   make test        - 运行后端测试
#   make install-be  - 安装后端依赖
#   make install-fe  - 安装前端依赖
# ==============================================================================

# 默认 shell
SHELL := /bin/bash

# Docker Compose 命令（兼容 v1/v2）
DC := docker compose

.PHONY: up down build rebuild test install-be install-fe logs ps \
        init-db migrate shell-db clean help

# ------------------------------------------------------------------------------
# Docker 服务管理
# ------------------------------------------------------------------------------

## 启动所有服务（后台运行）
up:
	$(DC) up -d

## 停止所有服务
down:
	$(DC) down

## 构建所有镜像
build:
	$(DC) build

## 重新构建并启动所有服务
rebuild: build up

## 查看实时日志
logs:
	$(DC) logs -f

## 查看服务状态
ps:
	$(DC) ps

## 停止并删除容器、网络（保留数据卷）
clean:
	$(DC) down --remove-orphans

## 停止并删除容器、网络、数据卷（慎用，数据将丢失）
clean-all:
	$(DC) down -v --remove-orphans

# ------------------------------------------------------------------------------
# 开发环境安装
# ------------------------------------------------------------------------------

## 安装后端 Python 依赖
install-be:
	cd backend && pip install -r requirements.txt
	cd backend && playwright install chromium

## 安装前端 Node.js 依赖
install-fe:
	cd frontend && npm install

# ------------------------------------------------------------------------------
# 测试
# ------------------------------------------------------------------------------

## 运行后端测试
test:
	cd backend && pytest -v --cov=. --cov-report=term-missing

## 运行后端测试（仅指定服务）
test-trendpulse:
	cd backend && pytest tests/trendpulse/ -v

test-ideaforge:
	cd backend && pytest tests/ideaforge/ -v

test-marketprobe:
	cd backend && pytest tests/marketprobe/ -v

## 运行前端测试
test-fe:
	cd frontend && npm test

# ------------------------------------------------------------------------------
# 数据库
# ------------------------------------------------------------------------------

## 初始化数据库
init-db:
	$(DC) exec postgres psql -U miniso -d miniso_ai -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"

## 运行数据库迁移
migrate:
	cd backend && alembic upgrade head

## 进入 PostgreSQL 交互终端
shell-db:
	$(DC) exec postgres psql -U miniso -d miniso_ai

# ------------------------------------------------------------------------------
# 帮助
# ------------------------------------------------------------------------------

## 显示帮助信息
help:
	@echo "名创优品 AI 产品开发智能决策引擎 - 可用命令:"
	@echo ""
	@echo "Docker 服务管理:"
	@echo "  make up          启动所有服务（后台）"
	@echo "  make down        停止所有服务"
	@echo "  make build       构建所有镜像"
	@echo "  make rebuild     重新构建并启动"
	@echo "  make logs        查看实时日志"
	@echo "  make ps          查看服务状态"
	@echo "  make clean       停止并删除容器（保留数据）"
	@echo "  make clean-all   停止并删除容器和数据（慎用）"
	@echo ""
	@echo "开发环境安装:"
	@echo "  make install-be  安装后端依赖"
	@echo "  make install-fe  安装前端依赖"
	@echo ""
	@echo "测试:"
	@echo "  make test        运行后端测试"
	@echo "  make test-fe     运行前端测试"
	@echo ""
	@echo "数据库:"
	@echo "  make init-db     初始化数据库"
	@echo "  make migrate     运行数据库迁移"
	@echo "  make shell-db    进入 PostgreSQL 终端"
