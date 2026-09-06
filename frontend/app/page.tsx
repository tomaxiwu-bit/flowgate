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
          Skeleton v0.1
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
          目标功能（MVP 路线图）
        </h2>
        <ul style={{ color: "var(--text-secondary)", fontSize: 15, paddingLeft: 20 }}>
          <li>FCS 文件上传与解析</li>
          <li>交互式散点图 + 拖放门控（gating）</li>
          <li>层级门控树 + 群体统计</li>
          <li>统计导出 + GatingML 2.0 互操作</li>
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
          上传 FCS 文件（骨架演示）
        </Link>
        <a
          href="http://127.0.0.1:8000/docs"
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
