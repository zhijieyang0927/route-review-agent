from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .models import Location, Order, ReviewResult, ScreenshotEvidence, normalize_vehicle_type, parse_time


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _location(row: dict[str, Any], prefix: str, fallback_label: str) -> Location:
    label = str(row.get(f"{prefix}_name") or fallback_label).strip()
    address = str(row.get(f"{prefix}_address") or "").strip()
    lat = _float_or_none(row.get(f"{prefix}_lat"))
    lng = _float_or_none(row.get(f"{prefix}_lng"))
    return Location(label=label, address=address, lat=lat, lng=lng)


def _order_from_row(row: dict[str, Any]) -> Order:
    return Order(
        order_id=str(row.get("order_id") or "").strip(),
        courier_id=str(row.get("courier_id") or "").strip(),
        vehicle_type=normalize_vehicle_type(str(row.get("vehicle_type") or "bike")),
        accepted_at=parse_time(str(row.get("accepted_at") or "")),
        arrived_store_at=parse_time(str(row.get("arrived_store_at") or "")),
        picked_up_at=parse_time(str(row.get("picked_up_at") or "")),
        delivered_at=parse_time(str(row.get("delivered_at") or "")),
        accept_location=_location(row, "accept", "接单位置"),
        pickup_location=_location(row, "pickup", "商家/取点"),
        dropoff_location=_location(row, "dropoff", "顾客/落点"),
        expected_accept_to_store_min=_float_or_none(row.get("expected_accept_to_store_min")),
        expected_pickup_to_dropoff_min=_float_or_none(row.get("expected_pickup_to_dropoff_min")),
        raw=row,
    )


def load_orders(path: str | Path) -> list[Order]:
    path = Path(path)
    if path.suffix.lower() == ".json":
        rows = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(rows, dict):
            rows = rows.get("orders", [])
        return [_order_from_row(row) for row in rows]
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return [_order_from_row(row) for row in csv.DictReader(fh)]


def collect_screenshot_files(path: str | Path | None) -> list[Path]:
    if not path:
        return []
    root = Path(path)
    if not root.exists():
        return []
    extensions = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
    return sorted(p for p in root.rglob("*") if p.suffix.lower() in extensions)


def review_to_dict(result: ReviewResult) -> dict[str, Any]:
    def loc(location: Location) -> dict[str, Any]:
        return {
            "label": location.label,
            "address": location.address,
            "lat": location.lat,
            "lng": location.lng,
            "source": location.source,
            "needs_confirmation": location.needs_confirmation,
        }

    return {
        "courier_id": result.courier_id,
        "vehicle_type": result.vehicle_type,
        "conclusion_level": result.conclusion_level,
        "conclusion": result.conclusion,
        "recommendations": result.recommendations,
        "warnings": result.warnings,
        "sequence_review": None
        if result.sequence_review is None
        else {
            "start_event": result.sequence_review.start_event,
            "start_time": result.sequence_review.start_time.isoformat(sep=" "),
            "start_location": loc(result.sequence_review.start_location),
            "actual_order": result.sequence_review.actual_order,
            "optimal_order": result.sequence_review.optimal_order,
            "actual_total_min": round(result.sequence_review.actual_total_min, 2),
            "actual_sequence_expected_min": None
            if result.sequence_review.actual_sequence_expected_min is None
            else round(result.sequence_review.actual_sequence_expected_min, 2),
            "optimal_sequence_expected_min": None
            if result.sequence_review.optimal_sequence_expected_min is None
            else round(result.sequence_review.optimal_sequence_expected_min, 2),
            "extra_due_to_sequence_min": None
            if result.sequence_review.extra_due_to_sequence_min is None
            else round(result.sequence_review.extra_due_to_sequence_min, 2),
            "level": result.sequence_review.level,
            "reason": result.sequence_review.reason,
            "recommendation": result.sequence_review.recommendation,
        },
        "orders": [
            {
                "order_id": order.order_id,
                "courier_id": order.courier_id,
                "vehicle_type": order.vehicle_type,
                "accepted_at": order.accepted_at.isoformat(sep=" "),
                "arrived_store_at": order.arrived_store_at.isoformat(sep=" "),
                "picked_up_at": order.picked_up_at.isoformat(sep=" "),
                "delivered_at": order.delivered_at.isoformat(sep=" "),
                "accept_location": loc(order.accept_location),
                "pickup_location": loc(order.pickup_location),
                "dropoff_location": loc(order.dropoff_location),
            }
            for order in result.orders
        ],
        "segments": [
            {
                "order_id": s.order_id,
                "segment_type": s.segment_type,
                "start_time": s.start_time.isoformat(sep=" "),
                "end_time": s.end_time.isoformat(sep=" "),
                "origin": loc(s.origin),
                "destination": loc(s.destination),
                "actual_min": round(s.actual_min, 2),
                "expected_min": None if s.expected_min is None else round(s.expected_min, 2),
                "delta_min": None if s.delta_min is None else round(s.delta_min, 2),
                "ratio": None if s.ratio is None else round(s.ratio, 2),
                "level": s.level,
                "rider_controlled": s.rider_controlled,
                "reason": s.reason,
                "estimate_source": s.estimate_source,
                "recommendation": s.recommendation,
            }
            for s in result.segments
        ],
        "route_legs": [
            {
                "leg_index": leg.leg_index,
                "from_event": leg.from_event,
                "to_event": leg.to_event,
                "order_context": leg.order_context,
                "start_time": leg.start_time.isoformat(sep=" "),
                "end_time": leg.end_time.isoformat(sep=" "),
                "origin": loc(leg.origin),
                "destination": loc(leg.destination),
                "actual_min": round(leg.actual_min, 2),
                "expected_min": None if leg.expected_min is None else round(leg.expected_min, 2),
                "buffer_min": round(leg.buffer_min, 2),
                "allowed_min": None if leg.allowed_min is None else round(leg.allowed_min, 2),
                "delta_after_buffer_min": None if leg.delta_after_buffer_min is None else round(leg.delta_after_buffer_min, 2),
                "ratio_after_buffer": None if leg.ratio_after_buffer is None else round(leg.ratio_after_buffer, 2),
                "level": leg.level,
                "reason": leg.reason,
                "estimate_source": leg.estimate_source,
                "recommendation": leg.recommendation,
            }
            for leg in result.route_legs
        ],
        "screenshots": [
            {
                "path": shot.path,
                "node_hint": shot.node_hint,
                "order_hint": shot.order_hint,
                "text": shot.text,
                "needs_confirmation": shot.needs_confirmation,
                "error": shot.error,
            }
            for shot in result.screenshots
        ],
    }


def write_json(result: ReviewResult, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(review_to_dict(result), ensure_ascii=False, indent=2), encoding="utf-8")
