from __future__ import annotations

import asyncio
import os
import queue
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from configs.parameters import Fastener_KV, RailParams, VehicleParams
from desktop_backend.database import SimulationDatabase
from desktop_backend.models import SimulationConfig, SimulationCreateResponse, SimulationStatus
from desktop_backend.result_reader import read_result_summary
from desktop_backend.runner import SimulationRunner


app = FastAPI(title="VTCM Desktop Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "app://local"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = SimulationDatabase()
runner = SimulationRunner(db)


def _status_from_row(row: dict) -> SimulationStatus:
    return SimulationStatus(
        run_id=row["run_id"],
        status=row["status"],
        progress=float(row["progress"]),
        current_step=int(row["current_step"]),
        total_steps=int(row["total_steps"]),
        message=row["message"],
        result_path=row["result_path"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


def _parse_external_files(items: List[str]) -> dict:
    parsed = {}
    for item in items or []:
        if "=" in item:
            key, value = item.split("=", 1)
            parsed[key.strip()] = value.strip()
    return parsed


def run_preflight(config: SimulationConfig) -> dict:
    missing = []
    warnings = []

    curve_path = Path(config.curve_file_dir)
    gradient_path = Path(config.gradient_file_dir)
    profile_dir = Path(config.param_profile_dir)
    rail_profile = Path("Profile_file/rail_fade.txt")
    wheel_profile = Path("Profile_file/wheel_fade.txt")

    if not curve_path.exists():
        missing.append(f"曲线台账文件不存在：{config.curve_file_dir}")
    if not gradient_path.exists():
        missing.append(f"坡度台账文件不存在：{config.gradient_file_dir}")
    if not profile_dir.exists():
        missing.append(f"参数目录不存在：{config.param_profile_dir}")
    if not rail_profile.exists():
        missing.append("钢轨廓形文件缺失：Profile_file/rail_fade.txt")
    if not wheel_profile.exists():
        missing.append("车轮廓形文件缺失：Profile_file/wheel_fade.txt")

    if config.tz <= 0:
        missing.append("仿真时长必须大于 0")
    if config.tstep <= 0:
        missing.append("积分步长必须大于 0")
    if config.N_sub <= 0:
        missing.append("轨下离散单元数量必须大于 0")

    if config.irr_type == "外部导入":
        ext = _parse_external_files(config.external_files)
        for key in ["VL", "VR", "LL", "LR"]:
            value = ext.get(key)
            if not value:
                missing.append(f"外部不平顺缺少 {key} 通道文件")
            elif not Path(value).exists():
                missing.append(f"外部不平顺 {key} 文件不存在：{value}")

    if curve_path.exists() and gradient_path.exists():
        try:
            curve_data = pd.read_csv(curve_path)
            gradient_data = pd.read_csv(gradient_path)
            ledger_min = min(curve_data["Start"].min(), gradient_data["Start"].min())
            ledger_max = max(curve_data["End"].max(), gradient_data["End"].max())
            if not (ledger_min <= config.start_mileage <= ledger_max):
                missing.append(
                    f"起始里程 {config.start_mileage:.6f} km 不在台账范围 "
                    f"[{ledger_min:.6f}, {ledger_max:.6f}] km 内"
                )
            required_curve = {"Start", "End", "Curve Radius", "Superelevation"}
            required_gradient = {"Start", "End", "Gradient"}
            if not required_curve.issubset(set(curve_data.columns)):
                missing.append("曲线台账列不完整，需要 Start、End、Curve Radius、Superelevation")
            if not required_gradient.issubset(set(gradient_data.columns)):
                missing.append("坡度台账列不完整，需要 Start、End、Gradient")
        except Exception as exc:
            missing.append(f"台账文件读取失败：{type(exc).__name__}: {exc}")

    try:
        results_dir = Path("results")
        results_dir.mkdir(exist_ok=True)
        test_file = results_dir / ".desktop_write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
    except Exception as exc:
        missing.append(f"results 目录不可写：{type(exc).__name__}: {exc}")

    estimated_steps = int(round((config.tz + (config.irr_lead_time if config.irr_type in ["随机不平顺", "外部导入"] else 0)) / config.tstep))
    if estimated_steps > 80000:
        warnings.append(f"预计积分步数约 {estimated_steps}，计算时间可能较长")
    if config.save_dof_mode == "full" and config.N_sub >= 2000:
        warnings.append("保存 full 全系统自由度会生成较大结果文件，首版建议使用 vehicle")

    return {"ok": not missing, "missing": missing, "warnings": warnings}


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "standard_profile_exists": Path("configs/standard").exists(),
        "profile_files_exist": Path("Profile_file/rail_fade.txt").exists()
        and Path("Profile_file/wheel_fade.txt").exists(),
        "results_writable": Path("results").exists() or Path(".").exists(),
    }


@app.head("/api/health")
def health_head():
    return None


@app.get("/api/metadata")
def metadata():
    try:
        vehicle_presets = VehicleParams(vehicle_type="高速客车")._PRESETS
        vehicle_types = (
            list(vehicle_presets.get("客车", {}).keys())
            + list(vehicle_presets.get("机车", {}).keys())
            + list(vehicle_presets.get("货车", {}).keys())
        )
    except Exception:
        vehicle_types = ["高速客车", "提速客车", "普通客车"]

    try:
        rail_types = list(RailParams(rail_type="CHN60")._PRESETS.keys())
    except Exception:
        rail_types = ["CHN60"]

    try:
        fastener_types = list(Fastener_KV(fastener_type="Standard_KV")._PRESETS.keys())
    except Exception:
        fastener_types = ["Standard_KV"]

    return {
        "defaults": SimulationConfig().model_dump(),
        "vehicle_types": vehicle_types,
        "rail_types": rail_types,
        "fastener_types": fastener_types,
        "irr_types": ["外部导入", "随机不平顺", "谐波不平顺", "无不平顺"],
        "psd_types": ["高铁谱", "干线谱", "美国谱", "德国低干扰谱"],
    }


@app.post("/api/preflight")
def preflight(config: SimulationConfig):
    return run_preflight(config)


def _sample_indices(n: int, max_points: int = 1600):
    if n <= max_points:
        return np.arange(n)
    return np.linspace(0, n - 1, max_points).astype(int)


@app.get("/api/alignment/preview")
def alignment_preview(
    curve_file_dir: str = Query(...),
    gradient_file_dir: str = Query(...),
    start_mileage: Optional[float] = None,
    window_m: float = 5000.0,
):
    curve_path = Path(curve_file_dir)
    gradient_path = Path(gradient_file_dir)
    if not curve_path.exists():
        raise HTTPException(status_code=404, detail=f"曲线台账不存在: {curve_file_dir}")
    if not gradient_path.exists():
        raise HTTPException(status_code=404, detail=f"坡度台账不存在: {gradient_file_dir}")

    curve_data = pd.read_csv(curve_path)
    gradient_data = pd.read_csv(gradient_path)
    min_s = min(curve_data["Start"].min(), gradient_data["Start"].min()) * 1000.0
    max_s = max(curve_data["End"].max(), gradient_data["End"].max()) * 1000.0
    if start_mileage is not None:
        center = start_mileage * 1000.0
        min_s = max(min_s, center - window_m * 0.25)
        max_s = min(max_s, center + window_m * 0.75)
    s_grid = np.linspace(min_s, max_s, min(4000, max(2, int((max_s - min_s) / 2.0))))
    k_grid = np.zeros_like(s_grid)
    h_grid = np.zeros_like(s_grid)
    g_grid = np.zeros_like(s_grid)

    for _, row in curve_data.iterrows():
        zh = float(row["Start"]) * 1000.0
        hz = float(row["End"]) * 1000.0
        l1 = float(row.get("Initial Transition Length", 0.0) or 0.0)
        l2 = float(row.get("Final Transition Length", 0.0) or 0.0)
        hy = zh + l1
        yh = hz - l2
        radius = float(row.get("Curve Radius", 0.0) or 0.0)
        direction = str(row.get("Curve Direction", "Left"))
        sign = 1.0 if direction.lower() == "left" or direction == "左" else -1.0
        target_k = sign / radius if radius else 0.0
        target_h = float(row.get("Superelevation", 0.0) or 0.0) * 0.001

        m1 = (s_grid >= zh) & (s_grid < hy)
        if l1 > 0:
            k_grid[m1] = target_k * (s_grid[m1] - zh) / l1
            h_grid[m1] = target_h * (s_grid[m1] - zh) / l1
        m2 = (s_grid >= hy) & (s_grid <= yh)
        k_grid[m2] = target_k
        h_grid[m2] = target_h
        m3 = (s_grid > yh) & (s_grid <= hz)
        if l2 > 0:
            k_grid[m3] = target_k * (hz - s_grid[m3]) / l2
            h_grid[m3] = target_h * (hz - s_grid[m3]) / l2

    for _, row in gradient_data.iterrows():
        start = float(row["Start"]) * 1000.0
        end = float(row["End"]) * 1000.0
        gradient = float(row["Gradient"]) * 0.001
        mask = (s_grid >= start) & (s_grid <= end)
        g_grid[mask] = gradient

    ds = np.gradient(s_grid)
    z_profile = np.cumsum(g_grid * ds)
    idx = _sample_indices(len(s_grid))
    choices = sorted(
        set(round(float(v), 6) for v in curve_data["Start"].tolist() + gradient_data["Start"].tolist())
    )
    return {
        "mileage_choices": choices[:1000],
        "series": {
            "mileage_km": (s_grid[idx] / 1000.0).tolist(),
            "curvature": k_grid[idx].tolist(),
            "cant_m": h_grid[idx].tolist(),
            "gradient": g_grid[idx].tolist(),
            "vertical_profile_m": z_profile[idx].tolist(),
        },
    }


def _read_two_column_file(path: Path) -> np.ndarray:
    try:
        df = pd.read_csv(path, sep=None, engine="python", comment="#", header=None)
        values = df.iloc[:, :2].apply(pd.to_numeric, errors="coerce").dropna().to_numpy(dtype=float)
    except Exception:
        values = np.loadtxt(path)
        if values.ndim == 1:
            values = values.reshape(-1, 2)
        values = values[:, :2]
    return values


@app.get("/api/irregularity/preview")
def irregularity_preview(
    irr_type: str = "外部导入",
    psd_type: str = "高铁谱",
    files: List[str] = Query(default=[]),
    start_mileage: Optional[float] = None,
    duration_s: float = 5.0,
    speed_kmh: float = 215.0,
):
    sim_length = max(0.0, float(duration_s)) * max(0.0, float(speed_kmh)) / 3.6

    def _clip_to_simulation(values: np.ndarray) -> np.ndarray:
        if values.size == 0:
            return values
        out = values.copy()
        x = out[:, 0].astype(float)
        if start_mileage is not None and np.nanmax(np.abs(x)) < 1.0e4:
            x_m = (x - float(start_mileage)) * 1000.0
        elif start_mileage is not None and np.nanmax(np.abs(x)) >= 1.0e4:
            x_m = x - float(start_mileage) * 1000.0
        else:
            x_m = x - float(x[0])
        mask = (x_m >= 0.0) & (x_m <= sim_length if sim_length > 0 else True)
        clipped = out[mask]
        if clipped.size == 0:
            clipped = out[: min(len(out), 1600)]
        return clipped

    if irr_type != "外部导入":
        x = np.linspace(0.0, sim_length if sim_length > 0 else 500.0, 1200)
        if irr_type == "无不平顺":
            y = np.zeros_like(x)
        elif irr_type == "谐波不平顺":
            y = 0.008 * np.sin(2 * np.pi * x / 10.0)
        else:
            rng = np.random.default_rng(20260609)
            y = np.cumsum(rng.normal(0.0, 0.00003, size=x.shape))
        series = {"preview": {"x": x.tolist(), "y": y.tolist()}}
        return {
            "template": psd_type,
            "full_available": False,
            "series": series,
            "simulation_series": series,
            "full_series": {},
        }

    full_parsed = {}
    simulation_parsed = {}
    for item in files:
        if "=" in item:
            key, raw_path = item.split("=", 1)
        else:
            key, raw_path = Path(item).stem, item
        path = Path(raw_path)
        if not path.exists():
            continue
        values = _read_two_column_file(path)
        idx = _sample_indices(len(values))
        full_parsed[key.strip()] = {
            "x": values[idx, 0].tolist(),
            "y": values[idx, 1].tolist(),
        }
        sim_values = _clip_to_simulation(values)
        sim_idx = _sample_indices(len(sim_values))
        simulation_parsed[key.strip()] = {
            "x": sim_values[sim_idx, 0].tolist(),
            "y": sim_values[sim_idx, 1].tolist(),
        }
    return {
        "template": "external-two-column",
        "full_available": bool(full_parsed),
        "series": simulation_parsed,
        "simulation_series": simulation_parsed,
        "full_series": full_parsed,
    }


@app.post("/api/simulations", response_model=SimulationCreateResponse)
def create_simulation(config: SimulationConfig):
    check = run_preflight(config)
    if not check["ok"]:
        raise HTTPException(status_code=400, detail=check)
    run_id = runner.submit(config)
    return SimulationCreateResponse(run_id=run_id)


@app.get("/api/simulations/{run_id}", response_model=SimulationStatus)
def get_simulation(run_id: str):
    row = db.get(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return _status_from_row(row)


@app.post("/api/simulations/{run_id}/cancel")
def cancel_simulation(run_id: str):
    if not runner.cancel(run_id):
        raise HTTPException(status_code=404, detail="Simulation not found")
    return {"ok": True}


@app.get("/api/results", response_model=List[SimulationStatus])
def list_results():
    return [_status_from_row(row) for row in db.list()]


@app.get("/api/results/{run_id}")
def get_result(run_id: str):
    row = db.get(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Simulation not found")
    if not row["result_path"]:
        raise HTTPException(status_code=409, detail="Simulation has no result file yet")
    try:
        return read_result_summary(run_id, row["result_path"])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Result file not found")


@app.websocket("/api/simulations/{run_id}/events")
async def simulation_events(websocket: WebSocket, run_id: str):
    await websocket.accept()
    q = runner.get_queue(run_id)
    try:
        while True:
            try:
                event = await asyncio.to_thread(q.get, True, 1.0)
                await websocket.send_json(event)
            except queue.Empty:
                await websocket.send_json({"type": "heartbeat", "run_id": run_id})
    except WebSocketDisconnect:
        return


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("VTCM_BACKEND_PORT", "18765"))
    uvicorn.run("desktop_backend.main:app", host="127.0.0.1", port=port, reload=False)
