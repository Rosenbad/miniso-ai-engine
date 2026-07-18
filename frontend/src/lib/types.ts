// ==============================================================================
// 名创优品 AI 产品开发智能决策引擎 - 前端 TypeScript 类型定义 (Task 14)
// ==============================================================================
// 对应后端 shared/models.py 的 Pydantic 数据模型:
//   - TrendSignal      (spec §3.4 - 数据感知层输出)
//   - IPMatch          (spec §4.3 - IP 联名匹配输出)
//   - ProductIdeaCard  (spec §4.4 - 决策推理层输出)
//   - FunnelStage      (spec §4.3 - 规模化漏斗阶段)
//
// 字段严格对齐后端实际实现 (backend/shared/models.py, backend/ideaforge/routes.py)。
// ==============================================================================

// ------------------------------------------------------------------------------
// 枚举类型 (对应后端 Literal 字段)
// ------------------------------------------------------------------------------

/** 趋势生命周期阶段 */
export type Lifecycle = "rising" | "peak" | "declining";

/** 区域标识 */
export type Region = "china" | "sea" | "us" | "eu" | "global";

/** IP 可用性状态 */
export type Availability =
  | "available"
  | "exclusive"
  | "expiring"
  | "unavailable";

// ------------------------------------------------------------------------------
// 模型 1: TrendSignal (spec §3.4 - 数据感知层输出, 13 字段)
// ------------------------------------------------------------------------------

/**
 * 趋势信号 - TrendPulse 数据感知层的核心输出。
 *
 * 描述一个市场趋势话题的热度、增长、情感、生命周期及跨区域差异。
 */
export interface TrendSignal {
  /** 话题名，如 "侘寂风家居" */
  topic: string;
  /** 0-100 热度分 */
  heatScore: number;
  /** 周环比增长率 (%)，如 +34.2 表示 +34.2% */
  growthRate: number;
  /** 品类，如 "家居/装饰" */
  category: string;
  /** -1~1 情感倾向，-1 最负面，1 最正面 */
  sentiment: number;
  /** 生命周期阶段 */
  lifecycle: Lifecycle;
  /** 预计窗口期，如 "2-4周" */
  predictWindow: string;
  /** 关联关键词列表 */
  relatedKeywords: string[];
  /** 来源分布，如 { xiaohongshu: 45, douyin: 30 } */
  sourceBreakdown: Record<string, number>;
  /** 区域标识 */
  region: Region;
  /** Z 世代审美标签，如 ["Y2K", "多巴胺"] */
  zGenTags: string[];
  /** 受众画像 { ageRange, aesthetic, spendingPower } */
  targetAudience: Record<string, unknown>;
  /** 跨区域热度差 { us: "peak", cn: "rising", sea: "nascent" } */
  crossRegionDiff: Record<string, string>;
}

// ------------------------------------------------------------------------------
// 模型 2: IPMatch (spec §4.3 - IP 联名匹配输出, 7 字段)
// ------------------------------------------------------------------------------

/**
 * IP 联名匹配结果 - IdeaForge 决策推理层的 IP 匹配输出。
 */
export interface IPMatch {
  /** IP 名称，如 "三丽鸥·库洛米" */
  ipName: string;
  /** IP 势能分 0-100 */
  ipPowerScore: number;
  /** 品类匹配度 0-1 */
  matchScore: number;
  /** 可用性状态 */
  availability: Availability;
  /** 独家期截止日，如 "2025-12-31"；无独家期时为 null */
  exclusiveUntil: string | null;
  /** 区域热度分布 { china: 92, sea: 78 } */
  regionHeatMap: Record<string, number>;
  /** 该 IP 最适合的品类列表 */
  recommendedCategories: string[];
}

// ------------------------------------------------------------------------------
// 模型 3: ProductIdeaCard (spec §4.4 - 决策推理层输出, 16 字段)
// ------------------------------------------------------------------------------

/** SHAP 影响因子 */
export interface TopFactor {
  feature: string;
  shap_value: number;
}

/** 决策链路追踪条目 */
export interface AgentTraceEntry {
  agent: string;
  step: number;
  output: string;
}

/**
 * 产品创意卡 - IdeaForge 决策推理层的最终输出。
 *
 * 整合趋势信号、IP 匹配、爆品预测与区域适配，形成完整的产品创意方案。
 */
export interface ProductIdeaCard {
  /** 创意 ID，如 "CPT-2025-0001" */
  conceptId: string;
  /** 产品名称 */
  productName: string;
  /** 品类，如 "家居/香氛" */
  category: string;
  /** 设计描述 */
  designDesc: string;
  /** 材质，如 "大豆蜡 + 陶瓷" */
  material: string;
  /** 价格区间，如 "59-89" */
  priceRange: string;
  /** IP 联名匹配结果 (嵌套 IPMatch) */
  ipMatch: IPMatch;
  /** 核心卖点列表 */
  sellingPoints: string[];
  /** 爆品概率 0-1 */
  hitScore: number;
  /** Top-3 影响因子 (SHAP 值) */
  topFactors: TopFactor[];
  /** 概念图 URL 列表 */
  conceptImages: string[];
  /** 关联的 TrendSignal 话题名 (趋势来源引用) */
  trendSource: string;
  /** Z 世代匹配度 0-1 */
  zGenMatchScore: number;
  /** 受众画像 */
  targetAudience: Record<string, unknown>;
  /** 区域适配度 { china: "high", sea: "medium" } */
  regionFit: Record<string, string>;
  /** 决策链路可追溯 */
  agentTrace: AgentTraceEntry[];
}

// ------------------------------------------------------------------------------
// 模型 4: FunnelStage / FunnelStatus (spec §4.3 - 规模化漏斗)
// ------------------------------------------------------------------------------

/**
 * 漏斗阶段信息。
 *
 * NOTE: 后端 ideaforge/routes.py 的 FunnelStage 使用 `level` 字段
 * (而非 task 描述中的 `name`)，此处对齐后端实际实现。
 */
export interface FunnelStage {
  /** 层级名称 (万级/千级/百级/Top100) */
  level: string;
  /** 该层数量 */
  count: number;
  /** 层级描述 */
  description: string;
}

/** 漏斗状态响应 (GET /funnel) */
export interface FunnelStatus {
  /** 漏斗阶段列表 */
  stages: FunnelStage[];
  /** hitScore 阈值 */
  threshold: number;
  /** 最终保留数量上限 */
  topN: number;
}

// ------------------------------------------------------------------------------
// TrendPulse API 辅助类型 (GET /trends, GET /trends/{topic}, GET /cross-region)
// ------------------------------------------------------------------------------

/** GET /trends 列表项 (按 topic 聚合) */
export interface TrendListItem {
  topic: string;
  region_count: number;
  regions: string[];
  max_heat: number;
  lifecycle_summary: Record<string, string>;
}

/** GET /trends/{topic} 详情响应 */
export interface TrendDetail {
  topic: string;
  region_count: number;
  signals: TrendSignal[];
}

/** GET /cross-region/{topic} 跨区域对比响应 */
export interface CrossRegionComparison {
  topic: string;
  diffusion_path: string[];
  follow_up_window: string;
  heat_map: Record<string, number>;
  localization: Record<string, string>;
  [key: string]: unknown;
}

/** POST /collect 采集摘要响应 */
export interface CollectResult {
  status: string;
  sources: Array<{ name: string; status: string; count: number }>;
  total_signals: number;
}

// ------------------------------------------------------------------------------
// MarketProbe API 辅助类型
// ------------------------------------------------------------------------------

/** POST /test-plan 请求 */
export interface TestPlanRequest {
  product_name: string;
  category: string;
  ip_name?: string | null;
  days?: number;
}

/** POST /simulate 请求 */
export interface SimulateRequest {
  test_plan?: Record<string, unknown> | null;
  days?: number | null;
  seed?: number;
}

/** POST /test-plan 响应 (测试计划) */
export interface TestPlan {
  product_name: string;
  category: string;
  combinations: Array<Record<string, unknown>>;
  test_days: number;
  kpi_baseline: Record<string, number>;
  [key: string]: unknown;
}

/** POST /simulate 响应 (模拟数据) */
export interface SimulationData {
  days: number;
  daily_data: Record<
    string,
    Array<{
      day: number;
      sales: number;
      conversion: number;
      return_rate: number;
      z_gen_engagement: number;
    }>
  >;
  summary: Record<string, unknown>;
  [key: string]: unknown;
}

/** POST /analyze 响应 - 赢家组合详情 */
export interface WinnerCombo {
  combination_id: string;
  composite_score: number;
  total_sales: number;
  avg_conversion: number;
  profit_margin: number;
  price: string;
  packaging: string;
  channel: string;
  region: string;
  [key: string]: unknown;
}

/** POST /analyze 响应 (分析结果) */
export interface AnalysisResult {
  winner: WinnerCombo | null;
  rankings: Array<{
    combination_id: string;
    score: number;
    [key: string]: unknown;
  }>;
  factor_contribution: Record<string, number>;
  confidence: number;
  [key: string]: unknown;
}

/** POST /calibrate 响应 (模型更新) */
export interface CalibrationResult {
  new_version: string;
  weight_changes: Record<string, number>;
  strategy_suggestions: string[];
  prediction_errors: Record<string, number>;
  [key: string]: unknown;
}

// ------------------------------------------------------------------------------
// 健康检查响应
// ------------------------------------------------------------------------------

export interface HealthStatus {
  status: string;
  service: string;
  version?: string;
}
