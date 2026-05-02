"""
自优化引擎 (Self-Optimize Engine)
全方位任务优化引擎，覆盖任务全生命周期：评估 → 规划 → 执行 → 监控 → 自愈 → 验证 → 沉淀
"""

__version__ = "1.0.0"

from .evaluator import TaskEvaluator, TaskRiskLevel, TaskType, EvaluationResult
from .circuit_breaker import CircuitBreaker, CircuitState, BreakerRegistry, CircuitBreakerConfig
from .validator import QualityValidator, ValidationResult
from .experience import ExperienceLibrary
from .cache import CacheManager
from .progress import ProgressTracker, TaskStatus
from .degradation import DegradationStrategy, DegradationLevel, DegradationResult
from .heartbeat import HeartbeatMonitor, HealthStatus, HeartbeatConfig
from .engine import SelfOptimizeEngine, EngineConfig, EngineState

__all__ = [
    "TaskEvaluator", "TaskRiskLevel", "TaskType", "EvaluationResult",
    "CircuitBreaker", "CircuitState", "BreakerRegistry", "CircuitBreakerConfig",
    "QualityValidator", "ValidationResult",
    "ExperienceLibrary",
    "CacheManager",
    "ProgressTracker", "TaskStatus",
    "DegradationStrategy", "DegradationLevel", "DegradationResult",
    "HeartbeatMonitor", "HealthStatus", "HeartbeatConfig",
    "SelfOptimizeEngine", "EngineConfig", "EngineState",
]
