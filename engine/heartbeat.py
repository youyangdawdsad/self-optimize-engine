"""
心跳监控 (Heartbeat Monitor)
持续监测各组件的存活状态和响应健康度。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    WARNING = "warning"
    UNHEALTHY = "unhealthy"
    DEAD = "dead"


@dataclass
class ComponentHeartbeat:
    """单个组件的心跳状态"""
    component_id: str
    last_heartbeat: float = 0.0
    status: str = "healthy"
    consecutive_misses: int = 0
    total_calls: int = 0
    total_errors: int = 0
    recent_latencies: list[float] = field(default_factory=list)
    avg_latency_ms: float = 0.0

    @property
    def error_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_errors / self.total_calls

    @property
    def error_rate_last_10(self) -> float:
        # 简化：用总错误率近似
        return self.error_rate

    def to_dict(self) -> dict:
        d = asdict(self)
        d["error_rate"] = round(self.error_rate, 3)
        return d


@dataclass
class HeartbeatConfig:
    """心跳配置"""
    check_interval_ms: int = 30_000       # 检查间隔
    timeout_threshold_ms: int = 60_000    # 超时阈值
    warning_ratio: float = 0.5            # warning = timeout * 0.5
    unhealthy_misses: int = 3             # 连续 miss 几次变 unhealthy
    dead_misses: int = 5                  # 连续 miss 几次变 dead
    latency_threshold_ms: float = 5000.0  # 延迟告警阈值
    error_rate_threshold: float = 0.5     # 错误率告警阈值
    max_latency_records: int = 20         # 保留最近N条延迟记录


class HeartbeatMonitor:
    """
    心跳监控器：监测组件存活和健康状态。

    用法::

        monitor = HeartbeatMonitor()
        # 注册组件
        monitor.register("tool_executor")
        monitor.register("cache_service")

        # 收到心跳
        monitor.beat("tool_executor", latency_ms=1200)

        # 检查健康状态
        status = monitor.check("tool_executor")
        if status != HealthStatus.HEALTHY:
            # 触发自救
            ...

        # 全局健康报告
        print(monitor.health_report())
    """

    def __init__(self, config: Optional[HeartbeatConfig] = None):
        self._config = config or HeartbeatConfig()
        self._components: dict[str, ComponentHeartbeat] = {}
        self._events: list[dict] = []

    # ── 注册与心跳 ────────────────────────────────────────────

    def register(self, component_id: str):
        """注册一个被监控组件"""
        if component_id not in self._components:
            self._components[component_id] = ComponentHeartbeat(
                component_id=component_id,
                last_heartbeat=time.time(),
            )

    def beat(self, component_id: str, latency_ms: float = 0.0):
        """收到组件心跳"""
        comp = self._components.get(component_id)
        if not comp:
            self.register(component_id)
            comp = self._components[component_id]

        comp.last_heartbeat = time.time()
        comp.consecutive_misses = 0
        comp.total_calls += 1

        # 记录延迟
        comp.recent_latencies.append(latency_ms)
        if len(comp.recent_latencies) > self._config.max_latency_records:
            comp.recent_latencies = comp.recent_latencies[-self._config.max_latency_records:]
        comp.avg_latency_ms = sum(comp.recent_latencies) / len(comp.recent_latencies)

        # 更新状态
        old_status = comp.status
        if latency_ms > self._config.latency_threshold_ms:
            comp.status = HealthStatus.DEGRADED.value
        else:
            comp.status = HealthStatus.HEALTHY.value

        if old_status != comp.status:
            self._record_event(component_id, "status_change", f"{old_status} → {comp.status}")

    def record_error(self, component_id: str, error: str = ""):
        """记录一次组件错误"""
        comp = self._components.get(component_id)
        if comp:
            comp.total_errors += 1

    def miss(self, component_id: str):
        """记录一次心跳缺失"""
        comp = self._components.get(component_id)
        if not comp:
            return

        comp.consecutive_misses += 1
        now = time.time()
        elapsed_ms = (now - comp.last_heartbeat) * 1000

        old_status = comp.status
        timeout = self._config.timeout_threshold_ms

        if comp.consecutive_misses >= self._config.dead_misses:
            comp.status = HealthStatus.DEAD.value
        elif comp.consecutive_misses >= self._config.unhealthy_misses:
            comp.status = HealthStatus.UNHEALTHY.value
        elif elapsed_ms >= timeout * self._config.warning_ratio:
            comp.status = HealthStatus.WARNING.value

                if old_status != comp.status:
            self._record_event(
                component_id, "status_change",
                f"{old_status} → {comp.status} (misses={comp.consecutive_misses})",
            )

    # ── 查询接口 ──────────────────────────────────────────────

    def check(self, component_id: str) -> HealthStatus:
        """检查组件健康状态（只读，不改变状态）"""
        comp = self._components.get(component_id)
        if not comp:
            return HealthStatus.DEAD
        return HealthStatus(comp.status)

        def check_all(self) -> dict[str, HealthStatus]:
        """周期性扫描所有组件健康状态，检测超时并记录 miss（返回各组件状态快照）"""
        now = time.time()
        results: dict[str, HealthStatus] = {}
        for comp in self._components.values():
            elapsed_ms = (now - comp.last_heartbeat) * 1000
            timeout = self._config.timeout_threshold_ms
            if elapsed_ms >= timeout:
                self.miss(comp.component_id)
            results[comp.component_id] = HealthStatus(comp.status)
        return results

    def get_status(self, component_id: str) -> Optional[dict]:
        comp = self._components.get(component_id)
        return comp.to_dict() if comp else None

    def all_statuses(self) -> dict[str, dict]:
        return {cid: comp.to_dict() for cid, comp in self._components.items()}

    def unhealthy_components(self) -> list[str]:
        """返回所有不健康的组件 ID"""
        return [
            cid for cid, comp in self._components.items()
            if comp.status in (HealthStatus.WARNING.value, HealthStatus.UNHEALTHY.value, HealthStatus.DEAD.value)
        ]

    # ── 报告 ──────────────────────────────────────────────────

    def health_report(self) -> str:
        """生成人类可读的健康报告"""
        lines = ["🏥 组件健康报告"]
        if not self._components:
            lines.append("  （无注册组件）")
            return "\n".join(lines)

        icon_map = {
            "healthy": "✅", "degraded": "🟡", "warning": "⚠️",
            "unhealthy": "🔴", "dead": "💀",
        }

        for cid, comp in self._components.items():
            icon = icon_map.get(comp.status, "❓")
            line = f"  {icon} {cid}: {comp.status}"
            if comp.avg_latency_ms > 0:
                line += f" | 延迟: {comp.avg_latency_ms:.0f}ms"
            if comp.total_errors > 0:
                line += f" | 错误率: {comp.error_rate:.0%}"
            if comp.consecutive_misses > 0:
                line += f" | 连续缺失: {comp.consecutive_misses}"
            lines.append(line)

        unhealthy = self.unhealthy_components()
        if unhealthy:
            lines.append(f"\n⚠️ {len(unhealthy)} 个组件需要关注: {', '.join(unhealthy)}")

        return "\n".join(lines)

    def _record_event(self, component_id: str, event_type: str, detail: str):
        self._events.append({
            "component": component_id,
            "type": event_type,
            "detail": detail,
            "timestamp": time.time(),
        })

    def get_events(self, limit: int = 20) -> list[dict]:
        return self._events[-limit:]

    def to_dict(self) -> dict:
        return {
            "components": self.all_statuses(),
            "unhealthy": self.unhealthy_components(),
            "recent_events": self.get_events(),
        }
