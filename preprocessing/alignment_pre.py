from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common_io import ensure_mileage_sorted, save_csv


CHANNEL_MAP: Dict[str, Tuple[str, str]] = {
    "左高低": ("左高低", "实测左高低"),
    "右高低": ("右高低", "实测右高低"),
    "左轨向": ("左轨向", "实测左轨向"),
    "右轨向": ("右轨向", "实测右轨向"),
    "三角坑": ("三角坑", "实测三角坑"),
    "轨距": ("轨距", "实测轨距"),
    "超高": ("超高", "实测水平"),
}


def _interp_channel(df: pd.DataFrame, x_grid: np.ndarray, y_col: str) -> np.ndarray:
    x = pd.to_numeric(df["里程"], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(df[y_col], errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    if valid.sum() < 2:
        return np.full_like(x_grid, np.nan)
    x2 = x[valid]
    y2 = y[valid]
    order = np.argsort(x2)
    x2 = x2[order]
    y2 = y2[order]
    return np.interp(x_grid, x2, y2)


def estimate_shift_by_superelevation(
    dynamic_df: pd.DataFrame,
    static_df: pd.DataFrame,
    max_shift_m: float = 0.8,
    grid_step_km: float = 0.0001,
) -> float:
    """基于超高/水平通道估计里程偏移量，返回单位 km（加到静检里程上）。"""
    if "超高" not in dynamic_df.columns or "实测水平" not in static_df.columns:
        return 0.0

    ddf = ensure_mileage_sorted(dynamic_df)
    sdf = ensure_mileage_sorted(static_df)

    x0 = max(ddf["里程"].min(), sdf["里程"].min())
    x1 = min(ddf["里程"].max(), sdf["里程"].max())
    if not np.isfinite(x0) or not np.isfinite(x1) or x1 <= x0:
        return 0.0

    grid = np.arange(x0, x1, grid_step_km)
    if len(grid) < 100:
        return 0.0

    dyn = _interp_channel(ddf, grid, "超高")
    sta = _interp_channel(sdf, grid, "实测水平")
    valid = np.isfinite(dyn) & np.isfinite(sta)
    dyn = dyn[valid]
    sta = sta[valid]
    if len(dyn) < 200:
        return 0.0

    dyn = dyn - np.nanmean(dyn)
    sta = sta - np.nanmean(sta)

    corr = np.correlate(dyn, sta, mode="full")
    lags = np.arange(-len(sta) + 1, len(dyn))
    max_lag = int(max_shift_m / (grid_step_km * 1000.0))
    keep = np.abs(lags) <= max_lag
    if keep.sum() == 0:
        return 0.0

    best_lag = int(lags[keep][np.argmax(corr[keep])])
    return float(best_lag * grid_step_km)


def apply_shift_to_static(static_df: pd.DataFrame, shift_km: float) -> pd.DataFrame:
    out = static_df.copy()
    out["里程"] = pd.to_numeric(out["里程"], errors="coerce") + shift_km
    return ensure_mileage_sorted(out)


def get_alignment_range(
    dynamic_df: pd.DataFrame,
    static_df: pd.DataFrame,
    prefer_static: bool = True,
) -> tuple[float, float]:
    """
    获取对齐里程范围（单位 km）。
    - 默认以静检范围为主，再与动检取交集；
    - 若交集无效，退化为两者的严格交集检查。
    """
    dmin = float(pd.to_numeric(dynamic_df["里程"], errors="coerce").min())
    dmax = float(pd.to_numeric(dynamic_df["里程"], errors="coerce").max())
    smin = float(pd.to_numeric(static_df["里程"], errors="coerce").min())
    smax = float(pd.to_numeric(static_df["里程"], errors="coerce").max())

    if prefer_static:
        x0 = max(dmin, smin)
        x1 = min(dmax, smax)
    else:
        x0 = max(dmin, smin)
        x1 = min(dmax, smax)

    if not (np.isfinite(x0) and np.isfinite(x1) and x1 > x0):
        raise ValueError("动静检里程范围无有效交集，无法对齐。")
    return x0, x1


def clip_by_mileage_range(df: pd.DataFrame, x0: float, x1: float, mileage_col: str = "里程") -> pd.DataFrame:
    out = df.copy()
    out[mileage_col] = pd.to_numeric(out[mileage_col], errors="coerce")
    out = out[out[mileage_col].between(x0, x1, inclusive="both")]
    return ensure_mileage_sorted(out, mileage_col=mileage_col)


def plot_alignment_before_after(
    dynamic_df: pd.DataFrame,
    static_before: pd.DataFrame,
    static_after: pd.DataFrame,
    out_file: str | Path,
    focus_change_quantile: float = 0.90,
) -> Path:
    out_file = Path(out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    # 关注超高变化段
    x_s = pd.to_numeric(static_after["里程"], errors="coerce").to_numpy(dtype=float)
    y_s = pd.to_numeric(static_after.get("实测水平", np.nan), errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(x_s) & np.isfinite(y_s)
    if valid.sum() > 10:
        xs = x_s[valid]
        ys = y_s[valid]
        grad = np.abs(np.gradient(ys, xs))
        thr = np.quantile(grad[np.isfinite(grad)], focus_change_quantile)
        hot = grad >= thr
        if hot.any():
            x_min = float(xs[hot].min())
            x_max = float(xs[hot].max())
            pad = max(0.01, (x_max - x_min) * 0.2)
            xlim = (x_min - pad, x_max + pad)
        else:
            xlim = (float(np.nanmin(xs)), float(np.nanmax(xs)))
    else:
        xlim = None

    fig, axes = plt.subplots(7, 1, figsize=(16, 22), sharex=True, constrained_layout=True)

    for ax, (name, (d_col, s_col)) in zip(axes, CHANNEL_MAP.items()):
        if d_col in dynamic_df.columns:
            ax.plot(dynamic_df["里程"], dynamic_df[d_col], color="#1f77b4", lw=1.0, label=f"动检-{name}")
        if s_col in static_before.columns:
            ax.plot(static_before["里程"], static_before[s_col], color="#ff7f0e", lw=0.9, ls="--", label=f"静检对齐前-{name}")
        if s_col in static_after.columns:
            ax.plot(static_after["里程"], static_after[s_col], color="#2ca02c", lw=0.9, ls="-.", label=f"静检对齐后-{name}")

        ax.set_ylabel(name)
        ax.grid(True, alpha=0.35, ls="--")
        ax.legend(fontsize=8, loc="upper right")
        if xlim is not None:
            ax.set_xlim(*xlim)

    axes[-1].set_xlabel("绝对里程 (km)")
    fig.suptitle("动静检对齐前后对比（按超高变化段聚焦）", fontsize=14)
    fig.savefig(out_file, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return out_file


def save_aligned_results(
    dynamic_df: pd.DataFrame,
    static_aligned_df: pd.DataFrame,
    dynamic_out: str | Path,
    static_out: str | Path,
) -> tuple[Path, Path]:
    p1 = save_csv(dynamic_df, dynamic_out)
    p2 = save_csv(static_aligned_df, static_out)
    return p1, p2
