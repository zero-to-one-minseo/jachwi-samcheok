"use client";

import { useEffect, useRef, useState } from "react";
import type { Filters } from "@/lib/rooms";

type Key = "areas" | "range" | "contractTypes" | "kinds" | "items";

function Toggle({ on, label, onClick }: { on: boolean; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={`rounded-full border px-3 py-1.5 text-sm font-semibold transition-colors ${
        on ? "border-sea bg-sea text-white" : "border-line-strong bg-surface text-ink hover:border-ink"
      }`}
    >
      {label}
    </button>
  );
}

export default function FilterBar({
  filters,
  setFilters,
  top,
  options,
}: {
  filters: Filters;
  setFilters: (f: Filters) => void;
  top: number;
  options: { areas: string[]; contractTypes: string[]; kinds: string[]; items: string[] };
}) {
  const [open, setOpen] = useState<Key | null>(null);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(null);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(null);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, []);

  const flip = (key: "areas" | "contractTypes" | "kinds" | "items", v: string) => {
    const cur = filters[key];
    setFilters({ ...filters, [key]: cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v] });
  };
  const [lo, hi] = filters.range;
  const rangeOn = lo !== 0 || hi !== top;

  const chips: { key: Key; label: string; count: number }[] = [
    { key: "areas", label: "생활권", count: filters.areas.length },
    { key: "range", label: rangeOn ? `월 ${lo}~${hi}만` : "월 환산", count: 0 },
    { key: "contractTypes", label: "계약 방식", count: filters.contractTypes.length },
    { key: "kinds", label: "자료 종류", count: filters.kinds.length },
    { key: "items", label: "포함 항목", count: filters.items.length + (filters.unknown ? 1 : 0) },
  ];

  return (
    <div ref={root} className="relative">
      <div className="flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none]">
        {chips.map((c) => {
          const active = c.count > 0 || (c.key === "range" && rangeOn);
          return (
            <button
              key={c.key}
              type="button"
              aria-expanded={open === c.key}
              onClick={() => setOpen(open === c.key ? null : c.key)}
              className={`flex shrink-0 items-center gap-1 rounded-full border px-3.5 py-2 text-sm font-semibold shadow-[0_1px_3px_rgba(28,34,40,.12)] transition-colors ${
                active ? "border-sea bg-sea-soft text-sea" : "border-line-strong bg-surface text-ink"
              }`}
            >
              {c.label}
              {c.count > 0 && <span className="tabular">{c.count}</span>}
              <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden className={open === c.key ? "rotate-180" : ""}>
                <path d="M1.5 3.5 5 7l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
              </svg>
            </button>
          );
        })}
      </div>

      {open && (
        <div className="absolute left-0 top-full z-[1100] mt-2 w-[min(340px,calc(100vw-32px))] rounded-xl border border-line bg-surface p-4 shadow-[0_8px_24px_rgba(28,34,40,.16)]">
          {open === "areas" && (
            <Section title="생활권" hint="고르지 않으면 전체예요.">
              {options.areas.map((a) => <Toggle key={a} on={filters.areas.includes(a)} label={a} onClick={() => flip("areas", a)} />)}
            </Section>
          )}
          {open === "range" && (
            <div>
              <p className="mb-1 text-sm font-bold">월 환산</p>
              <p className="mb-3 text-xs text-muted">선세·연세는 총액을 개월 수로 나눈 값이에요.</p>
              <p className="tabular mb-2 text-lg font-extrabold">월 {lo}만 ~ {hi}만 원</p>
              <label className="mb-1 block text-xs text-muted">
                최소
                <input type="range" min={0} max={top} value={lo} className="w-full accent-[var(--sea)]"
                  onChange={(e) => setFilters({ ...filters, range: [Math.min(+e.target.value, hi), hi] })} />
              </label>
              <label className="block text-xs text-muted">
                최대
                <input type="range" min={0} max={top} value={hi} className="w-full accent-[var(--sea)]"
                  onChange={(e) => setFilters({ ...filters, range: [lo, Math.max(+e.target.value, lo)] })} />
              </label>
            </div>
          )}
          {open === "contractTypes" && (
            <Section title="계약 방식">
              {options.contractTypes.map((a) => <Toggle key={a} on={filters.contractTypes.includes(a)} label={a} onClick={() => flip("contractTypes", a)} />)}
            </Section>
          )}
          {open === "kinds" && (
            <Section title="자료 종류" hint="양도는 남은 기간을 넘기는 글이에요. 실거래는 실제로 맺은 계약이에요.">
              {options.kinds.map((a) => <Toggle key={a} on={filters.kinds.includes(a)} label={a} onClick={() => flip("kinds", a)} />)}
            </Section>
          )}
          {open === "items" && (
            <>
              <Section title="포함 항목" hint="고른 항목이 모두 월세·관리비에 들어 있는 방만 보여요.">
                {options.items.map((a) => <Toggle key={a} on={filters.items.includes(a)} label={a} onClick={() => flip("items", a)} />)}
              </Section>
              <label className="mt-3 flex items-center gap-2 text-sm">
                <input type="checkbox" checked={filters.unknown} className="size-4 accent-[var(--sea)]"
                  onChange={(e) => setFilters({ ...filters, unknown: e.target.checked })} />
                가격이 안 적힌 방도 보기
              </label>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1 text-sm font-bold">{title}</p>
      {hint && <p className="mb-3 text-xs text-muted">{hint}</p>}
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}
