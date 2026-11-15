"""Share railway endpoint resolution and totals between print and web maps."""

from __future__ import annotations

import re
from collections import Counter

from qgis.core import QgsFeature, QgsGeometry


STATION_CITY_OVERRIDES = {
    "赤峰南": "赤峰",
    "通辽": "通辽",
    "乌兰浩特": "兴安",
    "白城": "白城",
    "海拉尔": "呼伦贝尔",
    "满归": "呼伦贝尔",
    "漠河": "大兴安岭",
    "哈尔滨东": "哈尔滨",
    "哈尔滨西": "哈尔滨",
    "北京朝阳": "北京",
    "大兴机场": "北京",
}


def city_for_station(
    name: str,
    station_points: dict[str, object],
    city_features: list[QgsFeature],
) -> str:
    """Resolve an endpoint to the display city used by both maps."""
    override = STATION_CITY_OVERRIDES.get(name)
    if override:
        return override
    point = station_points.get(name)
    if point is None:
        return ""
    point_geometry = QgsGeometry.fromPointXY(point)
    for feature in city_features:
        if feature.geometry().contains(point_geometry):
            return str(feature["display"])
    return ""


def railway_statistics(routes, station_points, city_features) -> dict:
    """Count only recorded endpoints; intermediate stops add no cities/stations."""
    counts = Counter()
    distances = Counter()
    endpoints = set()
    months = []
    for route in routes:
        service = str(route["service"])
        counts[service] += 1
        distances[service] += int(route["table_km"])
        endpoints.update(str(route[field]) for field in ("origin", "destination"))
        match = re.search(r"(\d{4})[.年-](\d{1,2})", str(route["date"]))
        if match:
            months.append(tuple(map(int, match.groups())))
    city_names = {
        city_for_station(name, station_points, city_features) for name in endpoints
    } - {""}
    latest_month = "%04d.%02d" % max(months) if months else ""
    return {
        "route_count": sum(counts.values()),
        "distance_km": sum(distances.values()),
        "services": {
            service: {"trips": counts[service], "table_km": distances[service]}
            for service in ("conventional", "highspeed")
        },
        "station_count": len(endpoints),
        "city_count": len(city_names),
        "latest_month": latest_month,
    }


def railway_subtitle(summary: dict) -> str:
    conventional = summary["services"]["conventional"]
    highspeed = summary["services"]["highspeed"]
    return (
        f"{summary['route_count']} 段乘车记录｜普铁 {conventional['trips']} 次 · "
        f"高铁/动车 {highspeed['trips']} 次\n"
        f"总里程 {summary['distance_km']:,} km（其中普铁 {conventional['table_km']:,} km，"
        f"高铁/动车 {highspeed['table_km']:,} km）｜抵达 {summary['city_count']} 个城市的 "
        f"{summary['station_count']} 座车站"
    )
