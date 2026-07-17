"use client";

// ==============================================================================
// 名创优品 AI 产品开发智能决策引擎 - 主页面 (Task 15)
// ==============================================================================
// 三栏布局 (spec §7):
//   - Header  : 系统标题 + 服务状态
//   - 左栏 (300px)  : TrendRadar  趋势雷达 (趋势列表 / 生命周期 / Z世代标签)
//   - 中栏 (1fr)    : IdeaWorkbench 创意工作台 (生成按钮 / 创意卡瀑布 / Agent链路 / 漏斗)
//   - 右栏 (300px)  : ValidationPanel 验证反馈 (模拟按钮 / 销售曲线 / 赢家高亮 / 校准)
//   - Footer  : 版本与版权
//
// 响应式: 小屏幕单列堆叠 (grid-cols-1)，大屏三栏 (lg:grid-cols-[300px_1fr_300px])
// 各栏内部交互由对应组件 + Zustand store 驱动，page 仅负责布局编排。
// ==============================================================================

import { SERVICE_URLS } from "@/lib/api";
import TrendRadar from "@/components/TrendRadar";
import IdeaWorkbench from "@/components/IdeaWorkbench";
import ValidationPanel from "@/components/ValidationPanel";

export default function Home() {
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* ============================ Header ============================ */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 sticky top-0 z-10">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white font-bold text-sm">
              AI
            </div>
            <div>
              <h1 className="text-lg font-bold text-gray-900">
                名创优品 AI 产品开发智能决策引擎
              </h1>
              <p className="text-xs text-gray-500">
                TrendPulse · IdeaForge · MarketProbe 三层智能决策
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs">
            <ServiceBadge name="TrendPulse" port="8001" />
            <ServiceBadge name="IdeaForge" port="8002" />
            <ServiceBadge name="MarketProbe" port="8003" />
          </div>
        </div>
      </header>

      {/* ============================ Main 三栏 ============================ */}
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-[300px_1fr_300px] gap-4 p-4 min-h-0">
        {/* ----------------------- 左栏: TrendRadar ----------------------- */}
        <section
          className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 flex flex-col min-h-0 lg:max-h-[calc(100vh-140px)]"
          aria-label="趋势雷达"
        >
          <TrendRadar />
        </section>

        {/* ----------------------- 中栏: IdeaWorkbench ----------------------- */}
        <section
          className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 flex flex-col min-w-0 min-h-0 lg:max-h-[calc(100vh-140px)]"
          aria-label="创意工作台"
        >
          <IdeaWorkbench />
        </section>

        {/* ----------------------- 右栏: ValidationPanel ----------------------- */}
        <section
          className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 flex flex-col min-h-0 lg:max-h-[calc(100vh-140px)]"
          aria-label="验证反馈"
        >
          <ValidationPanel />
        </section>
      </main>

      {/* ============================ Footer ============================ */}
      <footer className="bg-white border-t border-gray-200 px-6 py-3">
        <div className="flex items-center justify-between flex-wrap gap-2 text-xs text-gray-400">
          <span>
            名创优品 AI 产品开发智能决策引擎 v0.2.0 · Task 15 前端核心组件
          </span>
          <span className="font-mono">
            {SERVICE_URLS.trendpulse} · {SERVICE_URLS.ideaforge} ·{" "}
            {SERVICE_URLS.marketprobe}
          </span>
        </div>
      </footer>
    </div>
  );
}

// ------------------------------------------------------------------------------
// 子组件
// ------------------------------------------------------------------------------

/** 服务状态徽章 */
function ServiceBadge({ name, port }: { name: string; port: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
      <span className="text-gray-600">{name}</span>
      <span className="text-gray-400 font-mono">:{port}</span>
    </div>
  );
}
