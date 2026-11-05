// 데이터는 tools/export_web_data.py가 만든 public/data/rooms.json. 필터 규칙은 Python의 lib/rooms_data.filter_rooms와 같다.

export type Tone = "cheap" | "pricey" | "neutral";

export type SelectedRoom = Record<string, unknown> & { name: string };

export interface Room {
  id: string;
  name: string;
  area: string;
  kind: string;
  kindWord: string;
  contractType: string;
  included: string[];
  monthly: number | null;
  monthlyLow: number | null;
  monthlyHigh: number | null;
  pin: string;
  tone: Tone;
  transfer: boolean;
  lat: number;
  lon: number;
  inCity: boolean;
  headline: string;
  terms: string;
  compare: { tone: Tone; chip: string; text: string; median: number } | null;
  priceLine: string;
  includedLine: string;
  detailLine: string;
  sourceLine: string;
  transferNote: string;
  selected: SelectedRoom;
}

export interface RoomsData {
  rooms: Room[];
  areas: string[];
  contractTypes: string[];
  kinds: string[];
  includedItems: string[];
  areaCenters: Record<string, [number, number]>;
  areaDongs: Record<string, string[]>;
  bounds: { min_lat: number; max_lat: number; min_lon: number; max_lon: number };
  baseline: { period: string; records: { dong: string; monthly: number; deposit: number | null }[] } | null;
  survey: { when: string; sources: string[] };
}

export interface Filters {
  areas: string[];
  range: [number, number];
  contractTypes: string[];
  kinds: string[];
  items: string[];
  unknown: boolean;
}

export function priceCeiling(rooms: Room[]): number {
  const max = Math.max(60, ...rooms.filter((r) => r.monthlyHigh != null).map((r) => r.monthlyHigh as number));
  return Math.ceil(max / 5) * 5;
}

export function emptyFilters(top: number): Filters {
  return { areas: [], range: [0, top], contractTypes: [], kinds: [], items: [], unknown: false };
}

export function filterRooms(rooms: Room[], f: Filters): Room[] {
  return rooms.filter((r) => {
    if (f.areas.length && !f.areas.includes(r.area)) return false;
    if (f.contractTypes.length && !f.contractTypes.includes(r.contractType)) return false;
    if (f.kinds.length && !f.kinds.includes(r.kind)) return false;
    if (f.items.length && !f.items.every((i) => r.included.includes(i))) return false;
    if (r.monthly == null) return f.unknown;
    const [lo, hi] = f.range;
    return !((r.monthlyHigh as number) < lo || (r.monthlyLow as number) > hi);
  });
}

export function median(values: number[]): number | null {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

export function fmtMan(v: number | null | undefined): string {
  if (v == null) return "";
  const r = Math.round(v * 10) / 10;
  return Number.isInteger(r) ? r.toLocaleString("ko-KR") : r.toLocaleString("ko-KR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

export function baselineSummary(data: RoomsData, areas: string[]) {
  const base = data.baseline;
  if (!base) return null;
  let records = base.records;
  let label = "삼척시 전체";
  if (areas.length) {
    const dongs = new Set(areas.flatMap((a) => data.areaDongs[a] ?? []));
    if (!dongs.size) return null;
    records = records.filter((r) => dongs.has(r.dong));
    label = [...dongs].sort().join("·");
  }
  if (!records.length) return null;
  return { label, count: records.length, monthly: median(records.map((r) => r.monthly)) as number, period: base.period };
}

export function filterCount(f: Filters, top: number): number {
  return (
    f.areas.length + f.contractTypes.length + f.kinds.length + f.items.length + (f.unknown ? 1 : 0) +
    (f.range[0] !== 0 || f.range[1] !== top ? 1 : 0)
  );
}
