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
        <MapView data={data} rooms={showSurvey ? rooms : []} selectedId={selected?.id ?? null} onSelect={pick} />
        <div className="absolute bottom-8 left-3 z-[900] flex gap-1 rounded-full border border-line bg-surface p-1 text-[13px] font-semibold shadow-sm">
          <button type="button" aria-pressed={!showSurvey} onClick={() => { setShowSurvey(false); setSelectedId(null); }}
            className={`rounded-full px-3 py-1 ${!showSurvey ? "bg-ink text-white" : "text-muted"}`}>실거래 평균</button>
          <button type="button" aria-pressed={showSurvey} onClick={() => setShowSurvey(true)}
            className={`rounded-full px-3 py-1 ${showSurvey ? "bg-ink text-white" : "text-muted"}`}>학생 조사 방</button>
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

      <aside ref={panel} className="flex flex-col border-line bg-surface md:min-h-0 md:w-[420px] md:shrink-0 md:border-l">
        <Summary count={rooms.length} studentMid={studentMid} base={base} resetable={filterCount(filters, top) > 0}
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

function Summary({ count, studentMid, base, resetable, onReset }: {
  count: number;
  studentMid: number | null;
  base: ReturnType<typeof baselineSummary>;
  resetable: boolean;
  onReset: () => void;
}) {
  const max = Math.max(studentMid ?? 0, base?.monthly ?? 0, 1);
  const bars = [
    { label: "학생들이 모은 값", value: studentMid, color: "bg-sea" },
    { label: "국토부 실거래", value: base?.monthly ?? null, color: "bg-line-strong" },
  ];
  return (
    <div className="border-b border-line px-5 pb-4 pt-5">
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
      <p className="mt-1 text-[13px] text-muted">직방에 잘 안 뜨는 방, 학생들이 직접 모은 값이에요. 월 환산 가운데 값을 비교해요.</p>
      <div className="mt-4 space-y-2.5">
        {bars.map((b) => (
          <div key={b.label} className="grid grid-cols-[96px_1fr_auto] items-center gap-3">
            <span className="text-[13px] font-semibold text-muted">{b.label}</span>
            <div className="h-2.5 overflow-hidden rounded-full bg-bg">
              {b.value != null && <div className={`h-full rounded-full ${b.color}`} style={{ width: `${(b.value / max) * 100}%` }} />}
            </div>
            <span className="tabular text-[15px] font-extrabold">{b.value != null ? `월 ${fmtMan(b.value)}만` : "없음"}</span>
          </div>
        ))}
      </div>
      <p className="mt-2 text-xs text-muted">
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
          <button type="button" onClick={() => onPick(r.id)} className="block w-full px-5 py-4 text-left transition-colors hover:bg-bg">
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
    <div className="px-5 py-4">
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
        <Row term="위치">
          {room.precise ? (
            <>
              {room.placeName} · {room.address}
              <span className="mt-0.5 block text-xs text-muted">네이버 지역 검색으로 찾은 건물 위치예요.</span>
            </>
          ) : (
            <span className="text-muted">건물을 특정할 수 없어 길·생활권 단위 대략 위치로 찍었어요.</span>
          )}
        </Row>
        <Row term="돈">{room.priceLine}</Row>
        <Row term="포함">{room.includedLine}</Row>
        {room.detailLine && <Row term="방">{room.detailLine}</Row>}
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
      <p className="mt-4 text-xs text-muted">{room.sourceLine}</p>
      <Link
        href={`/check?room=${room.id}`}
        className="mt-5 flex w-full items-center justify-center rounded-xl bg-sea px-4 py-3.5 text-[15px] font-bold text-white transition-colors hover:bg-[#0b6a73]"
      >
        이 방 계약서 점검하기
      </Link>
      <p className="mt-2 text-center text-xs text-muted">계약서 사진을 올리면 확인할 조항과 집주인에게 물을 질문을 짚어 줘요.</p>
    </div>
  );
}

function Row({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[40px_1fr] gap-3">
      <dt className="text-sm font-bold text-muted">{term}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Footer({ data }: { data: RoomsData }) {
  return (
    <footer className="border-t border-line px-5 py-5 text-xs leading-relaxed text-muted">
      <p>조사 {data.survey.when} · 출처: {data.survey.sources.join(", ")}</p>
      <p className="mt-1">
        팀원이 글을 직접 읽고 숫자와 조건만 옮겼어요. 연락처, 호수, 글 주소는 싣지 않았어요. 선세·연세는 개월 수로 나눈 월 환산으로 비교하고, 양도 글은
        생활권 가운데 값에서 뺐어요. 건물 이름이 분명한 방은 네이버 지역 검색으로 찾은 건물 위치이고, 나머지는 길·생활권 단위 대략 위치예요.
      </p>
      <p className="mt-2 font-bold text-ink">실제 매물 여부는 연락해서 확인하세요.</p>
    </footer>
  );
}
