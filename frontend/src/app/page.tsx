"use client";

// ==============================================================================
// 名创优品 AI 产品开发智能决策引擎 - 主页面 (Task 15 / Refactor v0.3.0)
// ==============================================================================
// 重构说明:
//   - 布局结构抽取为通用组件 `DashboardLayout` (components/DashboardLayout.tsx)
//   - 新增 `KpiGrid` 通用组件，用于系统级 KPI 摘要展示
//   - KPI 从 store 动态获取真实数据 (活跃趋势/创意卡片/验证通过率/平均爆品分)
//
// 三栏布局 (spec §7):
//   - Header  : 系统标题 + 服务状态 (ServiceHealthBadge × 3)
//   - 左栏 (300px)  : TrendRadar  趋势雷达
//   - 中栏 (1fr)    : KpiGrid (系统摘要) + IdeaWorkbench 创意工作台
//   - 右栏 (300px)  : ValidationPanel 验证反馈
//   - Footer  : 版本与版权
// ==============================================================================

import { useMemo } from "react";
import { SERVICE_URLS } from "@/lib/api";
import TrendRadar from "@/components/TrendRadar";
import IdeaWorkbench from "@/components/IdeaWorkbench";
import ValidationPanel from "@/components/ValidationPanel";
import { ServiceHealthBadge } from "@/components/ServiceHealthBadge";
import { DashboardLayout } from "@/components/DashboardLayout";
import { KpiGrid } from "@/components/KpiGrid";
import type { KpiItem } from "@/components/KpiGrid";
import { useAppStore } from "@/lib/store";

export default function Home() {
  // 从 store 获取真实数据
  const trends = useAppStore((s) => s.trends);
  const ideas = useAppStore((s) => s.ideas);
  const analysis = useAppStore((s) => s.analysis);
  const collectResult = useAppStore((s) => s.collectResult);

  // 动态计算 KPI
  const systemKpis: KpiItem[] = useMemo(() => {
    const activeTrends = trends.length;
    const ideaCount = ideas.length;

    // 验证通过率: 从 analysis 结果计算 (有 winner 即算通过)
    let passRate = "—";
    if (analysis?.winner) {
      passRate = "100%";
    } else if (ideas.length > 0) {
      passRate = "待验证";
    }

    // 平均爆品分: 从 ideas 计算
    let avgScore = 0;
    if (ideas.length > 0) {
      const scores = ideas
        .map((i) => Number(i.hitScore) || 0)
        .filter((s) => s > 0);
      avgScore = scores.length > 0
        ? Math.round((scores.reduce((a, b) => a + b, 0) / scores.length) * 100) / 100
        : 0;
    }

    // 如果有采集结果, 显示采集状态
    const collectMode = collectResult?.summary;
    const trendLabel = collectMode
      ? `${activeTrends}条`
      : `${activeTrends}`;

    return [
      {
        label: "活跃趋势",
        value: trendLabel,
        color: activeTrends > 0 ? "success" : "default",
      },
      {
        label: "创意卡片",
        value: ideaCount,
        color: ideaCount > 0 ? "success" : "default",
      },
      {
        label: "验证通过率",
        value: passRate,
        color: passRate === "100%" ? "success" : "default",
      },
      {
        label: "平均爆品分",
        value: avgScore || "—",
        color: avgScore > 0.5 ? "success" : "default",
      },
    ];
  }, [trends, ideas, analysis, collectResult]);

  return (
    <DashboardLayout
      title="名创优品 AI 产品开发智能决策引擎"
      subtitle="TrendPulse · IdeaForge · MarketProbe 三层智能决策"
      headerLogo={
        <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white font-bold text-sm">
          AI
        </div>
      }
      headerExtra={
        <>
          <ServiceHealthBadge name="TrendPulse" url={SERVICE_URLS.trendpulse} />
          <ServiceHealthBadge name="IdeaForge" url={SERVICE_URLS.ideaforge} />
          <ServiceHealthBadge name="MarketProbe" url={SERVICE_URLS.marketprobe} />
        </>
      }
      leftLabel="趋势雷达"
      leftPanel={<TrendRadar />}
      centerLabel="创意工作台"
      centerPanel={
        <div className="flex flex-col gap-4 min-h-0 flex-1">
          {/* 系统级 KPI 摘要 (动态) */}
          <KpiGrid items={systemKpis} columns={4} />
          {/* 创意工作台 (占据剩余高度) */}
          <div className="flex-1 min-h-0">
            <IdeaWorkbench />
          </div>
        </div>
      }
      rightLabel="验证反馈"
      rightPanel={<ValidationPanel />}
      footer={
        <div className="flex items-center justify-between flex-wrap gap-2 text-xs text-gray-400">
          <span>
            名创优品 AI 产品开发智能决策引擎 v0.3.0 · Task 15 前端核心组件 (DashboardLayout + KpiGrid 重构)
          </span>
          <span className="font-mono">
            {SERVICE_URLS.trendpulse} · {SERVICE_URLS.ideaforge} ·{" "}
            {SERVICE_URLS.marketprobe}
          </span>
        </div>
      }
    />
  );
}
