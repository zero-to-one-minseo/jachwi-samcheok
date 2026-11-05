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

// 바탕 지도 색. 네이버 지도처럼 밝은 바탕에 흰 길, 노란 큰길, 연파랑 학교, 하늘색 강.
const FILL: Record<string, Leaflet.PathOptions> = {
  residential: { fillColor: "#eee8e1", fillOpacity: 1, stroke: false },
  commercial: { fillColor: "#f1e9e2", fillOpacity: 1, stroke: false },
  green: { fillColor: "#ddefd0", fillOpacity: 1, stroke: false },
  pitch: { fillColor: "#c9e6b3", fillOpacity: 1, stroke: false },
  campus: { fillColor: "#dce6f2", fillOpacity: 1, stroke: false },
  water: { fillColor: "#a9d5f3", fillOpacity: 1, stroke: false },
  building: { fillColor: "#e7e7e4", fillOpacity: 1, color: "#d5d5d2", weight: 0.6 },
};
const ROADS: [string, string, number, string, number][] = [
  ["road_minor", "#dadad7", 5.5, "#ffffff", 3.8],
  ["road_middle", "#d0d0cc", 7.5, "#ffffff", 5.6],
  ["road_major", "#e9c46e", 9, "#fae19b", 7],
];
const LABEL_COLOR: Record<string, string> = { public: "#4f6fa8", shop: "#d9822b", park: "#3f944f" };

type Feature = GeoJSON.Feature<GeoJSON.Geometry, { k: string; kind?: string; name?: string; p?: number }>;

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

function drawBasemap(L: L, map: Leaflet.Map, features: Feature[]) {
  const renderer = L.canvas({ padding: 0.3 });
  const by: Record<string, Feature[]> = {};
  for (const f of features) (by[f.properties.k] ??= []).push(f);
  const layer = (kind: string, style: Leaflet.PathOptions) => {
    if (by[kind]?.length) L.geoJSON({ type: "FeatureCollection", features: by[kind] } as GeoJSON.FeatureCollection, { style: () => style, interactive: false, renderer } as Leaflet.GeoJSONOptions).addTo(map);
  };
  for (const k of ["residential", "commercial", "green", "pitch", "campus", "water"]) layer(k, FILL[k]);
  layer("river", { color: "#a9d5f3", weight: 6, opacity: 1 });
  layer("building", FILL.building);
  for (const [k, edge, ew] of ROADS) layer(k, { color: edge, weight: ew, opacity: 1, lineCap: "round" });
  for (const [k, , , fill, fw] of ROADS) layer(k, { color: fill, weight: fw, opacity: 1, lineCap: "round" });
  layer("rail", { color: "#a3a3a0", weight: 2.2, opacity: 1, dashArray: "7 5" });

  const seen = new Set<string>();
  for (const f of by.label ?? []) {
    const p = f.properties;
    const name = p.name === "삼척" ? "삼척역" : (p.name as string);
    if (seen.has(name) || f.geometry.type !== "Point") continue;
    seen.add(name);
    const [lon, lat] = f.geometry.coordinates;
    L.marker([lat, lon], {
      interactive: false,
      keyboard: false,
      icon: L.divIcon({
        className: "label-icon",
        iconSize: [0, 0],
        html: `<div class="bm-label ${p.p ? "major" : "minor"}" style="color:${LABEL_COLOR[p.kind ?? ""] ?? "#555"}">${esc(name)}</div>`,
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
      try {
        const res = await fetch("/data/basemap.geojson");
        const gj = (await res.json()) as GeoJSON.FeatureCollection;
        if (!cancelled) drawBasemap(L, map, gj.features as Feature[]);
      } catch {
        // 바탕 지도를 못 받아도 핀은 보이게 둔다.
      }
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
