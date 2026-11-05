"""바탕 지도 그리기. 타일 그림 대신 data/basemap.geojson(OpenStreetMap에서 뽑은 길·건물·강·공원)을
카카오맵(직방 지도)과 비슷한 밝은 색으로 직접 칠한다. 색은 web/components/rooms/MapView.tsx와 같게 둔다. 데이터는 tools/build_basemap.py가 만든다."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

import folium
import streamlit as st
from jinja2 import Template

from lib.rooms_data import APP_DIR

BASEMAP_GEOJSON = APP_DIR / "data" / "basemap.geojson"
BACKGROUND = "#F8F8F6"
ATTRIBUTION = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> 기여자'
# 이 확대부터 작은 이름표(학교·주민센터·마트 등)를 보인다. 큰 곳 이름표는 늘 보인다.
DETAIL_ZOOM = 16

_FILL = {
    "residential": {"fillColor": "#F2E8DB", "fillOpacity": 1, "weight": 0},
    "commercial": {"fillColor": "#F4EEE7", "fillOpacity": 1, "weight": 0},
    "forest": {"fillColor": "#EEF5E6", "fillOpacity": 1, "weight": 0},
    "green": {"fillColor": "#D7EDC6", "fillOpacity": 1, "weight": 0},
    "pitch": {"fillColor": "#C2E2A4", "fillOpacity": 1, "weight": 0},
    "campus": {"fillColor": "#DBE8F7", "fillOpacity": 1, "weight": 0},
    "water": {"fillColor": "#9DCFF3", "fillOpacity": 1, "weight": 0},
    "building": {"fillColor": "#ECECEA", "fillOpacity": 1, "color": "#DCDCD8", "weight": 0.6},
}
# 길은 테두리(밑칠)를 먼저 굵게 칠하고 그 위에 속을 칠한다.
_ROADS = [
    ("road_minor", "#E0E0DC", 5.5, "#FFFFFF", 3.8),
    ("road_middle", "#EAD7A0", 7.5, "#FFF5D3", 5.6),
    ("road_major", "#E8BD4A", 9.0, "#FADB6E", 7.0),
    ("road_trunk", "#DF8434", 10.0, "#F6A54B", 8.0),
]
_LINE = {
    "river": {"color": "#9DCFF3", "weight": 6, "opacity": 1},
    "rail": {"color": "#A7B8D8", "weight": 3.5, "opacity": 1},
}
_LABEL_COLOR = {"public": "#3D6BC4", "shop": "#E07B22", "park": "#3A9A4B", "apt": "#8C6A47", "place": "#6F6F6F"}

_CSS = f"""<style>
.leaflet-container {{ background: {BACKGROUND}; font-family: SUIT, sans-serif; }}
.bm-label {{ transform: translate(-50%, -50%); white-space: nowrap; font: 600 11px SUIT, sans-serif;
  text-shadow: 0 0 2px #fff, 0 0 2px #fff, 0 0 3px #fff; pointer-events: none; }}
.bm-label.p {{ font-size: 12px; font-weight: 700; }}
.leaflet-container:not(.bm-near) .bm-label.minor {{ display: none; }}
</style>"""


class _ZoomClass(folium.MacroElement):
    """확대 정도에 따라 지도 상자에 bm-near 표시를 붙여, CSS가 작은 이름표를 숨기거나 보이게 한다."""

    _template = Template("""
        {% macro script(this, kwargs) %}
        (function(map) {
            function mark() { map.getContainer().classList.toggle('bm-near', map.getZoom() >= {{ this.zoom }}); }
            map.on('zoomend', mark); mark();
            if (map.attributionControl) { map.attributionControl.addAttribution({{ this.attribution|tojson }}); }
        })({{ this._parent.get_name() }});
        {% endmacro %}
    """)

    def __init__(self, zoom: int, attribution: str):
        super().__init__()
        self.zoom = zoom
        self.attribution = attribution


@st.cache_data(show_spinner=False)
def _load(path: str, mtime: float) -> dict[str, list[dict[str, Any]]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    groups: dict[str, list[dict[str, Any]]] = {}
    for f in data.get("features", []):
        groups.setdefault(f["properties"]["k"], []).append(f)
    return groups


def load_basemap(path: Path = BASEMAP_GEOJSON) -> dict[str, list[dict[str, Any]]]:
    if not path.exists():
        return {}
    return _load(str(path), path.stat().st_mtime)


def _layer(features: list[dict[str, Any]], style: dict[str, Any]) -> folium.GeoJson:
    return folium.GeoJson(
        {"type": "FeatureCollection", "features": features},
        style_function=lambda _f, s=style: s,
        interactive=False,
        control=False,
    )


def _label_html(name: str, kind: str, priority: bool) -> str:
    cls = "bm-label p" if priority else "bm-label minor"
    return f'<div class="{cls}" style="color:{_LABEL_COLOR.get(kind, "#555")}">{html.escape(name)}</div>'


def add_basemap(m: folium.Map) -> bool:
    """바탕 지도를 칠한다. 데이터 파일이 없으면 아무것도 하지 않고 False를 돌려준다(그때는 타일을 쓴다)."""
    groups = load_basemap()
    if not groups:
        return False
    m.get_root().header.add_child(folium.Element(_CSS))
    for kind in ("forest", "residential", "commercial", "green", "pitch", "campus", "water"):
        if groups.get(kind):
            _layer(groups[kind], _FILL[kind]).add_to(m)
    if groups.get("river"):
        _layer(groups["river"], _LINE["river"]).add_to(m)
    if groups.get("building"):
        _layer(groups["building"], _FILL["building"]).add_to(m)
    for kind, edge, edge_w, _fill, _fill_w in _ROADS:
        if groups.get(kind):
            _layer(groups[kind], {"color": edge, "weight": edge_w, "opacity": 1, "lineCap": "round"}).add_to(m)
    for kind, _edge, _edge_w, fill, fill_w in _ROADS:
        if groups.get(kind):
            _layer(groups[kind], {"color": fill, "weight": fill_w, "opacity": 1, "lineCap": "round"}).add_to(m)
    if groups.get("rail"):
        _layer(groups["rail"], _LINE["rail"]).add_to(m)
    seen: set[str] = set()
    for f in groups.get("label", []):
        p = f["properties"]
        name = p["name"] + ("역" if p["name"] == "삼척" else "")
        if name in seen:
            continue
        seen.add(name)
        lon, lat = f["geometry"]["coordinates"]
        folium.Marker(
            [lat, lon], icon=folium.DivIcon(html=_label_html(name, p["kind"], bool(p.get("p")) or p["kind"] == "place"), icon_size=(0, 0)),
            interactive=False,
        ).add_to(m)
    _ZoomClass(DETAIL_ZOOM, ATTRIBUTION).add_to(m)
    return True
