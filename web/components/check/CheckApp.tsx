"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";
import ReportView from "./ReportView";
import type { Room } from "@/lib/rooms";
import { analyze, markSeen, pickFile, SESSION_CAP, showSample, useCheckState, useElapsed, usedCount } from "@/lib/checkStore";

export default function CheckApp({ rooms }: { rooms: Room[] }) {
  const params = useSearchParams();
  const room = rooms.find((r) => r.id === params.get("room")) ?? null;
  const state = useCheckState();
  const elapsed = useElapsed(state);
  const used = typeof window === "undefined" ? 0 : usedCount();
  const result = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (state.step === "done" || state.step === "error") result.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    if (state.step === "done") markSeen();
  }, [state.step]);

  const busy = state.step === "running" || state.step === "preparing";
  const file = state.step === "ready" || state.step === "running" ? state.file : null;

  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-6 md:px-6 md:py-10">
      {room && (
        <div className="mb-5 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-line bg-surface px-4 py-3 text-sm">
          <span className="font-bold text-sea">점검 중인 방</span>
          <span className="font-semibold">{room.name}</span>
          <span className="tabular text-muted">{room.headline} · {room.area} · {room.contractType}</span>
          <Link href="/" className="ml-auto text-muted underline underline-offset-2 hover:text-ink">지도로</Link>
        </div>
      )}

      <h1 className="text-[28px] font-extrabold tracking-[-0.02em] md:text-[34px]">계약서 검사</h1>

      <section className="mt-6 rounded-2xl border border-line bg-surface p-5 md:p-6">
        <label
          className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors ${
            file ? "border-sea bg-sea-soft" : "border-line-strong hover:border-sea"
          } ${busy ? "pointer-events-none opacity-60" : ""}`}
        >
          <input type="file" accept="image/*,application/pdf,.pdf,.heic,.heif" className="sr-only" disabled={busy}
            onChange={(e) => { pickFile(e.target.files?.[0]); e.target.value = ""; }} />
          {file ? (
            <>
              {file.previewUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={file.previewUrl} alt="올릴 계약서 미리보기" className="max-h-56 rounded-lg border border-line" />
              ) : (
                <span className="text-base font-bold">PDF · {file.filename}</span>
              )}
              <span className="text-sm text-muted">다른 파일을 고르려면 다시 누르세요</span>
            </>
          ) : (
            <>
              <span className="text-[17px] font-bold">계약서 사진이나 PDF 올리기</span>
              <span className="text-sm text-ink">사진 1장 또는 PDF 1개(3MB까지)</span>
            </>
          )}
        </label>

        <p className="mt-4 rounded-lg bg-[#fff4d6] px-3 py-2 text-sm font-semibold text-[#7a5600]">
          주민번호·연락처·계좌는 가리고 올려 주세요. 법률 자문이 아닌 확인 체크리스트예요.
        </p>
        <p className="mt-2 text-xs leading-relaxed text-ink">
          사진은 분석을 위해 Anthropic API로 보내요. 이 앱은 사진과 결과를 저장하지 않아요. Anthropic은 받은 내용을 AI 학습에 쓰지 않고 30일 안에 지워요. 단, 안전
          점검에 걸리면 최대 2년, 법에 따라 필요하면 더 오래 보관될 수 있어요.
        </p>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled={!file || busy}
            onClick={() => file && analyze(file)}
            className="rounded-xl bg-sea px-6 py-3 text-[15px] font-bold text-white transition-colors hover:bg-[#0b6a73] disabled:cursor-not-allowed disabled:bg-line-strong"
          >
            {state.step === "running" ? `읽는 중 ${elapsed}초` : "확인하기"}
          </button>
          <button type="button" disabled={busy} onClick={showSample}
            className="rounded-xl border border-line-strong px-5 py-3 text-[15px] font-semibold hover:border-ink disabled:opacity-50">
            샘플로 해 보기
          </button>
          <span suppressHydrationWarning className="text-xs text-muted">이 브라우저에서 남은 분석 {Math.max(0, SESSION_CAP - used)}회</span>
        </div>
        {state.step === "running" && (
          <p className="tabular mt-3 text-[15px] font-bold text-sea" aria-live="polite">
            ⏱ 분석 중 {elapsed}초 · 다른 탭으로 가도 계속 돌아가요
          </p>
        )}
        {state.step === "done" && state.elapsedS != null && (
          <p className="tabular mt-3 text-[15px] font-bold text-sea">⏱ 결과까지 {state.elapsedS}초</p>
        )}
      </section>

      <div ref={result} className="mt-8 scroll-mt-20">
        {state.step === "error" && (
          <div role="alert" className="rounded-xl border border-pricey/30 bg-pricey-soft px-4 py-3">
            <p className="text-[15px] font-semibold text-ink">{state.message}</p>
            {state.retry && (
              <button type="button" onClick={() => state.retry && analyze(state.retry)} className="mt-2 text-sm font-bold text-pricey underline underline-offset-2">
                다시 시도
              </button>
            )}
          </div>
        )}
        {state.step === "done" && (
          <>
            {state.meta.source === "saved" && (
              <p className="mb-4 rounded-lg bg-bg px-3 py-2 text-sm text-muted">가상 샘플 계약서로 만든 결과예요. 실제 분석이 아니에요.</p>
            )}
            <ReportView report={state.report} meta={state.meta} photoUrl={state.photoUrl} />
          </>
        )}
      </div>
    </main>
  );
}
