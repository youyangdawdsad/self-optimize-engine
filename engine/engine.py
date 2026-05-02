"""
自优化引擎门面 (Engine Facade)
统一入口，串联所有组件：评估 → 规划 → 执行 → 监控 → 自愈 → 验证 → 沉淀。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .evaluator import TaskEvaluator, EvaluationResult, TaskType, TaskRiskLevel
from .circuit_breaker import BreakerRegistry, CircuitBreakerConfig
from .validator import QualityValidator, ValidationResult
from .experience import ExperienceLibrary
from .cache import CacheManager
from .progress import ProgressTracker, TaskStatus
from .degradation import DegradationStrategy, DegradationLevel
from .heartbeat import HeartbeatMonitor, HeartbeatConfig


@dataclass
class EngineConfig:
    """引擎配置"""
    # 断路器
    failure_threshold: int = 3
    cooldown_ms: int = 60_000
    # 缓存
    cache_max_entries: int = 200
    cache_default_ttl_ms: int = 300_000
    # 进度
    # 经验库
    log_dir: str = "./logs"
    # 质量
    min_quality_score: float = 60.0
    # 心跳
    heartbeat_check_interval_ms: int = 30_000


@dataclass
class EngineState:
    """引擎运行状态"""
    tasks_evaluated: int = 0
    tasks_executed: int = 0
    degradations: int = 0
    self_heals: int = 0
    cache_hits: int = 0
    cache_misses: int = 0

    def to_dict(self) -> dict:
        return {
            "tasks_evaluated": self.tasks_evaluated,
            "tasks_executed": self.tasks_executed,
            "degradations": self.degradations,
            "self_heals": self.self_heals,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
        }


class SelfOptimizeEngine:
    """
    自优化引擎：统一入口，串联所有组件。

    用法::

        engine = SelfOptimizeEngine()

        # 1. 评估任务
        plan = engine.evaluate_task(
            description="搜索三个平台的手机价格并生成对比报告",
            tool_calls=5,
            content_chars=3000,
            external_deps=3,
            coupling="partial",
        )
        print(plan.to_json())

        # 2. 执行工具（带断路器 + 缓存）
        result = engine.execute_with_protection(
            tool_name="web_search",
            query="小米手机价格",
            executor=lambda q: do_search(q),
        )

        # 3. 校验输出
        validation = engine.validate_output(result)

        # 4. 查看全局状态
        print(engine.status_report())
    """

    def __init__(self, config: Optional[EngineConfig] = None):
        self._config = config or EngineConfig()

        # 初始化各组件
        self._evaluator = TaskEvaluator()
        self._breakers = BreakerRegistry(CircuitBreakerConfig(
            failure_threshold=self._config.failure_threshold,
            cooldown_ms=self._config.cooldown_ms,
        ))
        self._validator = QualityValidator()
        self._experience = ExperienceLibrary(self._config.log_dir)
        self._cache = CacheManager(
            max_entries=self._config.cache_max_entries,
            default_ttl_ms=self._config.cache_default_ttl_ms,
        )
        self._degradation = DegradationStrategy()
        self._heartbeat = HeartbeatMonitor(HeartbeatConfig(
            check_interval_ms=self._config.heartbeat_check_interval_ms,
        ))
        self._state = EngineState()
        self._trackers: dict[str, ProgressTracker] = {}

    # ── 1. 任务评估 ──────────────────────────────────────────

    def evaluate_task(self, **kwargs) -> EvaluationResult:
        """评估任务复杂度，返回执行计划"""
        self._state.tasks_evaluated += 1
        return self._evaluator.evaluate(**kwargs)

    # ── 2. 带保护的工具执行 ──────────────────────────────────

    def execute_with_protection(
        self,
        tool_name: str,
        query: str,
        executor: Callable[[str], Any],
        use_cache: bool = True,
    ) -> Any:
        """
        带断路器 + 缓存 + 降级保护的工具执行。

        流程：缓存命中？→ 断路器放行？→ 执行 → 成功/失败处理
                """
        # 注册心跳
        self._heartbeat.register(tool_name)

        # 预计算缓存 key（熔断降级路径也需要）
        cache_key = CacheManager.make_key(tool_name, query)

        # 1. 检查缓存
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._state.cache_hits += 1
                return cached
            self._state.cache_misses += 1

        # 2. 断路器检查
        cb = self._breakers.get(tool_name)
        if not cb.allow_request():
            # 熔断中 → 降级
            self._state.degradations += 1
            degrade_result = self._degradation.execute(
                "tool_call",
                f"断路器熔断: {tool_name}",
                cached_result=self._cache.get(cache_key) if use_cache else None,
            )
            self._experience.record_circuit_breaker(
                tool=tool_name,
                failure_reason="circuit breaker open",
                cooldown_result="degraded",
                fallback=str(degrade_result.degraded_output)[:200],
            )
            return degrade_result.degraded_output

        # 3. 执行
        start = time.time()
        try:
            result = executor(query)
            elapsed = (time.time() - start) * 1000

            # 记录成功
            cb.record_success()
            self._heartbeat.beat(tool_name, latency_ms=elapsed)
            self._state.tasks_executed += 1

            # 写入缓存
            if use_cache and result is not None:
                self._cache.set(cache_key, result, source_tool=tool_name)

            return result

        except Exception as e:
            elapsed = (time.time() - start) * 1000
            error_msg = str(e)

            # 记录失败
            cb.record_failure(error_msg)
            self._heartbeat.record_error(tool_name, error_msg)
            self._state.tasks_executed += 1

                        # 记录经验
            self._experience.record_heal(
                tool=tool_name,
                problem=error_msg[:200],
                solution="等待下次重试或降级",
                result="failed",
                duration_sec=elapsed / 1000,
            )

            # 统计自愈次数
            self._state.self_heals += 1

            # 降级处理
            self._state.degradations += 1
            degrade_result = self._degradation.execute(
                "tool_call",
                error_msg,
                cached_result=self._cache.get(cache_key) if use_cache else None,
            )
            return degrade_result.degraded_output

    # ── 3. 质量校验 ──────────────────────────────────────────

    def validate_output(self, content: str, **kwargs) -> ValidationResult:
        """校验输出质量"""
        return self._validator.validate(content, min_score=self._config.min_quality_score, **kwargs)

    # ── 4. 进度追踪 ──────────────────────────────────────────

    def create_tracker(self, task_id: str, task_name: str = "") -> ProgressTracker:
        tracker = ProgressTracker(task_id, task_name)
        self._trackers[task_id] = tracker
        return tracker

    def get_tracker(self, task_id: str) -> Optional[ProgressTracker]:
        return self._trackers.get(task_id)

    # ── 5. 经验查询 ──────────────────────────────────────────

    def find_experience(self, **kwargs):
        return self._experience.find_matching(**kwargs)

    # ── 6. 全局状态报告 ──────────────────────────────────────

    def status_report(self) -> str:
        """生成引擎全局状态报告"""
        lines = [
            "⚙️ 自优化引擎状态报告",
            "=" * 40,
            "",
            f"📊 任务统计:",
            f"  评估次数: {self._state.tasks_evaluated}",
            f"  执行次数: {self._state.tasks_executed}",
            f"  降级次数: {self._state.degradations}",
            f"  自愈次数: {self._state.self_heals}",
            "",
            f"💾 缓存: {self._cache.stats()['hit_rate']} 命中率 ({self._cache.size} 条)",
            f"🔒 断路器: {len(self._breakers.all_snapshots())} 个工具",
            f"📝 经验库: {self._experience.count} 条记录",
            "",
            self._heartbeat.health_report(),
        ]
        return "\n".join(lines)

    def full_state(self) -> dict:
        """获取完整引擎状态（JSON 友好）"""
        return {
            "state": self._state.to_dict(),
            "cache": self._cache.to_dict(),
            "breakers": self._breakers.to_dict(),
            "experience": self._experience.to_dict(),
            "heartbeat": self._heartbeat.to_dict(),
            "degradation": self._degradation.to_dict(),
            "trackers": {k: v.to_dict() for k, v in self._trackers.items()},
        }

    # ── 组件直接访问 ──────────────────────────────────────────

    @property
    def evaluator(self) -> TaskEvaluator:
        return self._evaluator

    @property
    def breakers(self) -> BreakerRegistry:
        return self._breakers

    @property
    def validator(self) -> QualityValidator:
        return self._validator

    @property
    def experience(self) -> ExperienceLibrary:
        return self._experience

    @property
    def cache(self) -> CacheManager:
        return self._cache

    @property
    def degradation(self) -> DegradationStrategy:
        return self._degradation

    @property
    def heartbeat(self) -> HeartbeatMonitor:
        return self._heartbeat
