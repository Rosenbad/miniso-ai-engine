import type { Metadata } from "next";
import "./globals.css";

// ==============================================================================
// 名创优品 AI 产品开发智能决策引擎 - 根布局 (Task 14)
// ==============================================================================
// Next.js App Router 根布局，定义全局 HTML 结构与元数据。
// ==============================================================================

export const metadata: Metadata = {
  title: "名创优品 AI 产品开发智能决策引擎",
  description:
    "趋势感知 → 创意生成 → 验证反馈 三层智能决策工作台 (TrendPulse / IdeaForge / MarketProbe)",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="antialiased">{children}</body>
    </html>
  );
}
