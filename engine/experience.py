"""
经验库 (Experience Library)
记录自愈、降级、熔断事件，积累可复用的故障处理经验。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional
from pathlib import Path


@dataclass
class ExperienceEntry:
    """单条经验记录"""
    id: str
    kind: str           # "heal" | "circuit_breaker" | "experience"
    timestamp: str
    tool: str
    scenario: str       # 场景描述
    problem: str        # 遇到的问题
    pattern: str        # 故障模式
    solution: str       # 采取的措施
    result: str         # "success" | "partial" | "failed"
    confidence: int     # 1-10
    reuse_hint: str     # 复用建议
    duration_sec: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class ExperienceLibrary:
    """
    经验库：记录和复用故障处理经验。

    用法::

        lib = ExperienceLibrary("./logs")
        # 记录一次自愈事件
        lib.record_heal(
            tool="web_search",
            problem="API timeout",
            solution="切换到备用搜索引擎",
            result="success",
        )
        # 查找匹配经验
        exp = lib.find_matching(tool="web_search", pattern="timeout")
    """

    MAX_ENTRIES = 50
    HIGH_CONFIDENCE_THRESHOLD = 7

    def __init__(self, log_dir: str = "./logs"):
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self._log_dir / "self_heal_log.md"
        self._entries: list[ExperienceEntry] = []
        self._counters = {"heal": 0, "circuit_breaker": 0, "experience": 0}
        self._load()

    # ── 持久化 ────────────────────────

    def _load(self):
        """从日志文件加载经验"""
        if not self._log_file.exists():
            return
        try:
            content = self._log_file.read_text(encoding="utf-8")
            # 解析 markdown 表格格式的经验记录
            for block in content.split("---"):
                block = block.strip()
                if not block:
                    continue
                entry = self._parse_block(block)
                if entry:
                    self._entries.append(entry)
                    self._counters[entry.kind] = self._counters.get(entry.kind, 0) + 1
        except Exception:
            pass

    def _parse_block(self, block: str) -> Optional[ExperienceEntry]:
        """解析一个经验块"""
        lines = block.strip().split("\n")
        data = {}
        for line in lines:
            line = line.strip()
            if line.startswith("- **") and "**:" in line:
                key = line.split("**:")[0].replace("- **", "").strip()
                val = line.split("**:", 1)[1].strip()
                data[key] = val
        if not data.get("tool"):
            return None
        return ExperienceEntry(
            id=data.get("id", f"exp_{int(time.time()*1000)}"),
            kind=data.get("kind", "experience"),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            tool=data.get("tool", ""),
            scenario=data.get("scenario", ""),
            problem=data.get("problem", ""),
            pattern=data.get("pattern", ""),
            solution=data.get("solution", ""),
            result=data.get("result", "unknown"),
            confidence=int(data.get("confidence", "5")),
            reuse_hint=data.get("reuse_hint", ""),
        )

    def _save(self):
        """保存经验到日志文件"""
        lines = ["# Self-Heal Experience Log\n"]
        for entry in self._entries:
            lines.append(f"## {entry.id}\n")
            lines.append(f"- **id**: {entry.id}")
            lines.append(f"- **kind**: {entry.kind}")
            lines.append(f"- **timestamp**: {entry.timestamp}")
            lines.append(f"- **tool**: {entry.tool}")
            lines.append(f"- **scenario**: {entry.scenario}")
            lines.append(f"- **problem**: {entry.problem}")
            lines.append(f"- **pattern**: {entry.pattern}")
            lines.append(f"- **solution**: {entry.solution}")
            lines.append(f"- **result**: {entry.result}")
            lines.append(f"- **confidence**: {entry.confidence}")
            lines.append(f"- **reuse_hint**: {entry.reuse_hint}")
            lines.append(f"- **duration_sec**: {entry.duration_sec}")
            lines.append("\n---\n")
        self._log_file.write_text("\n".join(lines), encoding="utf-8")

    # ── 记录 ────────────────────────

    def record_heal(
        self,
        tool: str,
        problem: str,
        solution: str,
        result: str = "success",
        scenario: str = "",
        pattern: str = "",
        confidence: int = 5,
        reuse_hint: str = "",
        duration_sec: float = 0.0,
    ) -> ExperienceEntry:
        """记录一次自愈事件"""
        entry = ExperienceEntry(
            id=f"heal_{int(time.time() * 1000)}",
            kind="heal",
            timestamp=datetime.now().isoformat(),
            tool=tool,
            scenario=scenario or f"{tool} 自动修复",
            problem=problem,
            pattern=pattern or self._infer_pattern(problem),
            solution=solution,
            result=result,
            confidence=confidence,
            reuse_hint=reuse_hint or f"下次 {tool} 出现类似问题时可尝试: {solution}",
            duration_sec=duration_sec,
        )
        self._entries.append(entry)
        self._counters["heal"] = self._counters.get("heal", 0) + 1
        self._save()
        return entry

    def record_circuit_breaker(
        self,
        tool: str,
        state_change: str,
        reason: str,
    ) -> ExperienceEntry:
        """记录熔断器状态变更"""
        entry = ExperienceEntry(
            id=f"cb_{int(time.time() * 1000)}",
            kind="circuit_breaker",
            timestamp=datetime.now().isoformat(),
            tool=tool,
            scenario=f"{tool} 熔断器 {state_change}",
            problem=reason,
            pattern="circuit_breaker",
            solution=f"熔断器切换到 {state_change}",
            result="success",
            confidence=6,
            reuse_hint=f"{tool} 连续失败后熔断器自动 {state_change}",
        )
        self._entries.append(entry)
        self._counters["circuit_breaker"] = self._counters.get("circuit_breaker", 0) + 1
        self._save()
        return entry

    def record_experience(
        self,
        tool: str,
        scenario: str,
        problem: str,
        solution: str,
        result: str = "success",
        confidence: int = 5,
    ) -> ExperienceEntry:
        """记录一般经验"""
        entry = ExperienceEntry(
            id=f"exp_{int(time.time() * 1000)}",
            kind="experience",
            timestamp=datetime.now().isoformat(),
            tool=tool,
            scenario=scenario,
            problem=problem,
            pattern=self._infer_pattern(problem),
            solution=solution,
            result=result,
            confidence=confidence,
            reuse_hint=f"{scenario}: {solution}",
        )
        self._entries.append(entry)
        self._counters["experience"] = self._counters.get("experience", 0) + 1
        self._save()
        return entry

    # ── 查询 ────────────────────────

    def find_matching(
        self,
        tool: str,
        pattern: str = "",
        min_confidence: int = 3,
    ) -> list[ExperienceEntry]:
        """查找匹配的经验"""
        results = []
        for entry in self._entries:
            if entry.tool != tool:
                continue
            if entry.confidence < min_confidence:
                continue
            if pattern and pattern.lower() not in entry.pattern.lower():
                continue
            results.append(entry)
        results.sort(key=lambda e: e.confidence, reverse=True)
        return results

    def find_by_pattern(self, pattern: str) -> list[ExperienceEntry]:
        """按模式查找"""
        return [
            e for e in self._entries
            if pattern.lower() in e.pattern.lower()
        ]

    def get_recent(self, n: int = 10) -> list[ExperienceEntry]:
        """获取最近 N 条经验"""
        return self._entries[-n:]

    def get_successful(self) -> list[ExperienceEntry]:
        """获取成功的经验"""
        return [e for e in self._entries if e.result == "success"]

    def get_high_confidence(self) -> list[ExperienceEntry]:
        """获取高置信度经验"""
        return [e for e in self._entries if e.confidence >= self.HIGH_CONFIDENCE_THRESHOLD]

    def update_confidence(self, entry_id: str, delta: int):
        """更新某条经验的置信度"""
        for entry in self._entries:
            if entry.id == entry_id:
                entry.confidence = max(1, min(10, entry.confidence + delta))
                self._save()
                return

    def cleanup(self):
        """清理条目，严格遵守 MAX_ENTRIES 上限：优先保留高置信度，低置信度按时间排序截断"""
        if len(self._entries) <= self.MAX_ENTRIES:
            return
        high_conf = [e for e in self._entries if e.confidence >= self.HIGH_CONFIDENCE_THRESHOLD]
        low_conf = [e for e in self._entries if e.confidence < self.HIGH_CONFIDENCE_THRESHOLD]
        # 高置信度全部保留，低置信度按时间倒序填满剩余配额
        remaining = self.MAX_ENTRIES - len(high_conf)
        if remaining < 0:
            # 高置信度已超限，按置信度截断
            high_conf.sort(key=lambda e: e.confidence, reverse=True)
            high_conf = high_conf[:self.MAX_ENTRIES]
            remaining = 0
        low_conf.sort(key=lambda e: e.timestamp, reverse=True)
        kept_low = low_conf[:remaining]
        self._entries = high_conf + kept_low
        self._save()

    @property
    def count(self) -> int:
        return len(self._entries)

    def to_dict(self) -> dict:
        return {
            "total_entries": self.count,
            "counters": dict(self._counters),
            "entries": [e.to_dict() for e in self._entries[-10:]],  # 最近10条
        }

    # ── 内部工具 ────────────────────────

    @staticmethod
    def _infer_pattern(problem: str) -> str:
        """从问题描述推断故障模式"""
        problem_lower = problem.lower()
        if "timeout" in problem_lower or "超时" in problem_lower:
            return "timeout"
        if "rate limit" in problem_lower or "429" in problem_lower:
            return "rate_limit"
        if "connection" in problem_lower or "连接" in problem_lower:
            return "connection_error"
        if "auth" in problem_lower or "401" in problem_lower or "403" in problem_lower:
            return "auth_error"
        if "memory" in problem_lower or "内存" in problem_lower:
            return "memory_error"
        return "unknown"
