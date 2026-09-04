"""Parse visited places and railway records from the travel-history post."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


DEFAULT_POST = Path(r"F:\Desktop\Blog\source\_posts\行旅杂记.md")
DEFAULT_OUTPUT = Path(__file__).with_name("parsed_source.json")

PROVINCE_NAME_MAP = {
    "广东": "广东省",
    "贵州": "贵州省",
    "安徽": "安徽省",
    "湖北": "湖北省",
    "湖南": "湖南省",
    "江苏": "江苏省",
    "陕西": "陕西省",
    "山西": "山西省",
    "江西": "江西省",
    "浙江": "浙江省",
    "河南": "河南省",
    "山东": "山东省",
    "福建": "福建省",
    "河北": "河北省",
    "辽宁": "辽宁省",
    "甘肃": "甘肃省",
    "北京": "北京市",
    "上海": "上海市",
    "天津": "天津市",
    "广西": "广西壮族自治区",
    "内蒙古": "内蒙古自治区",
}

# Map service classes follow the article's statistical convention: D/C/S
# services are counted with high-speed/EMU records even when they use a
# conventional physical line.
CONVENTIONAL_TRAIN_EXCEPTIONS: set[str] = set()
ROUTE_CONTROL_POINTS = {
    ("湛江", "北京西", "K158"): [
        "遂溪", "廉江", "陆川", "玉林", "贵港", "柳州", "桂林北",
        "全州南", "永州", "衡阳", "长沙", "武昌", "花园", "广水",
        "信阳", "驻马店", "西平", "漯河", "许昌", "郑州", "新乡",
        "鹤壁", "安阳", "邯郸", "邢台", "石家庄", "定州", "保定",
        "高碑店",
    ],
    ("合肥", "德州", "K1036"): ["蚌埠", "宿州", "徐州"],
}


def split_markdown_row(line: str) -> list[str]:
    value = line.strip()
    if value.startswith("|"):
        value = value[1:]
    if value.endswith("|"):
        value = value[:-1]
    return [cell.strip() for cell in value.split("|")]


def parse_places(lines: list[str]) -> list[dict]:
    start = next(
        i for i, line in enumerate(lines) if "至此，共计去过21个省级行政区" in line
    )
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("<figure"))
    places = []
    category = "province"
    for line in lines[start + 1 : end]:
        stripped = line.strip()
        if stripped == "- 直辖市":
            category = "municipality"
            continue
        if stripped == "- 自治区":
            category = "autonomous_region"
            continue
        if not stripped.startswith("- ") or stripped in {"- 省"}:
            continue
        body = stripped[2:].strip()
        if "：" in body:
            province_part, city_part = body.split("：", 1)
            province = re.sub(r"（.*?）", "", province_part).strip()
            cities = [value.strip() for value in city_part.split("、") if value.strip()]
            places.append(
                {
                    "category": category,
                    "province": province,
                    "province_full": PROVINCE_NAME_MAP[province],
                    "cities": cities,
                }
            )
        else:
            names = [value.strip() for value in body.split("、") if value.strip()]
            for name in names:
                places.append(
                    {
                        "category": category,
                        "province": name,
                        "province_full": PROVINCE_NAME_MAP[name],
                        "cities": [name],
                    }
                )
    return places


def classify_service(train: str, origin: str, destination: str) -> str:
    normalized = re.sub(r"\s+", "", train).upper()
    if normalized in CONVENTIONAL_TRAIN_EXCEPTIONS:
        return "conventional"
    if normalized.startswith(("G", "C", "D", "S")):
        return "highspeed"
    if normalized == "不详":
        # Zhanjiang West services after the 2018 opening of the Jiangmao-
        # Shenzhen-Zhanjiang corridor used the passenger railway.
        if "湛江西" in {origin, destination} and (
            origin in {"小榄", "佛山西", "广州南", "湛江西"}
            or destination in {"小榄", "佛山西", "广州南", "湛江西"}
        ):
            return "highspeed"
        return "unknown"
    return "conventional"


def parse_rail_records(lines: list[str]) -> list[dict]:
    header = next(
        i for i, line in enumerate(lines) if line.strip() == "|时间|出发地|目的地|车次|里程（km）|"
    )
    end = next(i for i in range(header + 1, len(lines)) if lines[i].strip() == "{% endhideToggle %}")
    records = []
    current_date = ""
    for line in lines[header + 2 : end]:
        if not line.strip().startswith("|"):
            continue
        cells = split_markdown_row(line)
        if len(cells) != 5:
            raise ValueError(f"Unexpected railway row: {line}")
        date, origin, destination, train, distance = cells
        current_date = date or current_date
        train = re.sub(r"\s+", "", train).upper()
        distance_value = int(re.sub(r"[^0-9]", "", distance))
        record = {
                "seq": len(records) + 1,
                "date": current_date,
                "origin": origin,
                "destination": destination,
                "train": train,
                "distance_km": distance_value,
                "service_class": classify_service(train, origin, destination),
            }
        controls = ROUTE_CONTROL_POINTS.get((origin, destination, train))
        if controls:
            record["control_points"] = controls
        records.append(record)
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--post", type=Path, default=DEFAULT_POST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    lines = args.post.read_text(encoding="utf-8").splitlines()
    places = parse_places(lines)
    rail_records = parse_rail_records(lines)
    city_count = sum(len(item["cities"]) for item in places)
    station_names = sorted(
        {record["origin"] for record in rail_records}
        | {record["destination"] for record in rail_records}
    )
    payload = {
        "source": str(args.post.resolve()),
        "province_count": len(places),
        "city_count": city_count,
        "places": places,
        "rail_record_count": len(rail_records),
        "station_count": len(station_names),
        "service_counts": Counter(record["service_class"] for record in rail_records),
        "stations": station_names,
        "rail_records": rail_records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"provinces={payload['province_count']}; cities={city_count}; "
        f"records={len(rail_records)}; stations={len(station_names)}; "
        f"services={dict(payload['service_counts'])}"
    )
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
