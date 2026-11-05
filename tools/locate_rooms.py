"""방 이름으로 네이버 지역 검색(NAVER API HUB)을 불러 건물 위치 후보를 찾는다.

    .venv/bin/python tools/locate_rooms.py --out 후보.csv     # 후보만 뽑는다(지도는 안 바뀜)
    .venv/bin/python tools/locate_rooms.py --apply 검수.csv   # 사람이 ok로 표시한 줄만 data/coords.csv에 반영

열쇠는 .streamlit/secrets.toml의 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET에서 읽는다(저장소에 올리지 않는다).
검색 API는 하루 25,000회까지 무료이고 유료 구간이 없다. 방 하나에 많아야 두 번 부른다.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from lib import rooms_data as rd  # noqa: E402

SECRETS = APP_DIR / ".streamlit" / "secrets.toml"
COORDS_CSV = APP_DIR / "data" / "coords.csv"
ENDPOINT = "https://naverapihub.apigw.ntruss.com/search/v1/local"
# 위치를 특정할 수 없는 뭉뚱그린 이름. 이런 방은 검색하지 않는다.
VAGUE = ("일대", "후문", "정문", "근처", "부근", "쪽", "뒤편", "건너편", "도보", "같은 집주인", "자취방", "미기재",
         "원룸촌", "위 1372", "셰어하우스")
GENERIC_TAIL = re.compile(r"\s*(원룸형|원룸|투룸|1\.5룸|주택|빌라|아파트 원룸)$")
COORD_FIELDS = ["id", "name", "dong", "area", "lat", "lon", "precision", "method", "note", "address", "place_name"]


def keys() -> dict[str, str]:
    s = tomllib.load(SECRETS.open("rb"))
    return {"X-NCP-APIGW-API-KEY-ID": s["NAVER_CLIENT_ID"], "X-NCP-APIGW-API-KEY": s["NAVER_CLIENT_SECRET"]}


def search(query: str, headers: dict[str, str]) -> list[dict]:
    url = f"{ENDPOINT}?query={urllib.parse.quote(query)}&display=5"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15) as r:
        return json.load(r).get("items", [])


def base_name(name: str) -> str:
    return re.sub(r"\(.*?\)", "", name).strip()


def norm(text: str) -> str:
    return re.sub(r"<[^>]+>|\s", "", text or "")


def candidates(room: dict, headers: dict[str, str]) -> dict:
    name = room["name"]
    base = base_name(name)
    row = {"name": name, "dong": room["dong"], "area": room["area"], "kind": room["kind"], "query": "", "status": "",
           "place_name": "", "category": "", "address": "", "lat": "", "lon": "", "review": ""}
    if not base or any(w in name for w in VAGUE):
        row["status"] = "건너뜀(뭉뚱그린 이름)"
        return row
    tries = [base]
    short = GENERIC_TAIL.sub("", base)
    if short and short != base:
        tries.append(short)
    for core in tries:
        query = f"삼척 {core}"
        row["query"] = query
        items = search(query, headers)
        time.sleep(0.12)
        for it in items:
            title = norm(it["title"])
            addr = it.get("roadAddress") or it.get("address") or ""
            if "삼척" not in addr or norm(core) not in title:
                continue
            if "관리사무소" in title or "상가" in title or "입구" in title:
                continue
            row.update(status="후보", place_name=title, category=it.get("category", ""), address=addr,
                       lat=f"{int(it['mapy']) / 1e7:.6f}", lon=f"{int(it['mapx']) / 1e7:.6f}")
            return row
    row["status"] = "못 찾음"
    return row


def apply(review_path: Path) -> int:
    """검수 파일에서 review가 ok인 줄을 coords.csv에 넣는다(같은 이름·동이면 바꾼다)."""
    with review_path.open(encoding="utf-8-sig", newline="") as f:
        ok = [r for r in csv.DictReader(f) if r.get("review", "").strip().lower() == "ok"]
    with COORDS_CSV.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    by_key = {(r["name"], r["dong"]): r for r in rows}
    for r in ok:
        new = {
            "id": "", "name": r["name"], "dong": r["dong"], "area": r["area"],
            "lat": r["lat"], "lon": r["lon"], "precision": "건물",
            "method": "네이버 지역 검색(NAVER API HUB)", "note": f"검색어 '{r['query']}'",
            "address": r["address"], "place_name": r["place_name"],
        }
        old = by_key.get((r["name"], r["dong"]))
        if old:
            old.update(new | {"id": old.get("id", "")})
        else:
            rows.append(new)
    with COORDS_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COORD_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COORD_FIELDS})
    print(f"coords.csv: {len(ok)}곳을 건물 위치로 반영")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, help="후보를 쓸 CSV")
    ap.add_argument("--apply", type=Path, help="검수한 후보 CSV(review 칸이 ok인 줄만 반영)")
    args = ap.parse_args(argv)
    if args.apply:
        return apply(args.apply)
    if not args.out:
        ap.error("--out 또는 --apply가 필요해요")
    headers = keys()
    seen: dict[tuple[str, str], dict] = {}
    for room in rd.visible_rooms(rd.read_rooms()):
        key = (room["name"], room["dong"])
        if key not in seen:
            seen[key] = candidates(room, headers)
    rows = list(seen.values())
    with args.out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"{args.out}: {len(rows)}곳 {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
