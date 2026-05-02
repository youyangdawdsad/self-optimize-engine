"""
断路器 (Circuit Breaker)
工具调用连续失败时自动熔断，避免无效重试。支持指数退避冷却。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Callable, Any


class CircuitState(Enum):
    CLOSED = "closed"        # 正常：放行所有请求
    OPEN = "open"            # 熔断：拒绝所有请求
    HALF_OPEN = "half_open"  # 探测：放行 1 个请求试探恢复


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 3       # 连续失败多少次触发熔断
    cooldown_ms: int = 60_000        # 熔断后冷却时间（毫秒）
    probe_timeout_ms: int = 15_000   # 探测请求超时
    half_open_max_probes: int = 1    # HALF-OPEN 允许的探测次数
    max_cooldown_ms: int = 600_000   # 冷却时间上限（指数退避封顶）


@dataclass
class BreakerSnapshot:
    """断路器当前状态快照"""
    tool_name: str
    state: str
    consecutive_failures: int
    total_requests: int
    total_failures: int
    last_failure_time: Optional[float]
    cooldown_remaining_ms: float
    opened_at: Optional[float]

    def to_dict(self) -> dict:
        return asdict(self)


class CircuitBreaker:
    """
    按工具独立维护的断路器。

    用法::

        cb = CircuitBreaker("web_search")
        if cb.allow_request():
            try:
                result = do_search(...)
                cb.record_success()
            except Exception as e:
                cb.record_failure(str(e))
        else:
            result = fallback(...)
    """

    def __init__(self, tool_name: str, config: Optional[CircuitBreakerConfig] = None):
        self.tool_name = tool_name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._total_requests = 0
        self._total_failures = 0
        self._last_failure_time: Optional[float] = None
        self._opened_at: Optional[float] = None
        self._half_open_probes = 0
        self._cooldown_multiplier = 1
        self._history: list[dict] = []

    # ── 属性 ──────────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        # 检查是否该从 OPEN 转到 HALF_OPEN
        if self._state == CircuitState.OPEN and self._opened_at:
            elapsed = (time.time() - self._opened_at) * 1000
            if elapsed >= self._effective_cooldown():
                self._transition(CircuitState.HALF_OPEN)
        return self._state

    @property
    def is_available(self) -> bool:
        return self.state != CircuitState.OPEN

    def _effective_cooldown(self) -> float:
        """当前冷却时间（含指数退避）"""
        return min(
            self.config.cooldown_ms * self._cooldown_multiplier,
            self.config.max_cooldown_ms,
        )

    # ── 状态转换 ──────────────────────────────────────────────

    def _transition(self, new_state: CircuitState):
        old = self._state
        self._state = new_state
        event = {
            "type": "state_change",
            "tool": self.tool_name,
            "from": old.value,
            "to": new_state.value,
            "timestamp": time.time(),
        }
        if new_state == CircuitState.OPEN:
            self._opened_at = time.time()
            event["reason"] = f"consecutive_failures={self._consecutive_failures}"
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_probes = 0
            event["cooldown_ms"] = self._effective_cooldown()
        elif new_state == CircuitState.CLOSED:
            self._consecutive_failures = 0
            self._cooldown_multiplier = 1
            self._opened_at = None
        self._history.append(event)

    # ── 公开接口 ──────────────────────────────────────────────

    def allow_request(self) -> bool:
        """判断当前是否允许发起请求"""
        s = self.state  # 触发 OPEN→HALF_OPEN 检查
        if s == CircuitState.CLOSED:
            return True
        if s == CircuitState.HALF_OPEN:
            return self._half_open_probes < self.config.half_open_max_probes
        return False  # OPEN

    def record_success(self):
        """记录一次成功调用"""
        self._total_requests += 1
        if self._state == CircuitState.HALF_OPEN:
            self._transition(CircuitState.CLOSED)
        self._consecutive_failures = 0

    def record_failure(self, error: str = ""):
        """记录一次失败调用"""
        self._total_requests += 1
        self._total_failures += 1
        self._consecutive_failures += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            # 探测失败 → 回到 OPEN，冷却翻倍
            self._cooldown_multiplier *= 2
            self._transition(CircuitState.OPEN)
        elif self._consecutive_failures >= self.config.failure_threshold:
            self._transition(CircuitState.OPEN)

        self._history.append({
            "type": "failure",
            "tool": self.tool_name,
            "error": error[:200],
            "consecutive": self._consecutive_failures,
            "timestamp": time.time(),
        })

    def reset(self):
        """手动重置为 CLOSED"""
        self._transition(CircuitState.CLOSED)

    def snapshot(self) -> BreakerSnapshot:
        """获取当前状态快照"""
        cooldown_remaining = 0.0
        if self._state == CircuitState.OPEN and self._opened_at:
            elapsed = (time.time() - self._opened_at) * 1000
            cooldown_remaining = max(0, self._effective_cooldown() - elapsed)
        return BreakerSnapshot(
            tool_name=self.tool_name,
            state=self._state.value,
            consecutive_failures=self._consecutive_failures,
            total_requests=self._total_requests,
            total_failures=self._total_failures,
            last_failure_time=self._last_failure_time,
            cooldown_remaining_ms=cooldown_remaining,
            opened_at=self._opened_at,
        )

    def get_history(self) -> list[dict]:
        return list(self._history)

    def to_dict(self) -> dict:
        return self.snapshot().to_dict()


class BreakerRegistry:
    """
    管理多个工具的断路器实例。

    用法::

        registry = BreakerRegistry()
        cb = registry.get("web_search")
        if cb.allow_request():
            ...
    """

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self._config = config
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(self, tool_name: str) -> CircuitBreaker:
        if tool_name not in self._breakers:
            self._breakers[tool_name] = CircuitBreaker(tool_name, self._config)
        return self._breakers[tool_name]

    def all_snapshots(self) -> list[dict]:
        return [cb.to_dict() for cb in self._breakers.values()]

    def reset_all(self):
        for cb in self._breakers.values():
            cb.reset()

    def to_dict(self) -> dict:
        return {name: cb.to_dict() for name, cb in self._breakers.items()}
