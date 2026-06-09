from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request

from .models import Location, RouteEstimate


TRAVEL_MODE = {
    "walk": "WALK",
    "walking": "WALK",
    "bike": "BICYCLE",
    "bicycle": "BICYCLE",
    "ebike": "BICYCLE",
    "e-bike": "BICYCLE",
    "scooter": "TWO_WHEELER",
    "moped": "TWO_WHEELER",
    "car": "DRIVE",
    "drive": "DRIVE",
}


class GoogleMapsClient:
    def __init__(self, api_key: str | None = None, timeout: int = 20):
        self.api_key = api_key or os.environ.get("GOOGLE_MAPS_API_KEY", "")
        self.timeout = timeout
        self.insecure_ssl = os.environ.get("GOOGLE_MAPS_INSECURE_SSL") == "1"

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def geocode(self, location: Location) -> Location:
        if location.has_coordinates or not location.address or not self.enabled:
            return location
        params = urllib.parse.urlencode({"address": location.address, "key": self.api_key})
        url = f"https://maps.googleapis.com/maps/api/geocode/json?{params}"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout, context=self._ssl_context()) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            return Location(
                label=location.label,
                address=location.address,
                source=f"google_geocoding_failed:{exc}",
                needs_confirmation=True,
            )
        status = data.get("status", "")
        if status != "OK":
            message = data.get("error_message") or status or "unknown"
            return Location(
                label=location.label,
                address=location.address,
                source=f"google_geocoding_failed:{message}",
                needs_confirmation=True,
            )
        results = data.get("results") or []
        if not results:
            return Location(
                label=location.label,
                address=location.address,
                source="google_geocoding_failed:ZERO_RESULTS",
                needs_confirmation=True,
            )
        top = results[0]
        geo = top["geometry"]["location"]
        return Location(
            label=location.label,
            address=top.get("formatted_address") or location.address,
            lat=float(geo["lat"]),
            lng=float(geo["lng"]),
            source="google_geocoding",
            needs_confirmation=False,
        )

    def route(self, origin: Location, destination: Location, vehicle_type: str) -> RouteEstimate:
        if not self.enabled:
            return RouteEstimate(None, source="none", confidence="none", error="未配置 GOOGLE_MAPS_API_KEY。")
        if not origin.has_coordinates or not destination.has_coordinates:
            details = []
            if not origin.has_coordinates:
                details.append(f"起点缺少坐标，来源={origin.source}")
            if not destination.has_coordinates:
                details.append(f"终点缺少坐标，来源={destination.source}")
            return RouteEstimate(None, source="google_routes", confidence="none", error="；".join(details))

        travel_mode = TRAVEL_MODE.get(vehicle_type.lower(), "BICYCLE")
        body = {
            "origin": {"location": {"latLng": {"latitude": origin.lat, "longitude": origin.lng}}},
            "destination": {"location": {"latLng": {"latitude": destination.lat, "longitude": destination.lng}}},
            "travelMode": travel_mode,
            "routingPreference": "TRAFFIC_AWARE" if travel_mode == "DRIVE" else None,
            "computeAlternativeRoutes": False,
        }
        body = {key: value for key, value in body.items() if value is not None}
        request = urllib.request.Request(
            "https://routes.googleapis.com/directions/v2:computeRoutes",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": "routes.duration,routes.distanceMeters",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=self._ssl_context()) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            return RouteEstimate(None, source="google_routes", confidence="none", error=f"Google Routes错误：{detail}")
        except Exception as exc:
            return RouteEstimate(None, source="google_routes", confidence="none", error=f"Google Routes请求失败：{exc}")

        routes = data.get("routes") or []
        if not routes:
            return RouteEstimate(None, source="google_routes", confidence="none", error="Google Routes未返回路线。")
        route = routes[0]
        duration_text = str(route.get("duration") or "0s").rstrip("s")
        try:
            duration_min = float(duration_text) / 60
        except ValueError:
            duration_min = None
        return RouteEstimate(
            duration_min=duration_min,
            distance_m=route.get("distanceMeters"),
            source="google_routes",
            confidence="high" if duration_min is not None else "none",
        )

    def _ssl_context(self):
        if self.insecure_ssl:
            return ssl._create_unverified_context()
        return None
