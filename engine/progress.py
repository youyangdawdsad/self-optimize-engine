"""
进度追踪器 (Progress Tracker)
长任务的执行进度管理，支持子任务追踪和超时处理。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    DEGRADED = "degraded"
    TIMEOUT = "timeout"


@dataclass
class SubTask:
    id: str
    name: str
    status: str = "pending"
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    result_summary: Optional[str] = None

    @property
    def duration_sec(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.completed_at or time.time()
        return end - self.started_at

    def to_dict(self) -> dict:
        d = asdict(self)
        d["duration_sec"] = round(self.duration_sec, 2)
        return d


@dataclass
class ProgressSnapshot:
    task_id: str
    task_name: str
    status: str
    total_subtasks: int
    completed: int
    failed: int
    skipped: int
    progress_pct: float
    elapsed_sec: float
    subtasks: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


class ProgressTracker:
    """
    进度追踪器：管理长任务的子任务进度。

    用法::

        tracker = ProgressTracker("task-001", "生成项目报告")
        tracker.add_subtask("s1", "搜索资料")
        tracker.add_subtask("s2", "生成大纲")
        tracker.add_subtask("s3", "撰写正文")

        tracker.start("s1")
        # ... 执行 ...
        tracker.complete("s1", summary="找到15篇相关文档")

        tracker.start("s2")
        # ... 执行 ...
        tracker.fail("s2", error="大纲生成超时")

        print(tracker.progress_report())
    """

    # 超时阈值（秒）
    TIMEOUT_THRESHOLDS = {
        "web_search": 10,
        "device_chat": 120,
        "bash": 30,
        "file_write": 5,
        "cloud_upload": 60,
        "default": 30,
    }

    def __init__(self, task_id: str, task_name: str = ""):
        self.task_id = task_id
        self.task_name = task_name
        self._status = TaskStatus.PENDING
        self._subtasks: dict[str, SubTask] = {}
        self._started_at: Optional[float] = None
        self._completed_at: Optional[float] = None

    # ── 子任务管理 ────────────────────────────────────────────

    def add_subtask(self, subtask_id: str, name: str):
        self._subtasks[subtask_id] = SubTask(id=subtask_id, name=name)

    def start(self, subtask_id: str):
        st = self._subtasks.get(subtask_id)
        if st:
            st.status = "running"
            st.started_at = time.time()
            if self._status == TaskStatus.PENDING:
                self._status = TaskStatus.RUNNING
                self._started_at = time.time()

    def complete(self, subtask_id: str, summary: str = ""):
        st = self._subtasks.get(subtask_id)
        if st:
            st.status = "completed"
            st.completed_at = time.time()
            st.result_summary = summary

    def fail(self, subtask_id: str, error: str = ""):
        st = self._subtasks.get(subtask_id)
        if st:
            st.status = "failed"
            st.completed_at = time.time()
            st.error = error

    def skip(self, subtask_id: str, reason: str = ""):
        st = self._subtasks.get(subtask_id)
        if st:
            st.status = "skipped"
            st.completed_at = time.time()
            st.error = reason

    def degrade(self, subtask_id: str, summary: str = ""):
        st = self._subtasks.get(subtask_id)
        if st:
            st.status = "degraded"
            st.completed_at = time.time()
            st.result_summary = summary

    # ── 整体状态 ──────────────────────────────────────────────

    def finish(self, success: bool = True):
        self._completed_at = time.time()
        self._status = TaskStatus.COMPLETED if success else TaskStatus.FAILED

    @property
    def status(self) -> TaskStatus:
        return self._status

    @property
    def progress_pct(self) -> float:
        total = len(self._subtasks)
        if total == 0:
            return 0.0
        done = sum(
            1 for st in self._subtasks.values()
            if st.status in ("completed", "degraded")
        )
        return done / total * 100

    @property
    def elapsed_sec(self) -> float:
        if self._started_at is None:
            return 0.0
        end = self._completed_at or time.time()
                return end - self._started_at

    # ── 超时检测 ──────────────────────────────────────────────

        def check_timeout(self, subtask_id: str, tool_name: str = "default") -> bool:
        """检查子任务是否超时，超时则自动标记为 TIMEOUT 并更新父任务状态"""
        st = self._subtasks.get(subtask_id)
        if not st or st.status != "running":
            return False
        threshold = self.TIMEOUT_THRESHOLDS.get(tool_name, self.TIMEOUT_THRESHOLDS["default"])
        if st.duration_sec > threshold:
            st.status = TaskStatus.TIMEOUT.value
            st.completed_at = time.time()
            st.error = f"超时（阈值 {threshold}s，实际 {st.duration_sec:.1f}s）"
            if all(s.status not in ("pending", "running") for s in self._subtasks.values()):
                has_failure = any(s.status in ("failed", "timeout") for s in self._subtasks.values())
                self._completed_at = time.time()
                self._status = TaskStatus.FAILED if has_failure else TaskStatus.COMPLETED
            return True
        return False

    # ── 报告 ──────────────────────────────────────────────────

    def progress_report(self) -> str:
        """生成人类可读的进度报告"""
        total = len(self._subtasks)
        completed = sum(1 for st in self._subtasks.values() if st.status == "completed")
        failed = sum(1 for st in self._subtasks.values() if st.status == "failed")
        skipped = sum(1 for st in self._subtasks.values() if st.status == "skipped")
        degraded = sum(1 for st in self._subtasks.values() if st.status == "degraded")

        lines = [
            f"📊 {self.task_name or self.task_id}",
            f"状态: {self._status.value} | 进度: {self.progress_pct:.0f}% | 耗时: {self.elapsed_sec:.1f}s",
            f"子任务: {completed}/{total} 完成",
        ]
        if failed:
            lines.append(f"  ⚠️ {failed} 个失败")
        if skipped:
            lines.append(f"  ⏭️ {skipped} 个跳过")
        if degraded:
            lines.append(f"  ⬇️ {degraded} 个降级")

        for st in self._subtasks.values():
            icon = {
                "pending": "⏳", "running": "🔄", "completed": "✅",
                "failed": "❌", "skipped": "⏭️", "degraded": "⬇️", "timeout": "⏰",
            }.get(st.status, "❓")
            line = f"  {icon} {st.name}"
            if st.duration_sec > 0:
                line += f" ({st.duration_sec:.1f}s)"
            if st.error:
                line += f" — {st.error}"
            lines.append(line)

        return "\n".join(lines)

    def snapshot(self) -> ProgressSnapshot:
        return ProgressSnapshot(
            task_id=self.task_id,
            task_name=self.task_name,
            status=self._status.value,
            total_subtasks=len(self._subtasks),
            completed=sum(1 for st in self._subtasks.values() if st.status == "completed"),
            failed=sum(1 for st in self._subtasks.values() if st.status == "failed"),
            skipped=sum(1 for st in self._subtasks.values() if st.status == "skipped"),
            progress_pct=self.progress_pct,
            elapsed_sec=round(self.elapsed_sec, 2),
            subtasks=[st.to_dict() for st in self._subtasks.values()],
        )

    def to_dict(self) -> dict:
        return self.snapshot().to_dict()
