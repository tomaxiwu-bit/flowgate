"use client";

/**
 * 交互式散点图（Canvas 实现，零第三方依赖）。
 *
 * 支持：平移（pan）、框选缩放（zoom）、矩形门（rect）、多边形门（polygon）。
 * 门的坐标以数据单位（通道值）定义，与屏幕缩放无关，因此切换缩放后门保持正确。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { GateDef } from "@/app/lib/api";

export type ScatterMode = "pan" | "rect" | "polygon" | "zoom";

interface ScatterPlotProps {
  data: { x: number[]; y: number[] };
  xLabel: string;
  yLabel: string;
  /** 与当前 x/y 通道匹配的门 */
  gates: GateDef[];
  selectedGateId: string | null;
  mode: ScatterMode;
  onRectDrawn: (xMin: number, xMax: number, yMin: number, yMax: number) => void;
  onPolygonDrawn: (vertices: number[][]) => void;
  /** 为 canvas 指定 id，供 PNG 导出使用 */
  canvasId?: string;
  height?: number;
}

interface View {
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
}

const COLORS = {
  background: "#F4F3EE",
  grid: "#E4E3DD",
  axis: "#6B7280",
  point: "rgba(139, 200, 234, 0.55)", // m-09 商务/效率
  pointInGate: "rgba(139, 200, 234, 0.9)",
  gate: "#EA6668", // 错误/红
  gateFill: "rgba(234, 102, 104, 0.12)",
  gateSelected: "#1A1B1C",
  draft: "#C9A7E8", // m-04 神秘/艺术
};

function formatAxis(v: number): string {
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (Math.abs(v) >= 1e3) return `${(v / 1e3).toFixed(0)}k`;
  return v.toFixed(0);
}

/** 点是否落在门内（矩形或射线法多边形判定） */
function pointInGate(gate: GateDef, x: number, y: number): boolean {
  if (gate.type === "rect") {
    return (
      x >= (gate.x_min ?? -Infinity) &&
      x <= (gate.x_max ?? Infinity) &&
      y >= (gate.y_min ?? -Infinity) &&
      y <= (gate.y_max ?? Infinity)
    );
  }
  const v = gate.vertices ?? [];
  if (v.length < 3) return false;
  let inside = false;
  for (let i = 0, j = v.length - 1; i < v.length; j = i++) {
    const xi = v[i][0];
    const yi = v[i][1];
    const xj = v[j][0];
    const yj = v[j][1];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

export default function ScatterPlot({
  data,
  xLabel,
  yLabel,
  gates,
  selectedGateId,
  mode,
  onRectDrawn,
  onPolygonDrawn,
  canvasId,
  height = 480,
}: ScatterPlotProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // 初始视图：数据范围（含少量边距）
  const [view, setView] = useState<View | null>(null);
  const viewRef = useRef<View | null>(null);
  viewRef.current = view;

  const [dragStart, setDragStart] = useState<{ sx: number; sy: number; view: View } | null>(null);
  const [dragCurrent, setDragCurrent] = useState<{ sx: number; sy: number } | null>(null);
  const [polygonDraft, setPolygonDraft] = useState<number[][]>([]);
  const draftRef = useRef<number[][]>([]);
  draftRef.current = polygonDraft;

  // 视图变更 / 数据变更时重绘
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const cssW = canvas.clientWidth;
    const cssH = canvas.clientHeight;
    if (cssW === 0 || cssH === 0) return;
    if (canvas.width !== cssW * dpr || canvas.height !== cssH * dpr) {
      canvas.width = cssW * dpr;
      canvas.height = cssH * dpr;
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const pad = { top: 16, right: 16, bottom: 32, left: 52 };
    const w = cssW - pad.left - pad.right;
    const h = cssH - pad.top - pad.bottom;
    if (w <= 0 || h <= 0) return;

    const v = viewRef.current;
    if (!v) return;

    const sx = (vx: number) => pad.left + ((vx - v.xMin) / (v.xMax - v.xMin)) * w;
    const sy = (vy: number) => pad.top + (1 - (vy - v.yMin) / (v.yMax - v.yMin)) * h;

    // 背景
    ctx.fillStyle = COLORS.background;
    ctx.fillRect(0, 0, cssW, cssH);

    // 网格 + 轴标签
    ctx.strokeStyle = COLORS.grid;
    ctx.lineWidth = 1;
    ctx.fillStyle = COLORS.axis;
    ctx.font = "11px Roboto, 'PingFang SC', sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    const xTicks = 6;
    const yTicks = 5;
    for (let i = 0; i <= xTicks; i++) {
      const vx = v.xMin + ((v.xMax - v.xMin) * i) / xTicks;
      const px = sx(vx);
      ctx.beginPath();
      ctx.moveTo(px, pad.top);
      ctx.lineTo(px, pad.top + h);
      ctx.stroke();
      ctx.fillText(formatAxis(vx), px, pad.top + h + 6);
    }
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (let i = 0; i <= yTicks; i++) {
      const vy = v.yMin + ((v.yMax - v.yMin) * i) / yTicks;
      const py = sy(vy);
      ctx.beginPath();
      ctx.moveTo(pad.left, py);
      ctx.lineTo(pad.left + w, py);
      ctx.stroke();
      ctx.fillText(formatAxis(vy), pad.left - 8, py);
    }

    // 轴名
    ctx.fillStyle = COLORS.axis;
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    ctx.font = "12px Roboto, 'PingFang SC', sans-serif";
    ctx.fillText(xLabel, pad.left + w / 2, cssH - 4);
    ctx.save();
    ctx.translate(14, pad.top + h / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText(yLabel, 0, 0);
    ctx.restore();

    // 数据点
    const selectedGate = gates.find((g) => g.id === selectedGateId) ?? null;
    const n = data.x.length;
    ctx.fillStyle = COLORS.point;
    const size = 1.6;
    if (selectedGate) {
      for (let i = 0; i < n; i++) {
        const px = sx(data.x[i]);
        const py = sy(data.y[i]);
        if (px < pad.left || px > pad.left + w || py < pad.top || py > pad.top + h) continue;
        if (pointInGate(selectedGate, data.x[i], data.y[i])) {
          ctx.fillStyle = COLORS.pointInGate;
          ctx.fillRect(px, py, size + 0.6, size + 0.6);
          ctx.fillStyle = COLORS.point;
        } else {
          ctx.fillRect(px, py, size, size);
        }
      }
    } else {
      for (let i = 0; i < n; i++) {
        const px = sx(data.x[i]);
        const py = sy(data.y[i]);
        if (px < pad.left || px > pad.left + w || py < pad.top || py > pad.top + h) continue;
        ctx.fillRect(px, py, size, size);
      }
    }

    // 门
    ctx.font = "11px Roboto, 'PingFang SC', sans-serif";
    for (const gate of gates) {
      const selected = gate.id === selectedGateId;
      ctx.lineWidth = selected ? 2.5 : 1.5;
      ctx.strokeStyle = selected ? COLORS.gateSelected : COLORS.gate;
      ctx.fillStyle = COLORS.gateFill;
      if (gate.type === "rect" && gate.x_min != null && gate.x_max != null && gate.y_min != null && gate.y_max != null) {
        const px = sx(gate.x_min);
        const py = sy(gate.y_max);
        const pw = sx(gate.x_max) - px;
        const ph = sy(gate.y_min) - py;
        if (pw > 0 && ph > 0) {
          ctx.fillRect(px, py, pw, ph);
          ctx.strokeRect(px, py, pw, ph);
        }
        ctx.fillStyle = selected ? COLORS.gateSelected : COLORS.gate;
        ctx.textAlign = "left";
        ctx.textBaseline = "bottom";
        ctx.fillText(gate.name, px + 4, py - 3);
      } else if (gate.type === "polygon" && (gate.vertices?.length ?? 0) >= 3) {
        const v = gate.vertices!;
        ctx.beginPath();
        ctx.moveTo(sx(v[0][0]), sy(v[0][1]));
        for (let i = 1; i < v.length; i++) ctx.lineTo(sx(v[i][0]), sy(v[i][1]));
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      }
    }

    // 多边形草稿
    if (draftRef.current.length > 0) {
      ctx.strokeStyle = COLORS.draft;
      ctx.fillStyle = COLORS.draft;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(sx(draftRef.current[0][0]), sy(draftRef.current[0][1]));
      for (let i = 1; i < draftRef.current.length; i++) {
        ctx.lineTo(sx(draftRef.current[i][0]), sy(draftRef.current[i][1]));
      }
      ctx.stroke();
      for (const p of draftRef.current) {
        ctx.beginPath();
        ctx.arc(sx(p[0]), sy(p[1]), 3, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // 拖拽预览（rect / zoom）
    if (dragStart && dragCurrent) {
      const px = Math.min(dragStart.sx, dragCurrent.sx);
      const py = Math.min(dragStart.sy, dragCurrent.sy);
      const pw = Math.abs(dragCurrent.sx - dragStart.sx);
      const ph = Math.abs(dragCurrent.sy - dragStart.sy);
      ctx.strokeStyle = COLORS.draft;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([5, 4]);
      ctx.strokeRect(px, py, pw, ph);
      ctx.setLineDash([]);
    }
  }, [data, gates, selectedGateId, mode, dragStart, dragCurrent]);

  // 首次挂载 / 数据变化时建立视图
  useEffect(() => {
    if (data.x.length === 0) return;
    let xMin = Infinity;
    let xMax = -Infinity;
    let yMin = Infinity;
    let yMax = -Infinity;
    for (let i = 0; i < data.x.length; i++) {
      const x = data.x[i];
      const y = data.y[i];
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
      if (x < xMin) xMin = x;
      if (x > xMax) xMax = x;
      if (y < yMin) yMin = y;
      if (y > yMax) yMax = y;
    }
    if (!Number.isFinite(xMin)) return;
    const dx = (xMax - xMin) * 0.03 || 1;
    const dy = (yMax - yMin) * 0.03 || 1;
    const next: View = { xMin: xMin - dx, xMax: xMax + dx, yMin: yMin - dy, yMax: yMax + dy };
    setView(next);
    setPolygonDraft([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.x, data.y, xLabel, yLabel]);

  // 重绘（含 resize 监听）
  useEffect(() => {
    draw();
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => draw());
    ro.observe(el);
    return () => ro.disconnect();
  }, [draw]);

  // 鼠标事件：坐标系转换（canvas CSS 像素）
  const toCanvasPos = (e: React.MouseEvent): { sx: number; sy: number } => {
    const rect = canvasRef.current!.getBoundingClientRect();
    return { sx: e.clientX - rect.left, sy: e.clientY - rect.top };
  };
  const toData = (sx: number, sy: number): { x: number; y: number } | null => {
    const canvas = canvasRef.current;
    const v = viewRef.current;
    if (!canvas || !v) return null;
    const cssW = canvas.clientWidth;
    const cssH = canvas.clientHeight;
    const pad = { top: 16, right: 16, bottom: 32, left: 52 };
    const w = cssW - pad.left - pad.right;
    const h = cssH - pad.top - pad.bottom;
    if (w <= 0 || h <= 0) return null;
    return {
      x: v.xMin + ((sx - pad.left) / w) * (v.xMax - v.xMin),
      y: v.yMax - ((sy - pad.top) / h) * (v.yMax - v.yMin),
    };
  };

  const onMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    const pos = toCanvasPos(e);
    const v = viewRef.current;
    if (!v) return;
    if (mode === "pan") {
      setDragStart({ ...pos, view: v });
    } else if (mode === "rect" || mode === "zoom") {
      setDragStart({ ...pos, view: v });
      setDragCurrent(pos);
    }
  };

  const onMouseMove = (e: React.MouseEvent) => {
    if (!dragStart) return;
    const pos = toCanvasPos(e);
    const v = viewRef.current;
    if (!v) return;
    if (mode === "pan") {
      const canvas = canvasRef.current!;
      const cssW = canvas.clientWidth;
      const cssH = canvas.clientHeight;
      const pad = { top: 16, right: 16, bottom: 32, left: 52 };
      const w = cssW - pad.left - pad.right;
      const h = cssH - pad.top - pad.bottom;
      if (w <= 0 || h <= 0) return;
      const dx = ((pos.sx - dragStart.sx) / w) * (v.xMax - v.xMin);
      const dy = ((pos.sy - dragStart.sy) / h) * (v.yMax - v.yMin);
      const xRange = v.xMax - v.xMin;
      const yRange = v.yMax - v.yMin;
      setView({ xMin: v.xMin - dx, xMax: v.xMin - dx + xRange, yMin: v.yMin + dy, yMax: v.yMin + dy + yRange });
    } else {
      setDragCurrent(pos);
    }
  };

  const onMouseUp = () => {
    if (!dragStart || !dragCurrent) {
      setDragStart(null);
      setDragCurrent(null);
      return;
    }
    if (mode === "rect") {
      const a = toData(dragStart.sx, dragStart.sy);
      const b = toData(dragCurrent.sx, dragCurrent.sy);
      if (a && b) {
        const xMin = Math.min(a.x, b.x);
        const xMax = Math.max(a.x, b.x);
        const yMin = Math.min(a.y, b.y);
        const yMax = Math.max(a.y, b.y);
        if (xMax - xMin > 0.001 && yMax - yMin > 0.001) {
          onRectDrawn(xMin, xMax, yMin, yMax);
        }
      }
    } else if (mode === "zoom") {
      const a = toData(dragStart.sx, dragStart.sy);
      const b = toData(dragCurrent.sx, dragCurrent.sy);
      if (a && b) {
        const xMin = Math.min(a.x, b.x);
        const xMax = Math.max(a.x, b.x);
        const yMin = Math.min(a.y, b.y);
        const yMax = Math.max(a.y, b.y);
        if ((xMax - xMin) > 1e-9 && (yMax - yMin) > 1e-9) {
          setView({ xMin, xMax, yMin, yMax });
        }
      }
    }
    setDragStart(null);
    setDragCurrent(null);
  };

  const onClick = (e: React.MouseEvent) => {
    if (mode !== "polygon") return;
    const pos = toCanvasPos(e);
    const d = toData(pos.sx, pos.sy);
    if (!d) return;
    setPolygonDraft((prev) => [...prev, [d.x, d.y]]);
  };

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const v = viewRef.current;
    if (!v) return;
    const pos = toCanvasPos(e);
    const d = toData(pos.sx, pos.sy);
    if (!d) return;
    const factor = Math.exp(e.deltaY * 0.0015);
    const xRange = (v.xMax - v.xMin) * factor;
    const yRange = (v.yMax - v.yMin) * factor;
    const nxMin = d.x - ((d.x - v.xMin) / (v.xMax - v.xMin)) * xRange;
    const nyMin = d.y - ((d.y - v.yMin) / (v.yMax - v.yMin)) * yRange;
    setView({ xMin: nxMin, xMax: nxMin + xRange, yMin: nyMin, yMax: nyMin + yRange });
  };

  const finishPolygon = () => {
    if (draftRef.current.length >= 3) {
      onPolygonDrawn(draftRef.current.map((p) => [p[0], p[1]]));
    }
    setPolygonDraft([]);
  };

  const cancelPolygon = () => setPolygonDraft([]);

  const gateStats = useMemo(() => {
    const stats: Record<string, number> = {};
    const selected = gates.find((g) => g.id === selectedGateId);
    if (!selected) return stats;
    let count = 0;
    for (let i = 0; i < data.x.length; i++) {
      if (pointInGate(selected, data.x[i], data.y[i])) count++;
    }
    stats[selected.id] = data.x.length > 0 ? (count / data.x.length) * 100 : 0;
    return stats;
  }, [data, gates, selectedGateId]);

  return (
    <div ref={containerRef} style={{ position: "relative", width: "100%" }}>
      <canvas
        id={canvasId}
        ref={canvasRef}
        style={{ width: "100%", height, display: "block", touchAction: "none" }}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={() => {
          setDragStart(null);
          setDragCurrent(null);
        }}
        onClick={onClick}
        onWheel={onWheel}
        onDoubleClick={() => {
          if (mode === "polygon") finishPolygon();
        }}
      />
      {mode === "polygon" && (
        <div
          style={{
            position: "absolute",
            top: 8,
            left: "50%",
            transform: "translateX(-50%)",
            display: "flex",
            gap: 8,
            background: "#FFFFFF",
            border: "0.5px solid rgba(0,0,0,0.08)",
            borderRadius: 8,
            padding: "4px 8px",
            boxShadow: "0 1px 4px rgba(0,0,0,0.08)",
            alignItems: "center",
          }}
        >
          <span style={{ fontSize: 12, color: "#6B7280" }}>{polygonDraft.length} 个顶点</span>
          <button
            onClick={finishPolygon}
            disabled={polygonDraft.length < 3}
            style={{ fontSize: 12, padding: "2px 8px", cursor: polygonDraft.length >= 3 ? "pointer" : "not-allowed" }}
          >
            完成
          </button>
          <button onClick={cancelPolygon} style={{ fontSize: 12, padding: "2px 8px", cursor: "pointer" }}>
            取消
          </button>
        </div>
      )}
      {selectedGateId && gateStats[selectedGateId] != null && (
        <div
          style={{
            position: "absolute",
            bottom: 8,
            right: 8,
            background: "rgba(255,255,255,0.92)",
            border: "0.5px solid rgba(0,0,0,0.08)",
            borderRadius: 8,
            padding: "6px 10px",
            fontSize: 12,
            color: "#1A1B1C",
          }}
        >
          选中门「{gates.find((g) => g.id === selectedGateId)?.name}」：采样点占比{" "}
          {gateStats[selectedGateId].toFixed(1)}%
        </div>
      )}
    </div>
  );
}
