"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { uploadFcs, type FcsSummary } from "@/app/lib/api";

type UploadState =
  | { phase: "idle" }
  | { phase: "uploading" }
  | { phase: "done"; summary: FcsSummary; fileId: string }
  | { phase: "error"; message: string };

export default function UploadPage() {
  const router = useRouter();
  const [state, setState] = useState<UploadState>({ phase: "idle" });

  const handleFile = useCallback(
    async (file: File | undefined) => {
      if (!file) return;
      setState({ phase: "uploading" });
      try {
        const resp = await uploadFcs(file);
        setState({ phase: "done", summary: resp.summary, fileId: resp.file_id });
      } catch (err) {
        setState({
          phase: "error",
          message: err instanceof Error ? err.message : "未知错误",
        });
      }
    },
    []
  );

  const goAnalyze = useCallback(() => {
    if (state.phase === "done") {
      router.push(`/analyze/${state.fileId}`);
    }
  }, [router, state]);

  return (
    <main style={{ maxWidth: 880, margin: "0 auto", padding: "40px 20px" }}>
      <Link href="/" style={{ fontSize: 14 }}>
        ← 返回首页
      </Link>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: "16px 0 8px" }}>
        FCS 文件上传
      </h1>
      <p style={{ color: "var(--text-secondary)", fontSize: 15, marginBottom: 24 }}>
        骨架演示：上传后由后端 FlowKit 解析，返回文件元信息。门控分析将在后续里程碑实现。
      </p>

      <label
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexDirection: "column",
          gap: 8,
          padding: "40px 20px",
          borderRadius: 14,
          border: "2px dashed var(--border)",
          background: "var(--card)",
          cursor: "pointer",
          textAlign: "center",
        }}
      >
        <span style={{ fontSize: 16, fontWeight: 600 }}>
          {state.phase === "uploading" ? "正在解析…" : "点击选择 .fcs 文件"}
        </span>
        <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          {state.phase === "uploading"
            ? "上传并调用 FlowKit 解析，请稍候"
            : "单个文件，最大 500 MB（骨架阶段）"}
        </span>
        <input
          type="file"
          accept=".fcs"
          disabled={state.phase === "uploading"}
          onChange={(e) => handleFile(e.target.files?.[0] ?? undefined)}
          style={{ display: "none" }}
        />
      </label>

      {state.phase === "done" && (
        <section
          style={{
            marginTop: 24,
            background: "var(--card)",
            border: "1px solid var(--border)",
            borderRadius: 14,
            padding: 20,
          }}
        >
          <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>
            解析结果：{state.summary.filename}
          </h2>
          <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12 }}>
            <div>
              <dt style={{ fontSize: 12, color: "var(--text-secondary)" }}>事件数</dt>
              <dd style={{ fontSize: 20, fontWeight: 700 }}>
                {state.summary.event_count.toLocaleString()}
              </dd>
            </div>
            <div>
              <dt style={{ fontSize: 12, color: "var(--text-secondary)" }}>通道数</dt>
              <dd style={{ fontSize: 20, fontWeight: 700 }}>{state.summary.channel_count}</dd>
            </div>
            <div>
              <dt style={{ fontSize: 12, color: "var(--text-secondary)" }}>文件 ID</dt>
              <dd style={{ fontSize: 14, wordBreak: "break-all" }}>{state.fileId}</dd>
            </div>
          </dl>
          <button
            onClick={goAnalyze}
            style={{
              marginTop: 16,
              padding: "10px 20px",
              borderRadius: 8,
              border: "none",
              background: "#8BC8EA",
              color: "#1A1B1C",
              fontSize: 14,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            进入分析 → 画门控
          </button>
          <h3 style={{ fontSize: 14, fontWeight: 600, margin: "16px 0 6px" }}>荧光通道</h3>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", wordBreak: "break-all" }}>
            {state.summary.channel_labels.join(" · ") || "（无）"}
          </p>
          <h3 style={{ fontSize: 14, fontWeight: 600, margin: "12px 0 6px" }}>散射/时间参数</h3>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", wordBreak: "break-all" }}>
            {state.summary.scatter_labels.join(" · ") || "（无）"}
          </p>
        </section>
      )}

      {state.phase === "error" && (
        <section
          style={{
            marginTop: 24,
            padding: 16,
            borderRadius: 12,
            background: "rgba(232,104,74,0.08)",
            border: "1px solid rgba(232,104,74,0.3)",
            color: "#8a2d1d",
            fontSize: 14,
          }}
        >
          解析失败：{state.message}
        </section>
      )}
    </main>
  );
}
