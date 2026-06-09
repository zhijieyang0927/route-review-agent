from __future__ import annotations

import json
from pathlib import Path


def answer(result: dict, question: str) -> str:
    q = question.strip().lower()
    segments = result.get("segments", [])
    route_legs = result.get("route_legs", [])
    if any(key in q for key in ("总结", "summary", "结论")):
        return result.get("conclusion", "没有结论。")
    if any(key in q for key in ("异常时间线", "timeline", "时间线")):
        rows = []
        if route_legs:
            for leg in route_legs:
                if leg["level"] != "正常":
                    rows.append(_leg_line(leg))
        else:
            for s in segments:
                if s["level"] != "正常":
                    rows.append(_segment_line(s))
        return "\n".join(rows) if rows else "没有发现异常阶段。"
    if any(key in q for key in ("整轮", "跑动", "路径", "顺序")):
        if "顺序" in q:
            sequence = result.get("sequence_review")
            if sequence:
                return _sequence_line(sequence)
        rows = [_leg_line(leg) for leg in route_legs]
        return "\n".join(rows) if rows else "没有整轮路径数据。"
    if any(key in q for key in ("高风险", "明显", "严重")):
        rows = [_leg_line(leg) for leg in route_legs if leg["level"] == "明显异常"]
        if not rows:
            rows = [_segment_line(s) for s in segments if s["level"] == "明显异常"]
        return "\n".join(rows) if rows else "没有明显异常阶段。"
    if any(key in q for key in ("证据不足", "不足", "缺什么")):
        rows = [_segment_line(s) for s in segments if s["level"] == "证据不足"]
        warnings = result.get("warnings", [])
        body = "\n".join(rows) if rows else "没有被标记为证据不足的阶段。"
        if warnings:
            body += "\n\n数据限制：\n" + "\n".join(f"- {w}" for w in warnings)
        return body
    if any(key in q for key in ("建议", "核查", "复盘")):
        recs = result.get("recommendations", [])
        return "\n".join(f"- {rec}" for rec in recs) if recs else "暂无需要优先核查的阶段。"
    return (
        "我可以回答：总结、异常时间线、高风险、证据不足、建议核查。"
        "第一版聊天入口基于已生成的结构化复盘结果回答。"
    )


def _segment_line(segment: dict) -> str:
    expected = segment["expected_min"] if segment["expected_min"] is not None else "无"
    delta = segment["delta_min"] if segment["delta_min"] is not None else "无"
    return (
        f"- 订单 {segment['order_id']} {segment['segment_type']} "
        f"{segment['start_time'][-8:-3]}-{segment['end_time'][-8:-3]}："
        f"实际 {segment['actual_min']} 分钟，基准 {expected}，差异 {delta}，"
        f"等级 {segment['level']}。{segment['reason']}"
    )


def _leg_line(leg: dict) -> str:
    expected = leg["expected_min"] if leg["expected_min"] is not None else "无"
    allowed = leg["allowed_min"] if leg["allowed_min"] is not None else "无"
    delta = leg["delta_after_buffer_min"] if leg["delta_after_buffer_min"] is not None else "无"
    return (
        f"- 第 {leg['leg_index']} 段 {leg['from_event']} → {leg['to_event']} "
        f"{leg['start_time'][-8:-3]}-{leg['end_time'][-8:-3]}："
        f"实际 {leg['actual_min']} 分钟，Google {expected}，允许 {allowed}，"
        f"缓冲后差异 {delta}，等级 {leg['level']}。{leg['reason']}"
    )


def _sequence_line(sequence: dict) -> str:
    actual = " → ".join(sequence.get("actual_order") or [])
    optimal = " → ".join(sequence.get("optimal_order") or [])
    actual_expected = sequence.get("actual_sequence_expected_min")
    optimal_expected = sequence.get("optimal_sequence_expected_min")
    extra = sequence.get("extra_due_to_sequence_min")
    return (
        f"送达顺序判断：等级 {sequence.get('level')}。"
        f"实际顺序 {actual}；最短顺序 {optimal or '无可用基准'}。"
        f"实际顺序预计 {actual_expected} 分钟，最短顺序预计 {optimal_expected} 分钟，"
        f"顺序额外 {extra} 分钟。{sequence.get('reason')}"
    )


def load_result(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
