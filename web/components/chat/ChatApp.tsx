"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { prepareFile, UploadError } from "@/lib/upload";

interface Stats { n: number; median: number; low: number; high: number }
interface Group { label: string; basis: string; stats: Stats | null }
interface Result {
  price: number | null;
  price_how: string;
  verdict: "비싼 편" | "보통" | "싼 편" | "비교 못 함";
  diff: number | null;
  main: Group | null;
  groups: Group[];
  checks: string[];
  listing: Record<string, unknown>;
  building: { name: string; address: string; purpose: string; built: number; floors: number | null; households: number | null; deals: number } | null;
  building_candidates: number;
}
interface Step { tool: string; detail: string }
type Reply =
  | { kind: "listing"; result: Result; steps: Step[]; summary: string }
  | { kind: "contract" | "other" | "error"; message: string };
type Msg = { id: number; role: "user"; text: string; image: string | null } | { id: number; role: "bot"; reply: Reply };

const EXAMPLE =
  "[원룸 양도] 마달길 원룸 2015년 준공 7평 풀옵션, 보증금 200 / 월 38, 관리비 5만(인터넷 포함). 내년 2월까지 양도합니다.";
const VERDICT_STYLE: Record<Result["verdict"], string> = {
  "비싼 편": "bg-[#cf5f1f] text-white",
  "싼 편": "bg-[#23875a] text-white",
  보통: "bg-ink text-white",
  "비교 못 함": "bg-bg text-muted",
};

function readChips(l: Record<string, unknown>): string[] {
  const n = (k: string) => (typeof l[k] === "number" && (l[k] as number) >= 0 ? (l[k] as number) : null);
  const s = (k: string) => (typeof l[k] === "string" && l[k] ? (l[k] as string) : null);
  return [
    s("name"), s("dong"), s("road"),
    l.contract && l.contract !== "모름" ? String(l.contract) : null,
    n("deposit_man") != null ? `보증금 ${n("deposit_man")}만` : null,
    n("monthly_man") != null ? `월 ${n("monthly_man")}만` : null,
    n("prepaid_total_man") != null ? `한 번에 ${n("prepaid_total_man")}만` : null,
    n("fee_man") != null ? `관리비 ${n("fee_man")}만` : null,
    n("area_m2") != null ? `${Math.round(n("area_m2") as number)}㎡` : null,
    (l.built_year as number) > 0 ? `${l.built_year}년 준공` : null,
  ].filter(Boolean) as string[];
}

function ResultCard({ r }: { r: Result }) {
  const main = r.main?.stats;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-full px-3 py-1 text-sm font-extrabold ${VERDICT_STYLE[r.verdict]}`}>{r.verdict}</span>
        {r.price != null && <span className="text-lg font-extrabold text-ink">월 {r.price}만</span>}
        {r.price_how && r.price_how !== "월세" && <span className="text-xs text-muted">({r.price_how})</span>}
      </div>
      {main && r.main && (
        <p className="text-[15px] leading-relaxed text-ink">
          {r.main.label} 가운데 값은 <b>월 {main.median}만</b>
          <span className="text-muted">({main.n}건, 보통 {main.low}~{main.high}만)</span>
          {r.diff != null && r.diff !== 0 && <> 이라 <b>{Math.abs(r.diff)}만 {r.diff > 0 ? "비싸요" : "싸요"}</b></>}
          {r.diff === 0 && <> 과 같아요</>}.
        </p>
      )}
      {r.building && (
        <div className="rounded-lg border border-line p-3 text-sm">
          <p className="font-bold text-ink">
            건축물대장으로 찾은 건물: {r.building.name || r.building.address}
          </p>
          <p className="text-muted">
            {r.building.address} · {r.building.purpose} · {r.building.built}년 사용승인
            {r.building.floors ? ` · 지상 ${r.building.floors}층` : ""}
            {r.building.households ? ` · ${r.building.households}가구` : ""}
          </p>
        </div>
      )}
      {!r.building && r.building_candidates > 1 && (
        <p className="text-sm text-muted">같은 길·같은 준공 연도 건물이 {r.building_candidates}곳이라 한 건물로 좁히지 못했어요.</p>
      )}
      {r.groups.length > 0 && (
        <ul className="space-y-1 rounded-lg bg-bg p-3 text-sm">
          {r.groups.map((g) => (
            <li key={g.label} className="flex justify-between gap-3">
              <span>
                {g.label} <span className="text-xs text-muted">· {g.basis}</span>
              </span>
              <span className="shrink-0 font-bold tabular-nums">{g.stats ? `월 ${g.stats.median}만 · ${g.stats.n}건` : "-"}</span>
            </li>
          ))}
        </ul>
      )}
      {r.checks.length > 0 && (
        <div>
          <p className="mb-1 text-sm font-bold text-ink">계약 전에 확인할 것</p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-ink">
            {r.checks.map((c) => <li key={c}>{c}</li>)}
          </ul>
        </div>
      )}
      <div className="flex flex-wrap gap-1.5">
        <span className="text-xs text-muted">AI가 읽은 내용:</span>
        {readChips(r.listing).map((c) => (
          <span key={c} className="rounded-md border border-line px-1.5 py-0.5 text-xs text-ink">{c}</span>
        ))}
      </div>
      <p className="text-sm font-semibold text-sea">출처: 국토교통부 전월세 실거래(삼척, 2023.11~2026.11) · 건축물대장 · 직접 조사</p>
    </div>
  );
}

export default function ChatApp() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [image, setImage] = useState<{ b64: string; url: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const seq = useRef(0);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [msgs, busy]);

  async function attach(file: File) {
    setNote("");
    try {
      const p = await prepareFile(file);
      if (p.kind !== "image") throw new UploadError("캡처 사진만 올릴 수 있어요. 계약서 PDF는 '계약서 검사'에서 올려 주세요.");
      setImage({ b64: p.b64, url: p.previewUrl ?? "" });
    } catch (e) {
      setNote(e instanceof UploadError ? e.message : "사진을 준비하지 못했어요.");
    }
  }

  async function send() {
    if (busy || (!text.trim() && !image)) return;
    const userMsg: Msg = { id: ++seq.current, role: "user", text: text.trim(), image: image?.url ?? null };
    setMsgs((m) => [...m, userMsg]);
    const body = JSON.stringify({ text: text.trim(), image_b64: image?.b64 ?? null });
    setText("");
    setImage(null);
    setBusy(true);
    let reply: Reply;
    try {
      const res = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body });
      const data = await res.json();
      reply = data.ok
        ? data.kind === "listing"
          ? { kind: "listing", result: data.result, steps: data.steps ?? [], summary: data.summary ?? "" }
          : { kind: data.kind, message: data.message }
        : { kind: "error", message: data.message ?? "잠시 뒤 다시 시도해 주세요." };
    } catch {
      reply = { kind: "error", message: "연결이 끊겼어요. 잠시 뒤 다시 시도해 주세요." };
    }
    setMsgs((m) => [...m, { id: ++seq.current, role: "bot", reply }]);
    setBusy(false);
  }

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col px-4 py-6 md:h-[calc(100dvh-56px)]">
      <h1 className="text-2xl font-extrabold tracking-tight text-ink">매물 비교</h1>

      <div className="mt-4 flex-1 space-y-4 md:min-h-0 md:overflow-y-auto">
        {msgs.length === 0 && (
          <button type="button" onClick={() => setText(EXAMPLE)}
            className="rounded-lg border border-dashed border-line px-3 py-2 text-left text-sm text-muted hover:text-ink">
            예시 넣어 보기: {EXAMPLE.slice(0, 40)}…
          </button>
        )}
        {msgs.map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-ink px-4 py-3 text-[15px] text-white">
              {m.image && <img src={m.image} alt="올린 캡처" className="mb-2 max-h-48 rounded-lg" />}
              {m.text && <p className="whitespace-pre-wrap">{m.text}</p>}
            </div>
          ) : (
            <div key={m.id} className="max-w-[95%] rounded-2xl rounded-bl-sm border border-line bg-surface px-4 py-3">
              {m.reply.kind === "listing" ? (
                <div className="space-y-3">
                  {m.reply.steps.length > 0 && (
                    <ol className="space-y-1 rounded-lg bg-bg p-3 text-xs text-muted">
                      <li className="font-bold text-ink">에이전트가 한 일</li>
                      {m.reply.steps.map((s, i) => (
                        <li key={i}>
                          {i + 1}. <b className="text-ink">{s.tool}</b> · {s.detail}
                        </li>
                      ))}
                    </ol>
                  )}
                  {m.reply.summary && <p className="text-[15px] leading-relaxed text-ink">{m.reply.summary}</p>}
                  <ResultCard r={m.reply.result} />
                </div>
              ) : (
                <p className="text-[15px] text-ink">
                  {m.reply.message}{" "}
                  {m.reply.kind === "contract" && <Link href="/check" className="font-bold text-sea underline">계약서 검사로 가기</Link>}
                </p>
              )}
            </div>
          ),
        )}
        {busy && <p className="text-sm text-muted">에이전트가 건물을 찾고 건축물대장·실거래와 비교하는 중이에요(10~20초)…</p>}
        <div ref={end} />
      </div>

      <div className="mt-4 rounded-2xl border border-line bg-surface p-3">
        {image && (
          <div className="mb-2 flex items-center gap-2">
            <img src={image.url} alt="올릴 캡처" className="h-14 rounded-md" />
            <button type="button" onClick={() => setImage(null)} className="text-sm text-muted underline">빼기</button>
          </div>
        )}
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onPaste={(e) => {
            const f = Array.from(e.clipboardData.files).find((x) => x.type.startsWith("image/"));
            if (f) { e.preventDefault(); void attach(f); }
          }}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void send(); }}
          rows={3}
          placeholder="예) 후문 원룸 보증금 300 / 월 40, 관리비 7만, 6평, 2018년 준공"
          className="w-full resize-none bg-transparent text-[15px] text-ink outline-none placeholder:text-muted"
          aria-label="비교할 매물 글"
        />
        <div className="flex items-center justify-between gap-2">
          <label className="cursor-pointer rounded-full border border-line px-3 py-1.5 text-sm font-semibold text-ink">
            캡처 올리기
            <input type="file" accept="image/*" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) void attach(f); e.target.value = ""; }} />
          </label>
          <button type="button" onClick={() => void send()} disabled={busy || (!text.trim() && !image)}
            className="rounded-full bg-sea px-5 py-1.5 text-sm font-bold text-white disabled:opacity-40">
            비교하기
          </button>
        </div>
        {note && <p className="mt-2 text-sm text-[#cf5f1f]">{note}</p>}
      </div>
      <p className="mt-2 text-xs text-ink">전화번호·계좌는 AI가 옮기지 않아요. 올린 글과 사진은 저장하지 않아요.</p>
    </main>
  );
}
