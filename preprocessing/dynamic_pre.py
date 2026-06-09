from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd

from common_io import detect_text_encoding, ensure_mileage_sorted, save_csv


DYNAMIC_CHANNEL_MAP: Dict[str, list[str]] = {
    "左高低": ["左高低(mm)", "左高低", "高低左", "左高低值"],
    "右高低": ["右高低(mm)", "右高低", "高低右", "右高低值"],
    "左轨向": ["左轨向(mm)", "左轨向", "轨向左", "左轨向值"],
    "右轨向": ["右轨向(mm)", "右轨向", "轨向右", "右轨向值"],
    "三角坑": ["三角坑(mm)", "三角坑"],
    "轨距": ["轨距(mm)", "轨距"],
    "超高": ["超高(mm)", "超高"],
    "水平": ["水平(mm)", "水平"],
    "横向加速度(g)": ["横向加速度(g)", "横向加速度"],
    "垂向加速度(g)": ["垂向加速度(g)", "垂向加速度"],
}


def _pick_column(df: pd.DataFrame, aliases: list[str], fallback_index: int | None = None) -> str | None:
    cols = [str(c).strip() for c in df.columns]
    lower_map = {c.lower(): c for c in cols}

    for a in aliases:
        if a in cols:
            return a
        if a.lower() in lower_map:
            return lower_map[a.lower()]

    for c in cols:
        if any(k in c for k in aliases):
            return c

    if fallback_index is not None and 0 <= fallback_index < len(cols):
        return cols[fallback_index]
    return None


def read_dynamic_txt(file_path: str | Path) -> pd.DataFrame:
    p = Path(file_path)
    enc = detect_text_encoding(p)

    # 该文件通常是逗号分隔，第一行为标题
    df = pd.read_csv(p, encoding=enc, engine="python")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def unify_dynamic_mileage(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    统一动检里程为绝对里程(km)：
    绝对里程 = 公里标 + Meters / 1000
    """
    cols = [str(c).strip() for c in raw_df.columns]

    col_km = _pick_column(raw_df, ["公里标", "Kilometer", "KM"], fallback_index=0)
    col_m = _pick_column(raw_df, ["Meters", "米", "里程偏移"], fallback_index=1)
    if col_km is None or col_m is None:
        raise ValueError("动检文件缺少公里标/米偏移列，无法统一里程。")

    km = pd.to_numeric(raw_df[col_km], errors="coerce")
    meters = pd.to_numeric(raw_df[col_m], errors="coerce")

    out = pd.DataFrame({"里程": km + meters / 1000.0})

    # 优先按别名匹配；若编码导致乱码，退化使用固定列位置
    fallback_idx = {
        "左高低": 4,
        "右高低": 5,
        "左轨向": 6,
        "右轨向": 7,
        "轨距": 8,
        "超高": 9,
        "水平": 10,
        "三角坑": 11,
    }

    for std_name, aliases in DYNAMIC_CHANNEL_MAP.items():
        c = _pick_column(raw_df, aliases, fallback_index=fallback_idx.get(std_name))
        if c is not None:
            out[std_name] = pd.to_numeric(raw_df[c], errors="coerce")

    out = ensure_mileage_sorted(out, "里程")
    return out


def process_dynamic_file(raw_file: str | Path, save_file: str | Path | None = None) -> pd.DataFrame:
    raw_df = read_dynamic_txt(raw_file)
    dynamic_df = unify_dynamic_mileage(raw_df)
    if save_file is not None:
        save_csv(dynamic_df, save_file, encoding="utf-8-sig")
    return dynamic_df
