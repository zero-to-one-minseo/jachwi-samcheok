"""국토부 실거래가 공개시스템에서 받은 삼척시 전월세 원본(EUC-KR CSV)을 한 표로 정리한다.

    .venv/bin/python tools/build_molit.py            # data/raw/molit3y/*.csv → data/molit_rent.csv

원본 파일 이름은 '<기간 시작 YYYY-MM>_<종류 코드>.csv'(A 아파트, B 연립다세대, C 단독다가구, D 오피스텔).
단독다가구는 번지가 가려져 있어 건물 단위가 아니라 동·길 단위로만 쓴다.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = APP_DIR / "data" / "raw" / "molit3y"
OUT_CSV = APP_DIR / "data" / "molit_rent.csv"
TYPES = {"A": "아파트", "B": "연립다세대", "C": "단독다가구", "D": "오피스텔"}
FIELDS = ["id", "type", "dong", "road", "jibun", "building", "area_m2", "area_kind", "rent_kind", "deposit", "monthly",
          "floor", "built_year", "contract_ym", "term", "contract_kind", "prev_deposit", "prev_monthly", "roomlike"]
ROOMLIKE_MAX_M2 = 40.0


def num(text: str) -> float | None:
    t = (text or "").replace(",", "").strip()
    try:
        return float(t)
    except ValueError:
        return None


def read_raw(path: Path) -> list[dict]:
    lines = path.read_bytes().decode("euc-kr", errors="replace").splitlines()
    head = next(i for i, line in enumerate(lines) if line.startswith('"NO"'))
    return list(csv.DictReader(lines[head:]))


def normalize(r: dict, kind: str) -> dict:
    area = num(r.get("계약면적(㎡)") or r.get("전용면적(㎡)") or "")
    monthly = num(r.get("월세금(만원)", ""))
    rent_kind = r.get("전월세구분", "").strip()
    building = (r.get("건물명") or r.get("단지명") or "").strip()
    roomlike = (rent_kind == "월세" and area is not None and area <= ROOMLIKE_MAX_M2 and kind != "아파트")
    return {
        "type": kind,
        "dong": r.get("시군구", "").split()[-1],
        "road": r.get("도로명", "").strip(),
        "jibun": r.get("번지", "").strip(),
        "building": "" if building.startswith("(") else building,
        "area_m2": area,
        "area_kind": "계약면적" if kind == "단독다가구" else "전용면적",
        "rent_kind": rent_kind,
        "deposit": num(r.get("보증금(만원)", "")),
        "monthly": monthly,
        "floor": r.get("층", "").strip(),
        "built_year": r.get("건축년도", "").strip(),
        "contract_ym": r.get("계약년월", "").strip(),
        "term": r.get("계약기간", "").strip(),
        "contract_kind": r.get("계약구분", "").strip(),
        "prev_deposit": num(r.get("종전계약 보증금(만원)", "")),
        "prev_monthly": num(r.get("종전계약 월세(만원)", "")),
        "roomlike": "1" if roomlike else "",
    }


def main() -> int:
    rows = []
    for path in sorted(RAW_DIR.glob("*.csv")):
        kind = TYPES[path.stem.split("_")[1]]
        rows += [normalize(r, kind) for r in read_raw(path)]
    rows.sort(key=lambda r: (r["contract_ym"], r["type"], r["dong"]))
    for i, r in enumerate(rows, 1):
        r["id"] = f"m{i:05d}"
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        f.write('"출처: 국토교통부 실거래가공개시스템(rt.molit.go.kr) 조건별 자료제공, 강원특별자치도 삼척시 전월세 '
                '4종(아파트·연립다세대·단독다가구·오피스텔), 계약일 2023-11-06~2026-11-05, 2026-11-06 받음"\n')
        f.write('"roomlike=1: 월세 계약, 40㎡ 이하, 아파트 제외(학생 원룸형 후보). 단독다가구 번지는 원본에서 가려져 있음"\n')
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"{OUT_CSV.name}: {len(rows)}건, 원룸형 {sum(r['roomlike'] == '1' for r in rows)}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
