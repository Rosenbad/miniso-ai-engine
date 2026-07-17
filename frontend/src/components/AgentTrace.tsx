"use client";

// ==============================================================================
// AgentTrace - 决策链路回放 (Task 15)
// ==============================================================================
// 将 ProductIdeaCard.agentTrace (AgentTraceEntry[]) 渲染为竖直时间线，
// 每个 Agent 步骤显示 step 序号、agent 名称与 output 输出。
// spec §7.1 step5: 展开创意卡后回放 Agent 推理链路。
// ==============================================================================

import type { AgentTraceEntry } from "@/lib/types";

// Agent 名称 → 主题色 (与 4 个 Agent 协作动画对应)
const AGENT_COLORS: Record<string, string> = {
  TrendAnalyst: "bg-blue-100 text-blue-700 ring-blue-300",
  ProductPlanner: "bg-purple-100 text-purple-700 ring-purple-300",
  ConceptDesigner: "bg-pink-100 text-pink-700 ring-pink-300",
  IPMatcher: "bg-amber-100 text-amber-700 ring-amber-300",
};

const DEFAULT_COLOR = "bg-gray-100 text-gray-700 ring-gray-300";

export interface AgentTraceProps {
  /** 决策链路条目列表 */
  traces: AgentTraceEntry[];
  /** 是否紧凑模式 (用于卡片内嵌) */
  compact?: boolean;
}

export default function AgentTrace({ traces, compact = false }: AgentTraceProps) {
  if (!traces || traces.length === 0) {
    return (
      <div className="text-[11px] text-gray-400 italic py-2">
        暂无决策链路数据
      </div>
    );
  }

  // 按 step 排序确保时间线顺序
  const sorted = [...traces].sort((a, b) => a.step - b.step);

  return (
    <div className="relative">
      {/* 竖直连接线 */}
      <div
        className="absolute left-[11px] top-2 bottom-2 w-px bg-gray-200"
        aria-hidden
      />
      <ol className={`relative ${compact ? "space-y-2" : "space-y-3"}`}>
        {sorted.map((entry, idx) => {
          const color =
            AGENT_COLORS[entry.agent] ?? DEFAULT_COLOR;
          return (
            <li key={`${entry.agent}-${entry.step}-${idx}`} className="relative pl-8">
              {/* 序号节点 */}
              <span
                className={`absolute left-0 top-0 w-6 h-6 rounded-full ring-2 ring-offset-1 flex items-center justify-center text-[10px] font-bold ${color}`}
              >
                {entry.step}
              </span>
              <div className="min-w-0">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-xs font-semibold text-gray-800">
                    {entry.agent}
                  </span>
                </div>
                <p
                  className={`text-gray-600 leading-snug mt-0.5 ${
                    compact ? "text-[11px]" : "text-xs"
                  }`}
                >
                  {entry.output}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
