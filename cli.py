#!/usr/bin/env python3
"""
自优化引擎 CLI
用法:
    python cli.py evaluate --tool-calls 5 --content-chars 3000 --deps 3 --coupling partial
    python cli.py validate --file output.txt
    python cli.py validate --text "要校验的内容"
    python cli.py status
    python cli.py cache stats
    python cli.py cache clear [--tool web_search]
    python cli.py breaker list
    python cli.py breaker reset [--tool web_search]
    python cli.py experience list [--min-confidence 5]
    python cli.py experience stats
    python cli.py demo
"""

import argparse
import json
import sys
import os

# 确保 engine 包可导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import (
    TaskEvaluator, TaskRiskLevel, TaskType,
    CircuitBreaker, CircuitState, BreakerRegistry,
    QualityValidator, ValidationResult,
    ExperienceLibrary,
    CacheManager,
    ProgressTracker, TaskStatus,
    DegradationStrategy, DegradationLevel,
    HeartbeatMonitor, HealthStatus,
)
from engine.engine import SelfOptimizeEngine, EngineConfig


def cmd_evaluate(args):
    """评估任务复杂度"""
    evaluator = TaskEvaluator()
    task_type = TaskType(args.type) if args.type else None
    result = evaluator.evaluate(
        description=args.description or "",
        tool_calls=args.tool_calls,
        content_chars=args.content_chars,
        external_deps=args.deps,
        coupling=args.coupling,
        task_type=task_type,
    )
    print(result.to_json())


def cmd_validate(args):
    """校验输出质量"""
    validator = QualityValidator()
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            content = f.read()
    elif args.text:
        content = args.text
    else:
        content = sys.stdin.read()

    result = validator.validate(content, min_score=args.min_score)
    print(result.to_json())


def cmd_status(args):
    """引擎全局状态"""
    engine = SelfOptimizeEngine(EngineConfig(
        log_dir=args.log_dir,
    ))
    print(engine.status_report())


def cmd_cache_stats(args):
    """缓存统计"""
    engine = SelfOptimizeEngine()
    stats = engine.cache.stats()
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def cmd_cache_clear(args):
    """清空缓存"""
    engine = SelfOptimizeEngine()
    engine.cache.clear(tool=args.tool)
    if args.tool:
        print(f"已清空 {args.tool} 的缓存")
    else:
        print("已清空全部缓存")


def cmd_breaker_list(args):
    """列出断路器状态"""
    engine = SelfOptimizeEngine()
    snapshots = engine.breakers.all_snapshots()
    if not snapshots:
        print("暂无断路器记录")
    else:
        print(json.dumps(snapshots, ensure_ascii=False, indent=2))


def cmd_breaker_reset(args):
    """重置断路器"""
    engine = SelfOptimizeEngine()
    if args.tool:
        cb = engine.breakers.get(args.tool)
        cb.reset()
        print(f"已重置 {args.tool} 的断路器")
    else:
        engine.breakers.reset_all()
        print("已重置全部断路器")


def cmd_experience_list(args):
    """列出经验库"""
    engine = SelfOptimizeEngine()
    entries = engine.find_experience(min_confidence=args.min_confidence)
    if not entries:
        print("暂无匹配经验")
    else:
        for e in entries:
            print(f"[{e.id}] {e.scenario} | {e.problem} → {e.solution} (置信度: {e.confidence})")


def cmd_experience_stats(args):
    """经验库统计"""
    engine = SelfOptimizeEngine()
    data = engine.experience.to_dict()
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_demo(args):
    """运行完整演示"""
    print("🚀 自优化引擎演示\n")

    # 1. 评估
    print("=" * 50)
    print("📋 Step 1: 任务评估")
    print("=" * 50)
    engine = SelfOptimizeEngine(EngineConfig(log_dir="./logs"))
    plan = engine.evaluate_task(
        description="搜索三个平台的手机价格并生成对比报告",
        tool_calls=5,
        content_chars=3000,
        external_deps=3,
        coupling="partial",
    )
    print(f"  任务类型: {plan.task_type.value}")
    print(f"  风险等级: {plan.risk_level.value}")
    print(f"  总分: {plan.total_score}/12")
    print(f"  推荐组件: {', '.join(plan.recommended_components)}")
    if plan.suggested_degradation:
        print(f"  降级建议: {plan.suggested_degradation}")

    # 2. 带保护执行
    print(f"\n{'=' * 50}")
    print("🔧 Step 2: 带保护的工具执行")
    print("=" * 50)

    # 模拟成功调用
    def mock_search(query):
        return f"搜索结果: {query} 的价格数据"

    result1 = engine.execute_with_protection(
        tool_name="web_search",
        query="小米手机价格",
        executor=mock_search,
    )
    print(f"  ✅ 成功: {result1}")

    # 模拟失败调用
    def mock_failing_search(query):
        raise ConnectionError("API timeout")

    result2 = engine.execute_with_protection(
        tool_name="failing_api",
        query="test",
        executor=mock_failing_search,
    )
    print(f"  ⬇️ 降级: {result2}")

    # 3. 质量校验
    print(f"\n{'=' * 50}")
    print("✅ Step 3: 质量校验")
    print("=" * 50)
    validation = engine.validate_output("这是一段正常的输出内容，没有占位符和乱码。")
    print(f"  {validation.summary}")

    validation_bad = engine.validate_output("内容包含 [TODO] 和 {{placeholder}} 标记")
    print(f"  {validation_bad.summary}")

    # 4. 进度追踪
    print(f"\n{'=' * 50}")
    print("📊 Step 4: 进度追踪")
    print("=" * 50)
    tracker = engine.create_tracker("demo-001", "演示任务")
    tracker.add_subtask("s1", "搜索资料")
    tracker.add_subtask("s2", "生成报告")
    tracker.add_subtask("s3", "校验输出")

    tracker.start("s1")
    tracker.complete("s1", summary="找到15篇文档")
    tracker.start("s2")
    tracker.complete("s2", summary="报告已生成")
    tracker.start("s3")
    tracker.complete("s3", summary="校验通过")
    tracker.finish(success=True)

    print(tracker.progress_report())

    # 5. 全局状态
    print(f"\n{'=' * 50}")
    print("⚙️ Step 5: 全局状态")
    print("=" * 50)
    print(engine.status_report())

    print(f"\n{'=' * 50}")
    print("✅ 演示完成！")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(
        description="自优化引擎 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # evaluate
    p_eval = subparsers.add_parser("evaluate", help="评估任务复杂度")
    p_eval.add_argument("--description", "-d", default="", help="任务描述")
    p_eval.add_argument("--tool-calls", "-t", type=int, default=1, help="预计工具调用次数")
    p_eval.add_argument("--content-chars", "-c", type=int, default=0, help="预计生成字数")
    p_eval.add_argument("--deps", type=int, default=0, help="外部依赖数")
    p_eval.add_argument("--coupling", choices=["none", "partial", "strict"], default="none", help="步骤耦合度")
    p_eval.add_argument("--type", choices=["info_query", "content_gen", "data_process", "file_op", "cross_device", "orchestration"], default=None, help="手动指定任务类型")

    # validate
    p_val = subparsers.add_parser("validate", help="校验输出质量")
    p_val.add_argument("--file", "-f", help="从文件读取内容")
    p_val.add_argument("--text", help="直接传入文本")
    p_val.add_argument("--min-score", type=float, default=60.0, help="及格分数线")

                # status
    p_log = subparsers.add_parser("status", help="引擎全局状态")
    p_log.add_argument("--log-dir", default="./logs", help="日志目录")

    # cache
    p_cache = subparsers.add_parser("cache", help="缓存管理")
    cache_sub = p_cache.add_subparsers(dest="cache_action")
    cache_sub.add_parser("stats", help="缓存统计")
    p_cache_clear = cache_sub.add_parser("clear", help="清空缓存")
    p_cache_clear.add_argument("--tool", help="指定工具名")

    # breaker
    p_breaker = subparsers.add_parser("breaker", help="断路器管理")
    breaker_sub = p_breaker.add_subparsers(dest="breaker_action")
    breaker_sub.add_parser("list", help="列出状态")
    p_breaker_reset = breaker_sub.add_parser("reset", help="重置断路器")
    p_breaker_reset.add_argument("--tool", help="指定工具名")

    # experience
    p_exp = subparsers.add_parser("experience", help="经验库管理")
    exp_sub = p_exp.add_subparsers(dest="exp_action")
    p_exp_list = exp_sub.add_parser("list", help="列出经验")
    p_exp_list.add_argument("--min-confidence", type=int, default=5, help="最低置信度")
    exp_sub.add_parser("stats", help="经验库统计")

    # demo
    subparsers.add_parser("demo", help="运行完整演示")

    args = parser.parse_args()

    if args.command == "evaluate":
        cmd_evaluate(args)
    elif args.command == "validate":
        cmd_validate(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "cache":
        if args.cache_action == "stats":
            cmd_cache_stats(args)
        elif args.cache_action == "clear":
            cmd_cache_clear(args)
        else:
            cmd_cache_stats(args)
    elif args.command == "breaker":
        if args.breaker_action == "list":
            cmd_breaker_list(args)
        elif args.breaker_action == "reset":
            cmd_breaker_reset(args)
        else:
            cmd_breaker_list(args)
    elif args.command == "experience":
        if args.exp_action == "list":
            cmd_experience_list(args)
        elif args.exp_action == "stats":
            cmd_experience_stats(args)
        else:
            cmd_experience_stats(args)
    elif args.command == "demo":
        cmd_demo(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
