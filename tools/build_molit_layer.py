"""국토부 실거래(data/molit_rent.csv)로 지도에 올릴 '길별 원룸 평균 시세'와 '건물 이름표'를 만든다.

    .venv/bin/python tools/build_molit_layer.py      # → web/public/data/molit_layer.json

길 위치와 건물 위치는 OpenStreetMap에서 받아 둔 data/raw/osm_roads.json, data/raw/osm_buildings.json을 쓴다.
단독다가구는 번지가 가려져 있어 길 단위로만 묶는다. 건물 이름표는 OSM에 같은 이름 건물이 있는 곳만 단다.
"""

from __future__ import annotations

import csv
import json
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from lib import rooms_data as rd  # noqa: E402

MOLIT_CSV = APP_DIR / "data" / "molit_rent.csv"
ROADS_JSON = APP_DIR / "data" / "raw" / "osm_roads.json"
BUILDINGS_JSON = APP_DIR / "data" / "raw" / "osm_buildings.json"
OUT = APP_DIR / "web" / "public" / "data" / "molit_layer.json"
CITY_DONGS = sorted({d for ds in rd.AREA_DONGS.values() for d in ds})
MIN_ROAD_RECORDS = 3


def read_molit() -> list[dict]:
    lines = MOLIT_CSV.read_text(encoding="utf-8-sig").splitlines()[2:]
    return list(csv.DictReader(lines))


def base_road(road: str) -> str:
    return re.sub(r"\s+\d[\d-]*$", "", road or "").strip()


def norm_name(name: str) -> str:
    return re.sub(r"\s|\(.*?\)", "", name or "")


def road_points() -> dict[str, list[tuple[float, float]]]:
    pts: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for e in json.loads(ROADS_JSON.read_text(encoding="utf-8"))["elements"]:
        pts[e["tags"]["name"]] += [(g["lat"], g["lon"]) for g in e.get("geometry", [])]
    return pts


def middle_point(points: list[tuple[float, float]]) -> tuple[float, float]:
    """길 위에 있는 점 가운데, 그 길 전체의 무게중심에 가장 가까운 점."""
    clat = sum(p[0] for p in points) / len(points)
    clon = sum(p[1] for p in points) / len(points)
    return min(points, key=lambda p: (p[0] - clat) ** 2 + (p[1] - clon) ** 2)


def med(values: list[float]) -> float | None:
    return round(st.median(values), 1) if values else None


def summarize(group: list[dict]) -> dict:
    monthly = [float(r["monthly"]) for r in group if r["rent_kind"] == "월세" and r["monthly"]]
    deposit = [float(r["deposit"]) for r in group if r["deposit"]]
    area = [float(r["area_m2"]) for r in group if r["area_m2"]]
    built = [int(r["built_year"]) for r in group if r["built_year"].isdigit()]
    yms = sorted(r["contract_ym"] for r in group)
    return {"n": len(group), "monthly": med(monthly), "deposit": med(deposit), "area": med(area),
            "built": int(st.median(built)) if built else None, "from": yms[0], "to": yms[-1]}


def write_market(all_rows: list[dict]) -> None:
    """챗봇 비교용 자료(web/api/_engine/data/market.json). 실거래 전체와 팀 조사 방을 짧은 칸으로만 담는다."""
    fnum = lambda v: float(v) if v not in ("", None) else None  # noqa: E731
    molit = [{"type": r["type"], "dong": r["dong"], "road": base_road(r["road"]), "building": r["building"],
              "area": fnum(r["area_m2"]), "kind": r["rent_kind"], "deposit": fnum(r["deposit"]),
              "monthly": fnum(r["monthly"]), "built": int(r["built_year"]) if r["built_year"].isdigit() else None,
              "ym": r["contract_ym"], "roomlike": r["roomlike"] == "1"} for r in all_rows]
    survey = [{"name": r.get("name"), "area": r.get("area"), "dong": (r.get("dong") or "").split("(")[0],
               "monthly": r.get("monthly"), "deposit": r.get("deposit"), "contract": r.get("contract_type"),
               "kind": r.get("kind"), "size_m2": r.get("size_m2")} for r in rd.visible_rooms(rd.read_rooms())]
    out = APP_DIR / "web" / "api" / "_engine" / "data" / "market.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"area_dongs": rd.AREA_DONGS, "molit": molit, "survey": survey},
                              ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"market.json: 실거래 {len(molit)}건, 팀 조사 {len(survey)}곳")


def main() -> int:
    rows = [r for r in read_molit() if r["dong"] in CITY_DONGS]
    pts = road_points()

    by_road: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["roomlike"] == "1" and r["road"]:
            by_road[base_road(r["road"])].append(r)
    roads = []
    for name, group in by_road.items():
        if len(group) < MIN_ROAD_RECORDS or name not in pts:
            continue
        lat, lon = middle_point(pts[name])
        roads.append({"name": name, "lat": lat, "lon": lon, "dongs": sorted({r["dong"] for r in group}), **summarize(group)})
    roads.sort(key=lambda x: -x["n"])

    osm = {}
    for e in json.loads(BUILDINGS_JSON.read_text(encoding="utf-8"))["elements"]:
        osm.setdefault(norm_name(e["tags"]["name"]), (e["center"]["lat"], e["center"]["lon"]))
    by_building: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        if r["building"]:
            by_building[(r["type"], r["building"])].append(r)
    buildings, unplaced = [], []
    for (kind, name), group in by_building.items():
        key = norm_name(name)
        hit = osm.get(key) or next((v for k, v in osm.items() if len(k) >= 3 and (k in key or key in k)), None)
        item = {"name": name, "type": kind, "dong": group[0]["dong"], **summarize(group)}
        if hit:
            buildings.append({**item, "lat": hit[0], "lon": hit[1]})
        else:
            unplaced.append(item)

    dongs = []
    for d in CITY_DONGS:
        group = [r for r in rows if r["dong"] == d and r["roomlike"] == "1"]
        if group:
            dongs.append({"dong": d, **summarize(group)})

    write_market(read_molit())

    data = {"source": "국토교통부 실거래가 공개시스템 삼척시 전월세(계약일 2023-11-06~2026-11-05)",
            "roomlike": "월세, 40㎡ 이하, 아파트 제외", "roads": roads, "buildings": buildings, "dongs": dongs}
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"molit_layer.json: 길 {len(roads)}곳, 건물 {len(buildings)}곳(위치 못 찾음 {len(unplaced)}곳), 동 {len(dongs)}곳")
    return 0


if __name__ == "__main__":
    sys.exit(main())
