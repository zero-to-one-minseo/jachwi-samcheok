"""삼척 시내 바탕 지도 데이터를 OpenStreetMap(Overpass API)에서 받아 data/basemap.geojson으로 만든다.

앱은 바탕 지도 그림(타일)을 쓰지 않고 이 파일의 길·건물·강·공원을 직접 칠한다.
데이터: © OpenStreetMap 기여자, ODbL. 범위는 lib/map_view.py의 CITY_BOUNDS와 같다.

    .venv/bin/python tools/build_basemap.py                 # 받아서 만들기
    .venv/bin/python tools/build_basemap.py --raw 받은.json  # 이미 받은 Overpass JSON으로 만들기
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
OUT_PATH = APP_DIR / "data" / "basemap.geojson"
OVERPASS = "https://overpass-api.de/api/interpreter"
# CITY_BOUNDS보다 조금 넓게 받아 가장자리가 비지 않게 한다.
BBOX = (37.420, 129.128, 37.473, 129.202)

MAJOR = {"motorway", "trunk", "primary", "motorway_link", "trunk_link", "primary_link"}
MIDDLE = {"secondary", "tertiary", "secondary_link", "tertiary_link"}
MINOR = {"residential", "unclassified", "living_street", "service", "road"}
GREEN_LANDUSE = {"forest", "grass", "meadow", "recreation_ground", "village_green", "cemetery"}
LABEL_AMENITY = {"university", "college", "school", "townhall", "hospital", "police", "fire_station",
                 "bus_station", "library", "post_office"}
LABEL_SHOP = {"supermarket", "mall", "department_store"}


def query() -> str:
    s, w, n, e = BBOX
    b = f"({s},{w},{n},{e})"
    return f"""[out:json][timeout:90];
(
  way["highway"]{b};
  way["building"]{b};
  way["natural"~"water|wood"]{b};
  relation["natural"="water"]{b};
  way["waterway"~"riverbank|river"]{b};
  way["leisure"~"park|pitch|stadium|garden"]{b};
  way["landuse"]{b};
  way["amenity"~"university|college|school"]{b};
  way["railway"="rail"]{b};
  node["amenity"]["name"]{b};
  node["shop"]["name"]{b};
  node["railway"="station"]["name"]{b};
  way["amenity"]["name"]{b};
  way["shop"]["name"]{b};
);
out geom;"""


def fetch() -> dict:
    data = urllib.parse.urlencode({"data": query()}).encode()
    req = urllib.request.Request(OVERPASS, data=data, headers={"User-Agent": "jachwi-samcheok-basemap/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def _coords(geom: list[dict]) -> list[list[float]]:
    return [[round(p["lon"], 5), round(p["lat"], 5)] for p in geom]


def classify(tags: dict) -> str | None:
    hw = tags.get("highway")
    if hw:
        if hw in MAJOR:
            return "road_major"
        if hw in MIDDLE:
            return "road_middle"
        if hw in MINOR:
            return "road_minor"
        return None
    if tags.get("railway") == "rail":
        return "rail"
    if tags.get("natural") == "water" or tags.get("waterway") == "riverbank":
        return "water"
    if tags.get("waterway") == "river":
        return "river"
    if tags.get("amenity") in ("university", "college", "school"):
        return "campus"
    if tags.get("leisure") in ("pitch", "stadium"):
        return "pitch"
    if tags.get("leisure") in ("park", "garden") or tags.get("natural") == "wood" or tags.get("landuse") in GREEN_LANDUSE:
        return "green"
    if tags.get("landuse") == "residential":
        return "residential"
    if tags.get("landuse") in ("commercial", "retail"):
        return "commercial"
    if tags.get("building"):
        return "building"
    return None


LINE_KINDS = {"road_major", "road_middle", "road_minor", "rail", "river"}


# 같은 곳이 옛 이름·다른 이름으로 한 번 더 들어 있어 이름표가 겹치는 것.
DUPLICATE_NAMES = {"강원도 삼척의료원", "삼척 터미널"}
PRIORITY_WORDS = ("강원대학교", "삼척시청", "터미널", "홈플러스", "삼척의료원")


def is_priority(name: str, tags: dict) -> bool:
    return tags.get("railway") == "station" or any(w in name for w in PRIORITY_WORDS)


def label_kind(tags: dict) -> str | None:
    name = tags.get("name") or ""
    # 동네 의원·약국까지 넣으면 지도가 이름표로 덮인다.
    if not name or name.endswith("의원") or "(" in name or name in DUPLICATE_NAMES:
        return None
    if tags.get("amenity") in LABEL_AMENITY:
        return "public"
    if tags.get("shop") in LABEL_SHOP:
        return "shop"
    if tags.get("railway") == "station":
        return "public"
    if tags.get("leisure") == "park":
        return "park"
    return None


def _centroid(pts: list[list[float]]) -> list[float]:
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [round(sum(xs) / len(xs), 5), round(sum(ys) / len(ys), 5)]


def stitch(parts: list[list[list[float]]]) -> list[list[list[float]]]:
    """끝점이 맞닿은 선 조각들을 이어 닫힌 고리로 만든다(강처럼 여러 조각으로 그려진 면)."""
    pending = [p[:] for p in parts if len(p) >= 2]
    rings = []
    while pending:
        ring = pending.pop(0)
        grown = True
        while ring[0] != ring[-1] and grown:
            grown = False
            for i, p in enumerate(pending):
                if p[0] == ring[-1]:
                    ring += p[1:]
                elif p[-1] == ring[-1]:
                    ring += p[-2::-1]
                elif p[-1] == ring[0]:
                    ring = p[:-1] + ring
                elif p[0] == ring[0]:
                    ring = p[:0:-1] + ring
                else:
                    continue
                pending.pop(i)
                grown = True
                break
        if ring[0] == ring[-1]:
            rings.append(ring)
    return rings


def convert(raw: dict) -> dict:
    features: list[dict] = []
    labels: dict[str, dict] = {}
    for el in raw.get("elements", []):
        tags = el.get("tags", {})
        lk = label_kind(tags)
        if el["type"] == "node":
            if lk:
                labels.setdefault(tags["name"], {"name": tags["name"], "k": lk, "tags": tags, "at": [round(el["lon"], 5), round(el["lat"], 5)]})
            continue
        kind = classify(tags)
        if el["type"] == "way" and "geometry" in el:
            pts = _coords(el["geometry"])
            if lk and len(pts) > 2:
                labels.setdefault(tags["name"], {"name": tags["name"], "k": lk, "tags": tags, "at": _centroid(pts)})
            if not kind or len(pts) < 2:
                continue
            if kind in LINE_KINDS:
                geom = {"type": "LineString", "coordinates": pts}
            else:
                if pts[0] != pts[-1] or len(pts) < 4:
                    continue
                geom = {"type": "Polygon", "coordinates": [pts]}
            features.append({"type": "Feature", "properties": {"k": kind}, "geometry": geom})
        elif el["type"] == "relation" and kind == "water":
            def ring_list(role: str) -> list[list[list[float]]]:
                parts = [_coords(m["geometry"]) for m in el.get("members", []) if m.get("role") == role and m.get("geometry")]
                return [r for r in stitch(parts) if len(r) >= 4]
            holes = ring_list("inner")
            for outer in ring_list("outer"):
                features.append({"type": "Feature", "properties": {"k": "water"},
                                 "geometry": {"type": "Polygon", "coordinates": [outer, *holes]}})
    for lab in labels.values():
        props = {"k": "label", "kind": lab["k"], "name": lab["name"], "p": int(is_priority(lab["name"], lab["tags"]))}
        features.append({"type": "Feature", "properties": props, "geometry": {"type": "Point", "coordinates": lab["at"]}})
    return {"type": "FeatureCollection", "features": features}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw", type=Path, help="이미 받은 Overpass JSON 파일")
    ap.add_argument("--save-raw", type=Path, help="받은 Overpass JSON을 이 경로에 저장")
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    args = ap.parse_args(argv)
    raw = json.loads(args.raw.read_text(encoding="utf-8")) if args.raw else fetch()
    if args.save_raw:
        args.save_raw.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    gj = convert(raw)
    args.out.write_text(json.dumps(gj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    counts: dict[str, int] = {}
    for f in gj["features"]:
        counts[f["properties"]["k"]] = counts.get(f["properties"]["k"], 0) + 1
    print(f"{args.out} 저장: {len(gj['features'])}개 {counts}, {args.out.stat().st_size // 1024}KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
