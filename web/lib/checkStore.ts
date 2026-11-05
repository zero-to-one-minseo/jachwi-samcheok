// 계약서 검사 상태를 화면(컴포넌트) 밖에 둔다. 다른 탭으로 옮겨 가도 분석 요청이 계속되고, 돌아오면 결과가 남아 있다.
// 새로고침하면 사라진다(사진과 결과를 저장하지 않는다는 약속 그대로).

import { useEffect, useState, useSyncExternalStore } from "react";
import type { AnalyzeResponse, Report, ReportMeta } from "@/lib/report";
import { prepareFile, UploadError, type Prepared } from "@/lib/upload";

export const SESSION_CAP = 10;
const CAP_KEY = "jachwi_analyses";

export type CheckState =
  | { step: "idle" }
  | { step: "preparing" }
  | { step: "ready"; file: Prepared }
  | { step: "running"; file: Prepared; started: number }
  | { step: "done"; report: Report; meta: ReportMeta; photoUrl: string | null; elapsedS: number | null; seen: boolean }
  | { step: "error"; message: string; retry: Prepared | null };

let state: CheckState = { step: "idle" };
const listeners = new Set<() => void>();

function set(next: CheckState) {
  state = next;
  listeners.forEach((l) => l());
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

const IDLE: CheckState = { step: "idle" };

export function useCheckState(): CheckState {
  return useSyncExternalStore(subscribe, () => state, () => IDLE);
}

export function usedCount(): number {
  try {
    return Number(sessionStorage.getItem(CAP_KEY) || 0);
  } catch {
    return 0;
  }
}

function addUse() {
  try {
    sessionStorage.setItem(CAP_KEY, String(usedCount() + 1));
  } catch {
    // 저장이 막힌 브라우저면 세지 않는다(서버 상한이 따로 있다).
  }
}

export function markSeen() {
  if (state.step === "done" && !state.seen) set({ ...state, seen: true });
}

export async function pickFile(f: File | undefined) {
  if (!f) return;
  set({ step: "preparing" });
  try {
    set({ step: "ready", file: await prepareFile(f) });
  } catch (e) {
    set({ step: "error", message: e instanceof UploadError ? e.message : "파일을 준비하지 못했어요. 다른 파일로 해 주세요.", retry: null });
  }
}

export async function analyze(file: Prepared) {
  if (state.step === "running") return;
  if (usedCount() >= SESSION_CAP) {
    set({ step: "error", message: `이 브라우저에서 분석은 ${SESSION_CAP}회까지예요. '샘플로 해 보기'로 결과 모양을 볼 수 있어요.`, retry: null });
    return;
  }
  const started = Date.now();
  set({ step: "running", file, started });
  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_b64: file.b64, filename: file.filename }),
    });
    let data: AnalyzeResponse | null = null;
    try {
      data = (await res.json()) as AnalyzeResponse;
    } catch {
      data = null;
    }
    if (!data) {
      const msg = res.status === 413 ? "파일이 너무 커요. 계약서 쪽만 다시 찍어 올려 주세요." : "서버가 답을 주지 못했어요. 잠시 뒤 다시 해 주세요.";
      set({ step: "error", message: msg, retry: res.status === 413 ? null : file });
      return;
    }
    if (data.ok) {
      addUse();
      set({ step: "done", report: data.report, meta: data.meta, photoUrl: file.previewUrl,
        elapsedS: Math.round((Date.now() - started) / 1000), seen: false });
    } else {
      if (!["bad_file", "too_large", "too_often", "limit_reached"].includes(data.code)) addUse();
      set({ step: "error", message: data.message, retry: data.retryable ? file : null });
    }
  } catch {
    set({ step: "error", message: "인터넷 연결을 확인하고 다시 해 주세요.", retry: file });
  }
}

export async function showSample() {
  set({ step: "preparing" });
  try {
    const data = (await (await fetch("/data/sample_report.json")).json()) as AnalyzeResponse;
    if (data.ok) set({ step: "done", report: data.report, meta: data.meta, photoUrl: "/data/sample_a.jpg", elapsedS: null, seen: true });
  } catch {
    set({ step: "error", message: "샘플을 불러오지 못했어요.", retry: null });
  }
}

/** 분석 중일 때만 1초마다 다시 그려 경과 초를 돌려준다. */
export function useElapsed(s: CheckState): number {
  // 서버가 미리 그릴 때는 시각을 읽지 않는다(Next.js가 막는다). 브라우저에서 1초마다 잰다.
  const [now, setNow] = useState(0);
  const running = s.step === "running";
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [running]);
  return s.step === "running" && now > 0 ? Math.max(0, Math.floor((now - s.started) / 1000)) : 0;
}
