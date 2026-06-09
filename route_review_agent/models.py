from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%H:%M:%S",
    "%H:%M",
)


def parse_time(value: str) -> datetime:
    value = (value or "").strip()
    if not value:
        raise ValueError("missing time")
    for fmt in TIME_FORMATS:
        try:
            parsed = datetime.strptime(value, fmt)
            if fmt.startswith("%H"):
                return parsed.replace(year=1900, month=1, day=1)
            return parsed
        except ValueError:
            continue
    return datetime.fromisoformat(value)


def minutes_between(start: datetime, end: datetime) -> float:
    delta = (end - start).total_seconds() / 60
    if delta < 0 and start.year == 1900 and end.year == 1900:
        delta += 24 * 60
    return delta


def normalize_vehicle_type(value: str) -> str:
    text = (value or "").strip().lower()
    aliases = {
        "步行": "walk",
        "走路": "walk",
        "walk": "walk",
        "walking": "walk",
        "自行车": "bike",
        "单车": "bike",
        "bike": "bike",
        "bicycle": "bike",
        "电动车": "ebike",
        "电单车": "ebike",
        "电瓶车": "ebike",
        "ebike": "ebike",
        "e-bike": "ebike",
        "摩托车": "moped",
        "摩托": "moped",
        "moped": "moped",
        "scooter": "moped",
        "汽车": "car",
        "轿车": "car",
        "car": "car",
        "drive": "car",
    }
    return aliases.get(text, text or "bike")


@dataclass(frozen=True)
class Location:
    label: str
    address: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    source: str = "input"
    needs_confirmation: bool = False

    @property
    def has_coordinates(self) -> bool:
        return self.lat is not None and self.lng is not None

    def display(self) -> str:
        if self.address:
            return f"{self.label} ({self.address})"
        if self.has_coordinates:
            return f"{self.label} ({self.lat:.6f}, {self.lng:.6f})"
        return self.label


@dataclass
class Order:
    order_id: str
    courier_id: str
    vehicle_type: str
    accepted_at: datetime
    arrived_store_at: datetime
    picked_up_at: datetime
    delivered_at: datetime
    accept_location: Location
    pickup_location: Location
    dropoff_location: Location
    expected_accept_to_store_min: Optional[float] = None
    expected_pickup_to_dropoff_min: Optional[float] = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScreenshotEvidence:
    path: str
    node_hint: str = ""
    order_hint: str = ""
    text: str = ""
    needs_confirmation: bool = True
    error: str = ""


@dataclass
class RouteEstimate:
    duration_min: Optional[float]
    distance_m: Optional[float] = None
    source: str = "none"
    confidence: str = "none"
    error: str = ""


@dataclass
class SegmentReview:
    order_id: str
    segment_type: str
    start_time: datetime
    end_time: datetime
    origin: Location
    destination: Location
    actual_min: float
    expected_min: Optional[float]
    delta_min: Optional[float]
    ratio: Optional[float]
    level: str
    rider_controlled: bool
    reason: str
    estimate_source: str
    recommendation: str


@dataclass
class RouteLegReview:
    leg_index: int
    from_event: str
    to_event: str
    order_context: str
    start_time: datetime
    end_time: datetime
    origin: Location
    destination: Location
    actual_min: float
    expected_min: Optional[float]
    buffer_min: float
    allowed_min: Optional[float]
    delta_after_buffer_min: Optional[float]
    ratio_after_buffer: Optional[float]
    level: str
    reason: str
    estimate_source: str
    recommendation: str


@dataclass
class SequenceReview:
    start_event: str
    start_time: datetime
    start_location: Location
    actual_order: list[str]
    optimal_order: list[str]
    actual_total_min: float
    actual_sequence_expected_min: Optional[float]
    optimal_sequence_expected_min: Optional[float]
    extra_due_to_sequence_min: Optional[float]
    level: str
    reason: str
    recommendation: str


@dataclass
class ReviewResult:
    courier_id: str
    vehicle_type: str
    orders: list[Order]
    segments: list[SegmentReview]
    route_legs: list[RouteLegReview]
    sequence_review: Optional[SequenceReview]
    screenshots: list[ScreenshotEvidence]
    conclusion_level: str
    conclusion: str
    recommendations: list[str]
    warnings: list[str]
