from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import numpy as np


def _downsample(values: np.ndarray, max_points: int = 1600) -> List[float]:
    arr = np.asarray(values, dtype=float).reshape(-1)
    if arr.size == 0:
        return []
    if arr.size <= max_points:
        return arr.tolist()
    idx = np.linspace(0, arr.size - 1, max_points).astype(int)
    return arr[idx].tolist()


def _safe_col(data, key: str, col: int, n: int) -> np.ndarray:
    if key not in data:
        return np.zeros(n)
    arr = np.asarray(data[key])
    if arr.ndim != 2 or arr.shape[0] != n or arr.shape[1] <= col:
        return np.zeros(n)
    return arr[:, col]


def _safe_state(data, key: str, col: int, n: int) -> np.ndarray:
    if key not in data:
        return np.zeros(n)
    arr = np.asarray(data[key])
    if arr.ndim != 2 or arr.shape[0] != n or arr.shape[1] <= col:
        return np.zeros(n)
    return arr[:, col]


def _add_series(
    target: Dict,
    key: str,
    name: str,
    y: np.ndarray,
    time: np.ndarray,
    max_points: int,
) -> None:
    values = np.asarray(y, dtype=float).reshape(-1)
    if values.size == 0 or not np.isfinite(values).any():
        return
    target["series"].append(
        {
            "key": key,
            "name": name,
            "x": _downsample(time[: values.size], max_points),
            "y": _downsample(values, max_points),
        }
    )


def _make_group(key: str, title: str, y_name: str, y_unit: str, x_name: str = "时间", x_unit: str = "s") -> Dict:
    return {
        "key": key,
        "title": title,
        "x_name": x_name,
        "x_unit": x_unit,
        "y_name": y_name,
        "y_unit": y_unit,
        "series": [],
    }


def read_result_summary(run_id: str, result_path: str, max_points: int = 1600) -> Dict:
    path = Path(result_path)
    if not path.exists():
        raise FileNotFoundError(result_path)

    with np.load(path, allow_pickle=False) as data:
        a = np.asarray(data["A"])
        dt = float(data["dt"])
        n = int(a.shape[0])
        idx_car = int(data["idx_car_start"]) if "idx_car_start" in data else 0
        time = np.arange(n) * dt

        ay = _safe_state(data, "A", idx_car, n)
        az = _safe_state(data, "A", idx_car + 1, n)
        wheel_v = _safe_col(data, "TotalVerticalForce", 0, n)
        wheel_l = _safe_col(data, "TotalLateralForce", 0, n)
        yixi_z = _safe_col(data, "Yixi_Force_z", 0, n)
        erxi_z = _safe_col(data, "Erxi_Force_z", 0, n)
        irr_z = np.asarray(data["Irre_bz_L_ref"]).reshape(-1) if "Irre_bz_L_ref" in data else np.zeros(n)
        track_k = np.asarray(data["Track_curvature_1pm"]).reshape(-1) if "Track_curvature_1pm" in data else np.zeros(n)
        track_rel = np.asarray(data["Track_rel_mileage_m"]).reshape(-1) if "Track_rel_mileage_m" in data else np.arange(n)

        groups = []

        acceleration = _make_group("acceleration", "加速度", "加速度", "m/s²")
        _add_series(acceleration, "carbody_ay", "车体横向", ay, time, max_points)
        _add_series(acceleration, "carbody_az", "车体垂向", az, time, max_points)
        for i, start in enumerate((5, 10), start=1):
            _add_series(acceleration, f"bogie_{i}_ay", f"构架{i}横向", _safe_state(data, "A", idx_car + start, n), time, max_points)
            _add_series(acceleration, f"bogie_{i}_az", f"构架{i}垂向", _safe_state(data, "A", idx_car + start + 1, n), time, max_points)
        for i, start in enumerate((15, 20, 25, 30), start=1):
            _add_series(acceleration, f"wheelset_{i}_ay", f"轮对{i}横向", _safe_state(data, "A", idx_car + start, n), time, max_points)
            _add_series(acceleration, f"wheelset_{i}_az", f"轮对{i}垂向", _safe_state(data, "A", idx_car + start + 1, n), time, max_points)
        groups.append(acceleration)

        wheel_rail = _make_group("wheel_rail_force", "轮轨力", "力", "N")
        for col in range(np.asarray(data["TotalVerticalForce"]).shape[1] if "TotalVerticalForce" in data else 0):
            _add_series(wheel_rail, f"wheel_rail_vertical_{col + 1}", f"轮轨垂向力{col + 1}", _safe_col(data, "TotalVerticalForce", col, n), time, max_points)
        for col in range(np.asarray(data["TotalLateralForce"]).shape[1] if "TotalLateralForce" in data else 0):
            _add_series(wheel_rail, f"wheel_rail_lateral_{col + 1}", f"轮轨横向力{col + 1}", _safe_col(data, "TotalLateralForce", col, n), time, max_points)
        groups.append(wheel_rail)

        suspension = _make_group("suspension_force", "一二系悬挂力", "力", "N")
        for col in range(np.asarray(data["Yixi_Force_z"]).shape[1] if "Yixi_Force_z" in data else 0):
            _add_series(suspension, f"primary_vertical_{col + 1}", f"一系垂向力{col + 1}", _safe_col(data, "Yixi_Force_z", col, n), time, max_points)
        for col in range(np.asarray(data["Erxi_Force_z"]).shape[1] if "Erxi_Force_z" in data else 0):
            _add_series(suspension, f"secondary_vertical_{col + 1}", f"二系垂向力{col + 1}", _safe_col(data, "Erxi_Force_z", col, n), time, max_points)
        groups.append(suspension)

        irregularity = _make_group("irregularity", "不平顺", "不平顺", "m", x_name="距离", x_unit="m")
        for key, name in [
            ("Irre_bz_L_ref", "左轨高低"),
            ("Irre_bz_R_ref", "右轨高低"),
            ("Irre_by_L_ref", "左轨方向"),
            ("Irre_by_R_ref", "右轨方向"),
        ]:
            if key in data:
                dist = np.asarray(data["Irre_distance_m"]).reshape(-1) if "Irre_distance_m" in data else np.arange(np.asarray(data[key]).size)
                _add_series(irregularity, key, name, np.asarray(data[key]).reshape(-1), dist, max_points)
        groups.append(irregularity)

        track = _make_group("track_geometry", "线路几何", "线路参数", "m / 1/m", x_name="相对里程", x_unit="m")
        for key, name in [
            ("Track_curvature_1pm", "曲率"),
            ("Track_cant_m", "超高"),
            ("Track_gradient", "坡度"),
            ("Track_vertical_profile_m", "纵断面"),
        ]:
            if key in data:
                _add_series(track, key, name, np.asarray(data[key]).reshape(-1), track_rel, max_points)
        groups.append(track)

        groups = [group for group in groups if group["series"]]

        channels = {
            "carbody_az_range": [float(np.nanmin(az)), float(np.nanmax(az))],
            "carbody_ay_range": [float(np.nanmin(ay)), float(np.nanmax(ay))],
            "wheel_vertical_force_range": [float(np.nanmin(wheel_v)), float(np.nanmax(wheel_v))],
            "wheel_lateral_force_range": [float(np.nanmin(wheel_l)), float(np.nanmax(wheel_l))],
        }
        series = {
            "time": _downsample(time, max_points),
            "carbody_az": _downsample(az, max_points),
            "carbody_ay": _downsample(ay, max_points),
            "wheel_vertical_force": _downsample(wheel_v, max_points),
            "wheel_lateral_force": _downsample(wheel_l, max_points),
            "primary_vertical_force": _downsample(yixi_z, max_points),
            "secondary_vertical_force": _downsample(erxi_z, max_points),
            "irregularity_left_vertical": _downsample(irr_z[:n], max_points),
            "track_curvature": _downsample(track_k[:n], max_points),
        }

    return {
        "run_id": run_id,
        "result_path": str(path),
        "dt": dt,
        "steps": n,
        "duration": float((n - 1) * dt) if n else 0.0,
        "channels": channels,
        "series": series,
        "groups": groups,
    }
