/** 后端 API 客户端类型与封装 */

// 直连 FastAPI 后端：不要经 Next.js rewrites 代理上传大文件
// （Next.js 代理默认 10MB 请求体上限，FCS 文件常超过该值）。
// 部署时通过 NEXT_PUBLIC_API_BASE_URL 环境变量覆盖。
const API_BASE: string =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export interface FcsSummary {
  filename: string;
  event_count: number;
  channel_count: number;
  channel_labels: string[];
  scatter_labels: string[];
  sample_id: string | null;
  has_spillover: boolean;
  /** 补偿是否实际应用成功（False=无矩阵或矩阵损坏静默降级） */
  compensation_applied: boolean;
}

export interface FileUploadResponse {
  file_id: string;
  summary: FcsSummary;
}

/**
 * 上传 FCS 文件到后端并解析。
 */
export async function uploadFcs(file: File): Promise<FileUploadResponse> {
  const form = new FormData();
  form.append("file", file);

  const resp = await fetch(`${API_BASE}/api/files/upload`, {
    method: "POST",
    body: form,
  });

  if (!resp.ok) {
    throw new Error(await readErrorDetail(resp, "上传失败"));
  }

  return (await resp.json()) as FileUploadResponse;
}

async function readErrorDetail(resp: Response, fallback: string): Promise<string> {
  try {
    const body = await resp.json();
    if (body && typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    // 忽略非 JSON 响应体
  }
  return `${fallback}（HTTP ${resp.status}）`;
}

/* ---------- 文件 / 事件 / 门控 ---------- */

export interface EventsData {
  x_label: string;
  y_label: string;
  total_events: number;
  sampled: number;
  x: number[];
  y: number[];
  /** 数据空间：raw=原始未补偿，comp=补偿线性，logicle=补偿+logicle 显示 */
  data_space: "raw" | "comp" | "logicle";
  /** 是否实际应用了补偿 */
  compensated: boolean;
  /** 文件有 $SPILLOVER 但补偿失败：当前返回的是未补偿数据 */
  uncompensated_fallback: boolean;
}

export interface GateDef {
  id: string;
  name: string;
  type: "rect" | "polygon";
  x_label: string;
  y_label: string;
  x_min?: number;
  x_max?: number;
  y_min?: number;
  y_max?: number;
  vertices?: number[][];
  parent_id?: string | null;
}

export interface GateEvaluation {
  id: string;
  name: string;
  event_count: number;
  absolute_percent: number;
  relative_percent: number;
  /** 文件有 $SPILLOVER 但补偿失败：统计基于未补偿数据 */
  uncompensated_fallback: boolean;
}

/** 获取已上传文件的解析摘要。 */
export async function fetchFileInfo(fileId: string): Promise<FcsSummary> {
  const resp = await fetch(`${API_BASE}/api/files/${fileId}`);
  if (!resp.ok) throw new Error(await readErrorDetail(resp, "读取文件信息失败"));
  return (await resp.json()) as FcsSummary;
}

/** 获取两通道事件坐标（后端均匀下采样）。 */
export async function fetchEvents(
  fileId: string,
  x: string,
  y: string,
  limit = 20000,
  transform: "raw" | "logicle" = "raw"
): Promise<EventsData> {
  const params = new URLSearchParams({ x, y, limit: String(limit), transform });
  const resp = await fetch(`${API_BASE}/api/files/${fileId}/events?${params}`);
  if (!resp.ok) throw new Error(await readErrorDetail(resp, "读取事件数据失败"));
  return (await resp.json()) as EventsData;
}

/** 读取已保存的门控树。 */
export async function fetchGates(fileId: string): Promise<GateDef[]> {
  const resp = await fetch(`${API_BASE}/api/files/${fileId}/gates`);
  if (!resp.ok) throw new Error(await readErrorDetail(resp, "读取门控失败"));
  const body = (await resp.json()) as { gates: GateDef[] };
  return body.gates;
}

/** 保存门控树。 */
export async function saveGates(fileId: string, gates: GateDef[]): Promise<void> {
  const resp = await fetch(`${API_BASE}/api/files/${fileId}/gates`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ gates }),
  });
  if (!resp.ok) throw new Error(await readErrorDetail(resp, "保存门控失败"));
}

/** 评估门控树，返回每个门的统计。 */
export async function evaluateGates(
  fileId: string,
  gates: GateDef[]
): Promise<GateEvaluation[]> {
  const resp = await fetch(`${API_BASE}/api/files/${fileId}/gates/evaluate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ gates }),
  });
  if (!resp.ok) throw new Error(await readErrorDetail(resp, "评估门控失败"));
  return (await resp.json()) as GateEvaluation[];
}

/** 导出 GatingML 2.0 XML（返回 blob）。 */
export async function exportGatingml(fileId: string): Promise<Blob> {
  const resp = await fetch(`${API_BASE}/api/files/${fileId}/gatingml`);
  if (!resp.ok) throw new Error(await readErrorDetail(resp, "导出 GatingML 失败"));
  return await resp.blob();
}

/** 导入 GatingML 2.0 XML，返回门控树。 */
export async function importGatingml(fileId: string, file: File): Promise<GateDef[]> {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch(`${API_BASE}/api/files/${fileId}/gatingml/import`, {
    method: "POST",
    body: form,
  });
  if (!resp.ok) throw new Error(await readErrorDetail(resp, "导入 GatingML 失败"));
  const body = (await resp.json()) as { gates: GateDef[] };
  return body.gates;
}

/** 导出门控统计 CSV（返回 blob）。 */
export async function exportStatisticsCsv(fileId: string): Promise<Blob> {
  const resp = await fetch(`${API_BASE}/api/files/${fileId}/statistics.csv`);
  if (!resp.ok) throw new Error(await readErrorDetail(resp, "导出统计失败"));
  return await resp.blob();
}

/** 触发浏览器下载一个 Blob。 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
