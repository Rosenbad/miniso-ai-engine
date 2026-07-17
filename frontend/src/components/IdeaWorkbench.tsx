"use client";

// ==============================================================================
// IdeaWorkbench - 创意工作台 (中栏, Task 15)
// ==============================================================================
// 功能:
//   - 顶部: 当前趋势 + "生成产品创意" 按钮 (调用 generateIdeas API)
//   - Agent 协作动画: 4 个标签脉冲 (TrendAnalyst / ProductPlanner /
//     ConceptDesigner / IPMatcher)，在 generating 时显示
//   - 模式切换: 创意卡瀑布流 ↔ 规模化漏斗 (FunnelView)
//   - 瀑布流: 渲染 IdeaCard 列表
// spec §7.1 step3/4/6: 生成创意 → Agent 协作 → 瀑布流 → 漏斗模式。
// ==============================================================================

import { useState } from "react";
import IdeaCard from "./IdeaCard";
import FunnelView from "./FunnelView";
import { useAppStore } from "@/lib/store";
import type { ProductIdeaCard, TestPlanRequest } from "@/lib/types";

// 4 个 Agent 协作标签 (与 AgentTrace 配色对应)
const AGENT_TAGS = [
  { name: "TrendAnalyst", desc: "趋势解析", color: "bg-blue-500" },
  { name: "ProductPlanner", desc: "产品规划", color: "bg-purple-500" },
  { name: "ConceptDesigner", desc: "概念设计", color: "bg-pink-500" },
  { name: "IPMatcher", desc: "IP 匹配", color: "bg-amber-500" },
];

type Mode = "waterfall" | "funnel";

export default function IdeaWorkbench() {
  const selectedTopic = useAppStore((s) => s.selectedTopic);
  const trendDetail = useAppStore((s) => s.trendDetail);
  const ideas = useAppStore((s) => s.ideas);
  const generating = useAppStore((s) => s.generating);
  const errorGenerate = useAppStore((s) => s.errorGenerate);
  const selectedIdea = useAppStore((s) => s.selectedIdea);
  const selectIdea = useAppStore((s) => s.selectIdea);
  const generateProductIdeas = useAppStore((s) => s.generateProductIdeas);
  const runValidation = useAppStore((s) => s.runValidation);

  const [mode, setMode] = useState<Mode>("waterfall");

  const handleGenerate = () => {
    if (!selectedTopic) return;
    // 用选中趋势的首个 signal 作为生成输入 (至少包含 topic)
    const signal = trendDetail?.signals?.[0];
    const trendInput = signal
      ? { ...signal }
      : { topic: selectedTopic };
    void generateProductIdeas(trendInput);
  };

  // 验证回调: 由 IdeaCard 触发，构造 TestPlanRequest 送入右栏验证
  const handleValidate = (idea: ProductIdeaCard) => {
    selectIdea(idea);
    const req: TestPlanRequest = {
      product_name: idea.productName,
      category: idea.category,
      ip_name: idea.ipMatch?.ipName ?? null,
      days: 7,
    };
    void runValidation(req);
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* 标题 */}
      <div className="flex items-baseline justify-between border-b border-gray-100 pb-2">
        <h2 className="text-sm font-bold text-gray-900">创意工作台</h2>
        <span className="text-[10px] font-mono text-gray-400 uppercase tracking-wider">
          IdeaWorkbench
        </span>
      </div>

      {/* 控制栏: 当前趋势 + 模式切换 + 生成按钮 */}
      <div className="mt-3 flex items-center justify-between gap-3 flex-wrap">
        <div className="text-xs text-gray-500 min-w-0">
          当前趋势:
          <span className="ml-1 font-medium text-gray-800 truncate">
            {selectedTopic ?? "未选择"}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* 模式切换 */}
          <div className="inline-flex rounded-md border border-gray-200 overflow-hidden text-[11px]">
            <button
              type="button"
              onClick={() => setMode("waterfall")}
              className={`px-2 py-1 transition-colors ${
                mode === "waterfall"
                  ? "bg-brand-600 text-white"
                  : "bg-white text-gray-600 hover:bg-gray-50"
              }`}
            >
              创意瀑布
            </button>
            <button
              type="button"
              onClick={() => setMode("funnel")}
              className={`px-2 py-1 transition-colors ${
                mode === "funnel"
                  ? "bg-brand-600 text-white"
                  : "bg-white text-gray-600 hover:bg-gray-50"
              }`}
            >
              规模化漏斗
            </button>
          </div>

          <button
            type="button"
            onClick={handleGenerate}
            disabled={!selectedTopic || generating}
            className="px-4 py-1.5 rounded-md bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {generating ? "生成中…" : "生成产品创意"}
          </button>
        </div>
      </div>

      {/* Agent 协作动画 (generating 时显示) */}
      {generating && (
        <div className="mt-3 rounded-lg border border-brand-200 bg-brand-50/40 p-3">
          <div className="text-xs font-medium text-gray-700 mb-2 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-brand-500 animate-ping" />
            Agent 协作中…
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {AGENT_TAGS.map((agent, i) => (
              <div
                key={agent.name}
                className="rounded-md bg-white border border-gray-200 p-2 flex items-center gap-2"
                style={{
                  animation: `pulse-soft 1.2s ease-in-out ${i * 0.25}s infinite`,
                }}
              >
                <span
                  className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${agent.color} animate-pulse`}
                />
                <div className="min-w-0">
                  <div className="text-[11px] font-semibold text-gray-800 truncate">
                    {agent.name}
                  </div>
                  <div className="text-[9px] text-gray-400">{agent.desc}</div>
                </div>
              </div>
            ))}
          </div>
          <style jsx>{`
            @keyframes pulse-soft {
              0%,
              100% {
                opacity: 1;
                transform: scale(1);
              }
              50% {
                opacity: 0.65;
                transform: scale(0.97);
              }
            }
          `}</style>
        </div>
      )}

      {/* 生成错误 */}
      {errorGenerate && !generating && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-600">
          <div className="font-medium mb-1">创意生成失败</div>
          <div className="text-[11px] text-red-500/80 break-all">
            {errorGenerate}
          </div>
          <button
            type="button"
            onClick={handleGenerate}
            className="mt-2 px-2 py-1 rounded bg-red-100 text-red-700 hover:bg-red-200 transition-colors text-[11px]"
          >
            重试
          </button>
        </div>
      )}

      {/* 内容区: 瀑布流 / 漏斗 */}
      <div className="mt-3 flex-1 min-h-0 overflow-y-auto pr-1">
        {mode === "funnel" ? (
          <FunnelView />
        ) : (
          <>
            {ideas.length === 0 && !generating && (
              <div className="flex flex-col items-center justify-center h-40 text-gray-400 gap-2">
                <div className="text-3xl">💡</div>
                <div className="text-xs">
                  {selectedTopic
                    ? "点击「生成产品创意」开始 Agent 协作"
                    : "请先在左侧趋势雷达选择一个趋势"}
                </div>
              </div>
            )}

            {ideas.length === 0 && generating && (
              <div className="flex flex-col items-center justify-center h-40 text-gray-400 gap-2">
                <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
                <div className="text-xs">4 个 Agent 正在协作生成创意…</div>
              </div>
            )}

            {/* 创意卡瀑布流 */}
            {ideas.length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {ideas.map((idea) => (
                  <IdeaCard
                    key={idea.conceptId}
                    idea={idea}
                    isSelected={selectedIdea?.conceptId === idea.conceptId}
                    onSelect={selectIdea}
                    onValidate={handleValidate}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
