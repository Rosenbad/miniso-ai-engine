"use client";

// ==============================================================================
// IdeaCard - 产品创意卡 (Task 15)
// ==============================================================================
// 渲染单张 ProductIdeaCard:
//   - 概念图 (conceptImages[0])
//   - 爆品概率 hitScore (>0.8绿 / 0.7-0.8琥珀 / <0.7灰)
//   - Top-3 影响因子标签 (SHAP)
//   - IP 标签 + Z 世代匹配度
//   - 可展开: 大图 + Agent 决策链路 + IP 匹配面板 + 验证按钮
// spec §7.1 step4/5: 创意卡瀑布流 + 展开回放。
// ==============================================================================

import { useState } from "react";
import AgentTrace from "./AgentTrace";
import IPMatchPanel from "./IPMatchPanel";
import type { ProductIdeaCard as ProductIdeaCardType } from "@/lib/types";

// hitScore → 配色
function hitScoreColor(score: number): string {
  if (score > 0.8) return "text-green-600";
  if (score >= 0.7) return "text-amber-600";
  return "text-gray-500";
}

function hitScoreBadge(score: number): string {
  if (score > 0.8) return "bg-green-100 text-green-700";
  if (score >= 0.7) return "bg-amber-100 text-amber-700";
  return "bg-gray-200 text-gray-600";
}

export interface IdeaCardProps {
  /** 产品创意数据 */
  idea: ProductIdeaCardType;
  /** 是否选中 (高亮) */
  isSelected?: boolean;
  /** 点击卡片选中回调 */
  onSelect?: (idea: ProductIdeaCardType) => void;
  /** 点击验证按钮回调 */
  onValidate?: (idea: ProductIdeaCardType) => void;
}

export default function IdeaCard({
  idea,
  isSelected = false,
  onSelect,
  onValidate,
}: IdeaCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [imgError, setImgError] = useState(false);

  const cover = idea.conceptImages?.[0];
  const hitPercent = Math.round(idea.hitScore * 100);
  const zGenPercent = Math.round((idea.zGenMatchScore ?? 0) * 100);

  const handleCardClick = () => {
    onSelect?.(idea);
    setExpanded((v) => !v);
  };

  return (
    <div
      className={`border rounded-lg overflow-hidden transition-all cursor-pointer ${
        isSelected
          ? "border-brand-500 ring-1 ring-brand-300 shadow-md"
          : "border-gray-200 hover:border-brand-400 hover:shadow-sm"
      }`}
      onClick={handleCardClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          handleCardClick();
        }
      }}
    >
      {/* 顶部: 概念图 + 命中分 */}
      <div className="flex gap-3 p-3">
        {/* 概念图缩略 */}
        <div className="flex-shrink-0 w-16 h-16 rounded-md overflow-hidden bg-gray-100 flex items-center justify-center">
          {cover && !imgError ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={cover}
              alt={idea.productName}
              className="w-full h-full object-cover"
              onError={() => setImgError(true)}
            />
          ) : (
            <div className="text-[18px] text-gray-300 font-bold">
              {idea.category?.charAt(0) ?? "?"}
            </div>
          )}
        </div>

        {/* 标题 + 基础信息 */}
        <div className="flex-1 min-w-0">
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
              <div className="text-[10px] text-gray-400">爆品概率</div>
              <div className={`text-lg font-bold ${hitScoreColor(idea.hitScore)}`}>
                {hitPercent}%
              </div>
            </div>
          </div>

          {/* 标签行 */}
          <div className="mt-1.5 flex items-center gap-1 flex-wrap text-[10px]">
            <span className="px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
              {idea.category}
            </span>
            {idea.ipMatch?.ipName && (
              <span className="px-1.5 py-0.5 rounded bg-pink-50 text-pink-600">
                IP: {idea.ipMatch.ipName}
              </span>
            )}
            <span className={`px-1.5 py-0.5 rounded font-medium ${hitScoreBadge(idea.hitScore)}`}>
              {idea.hitScore > 0.8 ? "高潜" : idea.hitScore >= 0.7 ? "中潜" : "观察"}
            </span>
          </div>
        </div>
      </div>

      {/* Top 影响因子 + Z世代匹配 */}
      <div className="px-3 pb-2 flex items-center gap-2 flex-wrap text-[10px]">
        {idea.topFactors?.slice(0, 3).map((f, i) => (
          <span
            key={`${f.feature}-${i}`}
            className="px-1.5 py-0.5 rounded bg-blue-50 text-blue-600"
            title={`SHAP: ${f.shap_value}`}
          >
            {f.feature}
            <span className="ml-0.5 font-mono text-blue-400">
              {f.shap_value > 0 ? "+" : ""}
              {f.shap_value.toFixed(2)}
            </span>
          </span>
        ))}
        <span className="ml-auto text-purple-600">
          Z世代匹配 <span className="font-mono font-medium">{zGenPercent}%</span>
        </span>
      </div>

      {/* 展开提示 */}
      <div className="px-3 py-1.5 border-t border-gray-100 text-[10px] text-gray-400 flex items-center justify-center gap-1">
        {expanded ? "收起详情 ▲" : "展开详情 (大图 / 决策链路 / 验证) ▼"}
      </div>

      {/* 展开内容 */}
      {expanded && (
        <div className="border-t border-gray-100 p-3 space-y-3 bg-gray-50/50">
          {/* 大图 */}
          {cover && !imgError && (
            <div className="rounded-md overflow-hidden bg-white border border-gray-200">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={cover}
                alt={idea.productName}
                className="w-full max-h-64 object-contain"
              />
            </div>
          )}

          {/* 设计描述 / 材质 / 价格 */}
          <div className="text-xs space-y-1">
            {idea.designDesc && (
              <div className="text-gray-600">
                <span className="text-gray-400">设计: </span>
                {idea.designDesc}
              </div>
            )}
            <div className="flex gap-3 flex-wrap text-[11px]">
              {idea.material && (
                <span className="text-gray-500">材质: {idea.material}</span>
              )}
              {idea.priceRange && (
                <span className="text-gray-500">价格: ¥{idea.priceRange}</span>
              )}
            </div>
          </div>

          {/* 卖点 */}
          {idea.sellingPoints && idea.sellingPoints.length > 0 && (
            <div>
              <div className="text-[11px] font-medium text-gray-700 mb-1">
                核心卖点
              </div>
              <ul className="text-[11px] text-gray-600 space-y-0.5 list-disc list-inside">
                {idea.sellingPoints.map((sp, i) => (
                  <li key={i}>{sp}</li>
                ))}
              </ul>
            </div>
          )}

          {/* IP 匹配面板 */}
          {idea.ipMatch && <IPMatchPanel ipMatch={idea.ipMatch} compact />}

          {/* Agent 决策链路 */}
          <div>
            <div className="text-[11px] font-medium text-gray-700 mb-2">
              Agent 决策链路回放
            </div>
            <AgentTrace traces={idea.agentTrace ?? []} compact />
          </div>

          {/* 验证按钮 */}
          {onValidate && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onValidate(idea);
              }}
              className="w-full px-3 py-1.5 rounded-md bg-green-600 text-white text-xs font-medium hover:bg-green-700 transition-colors shadow-sm"
            >
              送入验证 (启动销售模拟)
            </button>
          )}
        </div>
      )}
    </div>
  );
}
