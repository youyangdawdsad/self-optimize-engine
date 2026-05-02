"""
任务评估器 (Task Evaluator)
执行前评估任务复杂度和风险等级，决定启用哪些优化策略。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class TaskType(Enum):
    """任务类型分类"""
    INFO_QUERY = "info_query"          # 信息查询类
    CONTENT_GEN = "content_gen"        # 内容生成类
    DATA_PROCESS = "data_process"      # 数据处理类
    FILE_OP = "file_op"                # 文件操作类
    CROSS_DEVICE = "cross_device"      # 跨设备协作类
    ORCHESTRATION = "orchestration"    # 编排调度类
    UNKNOWN = "unknown"


class TaskRiskLevel(Enum):
    """风险等级"""
    LOW = "low"          # 4-6分：直接执行
    MEDIUM = "medium"    # 7-9分：断路器 + 心跳监控
    HIGH = "high"        # 10-12分：全套防护


@dataclass
class EvaluationResult:
    """评估结果"""
    task_type: TaskType
    risk_level: TaskRiskLevel
    total_score: int
    dimension_scores: dict[str, int]
    recommended_components: list[str]
    suggested_degradation: Optional[str] = None
    subtasks: Optional[list[dict]] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["task_type"] = self.task_type.value
        d["risk_level"] = self.risk_level.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class TaskEvaluator:
    """
    任务评估器：在执行前对任务复杂度进行量化评估。

    评估维度（每项 1-3 分，总分 4-12）：
    1. 工具调用密度
    2. 内容生成量
    3. 外部依赖数
    4. 步骤耦合度
    """

    # ── 评分规则 ──────────────────────────────────────────────

    @staticmethod
    def _score_tool_density(tool_calls: int) -> int:
        if tool_calls <= 1:
            return 1
        elif tool_calls <= 4:
            return 2
        return 3

    @staticmethod
    def _score_content_volume(chars: int) -> int:
        if chars < 500:
            return 1
        elif chars <= 2000:
            return 2
        return 3

    @staticmethod
    def _score_external_deps(deps: int) -> int:
        if deps == 0:
            return 1
        elif deps <= 2:
            return 2
        return 3

    @staticmethod
    def _score_coupling(coupling: str) -> int:
        """coupling: 'none' | 'partial' | 'strict'"""
        mapping = {"none": 1, "partial": 2, "strict": 3}
        return mapping.get(coupling, 2)

    # ── 风险等级 ──────────────────────────────────────────────

    @staticmethod
    def _risk_level(total: int) -> TaskRiskLevel:
        if total <= 6:
            return TaskRiskLevel.LOW
        elif total <= 9:
            return TaskRiskLevel.MEDIUM
        return TaskRiskLevel.HIGH

    # ── 推荐组件 ──────────────────────────────────────────────

    @staticmethod
    def _recommended_components(risk: TaskRiskLevel, task_type: TaskType) -> list[str]:
        components = ["evaluator"]
        if risk in (TaskRiskLevel.MEDIUM, TaskRiskLevel.HIGH):
            components.append("circuit_breaker")
            components.append("heartbeat")
        if risk == TaskRiskLevel.HIGH:
            components.append("degradation")
            components.append("progress")
        # 按类型追加
        if task_type == TaskType.INFO_QUERY:
            components.append("cache")
        if task_type in (TaskType.CONTENT_GEN, TaskType.DATA_PROCESS):
            components.append("validator")
        if task_type == TaskType.CROSS_DEVICE:
            if "circuit_breaker" not in components:
                components.append("circuit_breaker")
            if "degradation" not in components:
                components.append("degradation")
        if task_type == TaskType.ORCHESTRATION:
            if "progress" not in components:
                components.append("progress")
            if "cache" not in components:
                components.append("cache")
        return components

    # ── 任务类型推断 ──────────────────────────────────────────

    @staticmethod
    def infer_task_type(description: str) -> TaskType:
        """根据任务描述推断任务类型"""
        desc = description.lower()
        # 关键词匹配
        query_kw = ["搜索", "查询", "查找", "检索", "search", "query", "look up", "查看"]
        gen_kw = ["写", "生成", "创作", "撰写", "报告", "文章", "write", "generate", "create"]
        data_kw = ["计算", "统计", "分析", "转换", "数据", "compute", "analyze", "convert"]
        file_kw = ["文件", "读写", "复制", "移动", "合并", "压缩", "file", "copy", "merge"]
        cross_kw = ["手机", "平板", "设备", "跨设备", "phone", "tablet", "device"]
        orch_kw = ["流水线", "多步骤", "编排", "调度", "pipeline", "orchestrat"]

        scores = {
            TaskType.INFO_QUERY: sum(1 for kw in query_kw if kw in desc),
            TaskType.CONTENT_GEN: sum(1 for kw in gen_kw if kw in desc),
            TaskType.DATA_PROCESS: sum(1 for kw in data_kw if kw in desc),
            TaskType.FILE_OP: sum(1 for kw in file_kw if kw in desc),
            TaskType.CROSS_DEVICE: sum(1 for kw in cross_kw if kw in desc),
            TaskType.ORCHESTRATION: sum(1 for kw in orch_kw if kw in desc),
        }
        best = max(scores, key=scores.get)
        if scores[best] == 0:
            return TaskType.UNKNOWN
        return best

    # ── 主评估入口 ────────────────────────────────────────────

    def evaluate(
        self,
        description: str = "",
        tool_calls: int = 1,
        content_chars: int = 0,
        external_deps: int = 0,
        coupling: str = "none",
        task_type: Optional[TaskType] = None,
    ) -> EvaluationResult:
        """
        评估任务复杂度。

        Args:
            description: 任务描述（用于自动推断类型）
            tool_calls: 预计工具调用次数
            content_chars: 预计生成内容字数
            external_deps: 外部依赖数
            coupling: 步骤耦合度 ('none' | 'partial' | 'strict')
            task_type: 手动指定任务类型（覆盖自动推断）

        Returns:
            EvaluationResult
        """
        if task_type is None:
            task_type = self.infer_task_type(description)

        scores = {
            "tool_density": self._score_tool_density(tool_calls),
            "content_volume": self._score_content_volume(content_chars),
            "external_deps": self._score_external_deps(external_deps),
            "coupling": self._score_coupling(coupling),
        }
        total = sum(scores.values())
        risk = self._risk_level(total)
        components = self._recommended_components(risk, task_type)

        # 高风险任务建议降级策略
        suggested_degradation = None
        if risk == TaskRiskLevel.HIGH:
            if task_type == TaskType.CONTENT_GEN:
                suggested_degradation = "分段生成 + 大纲先行"
            elif task_type == TaskType.CROSS_DEVICE:
                suggested_degradation = "超时降级到本机处理"
            elif task_type == TaskType.ORCHESTRATION:
                suggested_degradation = "DAG拆分 + 检查点恢复"
            else:
                suggested_degradation = "跳过失败步骤 + 部分交付"

        return EvaluationResult(
            task_type=task_type,
            risk_level=risk,
            total_score=total,
            dimension_scores=scores,
            recommended_components=components,
            suggested_degradation=suggested_degradation,
        )
