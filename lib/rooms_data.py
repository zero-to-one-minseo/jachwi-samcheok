"""현황판 데이터: rooms.csv 읽기, 필터, 생활권 가운데 값, 국토부 실거래 기준선."""

from __future__ import annotations

import csv
import io
import re
import statistics
from pathlib import Path
from typing import Any, Iterable

import streamlit as st

APP_DIR = Path(__file__).resolve().parent.parent
ROOMS_CSV = APP_DIR / "data" / "rooms.csv"
BASELINE_CSV = APP_DIR / "data" / "baseline_molit.csv"

AREAS = ["후문", "정문", "교동택지", "마달동", "당저동", "시내", "기타"]
CONTRACT_TYPES = ["월세", "선세", "연세", "전세", "양도", "모름"]
KINDS = ["신규 매물", "양도", "실거래"]
INCLUDED_ITEMS = ["수도", "인터넷", "난방", "전기", "가스", "관리비"]

# 할인된 값이라 시세 가운데 값에서 뺀다(설계_시세현황판 2장).
MEDIAN_EXCLUDE_KINDS = ("양도",)
COMPARE_MIN_COUNT = 3
# 가족형·투룸 실거래가 섞이면 가운데 값이 튄다. 국토부 기준선과 같은 40㎡ 이하만 센다.
MEDIAN_MAX_M2 = 40.0
# 기타는 근덕면·위치 미상이 섞여 있어 가운데 값이 의미가 없다.
NO_COMPARE_AREAS = ("기타",)

# 국토부 실거래가는 법정동 단위라 생활권을 동으로 옮겨 본다.
AREA_DONGS = {
    "후문": ["교동"],
    "정문": ["교동"],
    "교동택지": ["교동"],
    "마달동": ["마달동"],
    "당저동": ["당저동"],
    "시내": ["남양동", "정상동", "성내동", "사직동", "정라동", "성북동", "갈천동"],
}

_NUMBER_FIELDS = (
    "deposit", "monthly", "monthly_low", "monthly_high", "prepaid_total",
    "prepaid_months", "orig_total", "fee", "size_m2",
)


def _num(text: str | None) -> float | None:
    t = (text or "").replace(",", "").strip()
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def parse_room(row: dict[str, str]) -> dict[str, Any]:
    room: dict[str, Any] = {k: (v or "").strip() for k, v in row.items() if k}
    for key in _NUMBER_FIELDS:
        room[key] = _num(row.get(key))
    room["show"] = (row.get("show") or "").strip() == "1"
    room["included"] = [i for i in (row.get("included") or "").split("|") if i]
    if room["monthly"] is not None:
        room["monthly_low"] = room["monthly_low"] if room["monthly_low"] is not None else room["monthly"]
        room["monthly_high"] = room["monthly_high"] if room["monthly_high"] is not None else room["monthly"]
    return room


def read_rooms(path: Path | str = ROOMS_CSV) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return [parse_room(r) for r in csv.DictReader(f)]


@st.cache_data(show_spinner=False)
def _read_rooms_cached(path: str, mtime: float) -> list[dict[str, Any]]:
    return read_rooms(path)


def load_rooms(path: Path | str = ROOMS_CSV) -> list[dict[str, Any]] | None:
    """정적 파일이라 캐시한다. 파일을 바꾸면 수정 시각이 달라져 다시 읽는다. 파일이 없으면 None."""
    p = Path(path)
    if not p.exists():
        return None
    return _read_rooms_cached(str(p), p.stat().st_mtime)


def visible_rooms(rooms: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rooms if r.get("show")]


def filter_rooms(
    rooms: Iterable[dict[str, Any]],
    *,
    areas: Iterable[str] | None = None,
    monthly_range: tuple[float, float] | None = None,
    contract_types: Iterable[str] | None = None,
    kinds: Iterable[str] | None = None,
    required_items: Iterable[str] | None = None,
    include_unknown_price: bool = False,
) -> list[dict[str, Any]]:
    """빈 선택은 '전체'로 본다. 포함 항목은 고른 것이 모두 들어 있어야 통과한다."""
    areas_s = set(areas or ())
    contract_s = set(contract_types or ())
    kinds_s = set(kinds or ())
    items_s = set(required_items or ())
    out = []
    for r in rooms:
        if not r.get("show"):
            continue
        if areas_s and r.get("area") not in areas_s:
            continue
        if contract_s and r.get("contract_type") not in contract_s:
            continue
        if kinds_s and r.get("kind") not in kinds_s:
            continue
        if items_s and not items_s.issubset(r.get("included") or ()):
            continue
        if r.get("monthly") is None:
            if not include_unknown_price:
                continue
        elif monthly_range is not None:
            lo, hi = monthly_range
            if r["monthly_high"] < lo or r["monthly_low"] > hi:
                continue
        out.append(r)
    return out


def sort_rooms(rooms: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rooms, key=lambda r: (r.get("monthly") is None, r.get("monthly") or 0, r.get("id", "")))


def median(values: Iterable[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return statistics.median(vals) if vals else None


def area_medians(
    rooms: Iterable[dict[str, Any]],
    exclude_kinds: Iterable[str] = MEDIAN_EXCLUDE_KINDS,
    max_m2: float | None = MEDIAN_MAX_M2,
) -> dict[str, dict[str, float]]:
    """생활권별 월 환산 가운데 값과 방 수. 표시하는 방 가운데 월 환산이 있는 방만 센다.
    면적을 모르는 방은 넣는다."""
    exclude = set(exclude_kinds)
    groups: dict[str, list[float]] = {}
    for r in rooms:
        if not r.get("show") or r.get("monthly") is None or r.get("kind") in exclude:
            continue
        if max_m2 is not None and r.get("size_m2") is not None and r["size_m2"] > max_m2:
            continue
        groups.setdefault(r.get("area", "기타"), []).append(r["monthly"])
    return {a: {"median": statistics.median(v), "count": len(v)} for a, v in groups.items()}


def compare_to_area(
    room: dict[str, Any], medians: dict[str, dict[str, float]], min_count: int = COMPARE_MIN_COUNT
) -> dict[str, float] | None:
    """{'diff': 방 - 가운데 값, 'median', 'count'}. 비교할 방이 적거나 기타 생활권이면 None."""
    if room.get("monthly") is None or room.get("area") in NO_COMPARE_AREAS:
        return None
    m = medians.get(room.get("area", ""))
    if not m or m["count"] < min_count:
        return None
    return {"diff": round(room["monthly"] - m["median"], 1), "median": m["median"], "count": m["count"]}


def fmt_man(v: float | None) -> str:
    if v is None:
        return ""
    v = round(float(v), 1)
    if v.is_integer():
        return f"{int(v):,}"
    return f"{v:,.1f}"


def monthly_text(room: dict[str, Any]) -> str:
    lo, hi = room.get("monthly_low"), room.get("monthly_high")
    if room.get("monthly") is None:
        return ""
    if lo is not None and hi is not None and lo != hi:
        return f"{fmt_man(lo)}~{fmt_man(hi)}만 원"
    return f"{fmt_man(room['monthly'])}만 원"


def compare_text(cmp: dict[str, float] | None) -> str:
    if cmp is None:
        return ""
    base = f"생활권 가운데 값({fmt_man(cmp['median'])}만 원)"
    diff = cmp["diff"]
    if abs(diff) < 1:
        return f"{base}과 비슷해요"
    word = "비싸요" if diff > 0 else "싸요"
    return f"{base}보다 {fmt_man(abs(diff))}만 원 {word}"


def fee_summary(room: dict[str, Any]) -> str:
    fee, text = room.get("fee"), room.get("fee_text") or ""
    if fee is None:
        return f"관리비: {text}" if text else ""
    if fee == 0:
        return f"관리비 없음({text})" if text and text not in ("0", "없음") else "관리비 없음"
    return f"관리비 {fmt_man(fee)}만 원"


def to_selected_room(room: dict[str, Any]) -> dict[str, Any]:
    """현황판 → 계약서 점검으로 넘기는 사전(두 기능의 약속)."""
    return {
        "name": room.get("name") or "",
        "area": room.get("area") or "",
        "contract_type": room.get("contract_type") or "모름",
        "deposit": room.get("deposit"),
        "monthly": room.get("monthly"),
        "fee_text": fee_summary(room),
        "included": list(room.get("included") or []),
        "source": room.get("source") or "",
        "surveyed": room.get("surveyed") or "",
        "kind": room.get("kind") or "",
    }


# ---------- 국토부 전월세 실거래 기준선 ----------

_MOLIT_DEPOSIT = ("보증금(만원)", "보증금")
_MOLIT_MONTHLY = ("월세금(만원)", "월세(만원)", "월세")
_MOLIT_AREA = ("계약면적(㎡)", "전용면적(㎡)", "면적")
_MOLIT_DONG = ("시군구", "동", "법정동")
_MOLIT_YM = ("계약년월",)


def _pick(header: list[str], names: tuple[str, ...]) -> int | None:
    for n in names:
        if n in header:
            return header.index(n)
    return None


def parse_baseline_text(text: str, max_area: float | None = 40.0) -> dict[str, Any] | None:
    """국토부 rt.molit.go.kr 내려받기 CSV(위쪽 안내 줄 포함) 또는 '동,보증금,월세' 간단 CSV를 읽는다."""
    rows = list(csv.reader(io.StringIO(text)))
    header_idx = None
    for i, row in enumerate(rows):
        cells = [c.strip() for c in row]
        if _pick(cells, _MOLIT_DONG) is not None and _pick(cells, _MOLIT_MONTHLY) is not None:
            header_idx = i
            break
    if header_idx is None:
        return None
    header = [c.strip() for c in rows[header_idx]]
    i_dong, i_dep, i_mon = _pick(header, _MOLIT_DONG), _pick(header, _MOLIT_DEPOSIT), _pick(header, _MOLIT_MONTHLY)
    i_area, i_ym = _pick(header, _MOLIT_AREA), _pick(header, _MOLIT_YM)
    records = []
    for row in rows[header_idx + 1:]:
        if len(row) <= max(i_dong, i_mon):
            continue
        monthly = _num(row[i_mon])
        if not monthly:
            continue
        if max_area is not None and i_area is not None and i_area < len(row):
            area = _num(row[i_area])
            if area is not None and area > max_area:
                continue
        dong = row[i_dong].strip().split()[-1] if row[i_dong].strip() else ""
        records.append({
            "dong": dong,
            "deposit": _num(row[i_dep]) if i_dep is not None and i_dep < len(row) else None,
            "monthly": monthly,
            "ym": re.sub(r"\D", "", row[i_ym]) if i_ym is not None and i_ym < len(row) else "",
        })
    if not records:
        return None
    by_dong: dict[str, dict[str, float]] = {}
    for dong in sorted({r["dong"] for r in records}):
        sub = [r for r in records if r["dong"] == dong]
        by_dong[dong] = {
            "count": len(sub),
            "monthly_median": statistics.median(r["monthly"] for r in sub),
            "deposit_median": median(r["deposit"] for r in sub),
        }
    yms = sorted(r["ym"] for r in records if r["ym"])
    return {
        "by_dong": by_dong,
        "records": records,
        "period": f"{yms[0]}~{yms[-1]}" if yms else "",
        "count": len(records),
    }


@st.cache_data(show_spinner=False)
def _read_baseline_cached(path: str, mtime: float) -> dict[str, Any] | None:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return parse_baseline_text(raw.decode(enc))
        except UnicodeDecodeError:
            continue
    return None


def load_baseline(path: Path | str = BASELINE_CSV) -> dict[str, Any] | None:
    """동네별 기준선 {'by_dong': {동: {count, monthly_median, deposit_median}}, 'records', 'period', 'count'}.
    파일이 없거나 읽을 줄이 없으면 None."""
    p = Path(path)
    if not p.exists():
        return None
    return _read_baseline_cached(str(p), p.stat().st_mtime)


def baseline_summary(baseline: dict[str, Any] | None, areas: Iterable[str] | None = None) -> dict[str, Any] | None:
    """고른 생활권에 해당하는 동의 실거래만 모아 가운데 값을 낸다. 고른 게 없으면 삼척시 전체."""
    if not baseline:
        return None
    areas = [a for a in (areas or []) if a]
    dongs: set[str] = set()
    for a in areas:
        dongs.update(AREA_DONGS.get(a, []))
    records = baseline["records"]
    label = "삼척시 전체"
    if areas:
        if not dongs:
            return None
        records = [r for r in records if r["dong"] in dongs]
        label = "·".join(sorted(dongs))
    if not records:
        return None
    return {
        "label": label,
        "count": len(records),
        "monthly_median": statistics.median(r["monthly"] for r in records),
        "deposit_median": median(r["deposit"] for r in records),
        "period": baseline.get("period", ""),
    }
