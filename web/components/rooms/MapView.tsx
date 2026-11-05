"use client";

import { useEffect, useRef } from "react";
import type * as Leaflet from "leaflet";
import "leaflet/dist/leaflet.css";
import "leaflet.markercluster/dist/MarkerCluster.css";
import type { Room, RoomsData, Tone } from "@/lib/rooms";

type L = typeof Leaflet;

const INK = "#1c2228";
const SEA = "#0e7c86";
const TONE_BG: Record<Tone, string> = { cheap: "#23875a", pricey: "#cf5f1f", neutral: "#ffffff" };
const MIN_ZOOM = 14;
const MAX_ZOOM = 18;
const START_ZOOM = 15;
const PICK_ZOOM = 17;
const DETAIL_ZOOM = 16;
const PIN = { w: 56, h: 32, tail: 6 };

// 바탕 지도 색. 카카오맵(직방 지도)처럼 거의 흰 바탕에 노란 큰길, 주황 고속도로, 진한 하늘색 강, 베이지 아파트 단지.
const FILL: Record<string, Leaflet.PathOptions> = {
  residential: { fillColor: "#f2e8db", fillOpacity: 1, stroke: false },
  commercial: { fillColor: "#f4eee7", fillOpacity: 1, stroke: false },
  forest: { fillColor: "#eef5e6", fillOpacity: 1, stroke: false },
  green: { fillColor: "#d7edc6", fillOpacity: 1, stroke: false },
  pitch: { fillColor: "#c2e2a4", fillOpacity: 1, stroke: false },
  campus: { fillColor: "#dbe8f7", fillOpacity: 1, stroke: false },
  water: { fillColor: "#9dcff3", fillOpacity: 1, stroke: false },
  building: { fillColor: "#ececea", fillOpacity: 1, color: "#dcdcd8", weight: 0.6 },
};
// [종류, 테두리 색, 테두리 굵기, 속 색, 속 굵기]. 테두리를 먼저 모두 칠하고 속을 위에 칠한다.
const ROADS: [string, string, number, string, number][] = [
  ["road_minor", "#e0e0dc", 5.5, "#ffffff", 3.8],
  ["road_middle", "#ead7a0", 7.5, "#fff5d3", 5.6],
  ["road_major", "#e8bd4a", 9, "#fadb6e", 7],
  ["road_trunk", "#df8434", 10, "#f6a54b", 8],
];
const LABEL_COLOR: Record<string, string> = {
  public: "#3d6bc4",
  shop: "#e07b22",
  park: "#3a9a4b",
  apt: "#8c6a47",
  place: "#6f6f6f",
};

type Feature = GeoJSON.Feature<GeoJSON.Geometry, { k: string; kind?: string; name?: string; p?: number }>;

interface MolitStat {
  n: number;
  monthly: number | null;
  deposit: number | null;
  area: number | null;
  built: number | null;
  from: string;
  to: string;
}
interface MolitLayer {
  roads: (MolitStat & { name: string; lat: number; lon: number })[];
  buildings: (MolitStat & { name: string; type: string; lat: number; lon: number })[];
}

const normName = (s: string) => s.replace(/\s|\(.*?\)/g, "");
const ym = (s: string) => `${s.slice(0, 4)}.${s.slice(4)}`;

function molitPopup(title: string, what: string, s: MolitStat) {
  const money = [s.monthly != null ? `월세 ${s.monthly}만` : "", s.deposit != null ? `보증금 ${s.deposit}만` : ""].filter(Boolean).join(" · ");
  const room = [s.area != null ? `${s.area}㎡` : "", s.built ? `${s.built}년 준공` : ""].filter(Boolean).join(" · ");
  return (
    `<div class="molit-pop"><strong>${esc(title)}</strong>${esc(what)} ${s.n}건 가운데 값<br>${esc(money)}` +
    (room ? `<br>${esc(room)}` : "") +
    `<br><small>국토교통부 실거래 ${ym(s.from)}~${ym(s.to)}</small></div>`
  );
}

function roadTone(monthly: number, mid: number) {
  if (monthly <= mid * 0.9) return "cheap";
  if (monthly >= mid * 1.1) return "pricey";
  return "";
}

function drawMolit(L: L, map: Leaflet.Map, layer: MolitLayer) {
  const prices = layer.roads.map((r) => r.monthly).filter((m): m is number => m != null).sort((a, b) => a - b);
  const mid = prices.length ? prices[Math.floor(prices.length / 2)] : 40;
  for (const r of layer.roads) {
    if (r.monthly == null) continue;
    L.marker([r.lat, r.lon], {
      keyboard: false,
      icon: L.divIcon({
        className: "label-icon",
        iconSize: [0, 0],
        html: `<div class="molit-road ${roadTone(r.monthly, mid)}">${esc(r.name)} 원룸 <b>${r.monthly}만</b></div>`,
      }),
    })
      .bindPopup(molitPopup(`${r.name} 원룸 시세`, "원룸형 거래", r))
      .addTo(map);
  }
  for (const b of layer.buildings) {
    const price = b.monthly != null ? `월 ${b.monthly}만` : b.deposit != null ? `전세 ${b.deposit}만` : "";
    L.marker([b.lat, b.lon], {
      keyboard: false,
      icon: L.divIcon({ className: "label-icon", iconSize: [0, 0], html: `<div class="molit-bldg">${esc(b.name)}<span>${esc(price)}</span></div>` }),
    })
      .bindPopup(molitPopup(b.name, `${b.type} 전월세`, b))
      .addTo(map);
  }
}

function esc(s: string) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string);
}

function pinHtml(room: Room, selected: boolean) {
  const colored = room.tone !== "neutral" && !selected;
  const bg = selected ? INK : TONE_BG[room.tone];
  const fg = selected || room.tone !== "neutral" ? "#fff" : INK;
  const edge = colored ? "#fff" : INK;
  const tail = selected ? INK : room.tone === "neutral" ? INK : TONE_BG[room.tone];
  const label = room.pin === "?" ? "?" : room.pin;
  return (
    `<div style="display:flex;flex-direction:column;align-items:center;width:100%;height:100%">` +
    `<div style="box-sizing:border-box;min-width:34px;height:${PIN.h - PIN.tail}px;padding:0 7px;display:flex;align-items:center;` +
    `justify-content:center;border-radius:8px;background:${bg};color:${fg};font:800 ${selected ? 15 : 13}px SUIT,sans-serif;` +
    `font-variant-numeric:tabular-nums;border:2px ${room.transfer ? "dashed" : "solid"} ${edge};` +
    `box-shadow:0 2px 5px rgba(28,34,40,.28);white-space:nowrap">${esc(label)}</div>` +
    `<div style="width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-top:${PIN.tail}px solid ${tail}"></div></div>`
  );
}

function clusterIcon(L: L, n: number) {
  const s = n < 10 ? 34 : n < 30 ? 40 : 46;
  return L.divIcon({
    className: "cluster-icon",
    iconSize: [s, s],
    html:
      `<div style="width:${s}px;height:${s}px;border-radius:50%;background:${SEA};color:#fff;display:flex;align-items:center;` +
      `justify-content:center;font:800 14px SUIT,sans-serif;border:2px solid #fff;box-shadow:0 2px 6px rgba(28,34,40,.35)">${n}</div>`,
  });
}

function drawBasemap(L: L, map: Leaflet.Map, features: Feature[], skipNames: Set<string>) {
  const renderer = L.canvas({ padding: 0.3 });
  const by: Record<string, Feature[]> = {};
  for (const f of features) (by[f.properties.k] ??= []).push(f);
  const layer = (kind: string, style: Leaflet.PathOptions) => {
    if (by[kind]?.length) L.geoJSON({ type: "FeatureCollection", features: by[kind] } as GeoJSON.FeatureCollection, { style: () => style, interactive: false, renderer } as Leaflet.GeoJSONOptions).addTo(map);
  };
  for (const k of ["forest", "residential", "commercial", "green", "pitch", "campus", "water"]) layer(k, FILL[k]);
  layer("river", { color: "#9dcff3", weight: 6, opacity: 1 });
  layer("building", FILL.building);
  for (const [k, edge, ew] of ROADS) layer(k, { color: edge, weight: ew, opacity: 1, lineCap: "round" });
  for (const [k, , , fill, fw] of ROADS) layer(k, { color: fill, weight: fw, opacity: 1, lineCap: "round" });
  layer("rail", { color: "#a7b8d8", weight: 3.5, opacity: 1 });
  layer("rail", { color: "#ffffff", weight: 1.4, opacity: 1, dashArray: "6 6" });

  const seen = new Set<string>();
  for (const f of by.label ?? []) {
    const p = f.properties;
    const name = p.name === "삼척" ? "삼척역" : (p.name as string);
    if (seen.has(name) || f.geometry.type !== "Point" || skipNames.has(normName(name))) continue;
    seen.add(name);
    const [lon, lat] = f.geometry.coordinates;
    L.marker([lat, lon], {
      interactive: false,
      keyboard: false,
      icon: L.divIcon({
        className: "label-icon",
        iconSize: [0, 0],
        html: `<div class="bm-label ${p.p || p.kind === "place" ? "major" : "minor"} ${p.kind ?? ""}" style="color:${LABEL_COLOR[p.kind ?? ""] ?? "#555"}">${esc(name)}</div>`,
      }),
    }).addTo(map);
  }
}

export default function MapView({
  data,
  rooms,
  selectedId,
  onSelect,
}: {
  data: RoomsData;
  rooms: Room[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const ref = useRef<{ L: L; map: Leaflet.Map; cluster: Leaflet.MarkerClusterGroup; picked: Leaflet.LayerGroup } | null>(null);
  // 지도는 비동기로 한 번 만들어지므로, 핀을 그릴 때는 늘 최신 값을 읽게 ref에 둔다.
  const latest = useRef({ rooms, selectedId, onSelect });
  latest.current = { rooms, selectedId, onSelect };

  useEffect(() => {
    let cancelled = false;
    let resize: ResizeObserver | null = null;
    (async () => {
      const L = (await import("leaflet")).default;
      // markercluster 플러그인은 전역 L에 붙는다.
      (window as unknown as { L: L }).L = L;
      await import("leaflet.markercluster");
      if (cancelled || !box.current || ref.current) return;
      const b = data.bounds;
      const school = data.areaCenters["학교"] ?? [37.4505, 129.1615];
      const map = L.map(box.current, {
        center: school,
        zoom: START_ZOOM,
        minZoom: MIN_ZOOM,
        maxZoom: MAX_ZOOM,
        maxBounds: [[b.min_lat, b.min_lon], [b.max_lat, b.max_lon]],
        maxBoundsViscosity: 1,
        zoomControl: true,
        attributionControl: true,
      });
      map.attributionControl.setPrefix(false);
      map.attributionControl.addAttribution('© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> 기여자');
      L.control.scale({ imperial: false }).addTo(map);
      const mark = () => map.getContainer().classList.toggle("bm-near", map.getZoom() >= DETAIL_ZOOM);
      map.on("zoomend", mark);
      mark();
      for (const [area, c] of Object.entries(data.areaCenters)) {
        if (area === "학교") continue;
        L.marker(c, {
          interactive: false,
          keyboard: false,
          icon: L.divIcon({
            className: "label-icon",
            iconSize: [0, 0],
            html: `<div class="bm-label major" style="color:${SEA};background:rgba(255,255,255,.85);padding:1px 6px;border-radius:6px">${esc(area)}</div>`,
          }),
        }).addTo(map);
      }
      const cluster = L.markerClusterGroup({
        maxClusterRadius: 42,
        disableClusteringAtZoom: PICK_ZOOM,
        showCoverageOnHover: false,
        spiderfyOnMaxZoom: true,
        iconCreateFunction: (c) => clusterIcon(L, c.getChildCount()),
      }).addTo(map);
      const picked = L.layerGroup().addTo(map);
      ref.current = { L, map, cluster, picked };
      // 화면 폭이 바뀌어 지도 칸 크기가 달라지면 Leaflet에 다시 재게 한다(안 하면 빈 칸으로 남는다).
      resize = new ResizeObserver(() => map.invalidateSize());
      resize.observe(box.current);
      const [gj, molit] = await Promise.all([
        fetch("/data/basemap.geojson").then((r) => r.json() as Promise<GeoJSON.FeatureCollection>).catch(() => null),
        fetch("/data/molit_layer.json").then((r) => r.json() as Promise<MolitLayer>).catch(() => null),
      ]);
      // 바탕 지도나 실거래 층을 못 받아도 핀은 보이게 둔다. 실거래 건물 이름표와 겹치는 바탕 이름표는 뺀다.
      if (!cancelled && gj) drawBasemap(L, map, gj.features as Feature[], new Set(molit?.buildings.map((b) => normName(b.name)) ?? []));
      if (!cancelled && molit) drawMolit(L, map, molit);
      setPins();
    })();
    return () => {
      cancelled = true;
      resize?.disconnect();
      ref.current?.map.remove();
      ref.current = null;
    };
    // 지도는 한 번만 만든다. 핀은 아래 효과가 바꾼다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function setPins() {
    const cur = ref.current;
    if (!cur) return;
    const { L, cluster, picked } = cur;
    const { rooms, selectedId } = latest.current;
    cluster.clearLayers();
    picked.clearLayers();
    const markers: Leaflet.Marker[] = [];
    for (const r of rooms) {
      if (!r.inCity) continue;
      const sel = r.id === selectedId;
      const m = L.marker([r.lat, r.lon], {
        title: `${r.name} · ${r.headline}`,
        zIndexOffset: sel ? 1000 : 0,
        icon: L.divIcon({ className: "pin-icon", iconSize: [PIN.w, PIN.h], iconAnchor: [PIN.w / 2, PIN.h], html: pinHtml(r, sel) }),
      });
      m.on("click", () => latest.current.onSelect(r.id));
      if (sel) m.addTo(picked);
      else markers.push(m);
    }
    cluster.addLayers(markers);
  }

  useEffect(() => {
    setPins();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rooms, selectedId]);

  useEffect(() => {
    const cur = ref.current;
    if (!cur || !selectedId) return;
    const r = rooms.find((x) => x.id === selectedId);
    if (r?.inCity) cur.map.setView([r.lat, r.lon], Math.max(cur.map.getZoom(), PICK_ZOOM), { animate: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  return <div ref={box} className="h-full w-full" role="application" aria-label="삼척 시내 자취방 가격 지도" />;
}
