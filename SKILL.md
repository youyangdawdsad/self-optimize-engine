---
name: 自优化引擎
description: AI Agent 自优化引擎，提供任务评估、断路器、降级策略、心跳监控、进度追踪、经验库和质量校验。当需要执行复杂多步骤任务、工具调用可能失败、或需要质量把关时使用此技能。
official: false
---

# 自优化引擎 (Self-Optimize Engine)

## 何时使用

- **复杂任务执行**：多步骤、多工具、有依赖关系的任务
- **工具调用保护**：需要断路器防止级联失败
- **降级容错**：工具调用失败时需要自动降级
- **质量校验**：输出前检查内容完整性、编码、占位符
- **进度追踪**：长时间任务需要进度汇报
- **经验复用**：希望从历史失败中学习

## 快速开始

```python
from engine import (
    TaskEvaluator, CircuitBreaker, DegradationManager,
    HeartbeatMonitor, ProgressTracker, QualityValidator,
    ExperienceManager, BreakerRegistry,
)

# 1. 评估任务复杂度
evaluator = TaskEvaluator()
assessment = evaluator.evaluate(
    description="搜索三个平台的手机价格并生成对比报告",
    tool_count=5, content_limit=3000,
    external_deps=3, coupling="partial",
)
print(assessment.risk_level)  # "high"

# 2. 质量校验
validator = QualityValidator()
result = validator.validate("输出内容", min_score=60)
print(result.passed)  # True/False

# 3. 断路器保护工具调用
breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
breaker.record_success("web_search")
breaker.record_failure("api_call")  # 连续失败会熔断
```

## CLI 用法

```bash
# 评估任务
python cli.py evaluate -d "任务描述" -t 5 -c 3000 --deps 3 --coupling partial

# 质量校验
python cli.py validate --text "要校验的文本"
python cli.py validate --file output.md

# 全局状态
python cli.py status

# 断路器管理
python cli.py breaker list
python cli.py breaker reset <tool_name>

# 经验库
python cli.py experience list
python cli.py experience search "timeout"

# 完整演示
python cli.py demo
```

## 组件说明

| 组件 | 功能 | 关键参数 |
|------|------|----------|
| TaskEvaluator | 评估任务复杂度和风险 | tool_count, content_limit, external_deps, coupling |
| CircuitBreaker | 防止工具调用级联失败 | failure_threshold=3, recovery_timeout=60s |
| DegradationManager | 工具失败时自动降级 | 3级降级策略 |
| HeartbeatMonitor | 组件健康监控 | timeout_threshold_ms=30000 |
| ProgressTracker | 任务进度追踪 | 支持子任务、超时检测 |
| QualityValidator | 输出质量校验 | 6条内置规则，可扩展 |
| ExperienceManager | 历史经验存储和检索 | MAX_ENTRIES=100, 置信度衰减 |

## 降级策略

- **L0**：重试原工具
- **L1**：切换备用工具或简化输入
- **L2**：使用本地知识兜底
- **L3**：返回部分结果 + 未完成标记

## 依赖

- Python 3.10+
- 无第三方依赖（纯标准库）
