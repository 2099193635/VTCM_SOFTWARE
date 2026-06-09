from __future__ import annotations

import contextlib
import queue
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, Optional

from desktop_backend.database import SimulationDatabase
from desktop_backend.models import SimulationConfig


class _LogSink:
    def __init__(self, runner: "SimulationRunner", run_id: str):
        self.runner = runner
        self.run_id = run_id

    def write(self, text: str) -> int:
        for line in text.splitlines():
            line = line.strip()
            if line:
                self.runner.emit(self.run_id, {"type": "log", "message": line})
                self.runner.db.update(self.run_id, message=line)
        return len(text)

    def flush(self) -> None:
        return None


class SimulationRunner:
    def __init__(self, db: SimulationDatabase):
        self.db = db
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.events: Dict[str, "queue.Queue[dict]"] = {}
        self.cancel_events: Dict[str, threading.Event] = {}

    def emit(self, run_id: str, event: dict) -> None:
        q = self.events.setdefault(run_id, queue.Queue())
        event.setdefault("run_id", run_id)
        q.put(event)

    def get_queue(self, run_id: str) -> "queue.Queue[dict]":
        return self.events.setdefault(run_id, queue.Queue())

    def submit(self, config: SimulationConfig) -> str:
        run_id = uuid.uuid4().hex
        now = datetime.now().isoformat(timespec="seconds")
        self.events[run_id] = queue.Queue()
        self.cancel_events[run_id] = threading.Event()
        self.db.create(
            {
                "run_id": run_id,
                "status": "queued",
                "progress": 0.0,
                "current_step": 0,
                "total_steps": 0,
                "message": "任务已排队",
                "config_json": self.db.encode_config(config.model_dump()),
                "result_path": None,
                "created_at": now,
                "started_at": None,
                "finished_at": None,
            }
        )
        self.executor.submit(self._run, run_id, config)
        return run_id

    def cancel(self, run_id: str) -> bool:
        event = self.cancel_events.get(run_id)
        if event is None:
            return False
        event.set()
        self.emit(run_id, {"type": "log", "message": "已请求取消，当前步结束后停止。"})
        return True

    def _progress(self, run_id: str, current_step: int, total_steps: int, message: str = "") -> None:
        raw_progress = 0.0 if total_steps <= 0 else min(1.0, current_step / total_steps)
        progress = 0.05 + raw_progress * 0.90
        self.db.update(
            run_id,
            status="running",
            progress=progress,
            current_step=current_step,
            total_steps=total_steps,
            message=message or f"积分计算 {current_step}/{total_steps}",
        )
        self.emit(
            run_id,
            {
                "type": "progress",
                "progress": progress,
                "current_step": current_step,
                "total_steps": total_steps,
                "message": message or "积分计算中",
            },
        )

    def _run(self, run_id: str, config: SimulationConfig) -> None:
        import generate_main

        started = datetime.now().isoformat(timespec="seconds")
        self.db.update(run_id, status="running", started_at=started, message="仿真启动")
        self.emit(run_id, {"type": "status", "status": "running", "message": "仿真启动"})
        cancel_event = self.cancel_events[run_id]

        def progress_callback(current_step: int, total_steps: int) -> None:
            if current_step == 0 or current_step == total_steps or current_step % max(1, total_steps // 200) == 0:
                self._progress(run_id, current_step, total_steps)

        try:
            args = config.to_namespace()
            self.db.update(run_id, progress=0.02, message="前处理：读取参数、台账和不平顺")
            self.emit(run_id, {"type": "progress", "progress": 0.02, "current_step": 0, "total_steps": 0, "message": "前处理：读取参数、台账和不平顺"})
            with contextlib.redirect_stdout(_LogSink(self, run_id)):
                result_path = generate_main.main(
                    args,
                    progress_callback=progress_callback,
                    cancel_event=cancel_event,
                )
            finished = datetime.now().isoformat(timespec="seconds")
            status = "cancelled" if cancel_event.is_set() else "completed"
            self.db.update(
                run_id,
                status=status,
                progress=1.0 if status == "completed" else 0.0,
                result_path=result_path,
                finished_at=finished,
                message="仿真完成" if status == "completed" else "仿真已取消",
            )
            self.emit(run_id, {"type": "status", "status": status, "result_path": result_path})
        except Exception as exc:
            finished = datetime.now().isoformat(timespec="seconds")
            message = f"{type(exc).__name__}: {exc}"
            self.db.update(run_id, status="failed", finished_at=finished, message=message)
            self.emit(run_id, {"type": "error", "message": message, "traceback": traceback.format_exc()})
