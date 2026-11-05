"""Next.js 화면(web/)이 읽을 JSON을 만든다. 계산 규칙은 Streamlit 앱과 같은 lib/ 코드를 그대로 쓴다.

    .venv/bin/python tools/export_web_data.py

만드는 파일: web/public/data/rooms.json, web/public/data/basemap.geojson(data/basemap.geojson 복사)
방 데이터(data/rooms.csv)나 좌표·실거래 파일을 바꾸면 다시 돌린다.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from lib import map_view  # noqa: E402
from lib import rooms_data as rd  # noqa: E402

OUT_DIR = APP_DIR / "web" / "public" / "data"
KIND_WORD = {"양도": "양도 글", "실거래": "실거래", "신규 매물": "매물 글", "안내": "안내 글"}


def headline(room: dict) -> str:
    if room.get("monthly") is not None:
        label = map_view.price_label(room)
        return f"월 {label}만" if room.get("monthly_low") == room.get("monthly_high") else f"월 약 {label}만"
    if room.get("contract_type") == "전세" and room.get("deposit") is not None:
        return f"전세 {rd.fmt_man(room['deposit'])}만"
    return "가격 모름"


def terms(room: dict) -> str:
    bits = []
    if room.get("deposit") is not None and room.get("contract_type") != "전세":
        bits.append(f"보증금 {rd.fmt_man(room['deposit'])}")
    ctype = room.get("contract_type") or ""
    total = room.get("prepaid_total")
    if ctype in ("선세", "연세", "양도") and total:
        months = room.get("prepaid_months")
        word = "연세" if ctype == "연세" else "선세"
        bits.append(f"{rd.fmt_man(months)}개월 {word} {rd.fmt_man(total)}" if months else f"{word} {rd.fmt_man(total)}")
    elif ctype and ctype != "모름":
        bits.append(ctype)
    if room.get("fee"):
        bits.append(f"관리비 {rd.fmt_man(room['fee'])}")
    return " · ".join(bits)


def price_line(room: dict) -> str:
    dep = room.get("deposit")
    dep_txt = f"보증금 {rd.fmt_man(dep)}만 원" if dep is not None else "보증금 글에 없음"
    ctype = room.get("contract_type")
    if ctype == "전세":
        return f"전세 {rd.fmt_man(dep)}만 원" if dep is not None else "전세 · 금액 글에 없음"
    if room.get("monthly") is None:
        if room.get("prepaid_total"):
            return f"{dep_txt} · 선세 {rd.fmt_man(room['prepaid_total'])}만 원(기간이 안 적혀 월 환산을 못 해요)"
        return f"{dep_txt} · 월 금액이 글에 없어요"
    monthly = rd.monthly_text(room)
    total = room.get("prepaid_total")
    if ctype in ("선세", "연세", "양도") and total:
        months = room.get("prepaid_months")
        period = f"{rd.fmt_man(months)}개월 " if months else ""
        word = "연세" if ctype == "연세" else "선세"
        line = f"{dep_txt} · {period}{word} {rd.fmt_man(total)}만 원 · 월 환산 {monthly}"
        if not months and room.get("monthly_low") != room.get("monthly_high"):
            line += " (기간이 안 적혀 10~12개월로 나눴어요)"
        return line
    if ctype in ("선세", "연세"):
        return f"{dep_txt} · 월 환산 {monthly}"
    return f"{dep_txt} · 월세 {monthly}"


def included_line(room: dict) -> str:
    items = room.get("included") or []
    fee = rd.fee_summary(room)
    parts = [fee] if fee else []
    parts.append(f"포함: {'·'.join(items)}" if items else "포함 항목이 안 적혀 있어요")
    return " · ".join(parts)


def detail_line(room: dict) -> str:
    return " · ".join(str(b) for b in (room.get("structure"), room.get("size"), room.get("options"), room.get("distance")) if b)


def source_line(room: dict) -> str:
    bits = [f"출처 {room.get('source') or '미상'}", f"조사 {room.get('surveyed') or '미상'}"]
    if room.get("posted"):
        bits.append(f"게시·거래 {room['posted']}")
    return " · ".join(bits)


def transfer_note(room: dict) -> str:
    if room.get("kind") != "양도":
        return ""
    orig = room.get("orig_total")
    orig_txt = f" 원래 계약은 {rd.fmt_man(orig)}만 원이었다고 적혀 있어요." if orig else ""
    return ("양도(남은 기간 넘겨받기)는 집주인이 동의해야 해요(민법 제629조). "
            f"집주인에게 직접 확인하고, 계약서를 새로 쓰거나 동의 내용을 적어 두세요.{orig_txt}")


def compare(room: dict, medians: dict) -> dict | None:
    cmp = rd.compare_to_area(room, medians)
    if not cmp:
        return None
    tone = map_view.price_tone(room, medians)
    diff = abs(cmp["diff"])
    chip = {"cheap": f"{rd.fmt_man(diff)}만 쌈", "pricey": f"{rd.fmt_man(diff)}만 비쌈"}.get(tone, "보통")
    return {"tone": tone, "chip": chip, "text": rd.compare_text(cmp), "median": cmp["median"]}


def export_room(r: dict, medians: dict, in_city: bool) -> dict:
    cmp = compare(r, medians)
    return {
        "id": r["id"],
        "name": r.get("name") or "이름 없는 방",
        "area": r.get("area") or "기타",
        "kind": r.get("kind") or "",
        "kindWord": KIND_WORD.get(r.get("kind", ""), r.get("kind") or ""),
        "contractType": r.get("contract_type") or "모름",
        "included": r.get("included") or [],
        "monthly": r.get("monthly"),
        "monthlyLow": r.get("monthly_low"),
        "monthlyHigh": r.get("monthly_high"),
        "pin": map_view.price_label(r),
        "tone": cmp["tone"] if cmp else "neutral",
        "transfer": r.get("kind") == "양도",
        "lat": r["lat"],
        "lon": r["lon"],
        "inCity": in_city,
        "headline": headline(r),
        "terms": terms(r),
        "compare": cmp,
        "priceLine": price_line(r),
        "includedLine": included_line(r),
        "detailLine": detail_line(r),
        "sourceLine": source_line(r),
        "transferNote": transfer_note(r),
        "selected": rd.to_selected_room(r),
    }


def main() -> int:
    rooms = rd.read_rooms()
    shown = rd.visible_rooms(rooms)
    medians = rd.area_medians(shown)
    centers = map_view.load_centers()
    placed = map_view.attach_coords(shown, map_view.load_coords(), centers)
    b = map_view.CITY_BOUNDS
    out_rooms = [
        export_room(r, medians, b["min_lat"] <= r["lat"] <= b["max_lat"] and b["min_lon"] <= r["lon"] <= b["max_lon"])
        for r in rd.sort_rooms(placed)
    ]
    base = rd.parse_baseline_text(rd.BASELINE_CSV.read_text(encoding="utf-8-sig")) if rd.BASELINE_CSV.exists() else None
    dates = sorted({r["surveyed"] for r in shown if r.get("surveyed")})
    data = {
        "rooms": out_rooms,
        "areas": [a for a in rd.AREAS if any(r["area"] == a for r in out_rooms)],
        "contractTypes": [c for c in rd.CONTRACT_TYPES if any(r["contractType"] == c for r in out_rooms)],
        "kinds": [k for k in rd.KINDS if any(r["kind"] == k for r in out_rooms)],
        "includedItems": rd.INCLUDED_ITEMS,
        "areaCenters": {a: list(c) for a, c in centers.items()},
        "areaDongs": {a: list(d) for a, d in rd.AREA_DONGS.items()},
        "bounds": b,
        "baseline": {
            "period": base.get("period", ""),
            "records": [{"dong": x["dong"], "monthly": x["monthly"], "deposit": x["deposit"]} for x in base["records"]],
        } if base else None,
        "survey": {
            "when": dates[0] if len(dates) == 1 else (f"{dates[0]}~{dates[-1]}" if dates else "미상"),
            "sources": sorted({r["source"] for r in shown if r.get("source")}),
        },
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "rooms.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    shutil.copyfile(APP_DIR / "data" / "basemap.geojson", OUT_DIR / "basemap.geojson")
    print(f"rooms.json: 방 {len(out_rooms)}곳(시내 {sum(r['inCity'] for r in out_rooms)}), 실거래 {len(data['baseline']['records']) if base else 0}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
