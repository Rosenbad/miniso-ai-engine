"use client";

// ==============================================================================
// 名创优品 AI 产品开发智能决策引擎 - 主页面 (Task 15 / Refactor v0.3.0)
// ==============================================================================
// 重构说明:
//   - 布局结构抽取为通用组件 `DashboardLayout` (components/DashboardLayout.tsx)
//   - 新增 `KpiGrid` 通用组件，用于系统级 KPI 摘要展示
//   - 本页面仅负责: 数据装配 / 子组件编排 / KPI 静态值定义
//
// 三栏布局 (spec §7):
//   - Header  : 系统标题 + 服务状态 (ServiceHealthBadge × 3)
//   - 左栏 (300px)  : TrendRadar  趋势雷达
//   - 中栏 (1fr)    : KpiGrid (系统摘要) + IdeaWorkbench 创意工作台
//   - 右栏 (300px)  : ValidationPanel 验证反馈
//   - Footer  : 版本与版权
//
// 响应式: 小屏幕单列堆叠 (grid-cols-1)，大屏三栏 (lg:grid-cols-[300px_1fr_300px])
// 各栏内部交互由对应组件 + Zustand store 驱动，page 仅负责布局编排。
// ==============================================================================

import { SERVICE_URLS } from "@/lib/api";
import TrendRadar from "@/components/TrendRadar";
import IdeaWorkbench from "@/components/IdeaWorkbench";
import ValidationPanel from "@/components/ValidationPanel";
import { ServiceHealthBadge } from "@/components/ServiceHealthBadge";
import { DashboardLayout } from "@/components/DashboardLayout";
import { KpiGrid } from "@/components/KpiGrid";
import type { KpiItem } from "@/components/KpiGrid";

/**
 * 系统级 KPI 摘要 (静态占位值，后续可从 store 获取真实数据)
 *
 * 指标说明:
 *  - 活跃趋势   : 当前 TrendRadar 追踪的趋势数量
 *  - 创意卡片   : IdeaWorkbench 中累计生成的创意卡数量
 *  - 验证通过率 : MarketProbe 模拟验证中通过率 (winner 占比)
 *  - 平均爆品分 : 已生成创意的平均 hit_score
 */
const SYSTEM_KPIS: KpiItem[] = [
  { label: "活跃趋势", value: 3, color: "default" },
  { label: "创意卡片", value: 12, color: "success" },
  {
    label: "验证通过率",
    value: "75%",
    trend: "up",
    trendValue: "+5%",
    color: "success",
  },
  { label: "平均爆品分", value: 0.68, color: "default" },
];

export default function Home() {
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
          {/* 系统级 KPI 摘要 */}
          <KpiGrid items={SYSTEM_KPIS} columns={4} />
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

// ------------------------------------------------------------------------------
// 子组件 (ServiceBadge 已迁移为独立的 ServiceHealthBadge 组件)
// 布局结构已迁移为独立的 DashboardLayout 组件
// KPI 摘要已迁移为独立的 KpiGrid 组件
// ------------------------------------------------------------------------------
