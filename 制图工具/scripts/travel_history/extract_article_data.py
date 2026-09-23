"""Extract visited regions and railway records from 行旅杂记.md."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DEFAULT_ARTICLE = Path(r"F:\Desktop\Blog\source\_posts\行旅杂记.md")
EXPECTED_PROVINCES = 21
EXPECTED_CITIES = 88
EXPECTED_RAIL_TRIPS = 137
EXPECTED_RAIL_DISTANCE_KM = 55896


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--article", type=Path, default=DEFAULT_ARTICLE)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def parse_visited_regions(text: str) -> list[dict]:
    start = text.index("至此，共计去过21个省级行政区，88个城市")
    end = text.index("<figure", start)
    lines = text[start:end].splitlines()

    category = ""
    regions = []
    for raw in lines:
        line = raw.strip()
        if line in {"- 省", "- 直辖市", "- 自治区"}:
            category = line[2:]
            continue
        if not raw.startswith("  - "):
            continue
        content = raw[4:].strip()
        if category == "直辖市":
            for name in (value.strip() for value in content.split("、")):
                regions.append(
                    {
                        "category": category,
                        "province": name,
                        "cities": [name],
                    }
                )
            continue

        match = re.fullmatch(r"([^（]+)（(\d+)/(\d+)）：(.+)", content)
        if not match:
            raise ValueError(f"Unable to parse visited-region line: {raw}")
        province, stated_count, total_count, cities_text = match.groups()
        cities = [value.strip() for value in cities_text.split("、")]
        regions.append(
            {
                "category": category,
                "province": province.strip(),
                "cities": cities,
                "stated_count": int(stated_count),
                "listed_count": len(cities),
                "total_prefectures": int(total_count),
            }
        )
    return regions


def service_class(train: str, origin: str, destination: str) -> str:
    value = train.strip().upper()
    if value.startswith(("G", "D", "C", "S")):
        return "high_speed_emu"
    if value == "不详":
        # These six records all use 湛江西 after the 2018 opening of the
        # Jiangmen-Zhanjiang railway and are counted as EMU trips in the article.
        if "湛江西" in {origin, destination}:
            return "high_speed_emu"
    return "conventional"


def track_preference(train: str, origin: str, destination: str) -> str:
    value = train.strip().upper()
    # D37/D38/D901 are CR200J sleeper services on the conventional Beijing-Guangzhou
    # railway; S5xx services use the conventional Beijing-Chengde railway.
    if value in {"D37", "D38", "D901", "S501", "S502"}:
        return "conventional"
    return service_class(value, origin, destination)


def parse_rail_records(text: str) -> list[dict]:
    start = text.index("{% hideToggle 展开铁路记录表 %}")
    end = text.index("{% endhideToggle %}", start)
    records = []
    current_time = ""
    for line in text[start:end].splitlines():
        if not line.startswith("|") or line.startswith("|:") or "|时间|" in line:
            continue
        cells = [cell.strip() for cell in line.strip()[1:-1].split("|")]
        if len(cells) != 5:
            continue
        time, origin, destination, train, distance = cells
        if time:
            current_time = time
        if not origin or not destination or not train:
            continue
        distance_km = int(distance.strip())
        records.append(
            {
                "seq": len(records) + 1,
                "time": current_time,
                "origin": origin,
                "destination": destination,
                "train": train.strip(),
                "distance_km": distance_km,
                "service_class": service_class(train, origin, destination),
                "track_preference": track_preference(train, origin, destination),
            }
        )
    return records


def main() -> int:
    args = parse_args()
    text = args.article.read_text(encoding="utf-8")
    regions = parse_visited_regions(text)
    records = parse_rail_records(text)

    province_count = len(regions)
    city_count = sum(len(region["cities"]) for region in regions)
    distance_km = sum(record["distance_km"] for record in records)
    class_counts = {
        value: sum(record["service_class"] == value for record in records)
        for value in ("conventional", "high_speed_emu")
    }

    expected = (
        EXPECTED_PROVINCES,
        EXPECTED_CITIES,
        EXPECTED_RAIL_TRIPS,
        EXPECTED_RAIL_DISTANCE_KM,
    )
    actual = (province_count, city_count, len(records), distance_km)
    if actual != expected:
        raise RuntimeError(f"Article totals do not match: expected {expected}, got {actual}")
    if class_counts != {"conventional": 45, "high_speed_emu": 92}:
        raise RuntimeError(f"Rail class totals do not match article: {class_counts}")

    warnings = []
    for region in regions:
        stated = region.get("stated_count")
        if stated is not None and stated != region["listed_count"]:
            warnings.append(
                f"{region['province']} states {stated}, lists {region['listed_count']} cities"
            )

    payload = {
        "source": str(args.article.resolve()),
        "visited_regions": regions,
        "rail_records": records,
        "summary": {
            "province_count": province_count,
            "city_count": city_count,
            "rail_trip_count": len(records),
            "rail_distance_km": distance_km,
            "rail_class_counts": class_counts,
            "warnings": warnings,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
