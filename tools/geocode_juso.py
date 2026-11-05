"""방 주소(도로명주소)를 행정안전부 도로명주소 API로 건물 출입구 좌표로 바꾼다. 네이버 검색 좌표를 걷어 내는 용도다.

    .venv/bin/python tools/geocode_juso.py --out 후보.csv
    .venv/bin/python tools/geocode_juso.py --apply 후보.csv --fallback 옛좌표.csv

--out: data/coords.csv에서 네이버 지역 검색으로 찾은 줄의 주소를 검색 API(주소 → 건물 코드)와
좌표제공 API(건물 코드 → 출입구 좌표, UTM-K)에 차례로 넣고 위도·경도로 바꿔 후보 파일을 쓴다. 지도는 안 바뀐다.
주소가 똑같이 맞고 지금 좌표와 200m 안이면 review 칸에 ok를 미리 적는다. 나머지는 사람이 보고 ok를 적는다.
--apply: review가 ok인 줄을 coords.csv에 넣는다. --fallback(네이버를 쓰기 전 coords.csv)을 주면 ok가 아닌
네이버 줄은 예전 대략 위치로 되돌린다. 그래서 반영 뒤에는 네이버 검색 결과가 남지 않는다.
열쇠는 .streamlit/secrets.toml의 JUSO_SEARCH_KEY(필수), JUSO_COORD_KEY에서 읽는다(저장소에 올리지 않는다).
좌표 키가 아직 없으면 주소 확인과 건물 코드까지만 적고 좌표 칸은 비워 둔다.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
SECRETS = APP_DIR / ".streamlit" / "secrets.toml"
COORDS_CSV = APP_DIR / "data" / "coords.csv"
SEARCH_URL = "https://business.juso.go.kr/addrlink/addrLinkApi.do"
COORD_URL = "https://business.juso.go.kr/addrlink/addrCoordApi.do"
NAVER_METHOD = "네이버 지역 검색(NAVER API HUB)"
JUSO_METHOD = "행정안전부 도로명주소 API(건물 출입구 좌표)"
COORD_FIELDS = ["id", "name", "dong", "area", "lat", "lon", "precision", "method", "note", "address", "place_name"]
CODE_KEYS = ("admCd", "rnMgtSn", "udrtYn", "buldMnnm", "buldSlno")
OUT_FIELDS = ["name", "dong", "area", "address_in", "road_addr", "bd_nm", *CODE_KEYS,
              "ent_x", "ent_y", "lat", "lon", "gap_m", "status", "review"]
AUTO_OK_GAP_M = 200
# 좌표제공 API는 5초에 10건까지만 받는다.
COORD_PAUSE_S = 0.6

# UTM-K(EPSG:5179): GRS80 타원체, 원점 북위 38도·동경 127.5도, 축척 0.9996, 원점 가산값 동 1,000,000·북 2,000,000.
# 식은 Snyder, Map Projections: A Working Manual(USGS 1395)의 가로 메르카토르 식이다.
A = 6378137.0
F = 1 / 298.257222101
E2 = F * (2 - F)
EP2 = E2 / (1 - E2)
K0 = 0.9996
LAT0 = math.radians(38.0)
LON0 = math.radians(127.5)
FE, FN = 1_000_000.0, 2_000_000.0


def _meridian(phi: float) -> float:
    e4, e6 = E2 * E2, E2 ** 3
    return A * ((1 - E2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * phi
                - (3 * E2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * math.sin(2 * phi)
                + (15 * e4 / 256 + 45 * e6 / 1024) * math.sin(4 * phi)
                - (35 * e6 / 3072) * math.sin(6 * phi))


M0 = _meridian(LAT0)


def wgs84_to_utmk(lat: float, lon: float) -> tuple[float, float]:
    phi, lam = math.radians(lat), math.radians(lon)
    n = A / math.sqrt(1 - E2 * math.sin(phi) ** 2)
    t = math.tan(phi) ** 2
    c = EP2 * math.cos(phi) ** 2
    a = (lam - LON0) * math.cos(phi)
    x = FE + K0 * n * (a + (1 - t + c) * a ** 3 / 6 + (5 - 18 * t + t * t + 72 * c - 58 * EP2) * a ** 5 / 120)
    y = FN + K0 * (_meridian(phi) - M0 + n * math.tan(phi) * (
        a * a / 2 + (5 - t + 9 * c + 4 * c * c) * a ** 4 / 24
        + (61 - 58 * t + t * t + 600 * c - 330 * EP2) * a ** 6 / 720))
    return x, y


def utmk_to_wgs84(x: float, y: float) -> tuple[float, float]:
    mu = (M0 + (y - FN) / K0) / (A * (1 - E2 / 4 - 3 * E2 ** 2 / 64 - 5 * E2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - E2)) / (1 + math.sqrt(1 - E2))
    phi1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
            + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * math.sin(6 * mu)
            + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    s, co = math.sin(phi1), math.cos(phi1)
    n1 = A / math.sqrt(1 - E2 * s * s)
    r1 = A * (1 - E2) / (1 - E2 * s * s) ** 1.5
    t1 = math.tan(phi1) ** 2
    c1 = EP2 * co * co
    d = (x - FE) / (n1 * K0)
    phi = phi1 - (n1 * math.tan(phi1) / r1) * (
        d * d / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 * c1 - 9 * EP2) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 * t1 - 252 * EP2 - 3 * c1 * c1) * d ** 6 / 720)
    lam = LON0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6
                  + (5 - 2 * c1 + 28 * t1 - 3 * c1 * c1 + 8 * EP2 + 24 * t1 * t1) * d ** 5 / 120) / co
    return math.degrees(phi), math.degrees(lam)


def gap_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


def norm_addr(text: str) -> str:
    t = re.sub(r"\(.*?\)", "", text or "").replace("강원도", "강원특별자치도")
    return re.sub(r"\s", "", t)


def pick(address: str, items: list[dict]) -> dict | None:
    """도로명주소가 글자 그대로 같은 건물 하나를 고른다. 같은 주소에 동이 여럿이면 코드가 같으니 첫 줄을 쓴다."""
    want = norm_addr(address)
    exact = [it for it in items if norm_addr(it.get("roadAddrPart1", "")) == want]
    codes = {tuple(it.get(k, "") for k in CODE_KEYS) for it in exact}
    return exact[0] if len(codes) == 1 else None


def keys() -> dict[str, str | None]:
    """검색 키는 꼭 있어야 한다. 좌표 키가 없으면 주소 확인과 코드까지만 하고 좌표 칸은 비워 둔다."""
    with SECRETS.open("rb") as f:
        s = tomllib.load(f)
    if not s.get("JUSO_SEARCH_KEY"):
        sys.exit("secrets.toml에 JUSO_SEARCH_KEY가 없어요")
    return {"search": s["JUSO_SEARCH_KEY"], "coord": s.get("JUSO_COORD_KEY")}


class LinkError(Exception):
    """서버에 닿지 못했다(키 문제가 아니다). 그 주소만 건너뛰고 나중에 다시 돌린다."""


def _get(url: str, params: dict[str, str], tries: int = 3) -> list[dict]:
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(f"{url}?{urllib.parse.urlencode(params)}", timeout=20) as r:
                res = json.load(r)["results"]
            break
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == tries - 1:
                raise LinkError(str(e)) from e
            time.sleep(3 * (attempt + 1))
    common = res.get("common", {})
    if common.get("errorCode") != "0":
        raise RuntimeError(f"{common.get('errorCode')} {common.get('errorMessage')}")
    return res.get("juso") or []


def lookup(address: str, k: dict[str, str | None]) -> dict:
    out = {f: "" for f in OUT_FIELDS if f not in ("name", "dong", "area", "address_in")}
    items = _get(SEARCH_URL, {"confmKey": k["search"], "currentPage": "1", "countPerPage": "10",
                              "keyword": address, "resultType": "json"})
    time.sleep(0.2)
    item = pick(address, items)
    if not item:
        out["status"] = f"맞는 주소 없음(검색 {len(items)}건)"
        return out
    out.update(road_addr=item["roadAddrPart1"], bd_nm=item.get("bdNm", ""), **{c: item[c] for c in CODE_KEYS})
    if not k["coord"]:
        out["status"] = "주소 확인(좌표 키 대기)"
        return out
    rows = _get(COORD_URL, {"confmKey": k["coord"], "resultType": "json", **{c: item[c] for c in CODE_KEYS}})
    time.sleep(COORD_PAUSE_S)
    if not rows or not rows[0].get("entX"):
        out["status"] = "좌표 없음(비공개 건물일 수 있음)"
        return out
    lat, lon = utmk_to_wgs84(float(rows[0]["entX"]), float(rows[0]["entY"]))
    out.update(ent_x=rows[0]["entX"], ent_y=rows[0]["entY"], lat=f"{lat:.6f}", lon=f"{lon:.6f}",
               bd_nm=rows[0].get("bdNm") or out["bd_nm"], status="후보")
    return out


def build(out_path: Path) -> int:
    k = keys()
    with COORDS_CSV.open(encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["method"] == NAVER_METHOD]
    cache: dict[str, dict] = {}
    result = []
    for r in rows:
        addr = r["address"]
        if addr not in cache:
            try:
                cache[addr] = lookup(addr, k)
            except LinkError:
                cache[addr] = {f: "" for f in OUT_FIELDS} | {"status": "연결 실패(다시 돌리기)"}
        hit = {f: v for f, v in cache[addr].items() if f not in ("name", "dong", "area", "address_in")}
        if hit["lat"]:
            gap = gap_m(float(r["lat"]), float(r["lon"]), float(hit["lat"]), float(hit["lon"]))
            hit["gap_m"] = str(round(gap))
            hit["review"] = "ok" if gap <= AUTO_OK_GAP_M else ""
        result.append({"name": r["name"], "dong": r["dong"], "area": r["area"], "address_in": addr, **hit})
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        w.writeheader()
        w.writerows(result)
    counts: dict[str, int] = {}
    for r in result:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"{out_path}: {len(result)}곳 {counts}, 미리 ok {sum(r['review'] == 'ok' for r in result)}곳")
    return 0


def apply(review_path: Path, fallback_path: Path | None) -> int:
    with review_path.open(encoding="utf-8-sig", newline="") as f:
        ok = {(r["name"], r["dong"]): r for r in csv.DictReader(f) if r.get("review", "").strip().lower() == "ok"}
    old: dict[tuple[str, str], dict] = {}
    if fallback_path:
        with fallback_path.open(encoding="utf-8-sig", newline="") as f:
            old = {(r["name"], r["dong"]): r for r in csv.DictReader(f) if r.get("method") != NAVER_METHOD}
    with COORDS_CSV.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    moved = restored = left = 0
    for r in rows:
        if r["method"] != NAVER_METHOD:
            continue
        key = (r["name"], r["dong"])
        if key in ok:
            c = ok[key]
            r.update(lat=c["lat"], lon=c["lon"], precision="건물", method=JUSO_METHOD,
                     note=f"도로명주소 '{c['road_addr']}' 출입구", address=c["road_addr"],
                     place_name=c["bd_nm"] or re.sub(r"\(.*?\)", "", r["name"]).strip())
            moved += 1
        elif key in old:
            r.update({f: old[key].get(f, "") for f in ("lat", "lon", "precision", "method", "note")})
            r.update(address="", place_name="")
            restored += 1
        else:
            left += 1
    with COORDS_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COORD_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COORD_FIELDS})
    print(f"coords.csv: 도로명주소 좌표 {moved}곳, 예전 대략 위치로 되돌림 {restored}곳, 네이버 좌표로 남음 {left}곳")
    return 0 if left == 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, help="후보를 쓸 CSV")
    ap.add_argument("--apply", type=Path, help="검수한 후보 CSV(review 칸이 ok인 줄만 반영)")
    ap.add_argument("--fallback", type=Path, help="네이버를 쓰기 전 coords.csv(ok가 아닌 줄을 되돌릴 때)")
    args = ap.parse_args(argv)
    if args.apply:
        return apply(args.apply, args.fallback)
    if not args.out:
        ap.error("--out 또는 --apply가 필요해요")
    try:
        return build(args.out)
    except RuntimeError as e:
        # E0001은 키가 틀렸거나 등록한 주소에서만 쓰게 묶인 경우, E0014는 개발키 기간이 끝난 경우다.
        print(f"도로명주소 API 오류: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
