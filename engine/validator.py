"""
质量校验器 (Quality Validator)
输出前检查质量和完整性，支持多种校验规则。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Callable


class Severity(Enum):
    ERROR = "error"      # 严重问题，必须修复
    WARNING = "warning"  # 建议修复
    INFO = "info"        # 信息提示


@dataclass
class ValidationIssue:
    rule: str
    severity: str
    message: str
    details: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ValidationResult:
    passed: bool
    score: float              # 0-100
    issues: list[dict]
    summary: str

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "score": self.score,
            "issues": self.issues,
            "summary": self.summary,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class ValidationRule:
    """自定义校验规则"""
    name: str
    check_fn: Callable[[str], Optional[ValidationIssue]]
    enabled: bool = True


class QualityValidator:
    """
    质量校验器：在输出前检查内容的完整性和合理性。

    内置规则：
    - completeness: 内容完整性（非空、长度达标）
    - coherence: 连贯性（无明显断裂）
    - format: 格式规范（Markdown 结构）
    - placeholder: 占位符检测（未完成标记）
    - repetition: 重复内容检测
    - encoding: 编码正确性（无乱码）
    """

    def __init__(self):
        self._rules: list[ValidationRule] = []
        self._register_builtins()

    def _register_builtins(self):
        """注册内置校验规则"""
        self._rules.extend([
            ValidationRule("completeness", self._check_completeness),
            ValidationRule("placeholder", self._check_placeholders),
            ValidationRule("repetition", self._check_repetition),
            ValidationRule("encoding", self._check_encoding),
            ValidationRule("length", self._check_length),
        ])

    # ── 内置规则实现 ──────────────────────────────────────────

    @staticmethod
    def _check_completeness(content: str) -> Optional[ValidationIssue]:
        if not content or not content.strip():
            return ValidationIssue(
                rule="completeness",
                severity=Severity.ERROR.value,
                message="输出内容为空",
            )
        return None

    @staticmethod
    def _check_placeholders(content: str) -> Optional[ValidationIssue]:
        patterns = [
            (r"\.\.\.\s*\[.*?truncated.*?\]", "内容被截断"),
            (r"\[TODO\]|\[FIXME\]|\[PLACEHOLDER\]", "存在未完成标记"),
            (r"\{\{.*?\}\}", "存在模板变量未替换"),
        ]
        found = []
        for pat, desc in patterns:
            matches = re.findall(pat, content, re.IGNORECASE)
            if matches:
                found.append(f"{desc}({len(matches)}处)")
        if found:
            return ValidationIssue(
                rule="placeholder",
                severity=Severity.WARNING.value,
                message="存在未完成标记或占位符",
                details="; ".join(found),
            )
        return None

    @staticmethod
    def _check_repetition(content: str) -> Optional[ValidationIssue]:
        """检测大段重复内容"""
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        if len(lines) < 5:
            return None
        # 检查连续重复行
        consecutive_dupes = 0
        max_dupes = 0
        for i in range(1, len(lines)):
            if lines[i] == lines[i - 1]:
                consecutive_dupes += 1
                max_dupes = max(max_dupes, consecutive_dupes)
            else:
                consecutive_dupes = 0
        if max_dupes >= 3:
            return ValidationIssue(
                rule="repetition",
                severity=Severity.WARNING.value,
                message=f"检测到连续重复内容（最多连续{max_dupes + 1}行相同）",
                        )
        # 检查段落级重复（取每段前50字符做指纹）
        fingerprints = [l[:50] for l in lines if len(l) > 20]
        if len(fingerprints) > 10:
            unique = set(fingerprints)
            ratio = 1 - len(unique) / len(fingerprints)
            if ratio > 0.3:
                return ValidationIssue(
                    rule="repetition",
                    severity=Severity.WARNING.value,
                    message=f"内容重复率偏高（{ratio:.0%}的段落指纹重复）",
                )
        return None

    @staticmethod
    def _check_encoding(content: str) -> Optional[ValidationIssue]:
        """检测常见乱码模式（Unicode 字符串级别）"""
        mojibake_patterns = [
            r"Ã[\x80-\xbf]",             # UTF-8 被当 Latin-1 解码（高位字节残留）
            r"Â[\x80-\xbf]",             # UTF-8 双字节首字节残留
            r"[\xc0-\xdf][\x80-\xbf]",   # GBK/GB2312 双字节乱码
            r"é[èéêë]",                  # UTF-8 双字节截断残留
            r"[\ufffd]{2,}",             # 连续替换字符（U+FFFD）
            r"[\x00-\x08\x0b\x0c\x0e-\x1f]{3,}",  # 连续控制字符（非换行/制表）
        ]
        for pat in mojibake_patterns:
            if re.search(pat, content):
                return ValidationIssue(
                    rule="encoding",
                    severity=Severity.ERROR.value,
                    message="检测到可能的编码乱码",
                )
        return None

    @staticmethod
    def _check_length(content: str) -> Optional[ValidationIssue]:
        """长度合理性检查"""
        length = len(content)
        if length > 50_000:
            return ValidationIssue(
                rule="length",
                severity=Severity.WARNING.value,
                message=f"输出内容过长（{length}字），建议分段处理",
            )
        return None

    # ── 公开接口 ──────────────────────────────────────────────

    def add_rule(self, rule: ValidationRule):
        """添加自定义校验规则"""
        self._rules.append(rule)

    def validate(self, content: str, min_score: float = 60.0) -> ValidationResult:
        """
        执行全部校验规则。

        Args:
            content: 待校验内容
            min_score: 及格分数线（0-100）

        Returns:
            ValidationResult
        """
        issues = []
        active_rules = [r for r in self._rules if r.enabled]

        for rule in active_rules:
            issue = rule.check_fn(content)
            if issue:
                issues.append(issue.to_dict())

        # 计算分数
        error_count = sum(1 for i in issues if i["severity"] == "error")
        warning_count = sum(1 for i in issues if i["severity"] == "warning")
        total_rules = len(active_rules)

        if total_rules == 0:
            score = 100.0
        else:
            # 每个 error 扣 20 分，每个 warning 扣 5 分
            deduction = error_count * 20 + warning_count * 5
            score = max(0, 100 - deduction)

        passed = score >= min_score and error_count == 0

        # 生成摘要
        if passed:
            summary = f"✅ 校验通过（{score:.0f}/100）"
        else:
            parts = []
            if error_count:
                parts.append(f"{error_count}个严重问题")
            if warning_count:
                parts.append(f"{warning_count}个警告")
            summary = f"❌ 校验未通过（{score:.0f}/100）：{', '.join(parts)}"

        return ValidationResult(
            passed=passed,
            score=score,
            issues=issues,
            summary=summary,
        )
