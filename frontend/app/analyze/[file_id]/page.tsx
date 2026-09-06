"use client";

/** 流式数据分析页：通道选择 → 交互散点图 → 拖放门控 → 统计。 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import ScatterPlot, { type ScatterMode } from "@/components/ScatterPlot";
import {
  type EventsData,
  type FcsSummary,
  type GateDef,
  type GateEvaluation,
  downloadBlob,
  evaluateGates,
  exportGatingml,
  exportStatisticsCsv,
  fetchEvents,
  fetchFileInfo,
  fetchGates,
  importGatingml,
  saveGates,
} from "@/app/lib/api";

const TOOLS: { mode: ScatterMode; label: string; hint: string }[] = [
  { mode: "pan", label: "平移", hint: "拖拽移动视图" },
  { mode: "zoom", label: "缩放", hint: "框选区域放大" },
  { mode: "rect", label: "矩形门", hint: "拖拽画出矩形门" },
  { mode: "polygon", label: "多边形门", hint: "点击加点，完成闭合" },
];

function newGateId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID().slice(0, 8);
  }
  return `g${Date.now().toString(36)}`;
}

/** 删除门及其全部后代 */
function removeSubtree(gates: GateDef[], id: string): GateDef[] {
  const toRemove = new Set<string>([id]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const g of gates) {
      if (g.parent_id != null && toRemove.has(g.parent_id) && !toRemove.has(g.id)) {
        toRemove.add(g.id);
        changed = true;
      }
    }
  }
  return gates.filter((g) => !toRemove.has(g.id));
}

export default function AnalyzePage() {
  const params = useParams<{ file_id: string }>();
  const fileId = params.file_id;

  const [fileInfo, setFileInfo] = useState<FcsSummary | null>(null);
  const [xLabel, setXLabel] = useState("FSC-A");
  const [yLabel, setYLabel] = useState("SSC-A");
  const [events, setEvents] = useState<EventsData | null>(null);
  const [dataTransform, setDataTransform] = useState<"raw" | "logicle">("raw");
  const [gates, setGates] = useState<GateDef[]>([]);
  const [evaluations, setEvaluations] = useState<GateEvaluation[] | null>(null);
  const [selectedGateId, setSelectedGateId] = useState<string | null>(null);
  const [mode, setMode] = useState<ScatterMode>("pan");
  const [error, setError] = useState<string | null>(null);
  const [evaluating, setEvaluating] = useState(false);

  // 加载文件信息与已保存的门控树
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [info, saved] = await Promise.all([fetchFileInfo(fileId), fetchGates(fileId)]);
        if (cancelled) return;
        setFileInfo(info);
        setGates(saved);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [fileId]);

  const channels = useMemo(() => {
    if (!fileInfo) return [];
    return [...fileInfo.scatter_labels, ...fileInfo.channel_labels];
  }, [fileInfo]);

  // 加载事件数据（切换通道或显示变换时）
  useEffect(() => {
    if (!fileId) return;
    let cancelled = false;
    setEvents(null);
    setError(null);
    (async () => {
      try {
        const data = await fetchEvents(fileId, xLabel, yLabel, 20000, dataTransform);
        if (!cancelled) setEvents(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [fileId, xLabel, yLabel, dataTransform]);

  // Logicle 查看模式不支持画门：切回平移
  useEffect(() => {
    if (dataTransform === "logicle" && (mode === "rect" || mode === "polygon")) {
      setMode("pan");
    }
  }, [dataTransform, mode]);

  // 门控树变更 → 评估 + 持久化
  useEffect(() => {
    if (!fileId || gates.length === 0) {
      setEvaluations(null);
      return;
    }
    let cancelled = false;
    setEvaluating(true);
    (async () => {
      try {
        const [evals] = await Promise.all([evaluateGates(fileId, gates), saveGates(fileId, gates)]);
        if (!cancelled) setEvaluations(evals);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setEvaluating(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [fileId, gates]);

  // 当前通道可见的门（Logicle 查看模式下不绘制门，避免坐标空间混淆）
  const visibleGates = useMemo(
    () =>
      dataTransform === "logicle"
        ? []
        : gates.filter((g) => g.x_label === xLabel && g.y_label === yLabel),
    [gates, xLabel, yLabel, dataTransform]
  );

  // 切换通道后若选中的门不可见，取消选中
  useEffect(() => {
    if (selectedGateId && !visibleGates.some((g) => g.id === selectedGateId)) {
      setSelectedGateId(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [xLabel, yLabel]);

  const addGate = useCallback(
    (partial: Omit<GateDef, "id" | "name" | "x_label" | "y_label" | "parent_id">) => {
      const gate: GateDef = {
        ...partial,
        id: newGateId(),
        name: `门 ${gates.length + 1}`,
        x_label: xLabel,
        y_label: yLabel,
        parent_id: selectedGateId ?? null,
      };
      setGates((prev) => [...prev, gate]);
    },
    [gates.length, selectedGateId, xLabel, yLabel]
  );

  const handleRectDrawn = useCallback(
    (xMin: number, xMax: number, yMin: number, yMax: number) => {
      addGate({ type: "rect", x_min: xMin, x_max: xMax, y_min: yMin, y_max: yMax });
    },
    [addGate]
  );

  const handlePolygonDrawn = useCallback(
    (vertices: number[][]) => {
      addGate({ type: "polygon", vertices });
    },
    [addGate]
  );

  const handleRename = useCallback((id: string, name: string) => {
    setGates((prev) => prev.map((g) => (g.id === id ? { ...g, name } : g)));
  }, []);

  const handleDelete = useCallback((id: string) => {
    setGates((prev) => removeSubtree(prev, id));
    setSelectedGateId((prev) => (prev === id ? null : prev));
  }, []);

  /* ---------- 导出 / 导入 ---------- */

  const handleExportGatingml = useCallback(async () => {
    try {
      const blob = await exportGatingml(fileId);
      downloadBlob(blob, `flowgate-${fileId.slice(0, 8)}.xml`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [fileId]);

  const handleExportCsv = useCallback(async () => {
    try {
      const blob = await exportStatisticsCsv(fileId);
      downloadBlob(blob, `flowgate-${fileId.slice(0, 8)}-statistics.csv`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [fileId]);

  const handleExportPng = useCallback(() => {
    const canvas = document.getElementById("scatter-canvas") as HTMLCanvasElement | null;
    if (!canvas) {
      setError("未找到散点图画布");
      return;
    }
    const a = document.createElement("a");
    a.href = canvas.toDataURL("image/png");
    a.download = `flowgate-${fileId.slice(0, 8)}-${xLabel}_${yLabel}.png`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }, [fileId, xLabel, yLabel]);

  const handleImportGatingml = useCallback(
    async (file: File | undefined) => {
      if (!file) return;
      try {
        const imported = await importGatingml(fileId, file);
        if (imported.length === 0) {
          setError("文件中没有可导入的门控（仅支持矩形/多边形门）");
          return;
        }
        setGates(imported);
        setSelectedGateId(null);
        setMode("pan");
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [fileId]
  );

  const treeRoots = useMemo(() => gates.filter((g) => g.parent_id == null), [gates]);

  return (
    <main style={{ maxWidth: 1200, margin: "0 auto", padding: "24px 16px 48px", fontFamily: "Roboto, 'PingFang SC', sans-serif" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 600, margin: 0, color: "#1A1B1C" }}>FlowGate 分析</h1>
          <div style={{ fontSize: 13, color: "#6B7280", marginTop: 4 }}>
            {fileInfo ? `${fileInfo.filename} · ${fileInfo.event_count.toLocaleString()} 事件 · ${fileInfo.channel_count} 通道` : "加载中…"}
          </div>
        </div>
        <Link href="/upload" style={{ fontSize: 13, color: "#8BC8EA", textDecoration: "none" }}>
          ← 上传新文件
        </Link>
      </div>

      {error && (
        <div style={{ background: "rgba(234,102,104,0.1)", border: "1px solid rgba(234,102,104,0.3)", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "#1A1B1C", marginBottom: 16 }}>
          {error}
        </div>
      )}

      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        {/* 左侧控制面板 */}
        <aside style={{ flex: "1 1 300px", minWidth: 0, display: "flex", flexDirection: "column", gap: 16 }}>
          {/* 通道选择 */}
          <section style={{ background: "#FFFFFF", border: "0.5px solid rgba(0,0,0,0.08)", borderRadius: 12, padding: 14 }}>
            <h2 style={{ fontSize: 13, fontWeight: 600, color: "#6B7280", margin: "0 0 10px" }}>通道</h2>
            <div style={{ display: "flex", gap: 8 }}>
              <label style={{ flex: 1, fontSize: 12, color: "#6B7280" }}>
                X 轴
                <select value={xLabel} onChange={(e) => setXLabel(e.target.value)} style={{ width: "100%", marginTop: 4, padding: "6px 8px", borderRadius: 8, border: "1px solid #E4E3DD", fontSize: 12, background: "#fff" }}>
                  {channels.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </label>
              <label style={{ flex: 1, fontSize: 12, color: "#6B7280" }}>
                Y 轴
                <select value={yLabel} onChange={(e) => setYLabel(e.target.value)} style={{ width: "100%", marginTop: 4, padding: "6px 8px", borderRadius: 8, border: "1px solid #E4E3DD", fontSize: 12, background: "#fff" }}>
                  {channels.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </label>
            </div>
            {events && (
              <div style={{ fontSize: 11, color: "#6B7280", marginTop: 8 }}>
                显示 {events.sampled.toLocaleString()} / {events.total_events.toLocaleString()} 事件（均匀下采样）
                {events.compensated ? " · 已补偿" : fileInfo?.has_spillover ? " · 原始（未补偿）" : ""}
                {dataTransform === "logicle" ? " · Logicle" : ""}
              </div>
            )}
          </section>

          {/* 显示变换 */}
          <section style={{ background: "#FFFFFF", border: "0.5px solid rgba(0,0,0,0.08)", borderRadius: 12, padding: 14 }}>
            <h2 style={{ fontSize: 13, fontWeight: 600, color: "#6B7280", margin: "0 0 10px" }}>显示变换</h2>
            <div style={{ display: "flex", gap: 8 }}>
              {(["raw", "logicle"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setDataTransform(t)}
                  style={{
                    flex: 1,
                    padding: "6px 12px",
                    borderRadius: 8,
                    border: dataTransform === t ? "1px solid #8BC8EA" : "1px solid #E4E3DD",
                    background: dataTransform === t ? "rgba(139,200,234,0.15)" : "#fff",
                    color: "#1A1B1C",
                    fontSize: 12,
                    cursor: "pointer",
                  }}
                >
                  {t === "raw" ? "线性" : "Logicle"}
                </button>
              ))}
            </div>
            {fileInfo?.has_spillover && (
              <div style={{ fontSize: 11, color: "#6B7280", marginTop: 8 }}>
                检测到内嵌 $SPILLOVER 补偿矩阵，线性模式默认应用荧光补偿。
              </div>
            )}
            {dataTransform === "logicle" && (
              <div style={{ fontSize: 11, color: "#EA6668", marginTop: 8 }}>
                Logicle 仅用于查看数据分布；门控请在「线性」模式下进行（门定义与导出始终使用补偿线性坐标）。
              </div>
            )}
          </section>

          {/* 工具 */}
          <section style={{ background: "#FFFFFF", border: "0.5px solid rgba(0,0,0,0.08)", borderRadius: 12, padding: 14 }}>
            <h2 style={{ fontSize: 13, fontWeight: 600, color: "#6B7280", margin: "0 0 10px" }}>工具</h2>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {TOOLS.map((t) => {
                const locked = dataTransform === "logicle" && (t.mode === "rect" || t.mode === "polygon");
                return (
                  <button
                    key={t.mode}
                    onClick={() => setMode(t.mode)}
                    disabled={locked}
                    style={{
                      padding: "6px 12px",
                      borderRadius: 8,
                      border: mode === t.mode ? "1px solid #8BC8EA" : "1px solid #E4E3DD",
                      background: mode === t.mode ? "rgba(139,200,234,0.15)" : "#fff",
                      color: locked ? "#B0B0B0" : "#1A1B1C",
                      fontSize: 12,
                      cursor: locked ? "not-allowed" : "pointer",
                      opacity: locked ? 0.6 : 1,
                    }}
                    title={locked ? "Logicle 查看模式不支持画门，请切回线性模式" : t.hint}
                  >
                    {t.label}
                  </button>
                );
              })}
            </div>
            <div style={{ fontSize: 11, color: "#6B7280", marginTop: 8 }}>
              {dataTransform === "logicle"
                ? "Logicle 查看模式：仅平移/缩放，切回线性模式进行门控"
                : `${TOOLS.find((t) => t.mode === mode)?.hint} · 滚轮缩放 · 双击重置画门`}
            </div>
          </section>

          {/* 导出 / 互操作 */}
          <section style={{ background: "#FFFFFF", border: "0.5px solid rgba(0,0,0,0.08)", borderRadius: 12, padding: 14 }}>
            <h2 style={{ fontSize: 13, fontWeight: 600, color: "#6B7280", margin: "0 0 10px" }}>导出 / 互操作</h2>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button
                onClick={handleExportGatingml}
                disabled={gates.length === 0}
                style={{ padding: "6px 12px", borderRadius: 8, border: "1px solid #E4E3DD", background: "#fff", color: "#1A1B1C", fontSize: 12, cursor: gates.length ? "pointer" : "not-allowed" }}
                title="导出为标准 GatingML 2.0，可用 FlowJo 等软件打开"
              >
                GatingML 导出
              </button>
              <button
                onClick={handleExportCsv}
                disabled={gates.length === 0}
                style={{ padding: "6px 12px", borderRadius: 8, border: "1px solid #E4E3DD", background: "#fff", color: "#1A1B1C", fontSize: 12, cursor: gates.length ? "pointer" : "not-allowed" }}
                title="各门事件数与占比（基于全量事件）"
              >
                统计 CSV
              </button>
              <button
                onClick={handleExportPng}
                disabled={!events}
                style={{ padding: "6px 12px", borderRadius: 8, border: "1px solid #E4E3DD", background: "#fff", color: "#1A1B1C", fontSize: 12, cursor: events ? "pointer" : "not-allowed" }}
                title="当前散点图（含门）导出为 PNG"
              >
                图像 PNG
              </button>
              <label style={{ padding: "6px 12px", borderRadius: 8, border: "1px solid #E4E3DD", background: "#fff", color: "#1A1B1C", fontSize: 12, cursor: "pointer" }}>
                导入 GatingML
                <input
                  type="file"
                  accept=".xml,.gml,.gatingml"
                  style={{ display: "none" }}
                  onChange={(e) => handleImportGatingml(e.target.files?.[0] ?? undefined)}
                />
              </label>
            </div>
            <div style={{ fontSize: 11, color: "#6B7280", marginTop: 8 }}>
              GatingML 2.0 为 ISAC 标准格式，可与 FlowJo / FCS Express 等商业软件互操作。
            </div>
          </section>

          {/* 门控树 */}
          <section style={{ background: "#FFFFFF", border: "0.5px solid rgba(0,0,0,0.08)", borderRadius: 12, padding: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <h2 style={{ fontSize: 13, fontWeight: 600, color: "#6B7280", margin: 0 }}>
                门控树{evaluating ? " · 评估中…" : ""}
              </h2>
              {selectedGateId && (
                <button
                  onClick={() => setSelectedGateId(null)}
                  style={{ fontSize: 11, color: "#6B7280", border: "none", background: "none", cursor: "pointer" }}
                >
                  取消选择
                </button>
              )}
            </div>
            {gates.length === 0 ? (
              <div style={{ fontSize: 12, color: "#6B7280", padding: "8px 0" }}>
                还没有门。选择「矩形门」或「多边形门」，在散点图上拖拽/点击创建。
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                {treeRoots.map((g) => (
                  <GateTreeItem
                    key={g.id}
                    gate={g}
                    gates={gates}
                    depth={0}
                    evaluations={evaluations}
                    selectedId={selectedGateId}
                    onSelect={setSelectedGateId}
                    onDelete={handleDelete}
                    onRename={handleRename}
                  />
                ))}
              </div>
            )}
          </section>
        </aside>

        {/* 右侧散点图 */}
        <section style={{ flex: "1 1 600px", minWidth: 0 }}>
          <div style={{ background: "#FFFFFF", border: "0.5px solid rgba(0,0,0,0.08)", borderRadius: 12, padding: 12 }}>
            <ScatterPlot
              data={events ? { x: events.x, y: events.y } : { x: [], y: [] }}
              xLabel={xLabel}
              yLabel={yLabel}
              gates={visibleGates}
              selectedGateId={selectedGateId}
              mode={mode}
              onRectDrawn={handleRectDrawn}
              onPolygonDrawn={handlePolygonDrawn}
              canvasId="scatter-canvas"
              height={520}
            />
            {!events && !error && (
              <div style={{ textAlign: "center", color: "#6B7280", fontSize: 13, padding: 20 }}>加载事件数据…</div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

/* ---------- 门控树行 ---------- */

function GateTreeItem({
  gate,
  gates,
  depth,
  evaluations,
  selectedId,
  onSelect,
  onDelete,
  onRename,
}: {
  gate: GateDef;
  gates: GateDef[];
  depth: number;
  evaluations: GateEvaluation[] | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, name: string) => void;
}) {
  const children = gates.filter((g) => g.parent_id === gate.id);
  const ev = evaluations?.find((e) => e.id === gate.id);
  const selected = selectedId === gate.id;

  return (
    <div>
      <div
        onClick={() => onSelect(gate.id)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "4px 6px",
          marginLeft: depth * 18,
          borderRadius: 6,
          background: selected ? "rgba(139,200,234,0.18)" : "transparent",
          border: selected ? "1px solid #8BC8EA" : "1px solid transparent",
          cursor: "pointer",
        }}
      >
        <span style={{ fontSize: 12, color: "#EA6668" }}>{gate.type === "rect" ? "▭" : "⬠"}</span>
        <input
          value={gate.name}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => onRename(gate.id, e.target.value)}
          style={{
            flex: 1,
            minWidth: 0,
            fontSize: 12,
            border: "none",
            background: "transparent",
            color: "#1A1B1C",
            outline: "none",
          }}
        />
        {ev && (
          <span style={{ fontSize: 11, color: "#6B7280", whiteSpace: "nowrap" }}>
            {ev.event_count.toLocaleString()} · {ev.relative_percent.toFixed(1)}%
          </span>
        )}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete(gate.id);
          }}
          style={{
            border: "none",
            background: "none",
            color: "#6B7280",
            fontSize: 14,
            cursor: "pointer",
            padding: "0 2px",
          }}
          title="删除此门及其子门"
        >
          ×
        </button>
      </div>
      {children.map((c) => (
        <GateTreeItem
          key={c.id}
          gate={c}
          gates={gates}
          depth={depth + 1}
          evaluations={evaluations}
          selectedId={selectedId}
          onSelect={onSelect}
          onDelete={onDelete}
          onRename={onRename}
        />
      ))}
    </div>
  );
}
