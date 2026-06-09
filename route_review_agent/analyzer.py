from __future__ import annotations

from collections import Counter
from itertools import permutations

from .google_maps import GoogleMapsClient
from .models import (
    Location,
    Order,
    ReviewResult,
    RouteEstimate,
    RouteLegReview,
    SequenceReview,
    ScreenshotEvidence,
    SegmentReview,
    minutes_between,
)


CONTROLLED_SEGMENTS = {"接单到店", "取餐送达", "送达间移动"}

VEHICLE_BUFFERS = {
    "walk": 1.5,
    "bike": 2.0,
    "ebike": 3.0,
    "moped": 4.0,
    "car": 6.0,
}

DELIVERY_BUFFERS = {
    "walk": 1.0,
    "bike": 1.5,
    "ebike": 2.0,
    "moped": 2.5,
    "car": 4.0,
}


def _level(actual_min: float, expected_min: float | None, rider_controlled: bool) -> tuple[str, str, float | None, float | None]:
    if expected_min is None or expected_min <= 0:
        return "证据不足", "缺少地图或历史基准，无法可靠判断该阶段是否异常。", None, None
    delta = actual_min - expected_min
    ratio = actual_min / expected_min if expected_min else None
    if not rider_controlled:
        if actual_min >= 20:
            return "证据不足", "到店后取餐前耗时较长，但可能受商家出餐影响，不能直接归因骑手。", delta, ratio
        return "正常", "该阶段主要可能受商家影响，未直接计入骑手可控异常。", delta, ratio
    if delta >= 12 and ratio is not None and ratio >= 1.8:
        return "明显异常", "实际耗时显著高于地图/历史基准，属于骑手可控阶段，建议重点复盘。", delta, ratio
    if delta >= 7 or (ratio is not None and ratio >= 1.45):
        return "轻微异常", "实际耗时高于地图/历史基准，建议结合截图和后台日志复核。", delta, ratio
    return "正常", "实际耗时与地图/历史基准接近。", delta, ratio


def _leg_level(actual_min: float, expected_min: float | None, buffer_min: float) -> tuple[str, str, float | None, float | None, float | None]:
    if expected_min is None or expected_min <= 0:
        return "证据不足", "缺少地图路线基准，无法可靠判断该路段。", None, None, None
    allowed = expected_min + buffer_min
    delta = actual_min - allowed
    ratio = actual_min / allowed if allowed > 0 else None
    if delta >= 12 and ratio is not None and ratio >= 1.7:
        return "明显异常", "实际耗时显著超过 Google ETA + 交通工具缓冲，建议重点复盘该路段。", allowed, delta, ratio
    if delta >= 6 or (ratio is not None and ratio >= 1.35):
        return "轻微异常", "实际耗时超过 Google ETA + 交通工具缓冲，建议结合截图复核。", allowed, delta, ratio
    return "正常", "实际耗时在 Google ETA + 交通工具缓冲范围内。", allowed, delta, ratio


def _estimate(
    maps: GoogleMapsClient,
    origin: Location,
    destination: Location,
    vehicle_type: str,
    fallback_min: float | None,
) -> tuple[Location, Location, RouteEstimate]:
    geocoded_origin = maps.geocode(origin)
    geocoded_destination = maps.geocode(destination)
    estimate = maps.route(geocoded_origin, geocoded_destination, vehicle_type)
    if estimate.duration_min is None and fallback_min is not None:
        estimate = RouteEstimate(fallback_min, source="input_expected", confidence="medium")
    return geocoded_origin, geocoded_destination, estimate


def _segment(
    order: Order,
    segment_type: str,
    origin: Location,
    destination: Location,
    start_attr: str,
    end_attr: str,
    expected_min: float | None,
    maps: GoogleMapsClient,
    rider_controlled: bool,
) -> SegmentReview:
    start_time = getattr(order, start_attr)
    end_time = getattr(order, end_attr)
    actual_min = minutes_between(start_time, end_time)
    origin, destination, estimate = _estimate(maps, origin, destination, order.vehicle_type, expected_min)
    level, reason, delta, ratio = _level(actual_min, estimate.duration_min, rider_controlled)
    recommendation = _recommendation(segment_type, start_time, end_time, level, origin, destination)
    return SegmentReview(
        order_id=order.order_id,
        segment_type=segment_type,
        start_time=start_time,
        end_time=end_time,
        origin=origin,
        destination=destination,
        actual_min=actual_min,
        expected_min=estimate.duration_min,
        delta_min=delta,
        ratio=ratio,
        level=level,
        rider_controlled=rider_controlled,
        reason=reason if not estimate.error else f"{reason}（{estimate.error}）",
        estimate_source=estimate.source,
        recommendation=recommendation,
    )


def _recommendation(segment_type, start_time, end_time, level, origin, destination) -> str:
    if level == "正常":
        return "无需优先核查。"
    window = f"{start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}"
    if level == "证据不足":
        return f"补充该阶段地图坐标、地址或截图后再判断：{window}，{origin.display()} → {destination.display()}。"
    return f"重点查看 {window} 的后台位置更新和截图：{origin.display()} → {destination.display()}。"


def analyze_round(
    orders: list[Order],
    screenshots: list[ScreenshotEvidence],
    maps: GoogleMapsClient | None = None,
) -> ReviewResult:
    if not orders:
        raise ValueError("没有可分析的订单。")
    maps = maps or GoogleMapsClient()
    sorted_orders = sorted(orders, key=lambda order: order.accepted_at)
    segments: list[SegmentReview] = []
    for order in sorted_orders:
        segments.append(
            _segment(
                order,
                "接单到店",
                order.accept_location,
                order.pickup_location,
                "accepted_at",
                "arrived_store_at",
                order.expected_accept_to_store_min,
                maps,
                rider_controlled=True,
            )
        )
        restaurant_wait = minutes_between(order.arrived_store_at, order.picked_up_at)
        wait_level = "证据不足" if restaurant_wait >= 20 else "正常"
        wait_reason = "到店后取餐前等待可能受商家出餐影响，默认不直接归因骑手。"
        segments.append(
            SegmentReview(
                order_id=order.order_id,
                segment_type="到店等餐",
                start_time=order.arrived_store_at,
                end_time=order.picked_up_at,
                origin=order.pickup_location,
                destination=order.pickup_location,
                actual_min=restaurant_wait,
                expected_min=None,
                delta_min=None,
                ratio=None,
                level=wait_level,
                rider_controlled=False,
                reason=wait_reason,
                estimate_source="restaurant_wait_excluded",
                recommendation=(
                    f"如需判断责任，重点核查商家出餐记录和骑手是否确实到店："
                    f"{order.arrived_store_at.strftime('%H:%M')}-{order.picked_up_at.strftime('%H:%M')}。"
                ),
            )
        )
        segments.append(
            _segment(
                order,
                "取餐送达",
                order.pickup_location,
                order.dropoff_location,
                "picked_up_at",
                "delivered_at",
                order.expected_pickup_to_dropoff_min,
                maps,
                rider_controlled=True,
            )
        )

    route_legs = _analyze_route_legs(sorted_orders, maps)
    sequence_review = _analyze_delivery_sequence(sorted_orders, maps)
    conclusion_level = _overall_level(segments, route_legs, sequence_review)
    conclusion = _conclusion(conclusion_level, segments, route_legs, sequence_review, screenshots)
    recommendations = _recommendations(segments, route_legs, sequence_review, screenshots)
    warnings = _warnings(segments, screenshots, maps)
    vehicle_counts = Counter(order.vehicle_type for order in sorted_orders)
    return ReviewResult(
        courier_id=sorted_orders[0].courier_id,
        vehicle_type=vehicle_counts.most_common(1)[0][0],
        orders=sorted_orders,
        segments=segments,
        route_legs=route_legs,
        sequence_review=sequence_review,
        screenshots=screenshots,
        conclusion_level=conclusion_level,
        conclusion=conclusion,
        recommendations=recommendations,
        warnings=warnings,
    )


def _overall_level(
    segments: list[SegmentReview],
    route_legs: list[RouteLegReview],
    sequence_review: SequenceReview | None,
) -> str:
    if sequence_review and sequence_review.level == "明显异常":
        return "明显异常"
    if sequence_review and sequence_review.level == "轻微异常":
        if not any(leg.level == "明显异常" for leg in route_legs):
            return "轻微异常"
    has_route_signal = any(leg.level != "证据不足" for leg in route_legs)
    if route_legs and has_route_signal:
        if any(leg.level == "明显异常" for leg in route_legs):
            return "明显异常"
        if any(leg.level == "轻微异常" for leg in route_legs):
            return "轻微异常"
        if any(leg.level == "证据不足" for leg in route_legs):
            return "证据不足"
        return "正常"
    controlled = [s for s in segments if s.rider_controlled]
    if any(s.level == "明显异常" for s in controlled):
        return "明显异常"
    if any(s.level == "轻微异常" for s in controlled):
        return "轻微异常"
    if controlled and all(s.level == "证据不足" for s in controlled):
        return "证据不足"
    if any(s.level == "证据不足" for s in controlled):
        return "证据不足"
    return "正常"


def _conclusion(
    level: str,
    segments: list[SegmentReview],
    route_legs: list[RouteLegReview],
    sequence_review: SequenceReview | None,
    screenshots: list[ScreenshotEvidence],
) -> str:
    abnormal_legs = [leg for leg in route_legs if leg.level in {"轻微异常", "明显异常"}]
    if sequence_review and sequence_review.level in {"轻微异常", "明显异常"} and abnormal_legs:
        worst = sorted(abnormal_legs, key=lambda leg: (leg.level != "明显异常", -(leg.delta_after_buffer_min or 0)))[0]
        return (
            f"本轮结论：{level}。送达顺序存在{sequence_review.level}：实际 "
            f"{' → '.join(sequence_review.actual_order)}，最短应为 "
            f"{' → '.join(sequence_review.optimal_order)}，预计多 {sequence_review.extra_due_to_sequence_min:.1f} 分钟。"
            f"同时，第 {worst.leg_index} 段 {worst.from_event} → {worst.to_event} 实际耗时 "
            f"{worst.actual_min:.1f} 分钟，允许 {worst.allowed_min:.1f} 分钟，"
            f"缓冲后仍超出 {worst.delta_after_buffer_min:.1f} 分钟，是最需要复盘的时间段。"
        )
    if sequence_review and sequence_review.level in {"轻微异常", "明显异常"}:
        return (
            f"本轮结论：{level}。按“最快完成身上已有订单”的原则，实际送达顺序 "
            f"{' → '.join(sequence_review.actual_order)} 不是最短顺序；最短顺序应为 "
            f"{' → '.join(sequence_review.optimal_order)}。实际顺序预计比最短顺序多 "
            f"{sequence_review.extra_due_to_sequence_min:.1f} 分钟。"
        )
    if abnormal_legs:
        worst = sorted(abnormal_legs, key=lambda leg: (leg.level != "明显异常", -(leg.delta_after_buffer_min or 0)))[0]
        return (
            f"本轮结论：{level}。按整轮实际跑动顺序看，最值得复盘的是第 {worst.leg_index} 段："
            f"{worst.from_event} → {worst.to_event}，实际 {worst.actual_min:.1f} 分钟，"
            f"Google基准 {worst.expected_min:.1f} 分钟，缓冲 {worst.buffer_min:.1f} 分钟，"
            f"缓冲后仍超出 {worst.delta_after_buffer_min:.1f} 分钟。"
        )
    abnormal = [s for s in segments if s.rider_controlled and s.level in {"轻微异常", "明显异常"}]
    if abnormal:
        worst = sorted(abnormal, key=lambda s: (s.level != "明显异常", -(s.delta_min or 0)))[0]
        return (
            f"本轮结论：{level}。最值得复盘的阶段是订单 {worst.order_id} 的{worst.segment_type}，"
            f"实际 {worst.actual_min:.1f} 分钟，基准 {worst.expected_min:.1f} 分钟，"
            f"差异 {worst.delta_min:.1f} 分钟。"
        )
    if level == "证据不足":
        return "本轮结论：证据不足。关键骑手可控阶段缺少地图/历史基准或坐标，建议补充后再判断。"
    if screenshots and any(shot.needs_confirmation for shot in screenshots):
        return "本轮结论：未发现明显骑手可控异常，但部分截图未能自动识别，需要人工确认截图信息。"
    return "本轮结论：正常。骑手可控阶段未发现明显超出地图/历史基准的耗时。"


def _recommendations(
    segments: list[SegmentReview],
    route_legs: list[RouteLegReview],
    sequence_review: SequenceReview | None,
    screenshots: list[ScreenshotEvidence],
) -> list[str]:
    items = []
    if sequence_review and sequence_review.level in {"明显异常", "轻微异常", "证据不足"}:
        items.append(sequence_review.recommendation)
    if route_legs:
        for leg in route_legs:
            if leg.level in {"明显异常", "轻微异常", "证据不足"}:
                items.append(leg.recommendation)
    else:
        for segment in segments:
            if segment.level in {"明显异常", "轻微异常", "证据不足"}:
                items.append(segment.recommendation)
    if screenshots and any(shot.needs_confirmation for shot in screenshots):
        items.append("部分截图未能自动OCR，请人工确认截图中的时间、地址和骑手位置。")
    return list(dict.fromkeys(items))


def _warnings(segments: list[SegmentReview], screenshots: list[ScreenshotEvidence], maps: GoogleMapsClient) -> list[str]:
    warnings = []
    if not maps.enabled:
        warnings.append("未配置 GOOGLE_MAPS_API_KEY；本次只使用输入的 expected_* 基准，缺失基准的阶段会标记为证据不足。")
    if any(s.estimate_source == "none" for s in segments if s.rider_controlled):
        warnings.append("部分骑手可控阶段没有路线基准，不能判断具体偏航，只能提示补充证据。")
    if screenshots and any(shot.error for shot in screenshots):
        warnings.append("部分截图OCR失败或未执行，截图内容需要人工确认。")
    return list(dict.fromkeys(warnings))


def _analyze_route_legs(orders: list[Order], maps: GoogleMapsClient) -> list[RouteLegReview]:
    events = []
    for order in orders:
        events.append((order.accepted_at, f"接单 {order.order_id}", order.order_id, order.accept_location))
        events.append((order.picked_up_at, f"取餐 {order.order_id}", order.order_id, order.pickup_location))
        events.append((order.delivered_at, f"送达 {order.order_id}", order.order_id, order.dropoff_location))
    events = sorted(events, key=lambda item: item[0])
    compacted = []
    for event in events:
        if compacted and event[3].address == compacted[-1][3].address and minutes_between(compacted[-1][0], event[0]) < 0.2:
            compacted[-1] = event
        else:
            compacted.append(event)

    vehicle_type = orders[0].vehicle_type
    legs: list[RouteLegReview] = []
    for index, (start, end) in enumerate(zip(compacted, compacted[1:]), start=1):
        start_time, from_event, from_order, origin = start
        end_time, to_event, to_order, destination = end
        actual_min = minutes_between(start_time, end_time)
        if actual_min < 0.2:
            continue
        buffer_min = _buffer_for_leg(vehicle_type, to_event)
        origin, destination, estimate = _estimate(maps, origin, destination, vehicle_type, None)
        level, reason, allowed, delta, ratio = _leg_level(actual_min, estimate.duration_min, buffer_min)
        order_context = from_order if from_order == to_order else f"{from_order} → {to_order}"
        window = f"{start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}"
        if level == "正常":
            recommendation = "无需优先核查。"
        elif level == "证据不足":
            recommendation = f"补充该路段坐标或可识别截图后再判断：{window}，{origin.display()} → {destination.display()}。"
        else:
            recommendation = f"重点查看第 {index} 段 {window} 的位置变化：{origin.display()} → {destination.display()}。"
        legs.append(
            RouteLegReview(
                leg_index=index,
                from_event=from_event,
                to_event=to_event,
                order_context=order_context,
                start_time=start_time,
                end_time=end_time,
                origin=origin,
                destination=destination,
                actual_min=actual_min,
                expected_min=estimate.duration_min,
                buffer_min=buffer_min,
                allowed_min=allowed,
                delta_after_buffer_min=delta,
                ratio_after_buffer=ratio,
                level=level,
                reason=reason if not estimate.error else f"{reason}（{estimate.error}）",
                estimate_source=estimate.source,
                recommendation=recommendation,
            )
        )
    return legs


def _buffer_for_leg(vehicle_type: str, to_event: str) -> float:
    if to_event.startswith("取餐"):
        return VEHICLE_BUFFERS.get(vehicle_type, 3.0)
    if to_event.startswith("送达"):
        return DELIVERY_BUFFERS.get(vehicle_type, 2.0)
    return 0.0


def _analyze_delivery_sequence(orders: list[Order], maps: GoogleMapsClient) -> SequenceReview | None:
    if len(orders) < 2:
        return None
    if len(orders) > 6:
        latest_pickup = max(orders, key=lambda order: order.picked_up_at)
        return SequenceReview(
            start_event=f"取完全部订单（最后取餐 {latest_pickup.order_id}）",
            start_time=latest_pickup.picked_up_at,
            start_location=latest_pickup.pickup_location,
            actual_order=[order.order_id for order in sorted(orders, key=lambda order: order.delivered_at)],
            optimal_order=[],
            actual_total_min=minutes_between(latest_pickup.picked_up_at, max(order.delivered_at for order in orders)),
            actual_sequence_expected_min=None,
            optimal_sequence_expected_min=None,
            extra_due_to_sequence_min=None,
            level="证据不足",
            reason="本轮订单数超过 6，第一版不枚举所有送达顺序，避免组合爆炸。",
            recommendation="如需复盘大批量背单，请拆分为较小订单组或提供平台推荐顺序。",
        )

    latest_pickup = max(orders, key=lambda order: order.picked_up_at)
    start_location = maps.geocode(latest_pickup.pickup_location)
    vehicle_type = orders[0].vehicle_type
    actual_order_objs = sorted(orders, key=lambda order: order.delivered_at)
    actual_order_ids = [order.order_id for order in actual_order_objs]
    actual_total_min = minutes_between(latest_pickup.picked_up_at, max(order.delivered_at for order in orders))

    scored = []
    errors = []
    for candidate in permutations(orders):
        total = 0.0
        current = start_location
        candidate_ids = []
        ok = True
        for order in candidate:
            destination = maps.geocode(order.dropoff_location)
            _, destination, estimate = _estimate(maps, current, destination, vehicle_type, None)
            if estimate.duration_min is None:
                errors.append(estimate.error or "路线基准缺失")
                ok = False
                break
            total += estimate.duration_min + _buffer_for_leg(vehicle_type, f"送达 {order.order_id}")
            current = destination
            candidate_ids.append(order.order_id)
        if ok:
            scored.append((total, list(candidate_ids)))

    if not scored:
        return SequenceReview(
            start_event=f"取完全部订单（最后取餐 {latest_pickup.order_id}）",
            start_time=latest_pickup.picked_up_at,
            start_location=start_location,
            actual_order=actual_order_ids,
            optimal_order=[],
            actual_total_min=actual_total_min,
            actual_sequence_expected_min=None,
            optimal_sequence_expected_min=None,
            extra_due_to_sequence_min=None,
            level="证据不足",
            reason=f"缺少可用 Google 路线基准，无法判断最短送达顺序。{'；'.join(errors[:2])}",
            recommendation="补充顾客落点坐标或确认 Google Routes API 可用后，再判断送达顺序是否合理。",
        )

    optimal_expected, optimal_order = min(scored, key=lambda item: item[0])
    actual_sequence_expected = next((total for total, ids in scored if ids == actual_order_ids), None)
    if actual_sequence_expected is None:
        return None
    extra = actual_sequence_expected - optimal_expected
    if actual_order_ids == optimal_order or extra <= 2:
        level = "正常"
        reason = "实际送达顺序与最短顺序一致，或预计差异在 2 分钟以内。"
        recommendation = "无需优先核查送达顺序。"
    elif extra >= 8 or (optimal_expected > 0 and actual_sequence_expected / optimal_expected >= 1.35):
        level = "明显异常"
        reason = "实际送达顺序明显不是预计总配送时间最短的顺序，可能拉长了身上已有订单的整体完成时间。"
        recommendation = (
            f"重点核查送达顺序：实际 {' → '.join(actual_order_ids)}；"
            f"最短应为 {' → '.join(optimal_order)}。"
        )
    else:
        level = "轻微异常"
        reason = "实际送达顺序不是预计总配送时间最短的顺序，但额外耗时中等。"
        recommendation = (
            f"复核送达顺序是否有平台约束或顾客/商家因素：实际 {' → '.join(actual_order_ids)}；"
            f"最短应为 {' → '.join(optimal_order)}。"
        )

    return SequenceReview(
        start_event=f"取完全部订单（最后取餐 {latest_pickup.order_id}）",
        start_time=latest_pickup.picked_up_at,
        start_location=start_location,
        actual_order=actual_order_ids,
        optimal_order=optimal_order,
        actual_total_min=actual_total_min,
        actual_sequence_expected_min=actual_sequence_expected,
        optimal_sequence_expected_min=optimal_expected,
        extra_due_to_sequence_min=extra,
        level=level,
        reason=reason,
        recommendation=recommendation,
    )
