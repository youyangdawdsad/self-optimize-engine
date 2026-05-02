"""
降级策略 (Degradation Strategy)
正常执行路径失败时自动切换到简版方案，保证有产出。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Callable, Any


class DegradationLevel(Enum):
    """降级等级"""
    L1_REDUCE_SCOPE = "L1"    # 缩减范围：减少输出量
    L2_SIMPLIFY = "L2"        # 简化格式：降低格式复杂度
    L3_SKIP_SUBTASK = "L3"    # 跳过子任务：放弃部分子任务
    L4_PARTIAL = "L4"         # 部分交付：交付已有结果


@dataclass
class DegradationResult:
    """降级执行结果"""
    level: str
    original_error: str
    degraded_output: Any
    completed_steps: int
    total_steps: int
    annotation: str  # 降级说明

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DegradationPlan:
    """降级预案"""
    task_type: str
    levels: list[dict]  # 按等级排列的降级方案

    def to_dict(self) -> dict:
        return asdict(self)


class DegradationStrategy:
    """
    降级策略引擎。

    用法::

        strategy = DegradationStrategy()
        # 注册降级预案
        strategy.register_plan("content_gen", [
            {"level": "L1", "action": "输出大纲要点"},
            {"level": "L2", "action": "输出核心结论1-3条"},
            {"level": "L3", "action": "停止，标注原因"},
        ])
        # 执行降级
        result = strategy.execute("content_gen", "生成超时", current_output="部分大纲...")
    """

    def __init__(self):
        self._plans: dict[str, list[dict]] = {}
        self._execution_log: list[dict] = []
        self._register_defaults()

    def _register_defaults(self):
        """注册默认降级预案"""
        self._plans["content_gen"] = [
            {
                "level": DegradationLevel.L1_REDUCE_SCOPE.value,
                "action": "缩减范围",
                "description": "全文生成超时 → 先出大纲要点",
                "handler": self._degrade_content_l1,
            },
            {
                "level": DegradationLevel.L2_SIMPLIFY.value,
                "action": "简化输出",
                "description": "大纲也出不来 → 输出核心结论1-3条",
                "handler": self._degrade_content_l2,
            },
            {
                "level": DegradationLevel.L3_SKIP_SUBTASK.value,
                "action": "停止生成",
                "description": "连续降级3次 → 停止，标注原因",
                "handler": self._degrade_content_l3,
            },
        ]
        self._plans["tool_call"] = [
            {
                "level": DegradationLevel.L1_REDUCE_SCOPE.value,
                "action": "使用缓存/本地知识",
                "description": "搜索API失败 → 用缓存或本地知识回答",
                "handler": self._degrade_tool_l1,
            },
            {
                "level": DegradationLevel.L2_SIMPLIFY.value,
                "action": "获取部分数据",
                "description": "数据获取失败 → 获取能拿到的部分数据",
                "handler": self._degrade_tool_l2,
            },
            {
                "level": DegradationLevel.L3_SKIP_SUBTASK.value,
                "action": "跳过该工具",
                "description": "断路器熔断 → 跳过该工具，用替代方案",
                "handler": self._degrade_tool_l3,
            },
        ]
        self._plans["file_op"] = [
            {
                "level": DegradationLevel.L1_REDUCE_SCOPE.value,
                "action": "拆分写入",
                "description": "写入失败 → 拆分为多次小写入",
                "handler": self._degrade_file_l1,
            },
            {
                "level": DegradationLevel.L2_SIMPLIFY.value,
                "action": "分段写入再合并",
                "description": "文件过大 → 分段写入再合并",
                "handler": self._degrade_file_l2,
            },
                        {
                "level": DegradationLevel.L3_SKIP_SUBTASK.value,
                "action": "尝试备用路径",
                "description": "路径错误 → 尝试备用路径",
                "handler": self._degrade_file_l3,
            },
        ]

    # ── 降级处理函数 ──────────────────────────────────────────

    @staticmethod
    def _degrade_content_l1(error: str, current_output: Any = None, **kwargs) -> Any:
        """内容生成 L1：输出大纲要点"""
        if current_output and isinstance(current_output, str):
            lines = current_output.split("\n")
            bullets = [l for l in lines if l.strip().startswith(("#", "-", "*", "•"))][:10]
            if bullets:
                return "\n".join(bullets)
        return "⚠️ [降级L1] 内容生成超时，以下为核心要点：\n（请根据上下文补充具体要点）"

    @staticmethod
    def _degrade_content_l2(error: str, current_output: Any = None, **kwargs) -> Any:
        """内容生成 L2：输出核心结论"""
        return "⚠️ [降级L2] 内容生成受限，核心结论：\n1. （待补充）\n\n需要展开哪部分请告诉我"

    @staticmethod
    def _degrade_content_l3(error: str, current_output: Any = None, **kwargs) -> Any:
        """内容生成 L3：停止"""
        return f"⚠️ [降级L3] 内容生成已停止。原因：{error}"

    @staticmethod
    def _degrade_tool_l1(error: str, current_output: Any = None, **kwargs) -> Any:
        """工具调用 L1：使用缓存"""
        cached = kwargs.get("cached_result")
        if cached:
            return cached
        return f"⚠️ [降级L1] 工具调用失败（{error}），使用本地知识回答"

    @staticmethod
    def _degrade_tool_l2(error: str, current_output: Any = None, **kwargs) -> Any:
        """工具调用 L2：部分数据"""
        partial = kwargs.get("partial_data")
        if partial:
            return partial
        return f"⚠️ [降级L2] 数据获取不完整（{error}），以下为已获取的部分数据"

    @staticmethod
    def _degrade_tool_l3(error: str, current_output: Any = None, **kwargs) -> Any:
        """工具调用 L3：跳过"""
        return f"⚠️ [降级L3] 工具不可用（{error}），已跳过该步骤"

    @staticmethod
    def _degrade_file_l1(error: str, current_output: Any = None, **kwargs) -> Any:
        """文件操作 L1：拆分写入"""
        return {"action": "split_write", "reason": error, "chunk_size": 500}

    @staticmethod
    def _degrade_file_l2(error: str, current_output: Any = None, **kwargs) -> Any:
        """文件操作 L2：分段合并"""
        return {"action": "segmented_merge", "reason": error, "segment_size": 1000}

    @staticmethod
    def _degrade_file_l3(error: str, current_output: Any = None, **kwargs) -> Any:
        """文件操作 L3：备用路径"""
        fallback = kwargs.get("fallback_path", "/tmp/output")
        return {"action": "fallback_path", "path": fallback, "reason": error}

    # ── 公开接口 ──────────────────────────────────────────────

    def register_plan(self, task_type: str, levels: list[dict]):
        """注册自定义降级预案"""
        self._plans[task_type] = levels

    def get_plan(self, task_type: str) -> Optional[list[dict]]:
        """获取某类任务的降级预案"""
        return self._plans.get(task_type)

    def execute(
        self,
        task_type: str,
        error: str,
        current_level: int = 0,
        current_output: Any = None,
        **kwargs,
    ) -> DegradationResult:
        """
        执行降级。

        Args:
            task_type: 任务类型（content_gen / tool_call / file_op）
            error: 原始错误
            current_level: 当前已降级到第几级（0=首次降级）
            current_output: 当前已有的输出
            **kwargs: 额外参数（cached_result, partial_data, fallback_path 等）

        Returns:
            DegradationResult
        """
        plan = self._plans.get(task_type, self._plans.get("tool_call", []))

        if current_level >= len(plan):
            # 所有降级路径已用尽
            result = DegradationResult(
                level="EXHAUSTED",
                original_error=error,
                degraded_output=f"⚠️ 所有降级路径已用尽。原始错误：{error}",
                completed_steps=0,
                total_steps=0,
                annotation="降级路径已用尽，无法继续",
            )
        else:
            step = plan[current_level]
            handler = step.get("handler")
            if handler:
                output = handler(error, current_output=current_output, **kwargs)
            else:
                output = f"⚠️ [{step['level']}] {step['action']}"

            result = DegradationResult(
                level=step["level"],
                original_error=error,
                degraded_output=output,
                completed_steps=0,
                total_steps=0,
                annotation=f"降级到 {step['level']}：{step['description']}",
            )

        self._execution_log.append({
            "task_type": task_type,
            "error": error[:200],
            "level": result.level,
            "annotation": result.annotation,
        })
        return result

    def get_log(self) -> list[dict]:
        return list(self._execution_log)

    def to_dict(self) -> dict:
        return {
            "plans": {
                k: [{"level": s["level"], "action": s["action"], "description": s["description"]} for s in v]
                for k, v in self._plans.items()
            },
            "execution_log": self._execution_log[-10:],
        }
