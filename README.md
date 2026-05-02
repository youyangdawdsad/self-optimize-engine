# 🤖 Self-Optimize Engine

**AI Agent 自优化引擎** — 让你的 AI Agent 更聪明、更健壮、更可靠。

> 纯 Python 标准库，零依赖，开箱即用。

## ✨ 核心能力

| 模块 | 功能 | 一句话说明 |
|------|------|-----------|
| **TaskEvaluator** | 任务复杂度评估 | 执行前预判风险，该怂就怂 |
| **CircuitBreaker** | 断路器保护 | 工具连续失败？自动熔断，防止雪崩 |
| **DegradationManager** | 三级降级容错 | L0 重试 → L1 换路 → L2 兜底，总有退路 |
| **HeartbeatMonitor** | 心跳监控 | 组件挂了？第一时间知道 |
| **ProgressTracker** | 进度追踪 | 长任务不再黑盒，子任务、超时检测全支持 |
| **QualityValidator** | 质量校验 | 输出前自动检查，烂内容出不去 |
| **ExperienceManager** | 经验库 | 吃一堑长一智，历史失败自动沉淀 |

## 🚀 快速开始

```python
from engine import (
    TaskEvaluator, CircuitBreaker, DegradationManager,
    HeartbeatMonitor, ProgressTracker, QualityValidator,
    ExperienceManager,
)

# 评估任务复杂度
evaluator = TaskEvaluator()
assessment = evaluator.evaluate(
    description="搜索三个平台的手机价格并生成对比报告",
    tool_count=5, content_limit=3000,
    external_deps=3, coupling="partial",
)
print(assessment.risk_level)  # "high"

# 质量校验
validator = QualityValidator()
result = validator.validate("输出内容", min_score=60)
print(result.passed)  # True/False

# 断路器保护
breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
breaker.record_success("web_search")
breaker.record_failure("api_call")  # 连续失败会熔断
```

## 🛠️ CLI 命令行

```bash
# 评估任务复杂度
python cli.py evaluate -d "任务描述" -t 5 -c 3000 --deps 3 --coupling partial

# 质量校验
python cli.py validate --text "要校验的文本"
python cli.py validate --file output.md

# 查看全局状态
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

## 📐 架构设计

```
self-optimize-engine/
├── cli.py                  # 命令行入口
├── engine/
│   ├── __init__.py         # 统一导出
│   ├── engine.py           # 核心引擎
│   ├── evaluator.py        # 任务评估器
│   ├── circuit_breaker.py  # 断路器
│   ├── degradation.py      # 降级管理
│   ├── heartbeat.py        # 心跳监控
│   ├── progress.py         # 进度追踪
│   ├── validator.py        # 质量校验
│   ├── experience.py       # 经验库
│   └── cache.py            # 缓存工具
└── logs/
    └── self_heal_log.md    # 自修复日志
```

## 🎯 降级策略

当工具调用失败时，引擎会按以下策略自动降级：

- **L0** — 重试原工具（最轻量）
- **L1** — 切换备用工具或简化输入
- **L2** — 使用本地知识兜底
- **L3** — 返回部分结果 + 未完成标记（最后防线）

## 📦 依赖

- **Python 3.10+**
- **零第三方依赖** — 纯标准库实现

## 📄 License

MIT License
