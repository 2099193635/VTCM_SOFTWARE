from __future__ import annotations

from dataclasses import asdict, dataclass
from types import SimpleNamespace
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


Switch = Literal["On", "Off"]


class SimulationConfig(BaseModel):
    vx_set: float = Field(215.0, gt=0)
    tz: float = Field(5.0, gt=0)
    tstep: float = Field(1e-4, gt=0)
    start_mileage: float = 271.82269772001104
    curve_file_dir: str = "preprocessing/台账/处理后/curve_parameters.csv"
    gradient_file_dir: str = "preprocessing/台账/处理后/gradient_parameters.csv"
    cache_file_dir: str = "configs/track_cache.npz"
    force_rebuild: Switch = "Off"

    vehicle_type: str = "高速客车"
    rail_type: str = "CHN60"
    fastener_type: str = "Standard_KV"
    param_profile_dir: str = "configs/standard"

    irr_type: str = "外部导入"
    irr_lead_time: float = Field(2.0, ge=0)
    psd_type: str = "高铁谱"
    defect_switch: Literal["on", "off"] = "off"
    input_path: str = ""
    output_path: str = ""
    external_mileage_mode: Literal["absolute", "relative"] = "absolute"
    external_distance_unit: Literal["m", "km"] = "km"
    Type2: Literal["空间谱", "时间谱", "时间序列"] = "空间谱"
    external_files: List[str] = Field(
        default_factory=lambda: [
            "VL=preprocessing/静检数据/呼局/20210416/处理后/静检上行20210416-271-278.merged.aligned.external/静检上行20210416-271-278.merged.aligned_VL.txt",
            "VR=preprocessing/静检数据/呼局/20210416/处理后/静检上行20210416-271-278.merged.aligned.external/静检上行20210416-271-278.merged.aligned_VR.txt",
            "LL=preprocessing/静检数据/呼局/20210416/处理后/静检上行20210416-271-278.merged.aligned.external/静检上行20210416-271-278.merged.aligned_LL.txt",
            "LR=preprocessing/静检数据/呼局/20210416/处理后/静检上行20210416-271-278.merged.aligned.external/静检上行20210416-271-278.merged.aligned_LR.txt",
        ]
    )

    N_sub: int = Field(2000, gt=0)
    X0: float = 20.0
    alpha: float = 0.5
    beta: float = 0.25
    g: float = 9.81

    switch_curve_track: Switch = "On"
    switch_2point_contact: Switch = "On"
    switch_extra_force_element: Switch = "On"
    switch_pad_zone: Switch = "On"
    switch_pad_partition: Switch = "On"
    switch_railcant_unsymmetric: Switch = "On"

    switch_lock_veh_non_z: Switch = "On"
    switch_lock_axlebox: Switch = "Off"
    switch_lock_substructure: Switch = "Off"

    save_data: Switch = "On"
    save_dof_mode: Literal["full", "vehicle"] = "vehicle"
    project_name: str = "desktop_workbench"
    run_note: str = "desktop"
    plot_figs: Switch = "Off"

    def to_namespace(self) -> SimpleNamespace:
        return SimpleNamespace(**self.model_dump())


class SimulationCreateResponse(BaseModel):
    run_id: str


class SimulationStatus(BaseModel):
    run_id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    progress: float = 0.0
    current_step: int = 0
    total_steps: int = 0
    message: str = ""
    result_path: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class ResultSummary(BaseModel):
    run_id: str
    result_path: str
    dt: float
    steps: int
    duration: float
    channels: Dict[str, List[float]]
    series: Dict[str, List[float]]
    groups: List[Dict[str, Any]] = Field(default_factory=list)
