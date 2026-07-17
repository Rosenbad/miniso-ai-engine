"use client";

// ==============================================================================
// 名创优品 AI 产品开发智能决策引擎 - 主页面 (Task 14)
// ==============================================================================
// 三栏布局 (spec §7):
//   - Header  : 系统标题 + 服务状态
//   - 左栏 (300px)  : TrendRadar  趋势雷达 (趋势列表 / 生命周期 / Z世代标签)
//   - 中栏 (1fr)    : IdeaWorkbench 创意工作台 (生成按钮 / 创意卡瀑布 / Agent链路)
//   - 右栏 (300px)  : ValidationPanel 验证反馈 (模拟按钮 / 销售曲线 / 赢家高亮)
//   - Footer  : 版本与版权
//
// 响应式: 小屏幕单列堆叠 (grid-cols-1)，大屏三栏 (lg:grid-cols-[300px_1fr_300px])
// 本任务为布局骨架与占位内容，具体交互组件在 Task 15 实现。
// ==============================================================================

import { SERVICE_URLS } from "@/lib/api";

// ------------------------------------------------------------------------------
// 生命周期徽章配色
// ------------------------------------------------------------------------------

const LIFECYCLE_STYLES: Record<string, string> = {
  rising: "bg-green-100 text-green-700",
  peak: "bg-amber-100 text-amber-700",
  declining: "bg-gray-200 text-gray-600",
};

const LIFECYCLE_LABELS: Record<string, string> = {
  rising: "上升期",
  peak: "峰值期",
  declining: "衰退期",
};

// ------------------------------------------------------------------------------
// 占位数据 (Task 15 将替换为真实 API 数据)
// ------------------------------------------------------------------------------

const PLACEHOLDER_TRENDS = [
  {
    topic: "侘寂风家居",
    heat: 88,
    lifecycle: "rising",
    tags: ["侘寂", "新中式"],
    regions: ["china", "us", "eu"],
  },
  {
    topic: "Y2K千禧风穿搭",
    heat: 82,
    lifecycle: "peak",
    tags: ["Y2K"],
    regions: ["us", "sea"],
  },
  {
    topic: "多巴胺彩色配色",
    heat: 90,
    lifecycle: "peak",
    tags: ["多巴胺"],
    regions: ["china", "us"],
  },
];

const PLACEHOLDER_IDEAS = [
  {
    conceptId: "CPT-2025-0001",
    productName: "侘寂·大豆蜡香氛蜡烛",
    hitScore: 0.86,
    ip: "三丽鸥·库洛米",
    category: "家居/香氛",
  },
  {
    conceptId: "CPT-2025-0002",
    productName: "Y2K 金属感发夹套装",
    hitScore: 0.78,
    ip: "迪士尼·草莓熊",
    category: "饰品/发饰",
  },
];

const PLACEHOLDER_AGENTS = [
  { agent: "TrendAnalyst", step: 1, output: "识别侘寂风上升趋势，建议家居品类" },
  { agent: "ProductPlanner", step: 2, output: "确定香氛品类，IP方向: 库洛米" },
  { agent: "ConceptDesigner", step: 3, output: "生成大豆蜡+陶瓷香氛方案" },
];

// ------------------------------------------------------------------------------
// 主页面组件
// ------------------------------------------------------------------------------

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
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-[300px_1fr_300px] gap-4 p-4">
        {/* ----------------------- 左栏: TrendRadar ----------------------- */}
        <section
          className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 flex flex-col"
          aria-label="趋势雷达"
        >
          <SectionTitle title="趋势雷达" subtitle="TrendRadar" />

          <div className="mt-3 flex items-center justify-between text-xs text-gray-500">
            <span>共 {PLACEHOLDER_TRENDS.length} 条趋势</span>
            <button
              type="button"
              className="px-2 py-1 rounded bg-blue-50 text-blue-600 hover:bg-blue-100 transition-colors"
            >
              刷新采集
            </button>
          </div>

          <div className="mt-3 space-y-3 overflow-y-auto">
            {PLACEHOLDER_TRENDS.map((t) => (
              <div
                key={t.topic}
                className="border border-gray-100 rounded-lg p-3 hover:border-brand-500 hover:shadow-sm transition-all cursor-pointer"
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-sm text-gray-900 truncate">
                    {t.topic}
                  </span>
                  <span className="text-xs font-mono text-brand-600">
                    {t.heat}
                  </span>
                </div>
                <div className="mt-2 flex items-center gap-2 flex-wrap">
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                      LIFECYCLE_STYLES[t.lifecycle] ||
                      "bg-gray-100 text-gray-600"
                    }`}
                  >
                    {LIFECYCLE_LABELS[t.lifecycle] || t.lifecycle}
                  </span>
                  {t.tags.map((tag) => (
                    <span
                      key={tag}
                      className="px-1.5 py-0.5 rounded text-[10px] bg-purple-50 text-purple-600"
                    >
                      #{tag}
                    </span>
                  ))}
                </div>
                <div className="mt-2 text-[10px] text-gray-400">
                  区域: {t.regions.join(" / ")}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ----------------------- 中栏: IdeaWorkbench ----------------------- */}
        <section
          className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 flex flex-col min-w-0"
          aria-label="创意工作台"
        >
          <SectionTitle title="创意工作台" subtitle="IdeaWorkbench" />

          <div className="mt-3 flex items-center justify-between gap-3 flex-wrap">
            <div className="text-xs text-gray-500">
              当前趋势:
              <span className="ml-1 font-medium text-gray-700">
                侘寂风家居
              </span>
            </div>
            <button
              type="button"
              className="px-4 py-1.5 rounded-md bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 transition-colors shadow-sm"
            >
              生成产品创意
            </button>
          </div>

          {/* 创意卡瀑布流 (占位) */}
          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3 overflow-y-auto">
            {PLACEHOLDER_IDEAS.map((idea) => (
              <div
                key={idea.conceptId}
                className="border border-gray-200 rounded-lg p-3 hover:shadow-md transition-shadow"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-[10px] font-mono text-gray-400">
                      {idea.conceptId}
                    </div>
                    <div className="font-medium text-sm text-gray-900 truncate">
                      {idea.productName}
                    </div>
                  </div>
                  <div className="flex-shrink-0 text-right">
                    <div className="text-xs text-gray-400">爆品概率</div>
                    <div className="text-lg font-bold text-brand-600">
                      {(idea.hitScore * 100).toFixed(0)}%
                    </div>
                  </div>
                </div>
                <div className="mt-2 flex items-center gap-2 flex-wrap text-[10px]">
                  <span className="px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                    {idea.category}
                  </span>
                  <span className="px-1.5 py-0.5 rounded bg-pink-50 text-pink-600">
                    IP: {idea.ip}
                  </span>
                </div>
              </div>
            ))}
          </div>

          {/* Agent 决策链路 */}
          <div className="mt-4">
            <div className="text-xs font-medium text-gray-700 mb-2">
              Agent 决策链路
            </div>
            <div className="space-y-2">
              {PLACEHOLDER_AGENTS.map((a) => (
                <div
                  key={`${a.agent}-${a.step}`}
                  className="flex items-start gap-2 text-xs"
                >
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center font-bold text-[10px]">
                    {a.step}
                  </span>
                  <div className="min-w-0">
                    <span className="font-medium text-gray-700">
                      {a.agent}
                    </span>
                    <span className="text-gray-400"> → </span>
                    <span className="text-gray-600">{a.output}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ----------------------- 右栏: ValidationPanel ----------------------- */}
        <section
          className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 flex flex-col"
          aria-label="验证反馈"
        >
          <SectionTitle title="验证反馈" subtitle="ValidationPanel" />

          <div className="mt-3">
            <button
              type="button"
              className="w-full px-4 py-1.5 rounded-md bg-green-600 text-white text-sm font-medium hover:bg-green-700 transition-colors shadow-sm"
            >
              启动销售模拟
            </button>
          </div>

          {/* 销售曲线占位 */}
          <div className="mt-4">
            <div className="text-xs font-medium text-gray-700 mb-2">
              销售模拟曲线 (7天)
            </div>
            <div className="h-32 bg-gray-50 rounded-lg border border-dashed border-gray-200 flex items-end justify-around p-2">
              {[40, 55, 48, 70, 65, 82, 90].map((h, i) => (
                <div
                  key={i}
                  className="w-4 bg-gradient-to-t from-green-400 to-green-600 rounded-t"
                  style={{ height: `${h}%` }}
                  title={`Day ${i + 1}: ${h}`}
                />
              ))}
            </div>
            <div className="mt-1 flex justify-around text-[10px] text-gray-400">
              {["D1", "D2", "D3", "D4", "D5", "D6", "D7"].map((d) => (
                <span key={d}>{d}</span>
              ))}
            </div>
          </div>

          {/* 赢家高亮占位 */}
          <div className="mt-4">
            <div className="text-xs font-medium text-gray-700 mb-2">
              验证赢家
            </div>
            <div className="border-2 border-green-400 bg-green-50 rounded-lg p-3">
              <div className="flex items-center gap-2">
                <span className="text-base">🏆</span>
                <div className="min-w-0">
                  <div className="text-sm font-medium text-gray-900 truncate">
                    侘寂·大豆蜡香氛蜡烛
                  </div>
                  <div className="text-[10px] text-gray-500">
                    组合 A · 综合评分 0.82
                  </div>
                </div>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2 text-[10px]">
                <Metric label="转化率" value="6.8%" />
                <Metric label="退货率" value="3.2%" />
                <Metric label="Z世代互动" value="0.74" />
                <Metric label="置信度" value="0.91" />
              </div>
            </div>
          </div>

          {/* 模型校准占位 */}
          <div className="mt-4">
            <div className="text-xs font-medium text-gray-700 mb-2">
              模型校准
            </div>
            <div className="text-[11px] text-gray-500 bg-gray-50 rounded p-2 border border-gray-100">
              预测误差: <span className="font-mono text-amber-600">0.083</span>
              <br />
              权重更新: <span className="font-mono text-blue-600">v1.2.3</span>
            </div>
          </div>
        </section>
      </main>

      {/* ============================ Footer ============================ */}
      <footer className="bg-white border-t border-gray-200 px-6 py-3">
        <div className="flex items-center justify-between flex-wrap gap-2 text-xs text-gray-400">
          <span>
            名创优品 AI 产品开发智能决策引擎 v0.1.0 · Task 14 三栏布局骨架
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

/** 区块标题 */
function SectionTitle({
  title,
  subtitle,
}: {
  title: string;
  subtitle: string;
}) {
  return (
    <div className="flex items-baseline justify-between border-b border-gray-100 pb-2">
      <h2 className="text-sm font-bold text-gray-900">{title}</h2>
      <span className="text-[10px] font-mono text-gray-400 uppercase tracking-wider">
        {subtitle}
      </span>
    </div>
  );
}

/** 服务状态徽章 (占位) */
function ServiceBadge({ name, port }: { name: string; port: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
      <span className="text-gray-600">{name}</span>
      <span className="text-gray-400 font-mono">:{port}</span>
    </div>
  );
}

/** 指标小卡片 */
function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white/60 rounded px-1.5 py-1">
      <div className="text-gray-400">{label}</div>
      <div className="font-mono font-medium text-gray-700">{value}</div>
    </div>
  );
}
