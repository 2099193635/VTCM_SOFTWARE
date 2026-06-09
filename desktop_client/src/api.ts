export type SimulationStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface SimulationConfig {
  vx_set: number;
  tz: number;
  tstep: number;
  start_mileage: number;
  curve_file_dir: string;
  gradient_file_dir: string;
  cache_file_dir: string;
  force_rebuild: "On" | "Off";
  vehicle_type: string;
  rail_type: string;
  fastener_type: string;
  param_profile_dir: string;
  irr_type: string;
  irr_lead_time: number;
  psd_type: string;
  defect_switch: "on" | "off";
  input_path: string;
  output_path: string;
  external_mileage_mode: "absolute" | "relative";
  external_distance_unit: "m" | "km";
  Type2: "空间谱" | "时间谱" | "时间序列";
  external_files: string[];
  N_sub: number;
  X0: number;
  alpha: number;
  beta: number;
  g: number;
  switch_curve_track: "On" | "Off";
  switch_2point_contact: "On" | "Off";
  switch_extra_force_element: "On" | "Off";
  switch_pad_zone: "On" | "Off";
  switch_pad_partition: "On" | "Off";
  switch_railcant_unsymmetric: "On" | "Off";
  switch_lock_veh_non_z: "On" | "Off";
  switch_lock_axlebox: "On" | "Off";
  switch_lock_substructure: "On" | "Off";
  save_data: "On" | "Off";
  save_dof_mode: "full" | "vehicle";
  project_name: string;
  run_note: string;
  plot_figs: "On" | "Off";
}

export interface Metadata {
  defaults: SimulationConfig;
  vehicle_types: string[];
  rail_types: string[];
  fastener_types: string[];
  irr_types: string[];
  psd_types: string[];
}

export interface AlignmentPreview {
  mileage_choices: number[];
  series: {
    mileage_km: number[];
    curvature: number[];
    cant_m: number[];
    gradient: number[];
    vertical_profile_m: number[];
  };
}

export interface IrregularityPreview {
  template: string;
  full_available: boolean;
  series: Record<string, { x: number[]; y: number[] }>;
  simulation_series: Record<string, { x: number[]; y: number[] }>;
  full_series: Record<string, { x: number[]; y: number[] }>;
}

export interface SimulationRecord {
  run_id: string;
  status: SimulationStatus;
  progress: number;
  current_step: number;
  total_steps: number;
  message: string;
  result_path?: string;
  created_at: string;
  started_at?: string;
  finished_at?: string;
}

export interface ResultSummary {
  run_id: string;
  result_path: string;
  dt: number;
  steps: number;
  duration: number;
  channels: Record<string, [number, number]>;
  series: Record<string, number[]>;
  groups?: ResultPlotGroup[];
}

export interface ResultPlotSeries {
  key: string;
  name: string;
  x: number[];
  y: number[];
}

export interface ResultPlotGroup {
  key: string;
  title: string;
  x_name: string;
  x_unit: string;
  y_name: string;
  y_unit: string;
  series: ResultPlotSeries[];
}

export interface PreflightResult {
  ok: boolean;
  missing: string[];
  warnings: string[];
}

export async function getBackendUrl() {
  if (window.vtcm) return window.vtcm.backendUrl();
  return "http://127.0.0.1:18765";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const base = await getBackendUrl();
  const response = await fetch(`${base}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || response.statusText);
  }
  return response.json() as Promise<T>;
}

export const api = {
  metadata: () => request<Metadata>("/api/metadata"),
  createSimulation: (config: SimulationConfig) =>
    request<{ run_id: string }>("/api/simulations", {
      method: "POST",
      body: JSON.stringify(config)
    }),
  preflight: (config: SimulationConfig) =>
    request<PreflightResult>("/api/preflight", {
      method: "POST",
      body: JSON.stringify(config)
    }),
  getSimulation: (runId: string) => request<SimulationRecord>(`/api/simulations/${runId}`),
  cancelSimulation: (runId: string) =>
    request<{ ok: boolean }>(`/api/simulations/${runId}/cancel`, { method: "POST" }),
  listResults: () => request<SimulationRecord[]>("/api/results"),
  getResult: (runId: string) => request<ResultSummary>(`/api/results/${runId}`),
  alignmentPreview: (params: {
    curve_file_dir: string;
    gradient_file_dir: string;
    start_mileage?: number;
  }) => {
    const query = new URLSearchParams({
      curve_file_dir: params.curve_file_dir,
      gradient_file_dir: params.gradient_file_dir
    });
    if (params.start_mileage !== undefined) query.set("start_mileage", String(params.start_mileage));
    return request<AlignmentPreview>(`/api/alignment/preview?${query.toString()}`);
  },
  irregularityPreview: (params: {
    irr_type: string;
    psd_type: string;
    files: string[];
    start_mileage?: number;
    duration_s?: number;
    speed_kmh?: number;
  }) => {
    const query = new URLSearchParams({ irr_type: params.irr_type, psd_type: params.psd_type });
    if (params.start_mileage !== undefined) query.set("start_mileage", String(params.start_mileage));
    if (params.duration_s !== undefined) query.set("duration_s", String(params.duration_s));
    if (params.speed_kmh !== undefined) query.set("speed_kmh", String(params.speed_kmh));
    params.files.forEach((file) => query.append("files", file));
    return request<IrregularityPreview>(`/api/irregularity/preview?${query.toString()}`);
  }
};
