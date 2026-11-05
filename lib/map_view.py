"""현황판 지도 부품(사양서_조립.md R4). folium + streamlit-folium.
바탕 지도는 lib/basemap.py가 OpenStreetMap 데이터를 직접 칠하고, 그 파일이 없을 때만 OSM 타일 그림을 쓴다."""

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
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

from lib import basemap
from lib.rooms_data import APP_DIR, compare_to_area
from tools.build_rooms import vague_place

COORDS_CSV = APP_DIR / "data" / "coords.csv"
CENTERS_CSV = APP_DIR / "data" / "area_centers.csv"
SCHOOL = "학교"
DEFAULT_ZOOM = 15
SELECTED_ZOOM = 17
MIN_ZOOM = 14
MAX_ZOOM = 18
# 삼척 시내와 캠퍼스 둘레. 지도를 이 밖으로 끌거나 더 멀리 축소하지 못하게 한다(도계·근덕 방은 목록에만 보인다).
CITY_BOUNDS = {"min_lat": 37.425, "max_lat": 37.468, "min_lon": 129.135, "max_lon": 129.195}
CHEAP_DIFF = -3.0
PRICEY_DIFF = 3.0
# 좌표를 약 100m(소수 셋째 자리)로 뭉갰으니, 겹친 점을 떼어 놓는 거리는 그보다 작게 둔다.
JITTER_DEG = 0.00035
BUBBLE_SIZE = (54, 32)
TAIL = 6
INK = "#18222B"
SEA = "#1A8A93"
COLORS = {"cheap": "#23875A", "pricey": "#C65A1E", "neutral": "#ffffff"}
TILES = "OpenStreetMap"
# 바탕 지도의 색을 빼서 가격 핀이 먼저 보이게 한다(CARTO 밝은 지도는 API 키를 요구해서 쓰지 않는다).
_TILE_CSS = "<style>.leaflet-tile-pane{filter:grayscale(.8) brightness(1.2) contrast(.78);}</style>"
# 이 확대부터는 묶지 않고 핀을 하나씩 보인다. 그 위에서 같은 자리 핀은 펼쳐서 보인다.
CLUSTER_OFF_ZOOM = 17
_CLUSTER_ICON = f"""
function(cluster) {{
  var n = cluster.getChildCount();
  var s = n < 10 ? 34 : (n < 30 ? 40 : 46);
  return L.divIcon({{
    html: '<div style="width:' + s + 'px;height:' + s + 'px;border-radius:50%;background:{SEA};color:#fff;'
      + 'display:flex;align-items:center;justify-content:center;font:800 14px SUIT,sans-serif;'
      + 'border:2px solid #fff;box-shadow:0 2px 6px rgba(24,34,43,.35);">' + n + '</div>',
    className: '', iconSize: L.point(s, s)
  }});
}}
"""
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
        out[(vague_place(row.get("name", "")), row.get("dong", ""))] = {
            "lat": lat, "lon": lon, "precision": row.get("precision") or "블록",
            "address": row.get("address") or "", "place_name": row.get("place_name") or "",
        }
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
            r["address"], r["place_name"] = c.get("address", ""), c.get("place_name", "")
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
    """꼬리 달린 가격 핀. 꼬리 끝이 방 위치다."""
    if selected:
        bg, fg, edge, tail = INK, "#fff", INK, INK
    elif tone == "neutral":
        bg, fg, edge, tail = COLORS["neutral"], INK, INK, INK
    else:
        bg, fg, edge, tail = COLORS[tone], "#fff", "#fff", COLORS[tone]
    border = f"2px {'dashed' if transfer else 'solid'} {edge}"
    size = "15px" if selected else "13px"
    return (
        '<div style="display:flex;flex-direction:column;align-items:center;width:100%;height:100%;">'
        f'<div style="box-sizing:border-box;min-width:34px;height:{BUBBLE_SIZE[1] - TAIL}px;padding:0 7px;'
        f"display:flex;align-items:center;justify-content:center;border-radius:8px;background:{bg};color:{fg};"
        f"font:800 {size} SUIT,sans-serif;font-variant-numeric:tabular-nums;border:{border};"
        f'box-shadow:0 2px 5px rgba(24,34,43,.28);white-space:nowrap;">{html.escape(label)}</div>'
        f'<div style="width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;'
        f'border-top:{TAIL}px solid {tail};"></div></div>'
    )


def _area_label(name: str) -> str:
    return (
        f'<div style="transform:translate(-50%,-50%);font:700 11px SUIT,sans-serif;color:{SEA};'
        'background:rgba(255,255,255,.85);padding:1px 6px;border-radius:6px;white-space:nowrap;">'
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
    has_basemap = bool(basemap.load_basemap())
    m = folium.Map(
        location=list(start), zoom_start=zoom or DEFAULT_ZOOM, tiles=None if has_basemap else TILES,
        control_scale=True, prefer_canvas=True,
        min_zoom=MIN_ZOOM, max_zoom=MAX_ZOOM, max_bounds=True, max_bounds_viscosity=1.0, **CITY_BOUNDS,
    )
    # folium은 확대 한계를 타일에만 넘긴다. 타일 없이 그릴 때는 지도에 직접 넣어야 핀 묶기가 동작한다.
    m.options.update({"minZoom": MIN_ZOOM, "maxZoom": MAX_ZOOM})
    if has_basemap:
        basemap.add_basemap(m)
    else:
        m.get_root().header.add_child(folium.Element(_TILE_CSS))
    for area, (lat, lon) in centers.items():
        if area == SCHOOL and has_basemap:
            continue
        text = "강원대 삼척캠퍼스" if area == SCHOOL else area
        folium.Marker([lat, lon], icon=folium.DivIcon(html=_area_label(text), icon_size=(0, 0)), interactive=False).add_to(m)
    cluster = MarkerCluster(
        icon_create_function=_CLUSTER_ICON,
        options={
            "maxClusterRadius": 42,
            "disableClusteringAtZoom": CLUSTER_OFF_ZOOM,
            "showCoverageOnHover": False,
            "spiderfyOnMaxZoom": True,
        },
    ).add_to(m)
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
            icon_anchor=(BUBBLE_SIZE[0] // 2, BUBBLE_SIZE[1]),
        )
        marker = folium.Marker([r["lat"], r["lon"]], icon=icon, tooltip=html.escape(tooltip_text(r)))
        # 고른 방은 묶음에 숨지 않게 지도에 바로 올린다.
        marker.add_to(m if r.get("id") == selected_id else cluster)
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


def legend_html() -> str:
    items = [("cheap", LEGEND["cheap"]), ("pricey", LEGEND["pricey"]), ("neutral", LEGEND["neutral"]),
             ("transfer", "점선은 양도 글"), ("cluster", "동그라미는 묶인 방 수, 누르면 확대")]
    return '<div class="legend">' + "".join(f'<span><i class="{k}"></i>{html.escape(t)}</span>' for k, t in items) + "</div>"
