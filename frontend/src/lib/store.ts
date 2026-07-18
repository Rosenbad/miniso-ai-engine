"use client";

// ==============================================================================
// 名创优品 AI 产品开发智能决策引擎 - Zustand 全局状态 (Task 15)
// ==============================================================================
// 集中管理三层服务 (TrendPulse / IdeaForge / MarketProbe) 的数据状态、
// 加载态与错误信息，供三栏组件消费。所有 API 调用均在此处发起并处理异常，
// 组件层只需 read state + dispatch action，保持展示层纯粹。
// ==============================================================================

import { create } from "zustand";
import {
  analyzeResults,
  calibrateModel,
  collectTrends as collectTrendsApi,
  createTestPlan,
  generateIdeas,
  getCrossRegionCompare,
  getFunnelStatus,
  getTrendDetail,
  getTrends,
  simulateSales,
} from "./api";
import type {
  AnalysisResult,
  CalibrationResult,
  CollectResult,
  CrossRegionComparison,
  FunnelStatus,
  ProductIdeaCard,
  SimulationData,
  TestPlan,
  TestPlanRequest,
  TrendDetail,
  TrendListItem,
  TrendSignal,
} from "./types";

// ------------------------------------------------------------------------------
// Store 类型定义
// ------------------------------------------------------------------------------

interface AppState {
  // ---- 趋势数据 (TrendPulse) ----
  trends: TrendListItem[];
  selectedTopic: string | null;
  trendDetail: TrendDetail | null;
  crossRegion: CrossRegionComparison | null;
  collectResult: CollectResult | null;

  // ---- 创意数据 (IdeaForge) ----
  ideas: ProductIdeaCard[];
  selectedIdea: ProductIdeaCard | null;

  // ---- 漏斗数据 (IdeaForge) ----
  funnelStatus: FunnelStatus | null;

  // ---- 验证数据 (MarketProbe) ----
  testPlan: TestPlan | null;
  simulation: SimulationData | null;
  analysis: AnalysisResult | null;
  calibration: CalibrationResult | null;

  // ---- 加载态 ----
  loadingTrends: boolean;
  loadingDetail: boolean;
  collecting: boolean;
  generating: boolean;
  loadingFunnel: boolean;
  validating: boolean;
  calibrating: boolean;

  // ---- 错误态 ----
  errorTrends: string | null;
  errorDetail: string | null;
  errorCollect: string | null;
  errorGenerate: string | null;
  errorFunnel: string | null;
  errorValidation: string | null;
  errorCalibration: string | null;

  // ---- Actions ----
  fetchTrends: () => Promise<void>;
  collectTrends: () => Promise<void>;
  selectTopic: (topic: string | null) => void;
  fetchTrendDetail: (topic: string) => Promise<void>;
  fetchCrossRegion: (topic: string) => Promise<void>;
  generateProductIdeas: (trend: Partial<TrendSignal>) => Promise<void>;
  selectIdea: (idea: ProductIdeaCard | null) => void;
  fetchFunnel: () => Promise<void>;
  runValidation: (product: TestPlanRequest) => Promise<void>;
  runCalibration: () => Promise<void>;
  resetValidation: () => void;
}

// ------------------------------------------------------------------------------
// Store 实现
// ------------------------------------------------------------------------------

export const useAppStore = create<AppState>((set, get) => ({
  // ---- 初始状态 ----
  trends: [],
  selectedTopic: null,
  trendDetail: null,
  crossRegion: null,
  collectResult: null,

  ideas: [],
  selectedIdea: null,

  funnelStatus: null,

  testPlan: null,
  simulation: null,
  analysis: null,
  calibration: null,

  loadingTrends: false,
  loadingDetail: false,
  collecting: false,
  generating: false,
  loadingFunnel: false,
  validating: false,
  calibrating: false,

  errorTrends: null,
  errorDetail: null,
  errorCollect: null,
  errorGenerate: null,
  errorFunnel: null,
  errorValidation: null,
  errorCalibration: null,

  // ---- 获取趋势列表 ----
  fetchTrends: async () => {
    set({ loadingTrends: true, errorTrends: null });
    try {
      const trends = await getTrends();
      set({ trends, loadingTrends: false });
    } catch (e) {
      set({
        loadingTrends: false,
        errorTrends: e instanceof Error ? e.message : String(e),
      });
    }
  },

  // ---- 触发数据采集 (POST /collect) ----
  collectTrends: async () => {
    set({ collecting: true, errorCollect: null });
    try {
      const result = await collectTrendsApi();
      set({ collectResult: result, collecting: false });
      // 采集完成后自动刷新趋势列表
      const trends = await getTrends();
      set({ trends });
    } catch (e) {
      set({
        collecting: false,
        errorCollect: e instanceof Error ? e.message : String(e),
      });
    }
  },

  // ---- 选中趋势话题 (并拉取详情与跨区域对比) ----
  selectTopic: (topic) => {
    set({ selectedTopic: topic, trendDetail: null, crossRegion: null });
    if (topic) {
      void get().fetchTrendDetail(topic);
      void get().fetchCrossRegion(topic);
    }
  },

  fetchTrendDetail: async (topic) => {
    set({ loadingDetail: true, errorDetail: null });
    try {
      const detail = await getTrendDetail(topic);
      set({ trendDetail: detail, loadingDetail: false });
    } catch (e) {
      set({
        loadingDetail: false,
        errorDetail: e instanceof Error ? e.message : String(e),
      });
    }
  },

  fetchCrossRegion: async (topic) => {
    try {
      const cross = await getCrossRegionCompare(topic);
      set({ crossRegion: cross });
    } catch {
      // 跨区域对比为增强信息，失败时不阻塞主流程
      set({ crossRegion: null });
    }
  },

  // ---- 生成产品创意 ----
  generateProductIdeas: async (trend) => {
    set({ generating: true, errorGenerate: null, ideas: [] });
    try {
      const ideas = await generateIdeas(trend);
      set({ ideas, generating: false });
    } catch (e) {
      set({
        generating: false,
        errorGenerate: e instanceof Error ? e.message : String(e),
      });
    }
  },

  // ---- 选中创意卡 ----
  selectIdea: (idea) => {
    set({ selectedIdea: idea });
  },

  // ---- 获取漏斗状态 ----
  fetchFunnel: async () => {
    set({ loadingFunnel: true, errorFunnel: null });
    try {
      const funnelStatus = await getFunnelStatus();
      set({ funnelStatus, loadingFunnel: false });
    } catch (e) {
      set({
        loadingFunnel: false,
        errorFunnel: e instanceof Error ? e.message : String(e),
      });
    }
  },

  // ---- 运行验证链路: test-plan → simulate → analyze ----
  runValidation: async (product) => {
    set({
      validating: true,
      errorValidation: null,
      testPlan: null,
      simulation: null,
      analysis: null,
    });
    try {
      const testPlan = await createTestPlan(product);
      set({ testPlan });
      const simulation = await simulateSales(testPlan, { days: 7 });
      set({ simulation });
      const analysis = await analyzeResults(testPlan, simulation);
      set({ analysis, validating: false });
    } catch (e) {
      set({
        validating: false,
        errorValidation: e instanceof Error ? e.message : String(e),
      });
    }
  },

  // ---- 模型校准 (反哺链路修复) ----
  runCalibration: async () => {
    const { analysis, testPlan, selectedIdea } = get();
    set({ calibrating: true, errorCalibration: null });
    try {
      // predictedHits: 模型预测的爆品概率 (来自 IdeaForge 的 hitScore)
      // actualResults: 实际模拟验证的综合评分 (来自 MarketProbe 的 analysis.rankings)
      const predictedHits: Record<string, number> = {};
      const actualResults: Record<string, number> = {};
      if (analysis?.rankings) {
        for (const r of analysis.rankings) {
          // 实际结果: 使用模拟验证的综合评分
          actualResults[r.combination_id] = r.score;
          // 预测值: 使用选中创意卡的 hitScore 作为模型预测基线
          // (所有组合均源自同一产品创意, hitScore 代表模型对该创意的爆品预测概率)
          predictedHits[r.combination_id] = selectedIdea?.hitScore ?? r.score;
        }
      }
      const calibration = await calibrateModel(
        testPlan ?? null,
        predictedHits,
        actualResults,
      );
      set({ calibration, calibrating: false });
    } catch (e) {
      set({
        calibrating: false,
        errorCalibration: e instanceof Error ? e.message : String(e),
      });
    }
  },

  // ---- 重置验证区 ----
  resetValidation: () => {
    set({
      testPlan: null,
      simulation: null,
      analysis: null,
      errorValidation: null,
    });
  },
}));
