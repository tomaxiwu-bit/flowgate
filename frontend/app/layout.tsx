import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FlowGate - 流式细胞术 Web 分析",
  description:
    "免费、开源、浏览器即用的流式细胞术数据分析工具（FCS 解析 · 门控分析 · GatingML 互操作）",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
