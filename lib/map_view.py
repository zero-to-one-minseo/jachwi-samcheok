"""현황판 지도 부품(사양서_조립.md R4). folium + streamlit-folium, 바탕 지도는 OpenStreetMap."""

from __future__ import annotations

import csv
import hashlib
import html
import math
import re
from pathlib import Path
from typing import Any, Iterable

import folium
import streamlit as st
from streamlit_folium import st_folium

from lib.rooms_data import APP_DIR, compare_to_area
from tools.build_rooms import vague_place

COORDS_CSV = APP_DIR / "data" / "coords.csv"
CENTERS_CSV = APP_DIR / "data" / "area_centers.csv"
SCHOOL = "학교"
DEFAULT_ZOOM = 15
SELECTED_ZOOM = 17
CHEAP_DIFF = -3.0
PRICEY_DIFF = 3.0
# 좌표를 약 100m(소수 셋째 자리)로 뭉갰으니, 겹친 점을 떼어 놓는 거리는 그보다 작게 둔다.
JITTER_DEG = 0.00035
BUBBLE_SIZE = (46, 24)
COLORS = {"cheap": "#2e7d4f", "pricey": "#b85c00", "neutral": "#4f5866"}
LEGEND = {"cheap": "생활권 가운데 값보다 3만 원 넘게 쌈", "pricey": "3만 원 넘게 비쌈", "neutral": "비슷하거나 비교 못 함"}
_TOOLTIP_ID = re.compile(r"\[(r\d+)\]\s*$")


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


@st.cache_data(show_spinner=False)
def _cached_rows(path: str, mtime: float) -> list[dict[str, str]]:
    return _read_rows(Path(path))


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    return _cached_rows(str(path), path.stat().st_mtime)


def _float(text: str | None) -> float | None:
    try:
        return float(text) if text not in (None, "") else None
    except ValueError:
        return None


def load_coords(path: Path = COORDS_CSV) -> dict[tuple[str, str], dict[str, Any]]:
    """(name, dong) → {'lat', 'lon', 'precision'}. 데이터를 다시 만들면 id가 바뀔 수 있어 이름으로 맞춘다."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _rows(path):
        lat, lon = _float(row.get("lat")), _float(row.get("lon"))
        if lat is None or lon is None:
            continue
        # 좌표표는 번지를 지우기 전 이름으로 만들어졌으니, rooms.csv와 같은 규칙으로 맞춘다.
        out[(vague_place(row.get("name", "")), row.get("dong", ""))] = {"lat": lat, "lon": lon, "precision": row.get("precision") or "블록"}
    return out


def load_centers(path: Path = CENTERS_CSV) -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    for row in _rows(path):
        lat, lon = _float(row.get("lat")), _float(row.get("lon"))
        if lat is not None and lon is not None:
            out[row.get("area", "")] = (lat, lon)
    return out


def _jitter(room_id: str) -> tuple[float, float]:
    digest = hashlib.sha1(room_id.encode()).digest()
    angle = digest[0] / 255 * 2 * math.pi
    radius = JITTER_DEG * (0.5 + digest[1] / 255 / 2)
    return radius * math.sin(angle), radius * math.cos(angle)


def attach_coords(
    rooms: Iterable[dict[str, Any]],
    coords: dict[tuple[str, str], dict[str, Any]],
    centers: dict[str, tuple[float, float]],
) -> list[dict[str, Any]]:
    """방마다 lat, lon, geo_precision을 붙인 새 목록. 좌표가 없으면 생활권 중심(없으면 학교)을 쓰고,
    같은 자리에 여러 방이 겹치면 id로 정한 작은 고정 흩뜨림을 준다(같은 데이터면 늘 같은 자리)."""
    fallback = centers.get(SCHOOL)
    placed: list[dict[str, Any]] = []
    for room in rooms:
        r = dict(room)
        c = coords.get((r.get("name", ""), r.get("dong", "")))
        if c:
            r["lat"], r["lon"], r["geo_precision"] = c["lat"], c["lon"], c["precision"]
        else:
            center = centers.get(r.get("area", "")) or fallback
            if center is None:
                continue
            r["lat"], r["lon"], r["geo_precision"] = center[0], center[1], "생활권중심"
        placed.append(r)
    spots: dict[tuple[float, float], int] = {}
    for r in placed:
        spots[(r["lat"], r["lon"])] = spots.get((r["lat"], r["lon"]), 0) + 1
    for r in placed:
        if spots[(r["lat"], r["lon"])] > 1:
            dlat, dlon = _jitter(str(r.get("id", "")))
            r["lat"], r["lon"] = r["lat"] + dlat, r["lon"] + dlon
    return placed


def price_label(room: dict[str, Any]) -> str:
    monthly = room.get("monthly")
    if monthly is None:
        return "?"
    return f"{monthly:g}" if monthly != int(monthly) else str(int(monthly))


def price_tone(room: dict[str, Any], medians: dict[str, dict[str, float]]) -> str:
    cmp = compare_to_area(room, medians)
    if not cmp:
        return "neutral"
    if cmp["diff"] <= CHEAP_DIFF:
        return "cheap"
    if cmp["diff"] >= PRICEY_DIFF:
        return "pricey"
    return "neutral"


def tooltip_text(room: dict[str, Any]) -> str:
    label = price_label(room)
    price = f"월 {label}만 원" if label != "?" else "가격 모름"
    return f"{room.get('name', '')} · {price} [{room.get('id', '')}]"


def clicked_room_id(tooltip: str | None) -> str | None:
    if not tooltip:
        return None
    m = _TOOLTIP_ID.search(tooltip.strip())
    return m.group(1) if m else None


def _bubble(label: str, tone: str, *, selected: bool, transfer: bool) -> str:
    border = "2px dashed #ffffff" if transfer else "2px solid #ffffff"
    size = "15px" if selected else "13px"
    ring = "0 0 0 3px #1f2937," if selected else ""
    return (
        f'<div style="display:flex;align-items:center;justify-content:center;width:100%;height:100%;'
        f"box-sizing:border-box;border-radius:12px;background:{COLORS[tone]};color:#fff;font-weight:700;"
        f'font-size:{size};border:{border};box-shadow:{ring}0 1px 3px rgba(0,0,0,.35);white-space:nowrap;">'
        f"{html.escape(label)}</div>"
    )


def _area_label(name: str) -> str:
    return (
        '<div style="transform:translate(-50%,-50%);font-size:12px;font-weight:700;color:#374151;'
        'background:rgba(255,255,255,.8);padding:1px 5px;border-radius:6px;white-space:nowrap;">'
        f"{html.escape(name)}</div>"
    )


def build_map(
    rooms: list[dict[str, Any]],
    medians: dict[str, dict[str, float]],
    centers: dict[str, tuple[float, float]],
    *,
    selected_id: str | None = None,
    start: tuple[float, float] | None = None,
    zoom: int | None = None,
) -> folium.Map:
    start = start or centers.get(SCHOOL) or (37.4505, 129.1615)
    m = folium.Map(location=list(start), zoom_start=zoom or DEFAULT_ZOOM, tiles="OpenStreetMap", control_scale=True)
    for area, (lat, lon) in centers.items():
        text = "강원대 삼척캠퍼스" if area == SCHOOL else area
        folium.Marker([lat, lon], icon=folium.DivIcon(html=_area_label(text), icon_size=(0, 0))).add_to(m)
    for r in rooms:
        icon = folium.DivIcon(
            html=_bubble(
                price_label(r),
                price_tone(r, medians),
                selected=r.get("id") == selected_id,
                transfer=r.get("kind") == "양도",
            ),
            # 크기가 0이면 지도가 누른 자리를 말풍선으로 알아보지 못한다.
            icon_size=BUBBLE_SIZE,
            icon_anchor=(BUBBLE_SIZE[0] // 2, BUBBLE_SIZE[1] // 2),
        )
        folium.Marker([r["lat"], r["lon"]], icon=icon, tooltip=html.escape(tooltip_text(r))).add_to(m)
    return m


def render_map(
    rooms: list[dict[str, Any]],
    medians: dict[str, dict[str, float]],
    centers: dict[str, tuple[float, float]],
    *,
    selected_id: str | None = None,
    center: tuple[float, float] | None = None,
    zoom: int | None = None,
    key: str = "rooms_map",
    height: int = 520,
) -> str | None:
    """지도를 그리고, 이번 실행에서 **새로** 누른 방 id를 돌려준다(없으면 None).
    st_folium은 마지막으로 누른 것을 다음 실행에도 계속 돌려주므로, 지난번 값과 같으면 새 클릭으로 보지 않는다."""
    # 고른 방 강조가 바뀌면 지도를 다시 그리므로, 시작 위치를 고른 방에 둬야 보던 곳을 잃지 않는다.
    fmap = build_map(rooms, medians, centers, selected_id=selected_id, start=center, zoom=zoom)
    out = st_folium(
        fmap,
        key=key,
        height=height,
        use_container_width=True,
        returned_objects=["last_object_clicked_tooltip"],
        center=list(center) if center else None,
        zoom=zoom,
    )
    tooltip = (out or {}).get("last_object_clicked_tooltip")
    seen_key = f"{key}_last_tooltip"
    if tooltip == st.session_state.get(seen_key):
        return None
    st.session_state[seen_key] = tooltip
    return clicked_room_id(tooltip)


def legend_markdown() -> str:
    return "  \n".join(f"{name}: {text}" for name, text in [("초록", LEGEND["cheap"]), ("주황", LEGEND["pricey"]), ("회색", LEGEND["neutral"]), ("점선 테두리", "양도 매물")])
