import Link from "next/link";

export default function HomePage() {
  return (
    <main
      style={{
        maxWidth: 880,
        margin: "0 auto",
        padding: "48px 20px",
      }}
    >
      <header style={{ marginBottom: 32 }}>
        <div
          style={{
            display: "inline-block",
            padding: "4px 12px",
            borderRadius: 8,
            background: "var(--accent-soft)",
            color: "#2f5fd0",
            fontSize: 13,
            fontWeight: 600,
            marginBottom: 12,
          }}
        >
          v0.1 · 已可用
        </div>
        <h1 style={{ fontSize: 32, fontWeight: 700, letterSpacing: "-0.02em" }}>
          FlowGate
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: 16, marginTop: 8 }}>
          免费、开源、浏览器即用的流式细胞术数据分析工具
        </p>
      </header>

      <section
        style={{
          background: "var(--card)",
          border: "1px solid var(--border)",
          borderRadius: 14,
          padding: 24,
          marginBottom: 24,
        }}
      >
        <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 12 }}>
          已实现（v0.1）
        </h2>
        <ul style={{ color: "var(--text-secondary)", fontSize: 15, paddingLeft: 20 }}>
          <li>FCS 上传与解析（FlowKit，自动应用内嵌 $SPILLOVER 补偿）</li>
          <li>交互式散点图：平移 / 缩放 / 矩形门 / 多边形门</li>
          <li>层级门控树 + 基于全量事件的群体占比</li>
          <li>GatingML 2.0 导入导出（可回到 FlowJo）+ 统计 CSV + 图像 PNG</li>
        </ul>
      </section>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <Link
          href="/upload"
          style={{
            display: "inline-block",
            padding: "12px 24px",
            borderRadius: 10,
            background: "var(--accent)",
            color: "#fff",
            fontWeight: 600,
          }}
        >
          上传 FCS 文件开始分析
        </Link>
        <a
          href="/docs"
          target="_blank"
          rel="noreferrer"
          style={{
            display: "inline-block",
            padding: "12px 24px",
            borderRadius: 10,
            border: "1px solid var(--border)",
            background: "var(--card)",
            color: "var(--text)",
            fontWeight: 600,
          }}
        >
          后端 API 文档（FastAPI /docs）
        </a>
      </div>
    </main>
  );
}
