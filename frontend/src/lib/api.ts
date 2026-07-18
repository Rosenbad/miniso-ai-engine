// ==============================================================================
// 名创优品 AI 产品开发智能决策引擎 - 前端 API 客户端 (Task 14)
// ==============================================================================
// 对接 3 个后端微服务:
//   - TrendPulse  (port 8001): GET /trends, GET /trends/{topic},
//                              GET /cross-region/{topic}, POST /collect
//   - IdeaForge   (port 8002): POST /generate, GET /funnel
//   - MarketProbe (port 8003): POST /test-plan, POST /simulate,
//                              POST /analyze, POST /calibrate
//
// 环境变量 (与 docker-compose.yml 对齐):
//   NEXT_PUBLIC_TRENDPULSE_URL   (默认 http://localhost:8001)
//   NEXT_PUBLIC_IDEAFORGE_URL    (默认 http://localhost:8002)
//   NEXT_PUBLIC_MARKETPROBE_URL  (默认 http://localhost:8003)
// ==============================================================================

import type {
  AnalysisResult,
  CalibrationResult,
  CollectResult,
  CrossRegionComparison,
  FunnelStatus,
  HealthStatus,
  ProductIdeaCard,
  SimulationData,
  TestPlan,
  TestPlanRequest,
  TrendDetail,
  TrendListItem,
  TrendSignal,
} from "./types";

// ------------------------------------------------------------------------------
// 服务基础 URL (环境变量，支持 Docker 与本地开发)
// ------------------------------------------------------------------------------

const TRENDPULSE_URL =
  process.env.NEXT_PUBLIC_TRENDPULSE_URL || "http://localhost:8001";
const IDEAFORGE_URL =
  process.env.NEXT_PUBLIC_IDEAFORGE_URL || "http://localhost:8002";
const MARKETPROBE_URL =
  process.env.NEXT_PUBLIC_MARKETPROBE_URL || "http://localhost:8003";

// ------------------------------------------------------------------------------
// 内部请求工具
// ------------------------------------------------------------------------------

/**
 * 通用 fetch 封装，统一处理 JSON 解析与错误。
 *
 * @param url    完整请求地址
 * @param init   fetch 初始化参数 (method/body/headers)
 * @returns      解析后的 JSON 响应
 * @throws       Error (含 HTTP 状态码与后端 detail)
 */
async function request<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });

  if (!res.ok) {
    // 尝试解析后端错误 detail
    let detail = "";
    try {
      const errBody = await res.json();
      detail = errBody.detail || errBody.message || JSON.stringify(errBody);
    } catch {
      detail = await res.text().catch(() => "");
    }
    throw new Error(
      `HTTP ${res.status}: ${detail || res.statusText} (${url})`,
    );
  }

  return res.json() as Promise<T>;
}

/** POST JSON body 构造辅助 */
function jsonBody(body: unknown): RequestInit {
  return {
    method: "POST",
    body: JSON.stringify(body),
  };
}

// ==============================================================================
// TrendPulse API (数据感知层)
// ==============================================================================

/**
 * 获取趋势列表 (按 topic 去重，聚合多区域信号)。
 * GET /trends
 */
export async function getTrends(): Promise<TrendListItem[]> {
  return request<TrendListItem[]>(`${TRENDPULSE_URL}/trends`);
}

/**
 * 获取指定 topic 的趋势详情 (含多区域信号列表)。
 * GET /trends/{topic}
 */
export async function getTrendDetail(topic: string): Promise<TrendDetail> {
  const encoded = encodeURIComponent(topic);
  return request<TrendDetail>(`${TRENDPULSE_URL}/trends/${encoded}`);
}

/**
 * 跨区域趋势对比 (扩散路径/跟进窗口/热度图/本地化建议)。
 * GET /cross-region/{topic}
 */
export async function getCrossRegionCompare(
  topic: string,
): Promise<CrossRegionComparison> {
  const encoded = encodeURIComponent(topic);
  return request<CrossRegionComparison>(
    `${TRENDPULSE_URL}/cross-region/${encoded}`,
  );
}

/**
 * 触发数据采集 (demo 模式重载种子数据并返回采集摘要)。
 * POST /collect
 */
export async function collectTrends(): Promise<CollectResult> {
  return request<CollectResult>(`${TRENDPULSE_URL}/collect`, {
    method: "POST",
  });
}

/**
 * TrendPulse 健康检查。
 * GET /health
 */
export async function checkTrendPulseHealth(): Promise<HealthStatus> {
  return request<HealthStatus>(`${TRENDPULSE_URL}/health`);
}

// ==============================================================================
// IdeaForge API (决策推理层)
// ==============================================================================

/**
 * 根据趋势信号生成产品创意卡列表。
 * POST /generate
 *
 * @param trend 趋势信号 (至少包含 topic 字段)
 * @returns     ProductIdeaCard 列表，按 hitScore 降序
 */
export async function generateIdeas(
  trend: Partial<TrendSignal>,
): Promise<ProductIdeaCard[]> {
  return request<ProductIdeaCard[]>(
    `${IDEAFORGE_URL}/generate`,
    jsonBody(trend),
  );
}

/**
 * 获取规模化漏斗状态 (万级→千级→百级→Top100)。
 * GET /funnel
 */
export async function getFunnelStatus(): Promise<FunnelStatus> {
  return request<FunnelStatus>(`${IDEAFORGE_URL}/funnel`);
}

/**
 * IdeaForge 健康检查。
 * GET /health
 */
export async function checkIdeaForgeHealth(): Promise<HealthStatus> {
  return request<HealthStatus>(`${IDEAFORGE_URL}/health`);
}

// ==============================================================================
// MarketProbe API (验证反馈层)
// ==============================================================================

/**
 * 为产品生成 A/B 测试组合矩阵。
 * POST /test-plan
 */
export async function createTestPlan(
  product: TestPlanRequest,
): Promise<TestPlan> {
  return request<TestPlan>(
    `${MARKETPROBE_URL}/test-plan`,
    jsonBody(product),
  );
}

/**
 * 运行 7-14 天销售模拟。
 * POST /simulate
 *
 * @param testPlan 测试计划 (由 createTestPlan 生成)
 * @param options  模拟参数 { days: 模拟天数, seed?: 随机种子 }
 */
export async function simulateSales(
  testPlan: TestPlan,
  options: { days: number; seed?: number },
): Promise<SimulationData> {
  return request<SimulationData>(
    `${MARKETPROBE_URL}/simulate`,
    jsonBody({
      test_plan: testPlan,
      days: options.days,
      seed: options.seed ?? 42,
    }),
  );
}

/**
 * 分析模拟结果，判定赢家。
 * POST /analyze
 *
 * @param testPlan       测试计划 (与 simulate 入参一致)
 * @param simulationData 模拟数据 (simulate 的返回值)
 */
export async function analyzeResults(
  testPlan: TestPlan,
  simulationData: SimulationData,
): Promise<AnalysisResult> {
  return request<AnalysisResult>(
    `${MARKETPROBE_URL}/analyze`,
    jsonBody({
      test_plan: testPlan,
      simulation_data: simulationData,
    }),
  );
}

/**
 * 根据验证结果校准模型 (反哺链路修复)。
 * POST /calibrate
 *
 * @param testPlan      测试计划 (可为 null, 表示无对应测试计划)
 * @param predictedHits 模型预测的爆品概率 { combination_id: probability }
 * @param actualResults 实际模拟验证的综合评分 { combination_id: score }
 */
export async function calibrateModel(
  testPlan: TestPlan | null,
  predictedHits?: Record<string, number>,
  actualResults?: Record<string, number>,
): Promise<CalibrationResult> {
  return request<CalibrationResult>(
    `${MARKETPROBE_URL}/calibrate`,
    jsonBody({
      test_result: testPlan,
      predicted_hits: predictedHits ?? {},
      actual_results: actualResults ?? {},
    }),
  );
}

/**
 * MarketProbe 健康检查。
 * GET /health
 */
export async function checkMarketProbeHealth(): Promise<HealthStatus> {
  return request<HealthStatus>(`${MARKETPROBE_URL}/health`);
}

// ==============================================================================
// 导出服务基础 URL (供调试/状态展示使用)
// ==============================================================================

export const SERVICE_URLS = {
  trendpulse: TRENDPULSE_URL,
  ideaforge: IDEAFORGE_URL,
  marketprobe: MARKETPROBE_URL,
} as const;
