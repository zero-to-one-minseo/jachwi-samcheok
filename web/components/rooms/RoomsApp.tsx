"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useMemo, useRef, useState } from "react";
import FilterBar from "./FilterBar";
import {
  baselineSummary, emptyFilters, filterCount, filterRooms, fmtMan, median, priceCeiling,
  type Filters, type Room, type RoomsData,
} from "@/lib/rooms";

const MapView = dynamic(() => import("./MapView"), {
  ssr: false,
  loading: () => <div className="grid h-full place-items-center text-sm text-muted">지도를 불러오는 중이에요</div>,
});

const CHIP: Record<string, string> = {
  cheap: "bg-cheap-soft text-cheap",
  pricey: "bg-pricey-soft text-pricey",
  neutral: "bg-bg text-muted",
};

export default function RoomsApp({ data }: { data: RoomsData }) {
  const top = useMemo(() => priceCeiling(data.rooms), [data.rooms]);
  const [filters, setFilters] = useState<Filters>(() => emptyFilters(top));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showSurvey, setShowSurvey] = useState(false);
  const panel = useRef<HTMLElement>(null);

  const rooms = useMemo(() => filterRooms(data.rooms, filters), [data.rooms, filters]);
  const selected = rooms.find((r) => r.id === selectedId) ?? null;
  const studentMid = median(rooms.filter((r) => r.monthly != null).map((r) => r.monthly as number));
  const base = baselineSummary(data, filters.areas);

  const pick = (id: string | null) => {
    setSelectedId(id);
    if (id) setShowSurvey(true);
    if (id && window.matchMedia("(max-width: 767px)").matches) {
      panel.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  return (
    <main className="flex flex-1 flex-col md:h-[calc(100dvh-56px)] md:flex-none md:flex-row">
      <section className="relative h-[56dvh] shrink-0 md:h-auto md:flex-1">
        <MapView data={data} rooms={showSurvey ? rooms : []} selectedId={selected?.id ?? null} onSelect={pick} showMolit={!showSurvey} />
        <div className="absolute bottom-8 left-3 z-[900] flex gap-1 rounded-full border border-line bg-surface p-1 text-[13px] font-semibold shadow-sm">
          <button type="button" aria-pressed={!showSurvey} onClick={() => { setShowSurvey(false); setSelectedId(null); }}
            className={`rounded-full px-3 py-1 ${!showSurvey ? "bg-ink text-white" : "text-muted"}`}>실거래 평균</button>
          <button type="button" aria-pressed={showSurvey} onClick={() => setShowSurvey(true)}
            className={`rounded-full px-3 py-1 ${showSurvey ? "bg-ink text-white" : "text-muted"}`}>직접 조사</button>
        </div>
        <div className="pointer-events-none absolute inset-x-0 top-0 z-[900] p-3 md:p-4">
          <div className="pointer-events-auto ml-12 md:ml-14">
            <FilterBar
              filters={filters}
              setFilters={(f) => { setFilters(f); setSelectedId(null); }}
              top={top}
              options={{ areas: data.areas, contractTypes: data.contractTypes, kinds: data.kinds, items: data.includedItems }}
            />
          </div>
        </div>
      </section>

      <aside ref={panel} className="flex flex-col border-line bg-surface md:min-h-0 md:w-[240px] md:shrink-0 md:border-l">
        <Summary count={rooms.length} studentMid={studentMid} base={base} survey={showSurvey} resetable={filterCount(filters, top) > 0}
          onReset={() => { setFilters(emptyFilters(top)); setSelectedId(null); }} />
        <div className="flex-1 md:min-h-0 md:overflow-y-auto">
          {selected ? (
            <RoomDetail room={selected} onBack={() => setSelectedId(null)} />
          ) : (
            <RoomList rooms={rooms} onPick={pick} />
          )}
          <Footer data={data} />
        </div>
      </aside>
    </main>
  );
}

function Summary({ count, studentMid, base, survey, resetable, onReset }: {
  count: number;
  survey: boolean;
  studentMid: number | null;
  base: ReturnType<typeof baselineSummary>;
  resetable: boolean;
  onReset: () => void;
}) {
  const max = Math.max(studentMid ?? 0, base?.monthly ?? 0, 1);
  const surveyBar = { label: "직접 조사", value: studentMid, color: survey ? "bg-sea" : "bg-line-strong" };
  const molitBar = { label: "국토부 실거래", value: base?.monthly ?? null, color: survey ? "bg-line-strong" : "bg-sea" };
  const bars = survey ? [surveyBar, molitBar] : [molitBar, surveyBar];
  return (
    <div className="border-b border-line px-5 pb-4 pt-5 md:px-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-[22px] font-extrabold tracking-[-0.02em]">
          삼척 자취방 <span className="tabular">{count}</span>곳
        </h1>
        {resetable && (
          <button type="button" onClick={onReset} className="text-sm font-semibold text-sea hover:underline">
            조건 지우기
          </button>
        )}
      </div>
      <div className="mt-4 space-y-2.5">
        {bars.map((b) => (
          <div key={b.label} className="grid grid-cols-[96px_1fr_auto] items-center gap-3 md:grid-cols-[80px_1fr_auto] md:gap-2">
            <span className="whitespace-nowrap text-[13px] font-semibold text-muted">{b.label}</span>
            <div className="h-2.5 overflow-hidden rounded-full bg-bg">
              {b.value != null && <div className={`h-full rounded-full ${b.color}`} style={{ width: `${(b.value / max) * 100}%` }} />}
            </div>
            <span className="tabular text-[15px] font-extrabold">{b.value != null ? `월 ${fmtMan(b.value)}만` : "없음"}</span>
          </div>
        ))}
      </div>
      <p className="mt-3 text-[13px] font-semibold text-sea">
        {base
          ? `국토교통부 전월세 실거래 ${base.count}건(40㎡ 이하 월세) · ${base.label} · ${base.period}`
          : "고른 생활권에는 국토부 실거래가 없어요."}
      </p>
    </div>
  );
}

function RoomList({ rooms, onPick }: { rooms: Room[]; onPick: (id: string) => void }) {
  if (!rooms.length) {
    return <p className="px-5 py-10 text-center text-sm text-muted">조건에 맞는 방이 없어요. 위 단추에서 조건을 줄여 보세요.</p>;
  }
  return (
    <ul className="divide-y divide-line">
      {rooms.map((r) => (
        <li key={r.id}>
          <button type="button" onClick={() => onPick(r.id)} className="block w-full px-5 py-4 md:px-4 text-left transition-colors hover:bg-bg">
            <div className="flex items-center gap-2">
              <span className="tabular text-[19px] font-extrabold tracking-[-0.01em]">{r.headline}</span>
              {r.compare && <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${CHIP[r.compare.tone]}`}>{r.compare.chip}</span>}
              {r.transfer && <span className="rounded-full border border-dashed border-ink px-2 py-0.5 text-xs font-bold">양도</span>}
            </div>
            {r.terms && <p className="mt-0.5 text-sm">{r.terms}</p>}
            <p className="mt-1.5 text-[15px] font-semibold">{r.name}</p>
            <p className="mt-0.5 text-[13px] text-muted">
              {r.area} · {r.kindWord}{r.precise && " · 건물 위치"}{!r.inCity && " · 시내 밖이라 지도에는 없어요"}
            </p>
          </button>
        </li>
      ))}
    </ul>
  );
}

function RoomDetail({ room, onBack }: { room: Room; onBack: () => void }) {
  return (
    <div className="px-5 py-4 md:px-4">
      <button type="button" onClick={onBack} className="mb-3 flex items-center gap-1 text-sm font-semibold text-muted hover:text-ink">
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden><path d="M10 3 5 8l5 5" fill="none" stroke="currentColor" strokeWidth="1.8" /></svg>
        목록으로
      </button>
      <p className="tabular text-[30px] font-extrabold leading-tight tracking-[-0.02em]">{room.headline}</p>
      <p className="mt-1 text-[17px] font-bold">{room.name}</p>
      <p className="mt-0.5 text-[13px] text-muted">{room.area} · {room.kindWord} · {room.contractType}</p>
      {room.compare && (
        <p className={`mt-3 inline-block rounded-lg px-2.5 py-1 text-sm font-semibold ${CHIP[room.compare.tone]}`}>{room.compare.text}</p>
      )}
      <dl className="mt-4 space-y-3 text-[15px]">
        <Row term="위치" icon="pin">
          {room.precise ? (
            <>
              {room.placeName} · {room.address}
            </>
          ) : (
            <>{room.area} 일대</>
          )}
        </Row>
        <Row term="돈" icon="coin">{room.priceLine}</Row>
        <Row term="포함" icon="check">{room.includedLine}</Row>
        {room.detailLine && <Row term="방" icon="home">{room.detailLine}</Row>}
      </dl>
      {room.transferNote && (
        <div className="mt-4 rounded-lg border border-pricey/30 bg-pricey-soft px-3.5 py-3 text-sm text-ink">
          <p className="font-bold text-pricey">집주인 동의 확인</p>
          <p className="mt-1">{room.transferNote}</p>
        </div>
      )}
      {room.naverUrl && (
        <a
          href={room.naverUrl}
          target="_blank"
          rel="noreferrer"
          className="mt-4 flex w-full items-center justify-center gap-1.5 rounded-xl border border-line-strong px-4 py-3 text-[15px] font-semibold hover:border-ink"
        >
          네이버 지도에서 건물·거리뷰 보기
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden><path d="M5 2h7v7M12 2 5.5 8.5M10 9v3H2V4h3" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>
        </a>
      )}
      <p className="mt-4 text-sm font-semibold text-sea">{room.sourceLine}</p>
      <Link
        href={`/check?room=${room.id}`}
        className="mt-5 flex w-full items-center justify-center rounded-xl bg-sea px-4 py-3.5 text-[15px] font-bold text-white transition-colors hover:bg-[#0b6a73]"
      >
        이 방 계약서 검사하기
      </Link>
    </div>
  );
}

const ICON_PATHS: Record<"pin" | "coin" | "check" | "home", React.ReactNode> = {
  pin: <path d="M10 18s-5.5-5.2-5.5-9.2a5.5 5.5 0 0 1 11 0C15.5 12.8 10 18 10 18Zm0-7.2a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" />,
  coin: <><circle cx="10" cy="10" r="7" /><path d="M7 7.5l1.4 5 1.6-4 1.6 4 1.4-5M6.5 10h7" /></>,
  check: <><rect x="3.5" y="3.5" width="13" height="13" rx="3" /><path d="m6.8 10.2 2.2 2.2 4.3-4.6" /></>,
  home: <path d="M3.5 9.5 10 4l6.5 5.5V16a.5.5 0 0 1-.5.5h-3.5v-4h-5v4H4a.5.5 0 0 1-.5-.5V9.5Z" />,
};

function Row({ term, icon, children }: { term: string; icon: keyof typeof ICON_PATHS; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[64px_1fr] gap-3">
      <dt className="flex items-center gap-1.5 text-sm font-bold text-ink">
        <svg width="18" height="18" viewBox="0 0 20 20" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.7"
          strokeLinecap="round" strokeLinejoin="round" className="shrink-0 text-sea">{ICON_PATHS[icon]}</svg>
        {term}
      </dt>
      <dd>{children}</dd>
    </div>
  );
}

function Footer({ data }: { data: RoomsData }) {
  return (
    <footer className="border-t border-line px-5 py-5 md:px-4 leading-relaxed">
      <p className="text-sm font-semibold text-sea">
        조사 {data.survey.when} · 출처: {data.survey.sources.join(", ")} · 국토교통부 실거래가 공개시스템 · 건축물대장
      </p>
      <p className="mt-2 text-sm font-bold text-ink">실제 매물 여부는 연락해서 확인하세요.</p>
    </footer>
  );
}
