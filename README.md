# 名创优品 AI 产品开发智能决策引擎

> 趋势感知 → 产品创意 → 上市验证 全链路 AI 决策系统：基于三层微服务架构，借助飞书 AI 工具，将万级趋势信号筛选为 Top 100 爆品候选，缩短上市周期、提升爆品命中率。

---

## 目录

- [项目简介](#项目简介)
- [架构总览](#架构总览)
- [技术栈](#技术栈)
- [快速开始（一键启动）](#快速开始一键启动)
- [演示指南（8 步用户旅程）](#演示指南8-步用户旅程)
- [API 文档](#api-文档)
- [项目结构](#项目结构)
- [开发指南](#开发指南)
- [飞书集成指南](#飞书集成指南)
- [测试](#测试)
- [许可](#许可)

---

## 项目简介

名创优品 AI 产品开发智能决策引擎是一个面向全球 112 国场景的 AI 驱动产品开发决策系统。它将"趋势感知 → 产品创意生成 → 上市验证"全链路打通，通过三个微服务层级 + 飞书生态集成 + 决策工作台前端，实现：

- **万级趋势信号** 自动采集（中国 + 海外多源）与跨区域对比
- **4 Agent 协作** 产出产品创意卡（TrendAnalyst → ProductPlanner → IPMatchEngine → HitPredictor ∥ ConceptDesigner）
- **XGBoost 爆品预测**（AUC = 0.7717），规模化漏斗筛选 Top 100 打版池
- **7-14 天小批量验证** 替代传统 3-6 个月上市验证
- **反哺链路修复**：模型自动校准，系统越用越准
- **飞书集成**：Bitable 数据落库、Bot 推送、AI 报告、Wiki 知识沉淀

### 核心价值

| 维度 | 传统模式 | AI 决策引擎 |
|------|---------|------------|
| 爆品命中率 | 15-20% | 35-45%（2x 提升） |
| 趋势发现提前量 | 人工调研滞后 | 提前 2-4 周感知 |
| 上市验证周期 | 3-6 个月 | 7-14 天（缩短 80%+） |
| IP 联名决策 | 数周人工调研 | 秒级引擎匹配 |
| 人力成本 | 全流程人工 | 自动化覆盖 50%+ |

---

## 架构总览

系统采用三层微服务架构，各层职责清晰、通过 REST API 解耦，并通过飞书集成层与企业协作生态打通。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         前端决策工作台 (Next.js :3000)                      │
│          TrendRadar │ IdeaWorkbench │ ValidationPanel 三栏布局              │
└──────────────┬──────────────────┬──────────────────┬─────────────────────┘
               │                  │                  │
   ┌───────────▼─────┐  ┌────────▼─────────┐  ┌────▼──────────────┐
   │   TrendPulse    │  │    IdeaForge     │  │   MarketProbe     │
   │   数据感知层     │  │   决策推理层(核心) │  │   验证反馈层       │
   │   :8001         │  │   :8002          │  │   :8003           │
   │                 │  │                  │  │                   │
   │ · 中国采集器     │  │ · 4 Agent 协作   │  │ · A/B 测试设计     │
   │   (小红书/抖音/  │  │   (TrendAnalyst  │  │ · 销售模拟(7-14天) │
   │    电商/搜索指数)│  │    →ProductPlanner│  │ · 性能分析         │
   │ · 海外采集器     │  │    →IPMatch      │  │ · 模型校准(反哺)   │
   │   (TikTok/IG)   │  │    →HitPredictor │  │                   │
   │ · NLP 处理管道   │  │    ∥ConceptDesign)│  │ 4 步闭环:          │
   │ · 跨区域对比引擎 │  │ · XGBoost 预测    │  │ test-plan→simulate│
   │                 │  │ · 规模化漏斗      │  │ →analyze→calibrate│
   └────────┬────────┘  └────────┬─────────┘  └────────┬──────────┘
            │                    │                     │
            └──────────┬─────────┴─────────────────────┘
                       │
            ┌──────────▼──────────┐    ┌───────────────────────┐
            │  PostgreSQL 15      │    │   飞书集成层 (Feishu)  │
            │  + TimescaleDB      │    │   Bitable │ Bot │ AI │
            │  :5432              │    │   Wiki │ 报告生成     │
            └─────────────────────┘    └───────────────────────┘
            ┌─────────────────────┐
            │  Redis 7  :6379     │   缓存 & Celery 消息队列
            └─────────────────────┘
```

### 数据流：全链路闭环

```
万级趋势信号                  千级概念                百级创意卡          Top 100 打版池
(TrendPulse 采集)   ──▶   (Agent 1+2 产出)   ──▶   (Orchestrator)  ──▶  (FunnelFilter
                                                                        hitScore > 0.7)
                                                                            │
                                                                            ▼
                                                              MarketProbe 4 步闭环验证
                                                              (test-plan → simulate
                                                               → analyze → calibrate)
                                                                            │
                                                                            ▼
                                                              模型自动校准 → 反哺 IdeaForge
                                                              (越用越准，闭环修复)
```

### Agent 协作流程（IdeaForge 核心）

```
TrendSignal
    │
    ▼  [串行]
Agent 1: TrendAnalyst      ──▶  ProductDirection
    │
    ▼  [串行]
Agent 2: ProductPlanner    ──▶  ProductConcept[]
    │
    ▼  [串行]
IP Match Engine           ──▶  IPMatch (电力评估 + 品类匹配 + 授权窗口 + 区域偏好)
    │
    ├──────────────────────┐  [并行 fan-out]
    ▼                     ▼
Agent 3: HitPredictor   Agent 4: ConceptDesigner
(XGBoost + SHAP)        (概念图生成)
    │                     │
    └──────────┬──────────┘
               ▼
        ProductIdeaCard[]  (16 字段，按 hitScore 降序)
```

---

## 技术栈

| 层级 | 技术 | 版本 | 用途 |
|------|------|------|------|
| **后端框架** | FastAPI | 0.109.2 | 微服务 REST API |
| | Uvicorn | 0.27.1 | ASGI 服务器 |
| | Pydantic | 2.6.1 | 数据校验与序列化 |
| **语言** | Python | 3.12+ | 后端全部逻辑 |
| **机器学习** | XGBoost | 2.0.3 | 爆品命中率预测（AUC=0.7717） |
| | SHAP | 0.44.1 | 模型可解释性 |
| | scikit-learn | 1.4.1 | 特征工程与评估 |
| | Prophet | 1.1.5 | 时间序列预测（可降级为线性回归） |
| **NLP** | jieba | 0.42.1 | 中文分词 |
| | SnowNLP | 0.12.3 | 中文情感分析 |
| | BERTopic | 0.16.0 | 主题聚类 |
| **大模型** | OpenAI (GPT-4o) | 1.13.3 | 消费洞察接入 |
| | LangChain | 0.1.9 | LLM 编排 |
| | LangGraph | 0.0.40 | Agent 状态机 |
| **数据采集** | Scrapy | 2.11.1 | 爬虫框架 |
| | Playwright | 1.41.2 | 浏览器自动化 |
| | httpx | 0.26.0 | 异步 HTTP 客户端 |
| **数据库** | PostgreSQL 15 | — | 关系型存储 |
| | TimescaleDB | latest | 时序数据扩展 |
| | SQLAlchemy 2.0 | 2.0.27 | ORM |
| | asyncpg | 0.29.0 | 异步驱动 |
| **缓存/队列** | Redis | 7-alpine | 缓存 & Celery Broker |
| | Celery | 5.3.6 | 异步任务队列 |
| **前端** | Next.js | 15.0 | React 全栈框架 |
| | React | 19.0 | UI 库 |
| | TypeScript | 5.6 | 类型安全 |
| | Tailwind CSS | 3.4 | 原子化 CSS |
| | Zustand | 4.5 | 状态管理 |
| | ECharts | 6.1 | 数据可视化 |
| **飞书** | Lark OAPI | 1.3.0 | 飞书开放平台 SDK |
| **基础设施** | Docker Compose | — | 一键编排 |
| **测试** | pytest | 8.0.2 | 后端测试（761+ 用例） |

---

## 快速开始（一键启动）

### 前置要求

- [Docker](https://www.docker.com/) 20.10+
- [Docker Compose](https://docs.docker.com/compose/) v2+
- （可选）[Node.js](https://nodejs.org/) 18+ 与 Python 3.12+ 用于本地开发

### 一键启动

```bash
# 1. 克隆项目
git clone <repo-url> miniso-ai-engine
cd miniso-ai-engine

# 2. 复制环境变量模板并按需修改
cp .env.example .env

# 3. 一键启动全部服务（后台运行）
docker compose up -d
```

启动后各服务地址：

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端决策工作台 | http://localhost:3000 | Next.js 三栏工作台 |
| TrendPulse API | http://localhost:8001 | 数据感知层 |
| IdeaForge API | http://localhost:8002 | 决策推理层 |
| MarketProbe API | http://localhost:8003 | 验证反馈层 |
| PostgreSQL | localhost:5432 | 数据库 |
| Redis | localhost:6379 | 缓存 |

> **提示**：默认配置下，各后端服务均内置 demo 模式——无需真实数据源凭据即可运行完整演示流程。飞书集成在未配置 `FEISHU_APP_ID` 时同样进入 demo 模式，返回结构正确的 mock 响应。

### 常用命令

```bash
make up          # 启动所有服务（后台）
make down        # 停止所有服务
make logs        # 查看实时日志
make ps          # 查看服务状态
make rebuild     # 重新构建并启动
make clean       # 停止并删除容器（保留数据）
make clean-all   # 停止并删除容器和数据（慎用）
make test        # 运行后端测试
```

### 查看日志与排障

```bash
# 查看单个服务日志
docker compose logs -f trendpulse
docker compose logs -f ideaforge
docker compose logs -f marketprobe
docker compose logs -f frontend

# 健康检查
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```

---

## 演示指南（8 步用户旅程）

启动服务后，打开浏览器访问 **http://localhost:3000**，按以下 8 步体验完整闭环：

### Step 1 — 打开决策工作台

首页呈现三栏布局：
- **左栏 TrendRadar**（趋势雷达）：展示多区域趋势列表、生命周期标签、Z 世代审美标签
- **中栏 IdeaWorkbench**（创意工作台）：创意生成入口 + 创意卡瀑布 + Agent 决策链路 + 漏斗视图
- **右栏 ValidationPanel**（验证反馈）：模拟测试入口 + 销售曲线 + 赢家高亮 + 模型校准

顶部 Header 实时显示三个微服务状态徽章。

### Step 2 — 浏览趋势雷达

左栏 TrendRadar 列出所有趋势信号（如「侘寂风家居」「Y2K千禧风穿搭」「多巴胺彩色配色」），每条展示：
- 热度分（heatScore）
- 生命周期阶段（rising / peak / declining）
- 覆盖区域（china / us / eu / sea）
- Z 世代审美标签（侘寂、Y2K、多巴胺等）

### Step 3 — 生成产品创意

在中栏 IdeaWorkbench 点击「生成创意」按钮：
- 前端调用 `POST /ideaforge/generate`，传入选中的趋势信号
- 后端 AgentOrchestrator 启动 4 Agent 协作流程
- 实时展示 Agent 决策链路（AgentTrace 组件）

### Step 4 — 浏览创意卡瀑布

生成完成后，中栏以卡片瀑布流展示 `ProductIdeaCard[]`，每张卡含 16 个字段：
- 概念名称、品类、目标人群
- **hitScore**（爆品命中评分，0-1，按降序排列）
- IP 联名匹配结果（IPMatch）
- 概念设计图（ConceptDesigner 产出）
- topFactors（SHAP 归因的关键影响因素）

### Step 5 — 查看创意详情

点击任意创意卡展开详情：
- 查看 Agent 完整决策链路（agentTrace）
- 查看 IP 匹配详情（电力评估、品类匹配度、授权窗口、区域偏好）
- 查看 hitScore 归因（哪些特征驱动了该评分）

### Step 6 — 切换漏斗模式

在 IdeaWorkbench 切换到漏斗视图，可视化规模化筛选漏斗：
```
万级 (10,000+) → 千级 (1,000+) → 百级 (100+) → Top 100 (hitScore > 0.7)
```
展示每一层的数量与筛选逻辑。

### Step 7 — 发起市场验证

将选中的创意卡「发送到验证」（右栏 ValidationPanel）：
1. `POST /marketprobe/test-plan` — 生成 A/B 测试组合矩阵
2. `POST /marketprobe/simulate` — 模拟 7-14 天销售数据
3. `POST /marketprobe/analyze` — 分析结果，判定赢家组合

右栏实时展示销售曲线（ECharts）、赢家高亮、因子贡献度。

### Step 8 — 闭环校准（反哺链路修复）

点击「校准模型」：
- `POST /marketprobe/calibrate` — 对比预测 hitScore 与实际结果
- ModelCalibrator 计算预测误差、调整权重、产出策略建议
- 生成新模型版本（new_version），反馈到 IdeaForge 的预测器

至此完成「趋势感知 → 产品创意 → 上市验证 → 模型校准」完整闭环，系统越用越准。

---

## API 文档

三个微服务均提供 REST API，启动后可通过以下地址访问交互式文档：
- TrendPulse Swagger：http://localhost:8001/docs
- IdeaForge Swagger：http://localhost:8002/docs
- MarketProbe Swagger：http://localhost:8003/docs

### TrendPulse（数据感知层，:8001）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/trends` | 趋势列表（按 topic 去重，聚合多区域信号） |
| GET | `/trends/{topic}` | 趋势详情（含多区域信号列表） |
| GET | `/cross-region/{topic}` | 跨区域对比（扩散路径 / 跟进窗口 / 热度图 / 本地化建议） |
| POST | `/collect` | 触发数据采集（demo 模式重载种子数据并返回采集摘要） |

**示例：**
```bash
# 获取趋势列表
curl http://localhost:8001/trends

# 跨区域对比
curl http://localhost:8001/cross-region/侘寂风家居

# 触发采集
curl -X POST http://localhost:8001/collect
```

### IdeaForge（决策推理层，:8002）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/generate` | 接受趋势信号，运行 4 Agent 编排，返回 ProductIdeaCard 列表 |
| GET | `/funnel` | 返回规模化漏斗状态（万级→千级→百级→Top100） |

**示例：**
```bash
# 生成创意
curl -X POST http://localhost:8002/generate \
  -H "Content-Type: application/json" \
  -d '{"topic": "侘寂风家居", "heatScore": 88.0, "region": "us", "lifecycle": "peak"}'

# 查看漏斗
curl http://localhost:8002/funnel
```

### MarketProbe（验证反馈层，:8003）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/test-plan` | 生成 A/B 测试组合矩阵（Step 1） |
| POST | `/simulate` | 运行 7-14 天销售模拟（Step 2） |
| POST | `/analyze` | 分析测试结果，判定赢家（Step 3） |
| POST | `/calibrate` | 校准模型，调整权重 + 策略建议（Step 4，反哺核心） |

**链式调用示例：**
```bash
# Step 1: 生成测试计划
curl -X POST http://localhost:8003/test-plan \
  -H "Content-Type: application/json" \
  -d '{"product_name": "侘寂风香薰", "category": "家居/香氛", "days": 7}'

# Step 2: 运行模拟（使用存储的测试计划）
curl -X POST http://localhost:8003/simulate \
  -H "Content-Type: application/json" \
  -d '{"seed": 42}'

# Step 3: 分析结果
curl -X POST http://localhost:8003/analyze \
  -H "Content-Type: application/json" \
  -d '{}'

# Step 4: 校准模型（反哺）
curl -X POST http://localhost:8003/calibrate \
  -H "Content-Type: application/json" \
  -d '{}'
```

> MarketProbe 的 4 个端点支持**链式调用**（使用内部存储状态）和**显式传参**（每步独立）两种模式，详见各端点 Swagger 文档。

---

## 项目结构

```
miniso-ai-engine/
├── backend/                          # 后端（Python 3.12 + FastAPI）
│   ├── trendpulse/                   # 数据感知层（:8001）
│   │   ├── collectors/               #   数据采集器
│   │   │   ├── base.py               #     采集器基类（限流 + 降级 + 缓存）
│   │   │   ├── xiaohongshu.py        #     小红书采集器
│   │   │   ├── douyin.py             #     抖音采集器
│   │   │   ├── ecommerce.py          #     电商采集器
│   │   │   ├── search_index.py       #     搜索指数采集器
│   │   │   ├── tiktok.py             #     TikTok 采集器（海外）
│   │   │   ├── instagram.py          #     Instagram 采集器（海外）
│   │   │   └── utils.py              #     公共工具
│   │   ├── processors/               #   NLP 处理管道
│   │   │   ├── cleaner.py            #     数据清洗 + 广告过滤 + 去重
│   │   │   ├── sentiment_analyzer.py #     情感分析 + Z世代标签识别
│   │   │   ├── topic_clusterer.py    #     主题聚类
│   │   │   └── trend_predictor.py    #     趋势预测（Prophet / 线性降级）
│   │   ├── cross_region.py           #   跨区域对比引擎
│   │   ├── routes.py                 #   TrendPulse REST API
│   │   └── main.py                   #   FastAPI 应用入口
│   ├── ideaforge/                    # 决策推理层（:8002，核心）
│   │   ├── agents/                   #   4 Agent 实现
│   │   │   ├── trend_analyst.py      #     Agent 1: 趋势分析师
│   │   │   ├── product_planner.py    #     Agent 2: 产品策划师
│   │   │   └── concept_designer.py   #     Agent 4: 概念设计师
│   │   ├── models/                   #   爆品预测模型
│   │   │   ├── features.py           #     特征工程
│   │   │   ├── train.py              #     XGBoost 训练
│   │   │   └── predict.py            #     HitPredictor（Agent 3）
│   │   ├── ip_engine.py              #   IP 联名匹配引擎（独立模块）
│   │   ├── funnel.py                 #   规模化漏斗过滤器
│   │   ├── orchestrator.py           #   Agent 编排器（核心）
│   │   ├── routes.py                 #   IdeaForge REST API
│   │   └── main.py                   #   FastAPI 应用入口
│   ├── marketprobe/                  # 验证反馈层（:8003）
│   │   ├── test_designer.py          #   A/B 测试设计（Step 1）
│   │   ├── simulator.py              #   销售模拟器（Step 2）
│   │   ├── performance_analyzer.py   #   性能分析器（Step 3）
│   │   ├── model_calibrator.py       #   模型校准器（Step 4，反哺核心）
│   │   ├── data_collector.py         #   验证数据采集
│   │   ├── routes.py                 #   MarketProbe REST API
│   │   └── main.py                   #   FastAPI 应用入口
│   ├── feishu/                       # 飞书集成层
│   │   ├── client.py                 #   飞书客户端（token 管理 + demo 模式）
│   │   ├── bitable.py                #   多维表格（数据落库）
│   │   ├── bot.py                    #   机器人消息推送
│   │   ├── ai.py                     #   AI 报告生成
│   │   ├── wiki.py                   #   Wiki 知识沉淀
│   │   └── templates.py              #   消息/报告模板
│   ├── shared/                       # 共享模块
│   │   ├── models.py                 #   Pydantic 数据模型（TrendSignal 等）
│   │   ├── database.py               #   数据库连接
│   │   └── redis_client.py           #   Redis 客户端
│   ├── data/                         # 模型与数据
│   │   ├── xgboost_model.json        #   预训练 XGBoost 模型
│   │   ├── ip_database.json          #   IP 数据库
│   │   └── generate_mock_skus.py     #   Mock SKU 生成
│   ├── tests/                        # 测试套件（761+ 用例）
│   │   ├── trendpulse/               #   TrendPulse 测试
│   │   ├── ideaforge/                #   IdeaForge 测试
│   │   ├── marketprobe/              #   MarketProbe 测试
│   │   └── feishu/                   #   飞书集成测试
│   ├── conftest.py                   # pytest 配置
│   ├── pytest.ini
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                         # 前端（Next.js 15 + React 19）
│   ├── src/
│   │   ├── app/                      #   App Router
│   │   │   ├── layout.tsx            #     全局布局
│   │   │   ├── page.tsx              #     三栏主页
│   │   │   └── globals.css           #     全局样式
│   │   ├── components/               #   UI 组件
│   │   │   ├── TrendRadar.tsx        #     趋势雷达（左栏）
│   │   │   ├── IdeaWorkbench.tsx     #     创意工作台（中栏）
│   │   │   ├── ValidationPanel.tsx   #     验证反馈（右栏）
│   │   │   ├── IdeaCard.tsx          #     创意卡
│   │   │   ├── FunnelView.tsx        #     漏斗视图
│   │   │   ├── IPMatchPanel.tsx      #     IP 匹配面板
│   │   │   ├── AgentTrace.tsx        #     Agent 决策链路
│   │   │   └── EChart.tsx            #     ECharts 封装
│   │   └── lib/                      #   工具库
│   │       ├── api.ts                #     API 客户端
│   │       ├── store.ts              #     Zustand 状态管理
│   │       └── types.ts              #     TypeScript 类型
│   ├── Dockerfile
│   ├── package.json
│   ├── tailwind.config.ts
│   └── tsconfig.json
├── docs/                             # 文档
│   └── roi-analysis.md               #   ROI 分析报告
├── docker-compose.yml                # 一键编排
├── Makefile                          # 快捷命令
├── .env.example                      # 环境变量模板
└── README.md                         # 本文档
```

---

## 开发指南

### 本地开发环境

#### 后端

```bash
cd backend

# 1. 创建虚拟环境
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 安装 Playwright 浏览器（数据采集需要）
playwright install chromium

# 4. 复制环境变量
cp ../.env.example ../.env

# 5. 启动单个服务（开发模式，热重载）
uvicorn trendpulse.main:app --reload --port 8001
uvicorn ideaforge.main:app --reload --port 8002   # 注：按服务入口启动
uvicorn marketprobe.main:app --reload --port 8003 # 注：按服务入口启动
```

#### 前端

```bash
cd frontend

# 1. 安装依赖
npm install

# 2. 启动开发服务器（热重载）
npm run dev
# 访问 http://localhost:3000

# 3. 生产构建
npm run build
npm start
```

### 运行测试

```bash
# 后端全部测试
cd backend
python -m pytest tests/ -v --tb=short

# 按服务运行
python -m pytest tests/trendpulse/ -v      # TrendPulse 测试
python -m pytest tests/ideaforge/ -v       # IdeaForge 测试
python -m pytest tests/marketprobe/ -v     # MarketProbe 测试
python -m pytest tests/feishu/ -v          # 飞书集成测试

# 带覆盖率
python -m pytest tests/ --cov=. --cov-report=term-missing

# 或使用 Makefile
make test
make test-trendpulse
make test-ideaforge
make test-marketprobe
```

### 前端类型检查与构建

```bash
cd frontend

# 类型检查
npx tsc --noEmit

# 生产构建
npm run build

# 代码检查
npm run lint
```

### 添加新的数据采集器

TrendPulse 采用基类继承模式，新增采集器只需：

1. 在 `backend/trendpulse/collectors/` 下新建文件，继承 `BaseCollector`
2. 实现 `fetch()` 与 `parse()` 方法，返回标准 `RawDataItem`
3. 在 `processors/` 管道中接入清洗与情感分析
4. 在 `tests/trendpulse/` 添加对应测试

```python
# backend/trendpulse/collectors/my_source.py
from .base import BaseCollector

class MySourceCollector(BaseCollector):
    SOURCE_NAME = "my_source"

    async def fetch(self, keyword: str = "", region: str = "china"):
        # 实现采集逻辑
        ...

    def parse(self, raw: dict):
        # 解析为标准格式
        ...
```

### 添加新的 Agent

IdeaForge 的 Agent 遵循统一接口契约，新增 Agent：

1. 在 `backend/ideaforge/agents/` 下新建文件
2. 实现 `__call__` 或对应处理方法，输入/输出遵循 `shared/models.py` 中的数据模型
3. 在 `orchestrator.py` 中接入编排流程（串行或并行）
4. 在 `tests/ideaforge/` 添加测试

---

## 飞书集成指南

系统通过 `backend/feishu/` 模块集成飞书生态，覆盖 spec §2.2 全部能力：Bitable（多维表格）、Bot（机器人）、AI（报告生成）、Wiki（知识库）。

### 两种运行模式

#### Demo 模式（默认，无需配置）

当未设置 `FEISHU_APP_ID` 环境变量时，系统自动进入 demo 模式：
- 所有飞书 API 调用返回**结构正确的 mock 响应**
- 适配无真实凭据的原型演示场景
- 不发起任何真实网络请求

#### 生产模式

配置真实凭据后切换到生产模式：

```bash
# .env 文件
FEISHU_APP_ID=cli_your_app_id
FEISHU_APP_SECRET=your_app_secret
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook
FEISHU_API_BASE_URL=https://open.feishu.cn/open-apis
```

### 集成能力

| 模块 | 文件 | 能力 |
|------|------|------|
| **FeishuClient** | `client.py` | tenant_access_token 管理（缓存 + 自动续期），统一请求封装 |
| **Bitable** | `bitable.py` | 趋势信号、创意卡、验证结果落库到多维表格 |
| **Bot** | `bot.py` | 爆品预警、漏斗状态、验证结果机器人推送 |
| **AI** | `ai.py` | 调用飞书 AI 生成决策报告（趋势周报、爆品分析） |
| **Wiki** | `wiki.py` | 决策知识沉淀到飞书 Wiki |
| **Templates** | `templates.py` | 消息卡片与报告模板 |

### Token 管理

- 飞书 `tenant_access_token` 有效期约 2 小时
- `FeishuClient` 在过期前 5 分钟自动续期，避免边界过期
- Token 缓存在内存中，减少重复请求

### 飞书应用配置步骤（生产模式）

1. 前往[飞书开放平台](https://open.feishu.cn/)创建企业自建应用
2. 获取 `App ID` 与 `App Secret`，填入 `.env`
3. 为应用开通以下权限范围：
   - 多维表格：`bitable:app`（读写表格）
   - 机器人：`im:message`（发送消息）
   - AI：`ai:report`（生成报告，如适用）
   - Wiki：`wiki:wiki`（知识库读写）
4. 配置机器人 Webhook（用于消息推送）
5. 重启服务，系统自动从 demo 模式切换到生产模式

---

## 测试

### 后端测试

后端测试套件覆盖全部三层微服务与飞书集成，共 **761+ 测试用例**，分布在 13 个测试文件中：

```
backend/tests/
├── trendpulse/          # TrendPulse 测试
│   ├── test_base_collector.py        # 采集器基类（限流/降级/缓存）
│   ├── test_cn_collectors.py         # 中国数据源采集器
│   ├── test_overseas_collectors.py   # 海外数据源采集器
│   ├── test_processors.py            # NLP 处理管道
│   └── test_cross_region.py          # 跨区域对比引擎
├── ideaforge/           # IdeaForge 测试
│   ├── test_agents_12.py             # Agent 1 + Agent 2
│   ├── test_hit_predictor.py         # XGBoost 爆品预测
│   ├── test_ip_engine.py             # IP 联名匹配引擎
│   └── test_orchestrator.py          # Agent 编排器
├── marketprobe/         # MarketProbe 测试
│   └── test_validation.py            # 4 步闭环验证
├── feishu/              # 飞书集成测试
│   └── test_integration.py           # 端到端集成
└── test_models.py       # 共享数据模型
```

**运行结果：** 761 passed, 1 skipped（Prophet 可选依赖未安装时跳过，自动降级为线性回归）

### 前端验证

```bash
cd frontend
npx tsc --noEmit   # TypeScript 类型检查（0 错误）
npm run build       # Next.js 生产构建（4 个静态页面生成成功）
```

---

## 许可

内部项目，版权所有 © 2025 名创优品 AI 产品开发智能决策引擎团队。
