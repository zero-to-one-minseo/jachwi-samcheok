"""국토부 원룸형 거래가 있는 삼척 시내 길의 건물을 모두 찾아, 건축물대장 정보와 실거래를 건물 단위로 맞춘다.

    .venv/bin/python tools/build_buildings.py

1) 도로명주소 검색 API: 길 이름 → 그 길의 건물 목록(도로명주소, 지번, 건물 이름)
2) 건축HUB 건축물대장 표제부 API: 지번 → 주용도, 사용승인일, 연면적, 층수, 가구·세대 수
3) 연립다세대·오피스텔 거래는 번지가 그대로 나와 그 번지의 건물로 정한다.
   단독다가구 거래는 번지가 가려져 있어 길·준공 연도(±1)·번지 앞자리로 후보를 고르고, 거래 종류와 대장 용도,
   2가구 이상, 연면적÷가구 수, 층별개요의 한 칸 크기, 같은 준공 연도 순으로 좁힌다. 후보가 하나면 그 건물로 '추정'한다.

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
FLOOR_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrFlrOulnInfo"
HOUSING = ("다가구", "다세대", "연립", "단독주택", "공동주택", "도시형", "오피스텔", "기숙사", "근린생활")
CITY_DONGS = {d for ds in rd.AREA_DONGS.values() for d in ds}
YEAR_TOL = 1
UNIT_AREA_TOL = 0.35
FLOOR_UNIT_TOL = 0.2
MIN_PUBLIC_DEALS = 3
HOW = {"jibun": "번지 그대로(연립다세대·오피스텔)", "road": "길·연도·번지 앞자리", "type": "거래 종류와 대장 용도",
       "households": "2가구 이상", "size": "연면적÷가구 수", "floor": "층별개요", "year": "같은 준공 연도"}


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


def register(addr: dict, key: str, url: str = TITLE_URL) -> list[dict] | None:
    """대장 목록. 서버가 거절하거나 끊기면 None(다음 실행 때 다시 묻는다), 대장이 정말 없으면 빈 목록."""
    adm = addr["admCd"]
    q = urllib.parse.urlencode({"serviceKey": key, "sigunguCd": adm[:5], "bjdongCd": adm[5:],
                                "platGbCd": "1" if addr.get("mtYn") == "1" else "0",
                                "bun": str(addr["lnbrMnnm"]).zfill(4), "ji": str(addr["lnbrSlno"]).zfill(4),
                                "_type": "json", "numOfRows": "50", "pageNo": "1"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(f"{url}?{q}", timeout=20) as r:
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


def load(k: dict[str, str]) -> tuple[list[dict], dict, dict[str, dict], list[dict]]:
    rows = read_molit()
    roads = sorted({base_road(r["road"]) for r in rows if r["roomlike"] == "1" and r["dong"] in CITY_DONGS and r["road"]})
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {"roads": {}, "titles": {}}

    todo = [r for r in roads if r not in cache["roads"]]
    with ThreadPoolExecutor(3) as ex:
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
            # 오피스텔은 대장 주용도가 '업무시설'이고 가구·세대 수 대신 호수만 적힌다. 이름에 '오피스텔'이 있는 것만 넣는다.
            officetel = purpose == "업무시설" and "오피스텔" in (t.get("bldNm") or "")
            if not (any(h in purpose for h in HOUSING) or officetel) or not year.isdigit():
                continue
            name = (t.get("bldNm") or "").strip() or a["bdNm"]
            households = (t.get("fmlyCnt") or 0) + (t.get("hhldCnt") or 0) or (t.get("hoCnt") or 0 if officetel else 0)
            buildings.append({"id": f"b{len(buildings) + 1:04d}", "road": a["road"], "address": a["roadAddrPart1"],
                              "name": name, "dong": a["emdNm"], "purpose": "오피스텔" if officetel else purpose,
                              "built": int(year), "floors": t.get("grndFlrCnt"), "households": households,
                              "area_total": t.get("totArea"), "jibun": f"{a['lnbrMnnm']}-{a['lnbrSlno']}", "jkey": j})
    return rows, cache, addrs, buildings


def full_jibun(r: dict) -> str | None:
    """연립다세대·오피스텔 거래는 번지가 그대로 나온다('8-3', '197'). 가려진 번지('2**')면 None."""
    jb = r["jibun"].strip()
    if re.fullmatch(r"\d+(-\d+)?", jb):
        return jb if "-" in jb else f"{jb}-0"
    return None


def road_candidates(r: dict, by_road_year: dict[tuple[str, int], list[dict]]) -> list[tuple[list[dict], str]]:
    """번지가 가려진 거래의 후보를 단서마다 좁혀 간 단계 목록 [(남은 후보, 단서 이름)]."""
    y = int(r["built_year"])
    cands = [b for d in range(-YEAR_TOL, YEAR_TOL + 1) for b in by_road_year.get((base_road(r["road"]), y + d), [])]
    # 국토부는 단독다가구 번지를 '2**'처럼 앞자리와 자릿수만 남기고 가린다. 같은 동·같은 모양의 본번만 남긴다.
    mask = r["jibun"].strip()
    if re.fullmatch(r"\d?\*+", mask):
        pattern = re.compile("^" + mask.replace("*", r"\d") + "$")
        cands = [b for b in cands if b["dong"] == r["dong"] and pattern.match(b["jibun"].split("-")[0])]
    steps = [(cands, "road")]
    # 국토부는 대장 용도로 거래 종류를 나눈다. 단독다가구 거래는 공동주택(다세대·연립)이나 오피스텔에 있을 수 없다.
    if len(cands) > 1 and r["type"] == "단독다가구":
        house = [b for b in cands if b["purpose"] not in ("공동주택", "오피스텔")]
        if house and len(house) < len(cands):
            cands = house
            steps.append((cands, "type"))
    if len(cands) > 1 and any((b["households"] or 0) >= 2 for b in cands):
        cands = [b for b in cands if (b["households"] or 0) >= 2]
        steps.append((cands, "households"))
    area = float(r["area_m2"]) if r["area_m2"] else None
    if len(cands) > 1 and area:
        # 다가구는 연면적 ÷ 가구 수가 방 한 칸의 평균 크기에 가깝다. 거래 면적과 맞는 건물만 남긴다.
        sized = [b for b in cands if b["households"] and b["area_total"]
                 and abs(b["area_total"] / b["households"] - area) / area <= UNIT_AREA_TOL]
        # 평균 크기는 방마다 다를 수 있는 약한 단서라, 같은 준공 연도 후보를 모두 빼고 다른 해 건물만 남기지는 않는다.
        keeps_year = any(b["built"] == y for b in sized) or not any(b["built"] == y for b in cands)
        if sized and keeps_year:
            cands = sized
            steps.append((cands, "size"))
    return steps


def unit_sizes(b: dict, floors: dict[str, list[dict]]) -> list[float]:
    sizes = []
    for f in floors.get(b["jkey"], []):
        m = re.search(r"(\d+)\s*(가구|세대)", f.get("etcPurps") or "")
        if m and f.get("area") and int(m.group(1)) > 0:
            sizes.append(float(f["area"]) / int(m.group(1)))
    return sizes


def match(deals: list[dict], buildings: list[dict], cache: dict, addrs: dict[str, dict], k: dict[str, str]) -> list[tuple[list[dict], str]]:
    """거래마다 (남은 후보 건물, 후보를 하나로 줄인 단서). 후보가 여럿이면 단서는 ''."""
    by_road_year: dict[tuple[str, int], list[dict]] = defaultdict(list)
    by_jibun: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for b in buildings:
        by_road_year[(b["road"], b["built"])].append(b)
        by_jibun[(b["dong"], b["jibun"])].append(b)

    steps = []
    for r in deals:
        jb = full_jibun(r)
        if jb:
            # 번지가 그대로 나온 거래는 그 번지의 건물이다. 한 번지에 동이 여럿이면 준공 연도로 고른다.
            cands = by_jibun.get((r["dong"], jb), [])
            same_year = [b for b in cands if b["built"] == int(r["built_year"])]
            steps.append([(same_year if len(same_year) == 1 else cands, "jibun")])
        else:
            steps.append(road_candidates(r, by_road_year))

    cache.setdefault("floors", {})
    need = sorted({b["jkey"] for s in steps if len(s[-1][0]) > 1 for b in s[-1][0]} - set(cache["floors"]))
    print(f"후보가 여럿인 거래의 층별개요 새로 조회 {len(need)}곳")
    with ThreadPoolExecutor(3) as ex:
        for j, items in zip(need, ex.map(lambda j: register(addrs[j], k["data"], FLOOR_URL), need)):
            if items is not None:
                cache["floors"][j] = [{f: i.get(f) for f in ("etcPurps", "area", "mainAtchGbCdNm", "flrGbCdNm")} for i in items]
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    out = []
    for r, s in zip(deals, steps):
        cands = s[-1][0]
        area = float(r["area_m2"]) if r["area_m2"] else None
        if len(cands) > 1 and area and s[-1][1] != "jibun":
            # 층별개요의 '층 면적 ÷ 그 층 가구 수'가 거래 면적과 맞지 않는 건물을 뺀다.
            # 층별 가구 수가 안 적힌 건물('다가구주택'만 적힘)은 모르는 것이지 안 맞는 것이 아니라 남긴다.
            # 다만 다른 후보가 빠져 '모르는' 건물 하나만 남으면, 그 건물이 맞는다는 근거는 없으니 줄이지 않는다.
            def fits(b: dict) -> bool | None:
                sizes = unit_sizes(b, cache["floors"])
                return any(abs(u - area) / area <= FLOOR_UNIT_TOL for u in sizes) if sizes else None
            # 면적 단서로 같은 준공 연도 후보를 모두 빼고 다른 해 건물만 남기지도 않는다.
            fit = [b for b in cands if fits(b) is not False]
            y = int(r["built_year"])
            keeps_year = any(b["built"] == y for b in fit) or not any(b["built"] == y for b in cands)
            if fit and len(fit) < len(cands) and any(fits(b) for b in fit) and keeps_year:
                s.append((fit, "floor"))
                cands = fit
        if len(cands) > 1 and s[-1][1] != "jibun":
            # 국토부 건축년도와 대장 사용승인 연도는 1년 어긋날 때가 있어 ±1년으로 찾되, 남은 후보 중 같은 해가 하나면 그것으로 본다.
            same_year = [b for b in cands if b["built"] == int(r["built_year"])]
            if len(same_year) == 1:
                s.append((same_year, "year"))
                cands = same_year
        how = next((name for c, name in s if len(c) == 1), "") if len(cands) == 1 else ""
        out.append((cands, how))
    return out


def main() -> int:
    k = keys()
    rows, cache, addrs, buildings = load(k)
    deals = [r for r in rows if r["roomlike"] == "1" and r["dong"] in CITY_DONGS and r["built_year"].isdigit()]
    results = match(deals, buildings, cache, addrs, k)
    matched = defaultdict(list)
    stats = defaultdict(int)
    for r, (pick, how) in zip(deals, results):
        if len(pick) == 1:
            stats["unique"] += 1
            stats[how] += 1
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

    # 정밀한 대조 결과(지번, 거래 기간·면적)는 git이 무시하는 data/raw에만 둔다.
    (CACHE.parent / "buildings_full.json").write_text(json.dumps(buildings, ensure_ascii=False), encoding="utf-8")
    # 국토부가 번지를 가린 단독다가구 거래를 건물에 맞춘 결과라, 공개 파일에는 거래 3건 이상인 건물의 가운데 값만 싣는다.
    public = []
    for b in buildings:
        shown = b["deals"] >= MIN_PUBLIC_DEALS
        public.append({**{f: b[f] for f in ("id", "road", "address", "name", "dong", "purpose", "built", "floors",
                                            "households", "area_total")},
                       "deals": b["deals"] if shown else 0, "monthly": b["monthly"] if shown else None,
                       "deposit": b["deposit"] if shown else None})
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        f.write('"출처: 행정안전부 도로명주소 검색 API(건물 목록) + 국토교통부 건축HUB 건축물대장 표제부·층별개요 '
                '+ 국토부 전월세 실거래(번지가 가려진 거래는 길·준공 연도·방 크기로 맞춘 추정, 거래 3건 이상인 건물만 가운데 값 공개)"\n')
        w = csv.DictWriter(f, fieldnames=list(public[0].keys()))
        w.writeheader()
        w.writerows(public)
    OUT_JSON.write_text(json.dumps(public, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"주거용 건물 {len(buildings)}곳, 거래가 붙은 건물 {sum(1 for b in buildings if b['deals'])}곳"
          f"(가격 공개 {sum(1 for b in public if b['deals'])}곳)")
    print(f"원룸형 거래 맞춤: 건물 하나로 추정 {stats['unique']}건, 후보 여럿 {stats['several']}건, 후보 없음 {stats['none']}건")
    print("  하나로 정한 단서: " + ", ".join(f"{HOW[h]} {stats[h]}건" for h in HOW if stats[h]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
