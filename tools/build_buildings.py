"""국토부 원룸형 거래가 있는 삼척 시내 길의 건물을 모두 찾아, 건축물대장 정보와 실거래를 건물 단위로 맞춘다.

    .venv/bin/python tools/build_buildings.py

1) 도로명주소 검색 API: 길 이름 → 그 길의 건물 목록(도로명주소, 지번, 건물 이름)
2) 건축HUB 건축물대장 표제부 API: 지번 → 주용도, 사용승인일, 연면적, 층수, 가구·세대 수
3) 단독다가구 거래는 번지가 가려져 있어 (길, 준공 연도)로 건물 후보를 고른다. 후보가 하나면 그 건물로 '추정'한다.

받은 응답은 data/raw/buildings_cache.json에 모아 두어 다시 돌릴 때 API를 또 부르지 않는다.
만드는 파일: data/buildings.csv(건물 목록), web/api/_engine/data/buildings.json(챗봇 비교용)
열쇠: .streamlit/secrets.toml의 JUSO_SEARCH_KEY, DATA_GO_KR_KEY
"""

from __future__ import annotations

import csv
import json
import re
import statistics as st
import sys
import time
import tomllib
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from lib import rooms_data as rd  # noqa: E402
from tools import geocode_juso as gj  # noqa: E402

MOLIT_CSV = APP_DIR / "data" / "molit_rent.csv"
CACHE = APP_DIR / "data" / "raw" / "buildings_cache.json"
OUT_CSV = APP_DIR / "data" / "buildings.csv"
OUT_JSON = APP_DIR / "web" / "api" / "_engine" / "data" / "buildings.json"
TITLE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
HOUSING = ("다가구", "다세대", "연립", "단독주택", "공동주택", "도시형", "오피스텔", "기숙사", "근린생활")
CITY_DONGS = {d for ds in rd.AREA_DONGS.values() for d in ds}
YEAR_TOL = 1
UNIT_AREA_TOL = 0.35


def keys() -> dict[str, str]:
    with (APP_DIR / ".streamlit" / "secrets.toml").open("rb") as f:
        s = tomllib.load(f)
    return {"juso": s["JUSO_SEARCH_KEY"], "data": s["DATA_GO_KR_KEY"]}


def road_buildings(road: str, key: str) -> list[dict]:
    out, page = [], 1
    while True:
        items = gj._get(gj.SEARCH_URL, {"confmKey": key, "currentPage": str(page), "countPerPage": "100",
                                        "keyword": f"강원특별자치도 삼척시 {road}", "resultType": "json"})
        out += [i for i in items if i.get("rn") == road]
        if len(items) < 100 or page >= 10:
            return out
        page += 1


def register(addr: dict, key: str) -> list[dict] | None:
    """대장 목록. 서버가 거절하거나 끊기면 None(다음 실행 때 다시 묻는다), 대장이 정말 없으면 빈 목록."""
    adm = addr["admCd"]
    q = urllib.parse.urlencode({"serviceKey": key, "sigunguCd": adm[:5], "bjdongCd": adm[5:],
                                "platGbCd": "1" if addr.get("mtYn") == "1" else "0",
                                "bun": str(addr["lnbrMnnm"]).zfill(4), "ji": str(addr["lnbrSlno"]).zfill(4),
                                "_type": "json", "numOfRows": "50", "pageNo": "1"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(f"{TITLE_URL}?{q}", timeout=20) as r:
                res = json.load(r)["response"]
            if res.get("header", {}).get("resultCode") != "00":
                raise RuntimeError(res.get("header", {}).get("resultMsg"))
            items = (res["body"].get("items") or {}).get("item") or []
            return items if isinstance(items, list) else [items]
        except Exception:  # noqa: BLE001
            time.sleep(1.5 * (attempt + 1))
    return None


def read_molit() -> list[dict]:
    return list(csv.DictReader(MOLIT_CSV.read_text(encoding="utf-8-sig").splitlines()[2:]))


def base_road(road: str) -> str:
    return re.sub(r"\s+\d[\d-]*$", "", road or "").strip()


def main() -> int:
    k = keys()
    rows = read_molit()
    roads = sorted({base_road(r["road"]) for r in rows if r["roomlike"] == "1" and r["dong"] in CITY_DONGS and r["road"]})
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {"roads": {}, "titles": {}}

    todo = [r for r in roads if r not in cache["roads"]]
    with ThreadPoolExecutor(4) as ex:
        for road, items in zip(todo, ex.map(lambda r: road_buildings(r, k["juso"]), todo)):
            cache["roads"][road] = [{f: i.get(f, "") for f in ("roadAddrPart1", "bdNm", "admCd", "mtYn", "lnbrMnnm", "lnbrSlno", "emdNm")}
                                    for i in items]
    addrs = {}
    for road in roads:
        for a in cache["roads"].get(road, []):
            jkey = f"{a['admCd']}-{a['mtYn']}-{a['lnbrMnnm']}-{a['lnbrSlno']}"
            addrs.setdefault(jkey, {**a, "road": road})
    todo = [j for j in addrs if j not in cache["titles"]]
    print(f"길 {len(roads)}곳, 건물 주소 {len(addrs)}곳, 새로 조회할 건축물대장 {len(todo)}곳")
    with ThreadPoolExecutor(3) as ex:
        for j, items in zip(todo, ex.map(lambda j: register(addrs[j], k["data"]), todo)):
            if items is None:
                continue
            cache["titles"][j] = [{f: i.get(f) for f in ("bldNm", "mainPurpsCdNm", "useAprDay", "totArea", "grndFlrCnt",
                                                       "fmlyCnt", "hhldCnt", "hoCnt", "dongNm")} for i in items]
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    buildings = []
    for j, a in addrs.items():
        for t in cache["titles"].get(j, []):
            purpose = t.get("mainPurpsCdNm") or ""
            year = str(t.get("useAprDay") or "")[:4]
            if not any(h in purpose for h in HOUSING) or not year.isdigit():
                continue
            name = (t.get("bldNm") or "").strip() or a["bdNm"]
            buildings.append({"id": f"b{len(buildings) + 1:04d}", "road": a["road"], "address": a["roadAddrPart1"],
                              "name": name, "dong": a["emdNm"], "purpose": purpose, "built": int(year),
                              "floors": t.get("grndFlrCnt"), "households": (t.get("fmlyCnt") or 0) + (t.get("hhldCnt") or 0),
                              "area_total": t.get("totArea"), "jibun": f"{a['lnbrMnnm']}-{a['lnbrSlno']}"})

    by_road_year: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for b in buildings:
        by_road_year[(b["road"], b["built"])].append(b)
    matched = defaultdict(list)
    stats = {"unique": 0, "several": 0, "none": 0}
    for r in rows:
        if r["roomlike"] != "1" or r["dong"] not in CITY_DONGS or not r["built_year"].isdigit():
            continue
        y = int(r["built_year"])
        cands = [b for d in range(-YEAR_TOL, YEAR_TOL + 1) for b in by_road_year.get((base_road(r["road"]), y + d), [])]
        exact = [b for b in cands if b["built"] == y]
        pick = exact if len(exact) == 1 else cands
        area = float(r["area_m2"]) if r["area_m2"] else None
        if len(pick) > 1 and area:
            # 다가구는 연면적 ÷ 가구 수가 방 한 칸의 평균 크기에 가깝다. 거래 면적과 맞는 건물만 남긴다.
            sized = [b for b in pick if b["households"] and b["area_total"]
                     and abs(b["area_total"] / b["households"] - area) / area <= UNIT_AREA_TOL]
            if sized:
                pick = sized
        if len(pick) == 1:
            stats["unique"] += 1
            matched[pick[0]["id"]].append(r)
        else:
            stats["several" if pick else "none"] += 1

    for b in buildings:
        recs = matched.get(b["id"], [])
        monthly = [float(r["monthly"]) for r in recs if r["monthly"]]
        b["deals"] = len(recs)
        b["monthly"] = round(st.median(monthly), 1) if monthly else None
        b["deposit"] = round(st.median([float(r["deposit"]) for r in recs if r["deposit"]]), 1) if recs else None
        b["area"] = round(st.median([float(r["area_m2"]) for r in recs if r["area_m2"]]), 1) if recs else None
        b["period"] = f"{min(r['contract_ym'] for r in recs)}~{max(r['contract_ym'] for r in recs)}" if recs else ""

    fields = ["id", "road", "address", "name", "dong", "purpose", "built", "floors", "households", "area_total", "jibun",
              "deals", "monthly", "deposit", "area", "period"]
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        f.write('"출처: 행정안전부 도로명주소 검색 API(건물 목록) + 국토교통부 건축HUB 건축물대장 표제부(용도·사용승인일·층수·가구 수) '
                '+ 국토부 전월세 실거래(길·준공 연도로 맞춘 추정)"\n')
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(buildings)
    OUT_JSON.write_text(json.dumps(buildings, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"주거용 건물 {len(buildings)}곳, 거래가 붙은 건물 {sum(1 for b in buildings if b['deals'])}곳")
    print(f"원룸형 거래 맞춤: 건물 하나로 추정 {stats['unique']}건, 후보 여럿 {stats['several']}건, 후보 없음 {stats['none']}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
