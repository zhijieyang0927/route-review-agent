from __future__ import annotations

from pathlib import Path

from .models import ReviewResult


def render_markdown(result: ReviewResult) -> str:
    lines = [
        "# 某轮订单路线复盘报告",
        "",
        f"- 骑手ID：{result.courier_id}",
        f"- 配送工具：{result.vehicle_type}",
        f"- 订单数：{len(result.orders)}",
        f"- 结论等级：{result.conclusion_level}",
        "",
        "## 文字结论",
        "",
        result.conclusion,
        "",
        "## 整轮跑动路径",
        "",
        "| 段 | 时间段 | 事件 | 起点 | 终点 | 实际分钟 | Google分钟 | 缓冲 | 允许分钟 | 缓冲后差异 | 等级 | 说明 |",
        "|---:|---|---|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for leg in result.route_legs:
        expected = "" if leg.expected_min is None else f"{leg.expected_min:.1f}"
        allowed = "" if leg.allowed_min is None else f"{leg.allowed_min:.1f}"
        delta = "" if leg.delta_after_buffer_min is None else f"{leg.delta_after_buffer_min:.1f}"
        lines.append(
            "| "
            f"{leg.leg_index} | "
            f"{leg.start_time.strftime('%H:%M')}-{leg.end_time.strftime('%H:%M')} | "
            f"{leg.from_event} → {leg.to_event} | "
            f"{leg.origin.display()} | "
            f"{leg.destination.display()} | "
            f"{leg.actual_min:.1f} | "
            f"{expected} | "
            f"{leg.buffer_min:.1f} | "
            f"{allowed} | "
            f"{delta} | "
            f"{leg.level} | "
            f"{leg.reason} |"
        )
    if result.sequence_review:
        seq = result.sequence_review
        actual_expected = "" if seq.actual_sequence_expected_min is None else f"{seq.actual_sequence_expected_min:.1f}"
        optimal_expected = "" if seq.optimal_sequence_expected_min is None else f"{seq.optimal_sequence_expected_min:.1f}"
        extra = "" if seq.extra_due_to_sequence_min is None else f"{seq.extra_due_to_sequence_min:.1f}"
        lines.extend([
            "",
            "## 送达顺序合理性",
            "",
            "| 起点时间 | 起点 | 实际送达顺序 | 最短送达顺序 | 实际顺序预计分钟 | 最短顺序预计分钟 | 顺序额外分钟 | 实际完成总分钟 | 等级 | 说明 |",
            "|---|---|---|---|---:|---:|---:|---:|---|---|",
            "| "
            f"{seq.start_time.strftime('%H:%M')} | "
            f"{seq.start_location.display()} | "
            f"{' → '.join(seq.actual_order)} | "
            f"{' → '.join(seq.optimal_order) if seq.optimal_order else ''} | "
            f"{actual_expected} | "
            f"{optimal_expected} | "
            f"{extra} | "
            f"{seq.actual_total_min:.1f} | "
            f"{seq.level} | "
            f"{seq.reason} |",
        ])
    lines.extend([
        "",
        "## 异常时间线",
        "",
        "| 订单 | 阶段 | 时间段 | 起点 | 终点 | 实际分钟 | 基准分钟 | 差异 | 等级 | 说明 |",
        "|---|---|---|---|---|---:|---:|---:|---|---|",
    ])
    for segment in result.segments:
        expected = "" if segment.expected_min is None else f"{segment.expected_min:.1f}"
        delta = "" if segment.delta_min is None else f"{segment.delta_min:.1f}"
        lines.append(
            "| "
            f"{segment.order_id} | "
            f"{segment.segment_type} | "
            f"{segment.start_time.strftime('%H:%M')}-{segment.end_time.strftime('%H:%M')} | "
            f"{segment.origin.display()} | "
            f"{segment.destination.display()} | "
            f"{segment.actual_min:.1f} | "
            f"{expected} | "
            f"{delta} | "
            f"{segment.level} | "
            f"{segment.reason} |"
        )
    lines.extend(["", "## 建议核查", ""])
    if result.recommendations:
        lines.extend(f"- {item}" for item in result.recommendations)
    else:
        lines.append("- 暂无需要优先核查的阶段。")
    if result.warnings:
        lines.extend(["", "## 数据限制", ""])
        lines.extend(f"- {item}" for item in result.warnings)
    if result.screenshots:
        lines.extend(["", "## 截图识别", ""])
        lines.append("| 文件 | 节点提示 | 订单提示 | 状态 | OCR摘录 |")
        lines.append("|---|---|---|---|---|")
        for shot in result.screenshots:
            status = "需人工确认" if shot.needs_confirmation else "已识别"
            text = " ".join(shot.text.split())[:80]
            lines.append(f"| {shot.path} | {shot.node_hint} | {shot.order_hint} | {status} | {text} |")
    lines.append("")
    return "\n".join(lines)


def write_markdown(result: ReviewResult, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(render_markdown(result), encoding="utf-8")
