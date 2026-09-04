"""Check parsed place/station names against the local QGIS data sources."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from qgis.core import QgsApplication, QgsFeatureRequest, QgsVectorLayer


SCRIPT_DIR = Path(__file__).resolve().parent
PARSED = SCRIPT_DIR / "parsed_source.json"
PROVINCES = Path(r"F:\Desktop\Railway\province\province.json")
CITIES = Path(r"F:\Desktop\Railway\city\city.json")
RAIL_GPKG = Path(
    r"F:\Desktop\Railway\制图工具\数据源\GeoPackage\travel_map_home2_min_gan.gpkg"
)
REPORT = SCRIPT_DIR / "source_match_report.json"

CITY_SUFFIXES = (
    "布依族苗族自治州",
    "苗族侗族自治州",
    "回族自治州",
    "蒙古族藏族自治州",
    "土家族苗族自治州",
    "藏族自治州",
    "彝族自治州",
    "自治州",
    "地区",
    "盟",
    "市",
)


def short_admin_name(name: str) -> str:
    for suffix in CITY_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def sql_strings(values: list[str]) -> str:
    return ",".join("'" + value.replace("'", "''") + "'" for value in values)


def main() -> int:
    payload = json.loads(PARSED.read_text(encoding="utf-8"))
    app = QgsApplication([], False)
    app.initQgis()
    try:
        province_layer = QgsVectorLayer(str(PROVINCES), "provinces", "ogr")
        city_layer = QgsVectorLayer(str(CITIES), "cities", "ogr")
        station_layer = QgsVectorLayer(
            f"{RAIL_GPKG}|layername=china_railwayosm__points",
            "stations",
            "ogr",
        )
        for layer in (province_layer, city_layer, station_layer):
            if not layer.isValid():
                raise RuntimeError(f"Invalid layer: {layer.name()} / {layer.source()}")

        province_features = {
            str(feature["name"]): feature.id() for feature in province_layer.getFeatures()
        }
        expected_provinces = [item["province_full"] for item in payload["places"]]
        missing_provinces = sorted(set(expected_provinces) - set(province_features))

        city_candidates: dict[str, list[dict]] = defaultdict(list)
        for feature in city_layer.getFeatures(
            QgsFeatureRequest().setFilterExpression('"level" = \'city\'')
        ):
            full_name = str(feature["name"])
            city_candidates[short_admin_name(full_name)].append(
                {
                    "fid": feature.id(),
                    "full_name": full_name,
                    "adcode": str(feature["adcode"]),
                }
            )

        city_matches = []
        missing_cities = []
        ambiguous_cities = []
        municipalities = {"北京", "上海", "天津"}
        for place in payload["places"]:
            for city in place["cities"]:
                if city in municipalities:
                    city_matches.append(
                        {
                            "source_name": city,
                            "full_name": place["province_full"],
                            "province": place["province_full"],
                            "source": "province",
                        }
                    )
                    continue
                candidates = city_candidates.get(city, [])
                if not candidates:
                    missing_cities.append(city)
                    continue
                if len(candidates) > 1:
                    ambiguous_cities.append({"name": city, "candidates": candidates})
                selected = candidates[0]
                city_matches.append(
                    {
                        "source_name": city,
                        "full_name": selected["full_name"],
                        "province": place["province_full"],
                        "source": "city",
                        "fid": selected["fid"],
                        "adcode": selected["adcode"],
                    }
                )

        station_names = payload["stations"]
        request = QgsFeatureRequest().setFilterExpression(
            f'"name" IN ({sql_strings(station_names)})'
        )
        station_matches: dict[str, list[dict]] = defaultdict(list)
        for feature in station_layer.getFeatures(request):
            name = str(feature["name"])
            point = feature.geometry().asPoint()
            tags = str(feature["other_tags"] or "")
            station_matches[name].append(
                {
                    "fid": feature.id(),
                    "lon": point.x(),
                    "lat": point.y(),
                    "tags": tags,
                    "score": int('"railway"=>"station"' in tags) * 4
                    + int('"public_transport"=>"station"' in tags) * 2
                    + int('"train"=>"yes"' in tags),
                }
            )
        selected_stations = {}
        for name, candidates in station_matches.items():
            candidates.sort(key=lambda item: (-item["score"], item["fid"]))
            selected_stations[name] = candidates[0]
        missing_stations = sorted(set(station_names) - set(selected_stations))

        report = {
            "province_matches": len(expected_provinces) - len(missing_provinces),
            "missing_provinces": missing_provinces,
            "city_matches": city_matches,
            "missing_cities": sorted(missing_cities),
            "ambiguous_cities": ambiguous_cities,
            "station_matches": selected_stations,
            "missing_stations": missing_stations,
            "duplicate_station_names": {
                name: len(values)
                for name, values in station_matches.items()
                if len(values) > 1
            },
        }
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            f"provinces={report['province_matches']}/{len(expected_provinces)}; "
            f"cities={len(city_matches)}/{payload['city_count']}; "
            f"stations={len(selected_stations)}/{len(station_names)}"
        )
        print(f"missing_provinces={missing_provinces}")
        print(f"missing_cities={missing_cities}")
        print(f"ambiguous_cities={ambiguous_cities}")
        print(f"missing_stations={missing_stations}")
        print(REPORT)
        return 0
    finally:
        pass

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
