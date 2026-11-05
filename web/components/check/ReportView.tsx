"use client";

import { useState } from "react";
import type { Card, Evidence, FeeCard, Report, ReportMeta } from "@/lib/report";

const GRADE_STYLE: Record<string, string> = {
  주의: "bg-pricey text-white",
  "확인 필요": "bg-[#f3c34a] text-ink",
  괜찮음: "bg-cheap text-white",
  참고: "bg-line text-ink",
};
const GRADE_MEANINGS: [string, string][] = [
  ["주의", "학생에게 불리할 수 있는 내용이 적혀 있어요. 원문 인용이 있고, 검증된 근거가 있는 기준에서만 나와요."],
  ["확인 필요", "있어야 할 내용이 보이지 않거나, 애매하거나, 흐리거나, 근거가 없는 기준이에요."],
  ["괜찮음", "기준 목록의 '괜찮은 모습'대로 적혀 있어요. 기준에 걸리는 것이 없다는 뜻이지 안전 보증이 아니에요."],
];
const NOT_CHECKED = [
  "입주한 날 전입신고를 하고 확정일자를 받아 두세요. 등기부에 나보다 먼저 잡힌 근저당이 있는지도 확인하세요.",
  "집주인은 계약할 때 이 집의 확정일자·보증금 정보와 납세증명서를 보여 줘야 해요. 보증금이 1천만 원을 넘으면 계약 뒤 입주일 전까지 집주인 동의 없이도 밀린 세금 열람을 신청할 수 있어요.",
  '계약서에 "전입신고 금지" 같은 문구가 있으면 서명 전에 멈추고 상담 창구에 먼저 물어보세요.',
];
const GREETING = "안녕하세요. 계약하기 전에 몇 가지 여쭤보고 싶어요.";
const RETAKE_TIPS = [
  "밝은 곳에서 찍어 주세요.",
  "그림자가 지지 않게 찍어 주세요.",
  "한 번에 한 쪽씩 찍어 주세요.",
  "글자가 화면을 가득 채우게 가까이 찍어 주세요.",
];
const LINK = /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g;

function Badge({ grade }: { grade: string }) {
  return <span className={`rounded-md px-2 py-0.5 text-xs font-bold ${GRADE_STYLE[grade] ?? "bg-line text-ink"}`}>{grade}</span>;
}

function Tag({ children, tone = "plain" }: { children: React.ReactNode; tone?: "plain" | "violet" | "orange" }) {
  const c = tone === "violet" ? "bg-[#ece6fb] text-[#5b3fb0]" : tone === "orange" ? "bg-pricey-soft text-pricey" : "bg-bg text-muted";
  return <span className={`rounded-md px-2 py-0.5 text-xs font-semibold ${c}`}>{children}</span>;
}

function Sources({ name, link }: { name: string; link: string }) {
  const pairs = [...name.matchAll(LINK)];
  if (pairs.length) {
    return (
      <>
        {pairs.map((m, i) => (
          <span key={m[2]}>
            {i > 0 && " · "}
            <a href={m[2]} target="_blank" rel="noreferrer" className="text-sea underline underline-offset-2">{m[1]}</a>
          </span>
        ))}
      </>
    );
  }
  const label = name.replace(/https?:\/\/\S+/g, "").replace(/^[\s·]+|[\s·]+$/g, "") || "출처";
  return link ? <a href={link} target="_blank" rel="noreferrer" className="text-sea underline underline-offset-2">{label}</a> : <>{name}</>;
}

function EvidenceBody({ evidence, byCode }: { evidence: Evidence | null; byCode: boolean }) {
  if (!evidence) {
    return <p className="text-sm text-muted">{byCode ? "근거 없이 코드 규칙으로만 표시했어요." : "이 카드에는 검증된 근거가 붙어 있지 않아요. 집주인에게 직접 확인해 보세요."}</p>;
  }
  return (
    <div className="space-y-2 text-sm leading-relaxed">
      <p>{evidence.basis}</p>
      {evidence.limits && <p><b>이 근거가 말하지 않는 것:</b> {evidence.limits}</p>}
      {(evidence.source_name || evidence.source_link) && (
        <p><b>출처:</b> <Sources name={evidence.source_name} link={evidence.source_link} /></p>
      )}
    </div>
  );
}

function Quote({ text }: { text: string }) {
  return <blockquote className="whitespace-pre-wrap rounded-lg border-l-4 border-line-strong bg-bg px-3 py-2 text-[15px] leading-relaxed">{text}</blockquote>;
}

function CardView({ card, open = false }: { card: Card; open?: boolean }) {
  return (
    <article className="rounded-xl border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge grade={card.grade} />
        {card.tags.includes("AI 참고 의견") && <Tag>AI 참고 의견</Tag>}
        {card.text_kind !== "인쇄 글자" && <Tag tone="violet">{card.text_kind}</Tag>}
        {card.tags.includes("사진에서 읽은 값, 원본 확인") && <Tag tone="orange">사진에서 읽은 값, 원본 확인</Tag>}
      </div>
      <h3 className="mt-2 text-[17px] font-bold">{card.title}</h3>
      <div className="mt-2 space-y-2">
        {card.quote ? (
          <>
            <p className="text-xs text-muted">원문 그대로{card.location && ` · 위치: ${card.location}`}</p>
            <Quote text={card.quote} />
          </>
        ) : (
          <p className="text-xs text-muted">원문 인용 없음 · 올린 쪽에서 찾지 못했어요</p>
        )}
        <p className="text-[15px] leading-relaxed">{card.explanation}</p>
        {card.grade_notes.map((n) => <p key={n} className="text-xs text-muted">{n}</p>)}
        <p className="text-xs text-muted">
          {card.by_code ? "코드 규칙으로 표시" : "AI가 읽고 판단"}
          {card.rewritten && " · 법 표현이 있어 코드가 문장을 바꿨어요"}
        </p>
      </div>
      <details className="group mt-3 border-t border-line pt-3" open={open}>
        <summary className="cursor-pointer text-sm font-semibold text-sea">근거 보기</summary>
        <div className="mt-2"><EvidenceBody evidence={card.evidence} byCode={card.by_code} /></div>
      </details>
    </article>
  );
}

function FeeView({ fee }: { fee: FeeCard }) {
  return (
    <article className="rounded-xl border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge grade={fee.grade} />
        <Tag>코드 규칙으로 표시</Tag>
      </div>
      <h3 className="mt-2 text-[17px] font-bold">관리비 · {fee.label}</h3>
      <p className="mt-1 text-[15px]">{fee.summary}</p>
      {fee.formula && <p className="tabular mt-2 inline-block rounded-md bg-bg px-2 py-1 text-sm font-semibold">계산식 {fee.formula}</p>}
      {fee.items.length > 0 && (
        <table className="mt-3 w-full text-sm">
          <thead><tr className="text-left text-xs text-muted"><th className="pb-1 font-semibold">AI가 읽은 항목</th><th className="pb-1 font-semibold">금액</th></tr></thead>
          <tbody>{fee.items.map(([n, a]) => <tr key={n} className="border-t border-line"><td className="py-1">{n}</td><td className="py-1">{a || "금액 없음"}</td></tr>)}</tbody>
        </table>
      )}
      {(fee.source_text || fee.amount_text) && (
        <div className="mt-3 space-y-1"><p className="text-xs text-muted">AI가 읽은 원문</p><Quote text={fee.source_text || fee.amount_text} /></div>
      )}
      {fee.notes.map((n) => <p key={n} className="mt-1 text-xs text-muted">{n}</p>)}
      <details className="mt-3 border-t border-line pt-3">
        <summary className="cursor-pointer text-sm font-semibold text-sea">근거 보기</summary>
        <div className="mt-2"><EvidenceBody evidence={fee.evidence} byCode /></div>
      </details>
    </article>
  );
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          setTimeout(() => setDone(false), 1500);
        } catch {
          setDone(false);
        }
      }}
      className="shrink-0 rounded-lg border border-line-strong px-3 py-1.5 text-sm font-semibold hover:border-ink"
    >
      {done ? "복사했어요" : label}
    </button>
  );
}

function Questions({ questions }: { questions: string[] }) {
  const all = [GREETING, "", ...questions.map((q, i) => `${i + 1}. ${q}`)].join("\n");
  return (
    <section className="rounded-xl border border-sea/30 bg-sea-soft p-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-extrabold">집주인에게 이렇게 물어보세요</h2>
        <CopyButton text={all} label="전체 복사" />
      </div>
      <p className="mt-1 text-sm">{GREETING}</p>
      <ol className="mt-3 space-y-2">
        {questions.map((q, i) => (
          <li key={q} className="flex items-start gap-3 rounded-lg bg-surface p-3">
            <span className="tabular mt-0.5 text-sm font-bold text-sea">{i + 1}</span>
            <p className="flex-1 text-[15px] leading-relaxed">{q}</p>
            <CopyButton text={q} label="복사" />
          </li>
        ))}
      </ol>
      <p className="mt-3 text-xs text-muted">보내기는 직접 하세요. 집주인의 답은 문자 등 기록으로 받아 두세요.</p>
    </section>
  );
}

export function footerText(meta: ReportMeta) {
  const bits = [`답한 모델 ${meta.model}`, `effort ${meta.effort}`];
  if (meta.source === "live") bits.push(`걸린 시간 ${meta.elapsed_s.toFixed(1)}초`);
  bits.push(`기준 목록 ${meta.criteria_count}개(버전 ${meta.criteria_version || "알 수 없음"})`);
  return bits.join(" · ");
}

export default function ReportView({ report, meta, photoUrl }: { report: Report; meta: ReportMeta; photoUrl: string | null }) {
  const main = report.cards.filter((c) => c.grade !== "괜찮음");
  const ok = report.cards.filter((c) => c.grade === "괜찮음");
  const c = report.counts;
  return (
    <div className="space-y-5">
      {report.banners.map((b) => (
        <p key={b.text} className={`rounded-lg px-4 py-3 text-sm font-semibold ${b.level === "warning" ? "bg-[#fff4d6] text-[#7a5600]" : "bg-sea-soft text-sea"}`}>{b.text}</p>
      ))}
      {report.read_state === "일부 흐림" && report.read_note && <p className="text-xs text-muted">흐린 곳: {report.read_note}</p>}

      {report.unreadable ? (
        <section className="rounded-xl border border-line bg-surface p-4">
          <h2 className="font-bold">글자를 읽기 어려워요. 이렇게 다시 찍어 주세요.</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{RETAKE_TIPS.map((t) => <li key={t}>{t}</li>)}</ul>
        </section>
      ) : !report.not_interpreted && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <span className="tabular rounded-lg bg-pricey px-3 py-1.5 text-sm font-bold text-white">주의 {c["주의"]}</span>
            <span className="tabular rounded-lg bg-[#f3c34a] px-3 py-1.5 text-sm font-bold">확인 필요 {c["확인 필요"]}</span>
            <span className="tabular rounded-lg bg-cheap px-3 py-1.5 text-sm font-bold text-white">괜찮음 {c["괜찮음"]}</span>
            <span className="text-xs text-muted">괜찮음 = 안전 보증 아님</span>
          </div>
          <details className="rounded-lg bg-surface px-4 py-3 text-sm">
            <summary className="cursor-pointer font-semibold">등급 뜻</summary>
            <dl className="mt-2 space-y-1.5">{GRADE_MEANINGS.map(([g, m]) => <div key={g}><dt className="inline font-bold">{g}: </dt><dd className="inline">{m}</dd></div>)}</dl>
          </details>

          <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
            <div className="lg:sticky lg:top-20 lg:self-start">
              {photoUrl ? (
                <figure>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={photoUrl} alt="올린 계약서 사진(원문 대조용)" className="w-full rounded-xl border border-line" />
                  <figcaption className="mt-1 text-xs text-muted">AI가 읽은 사진. 카드의 원문과 대조해 보세요.</figcaption>
                </figure>
              ) : (
                <p className="rounded-xl border border-dashed border-line-strong p-4 text-sm text-muted">
                  {meta.kind === "pdf" ? "원본 PDF를 내 기기에서 열어 대조해 주세요." : "대조할 사진이 없어요."}
                </p>
              )}
            </div>
            <div className="space-y-3">
              {report.fee && <FeeView fee={report.fee} />}
              {!report.cards.length && !report.fee && <p className="text-sm text-muted">올린 쪽에서 기준에 맞는 조항을 찾지 못했어요. 문서 전체가 찍혔는지 확인해 주세요.</p>}
              {main.map((card) => <CardView key={card.criterion_id + card.title} card={card} />)}
              {ok.length > 0 && (
                <details className="rounded-xl border border-line bg-surface p-4">
                  <summary className="cursor-pointer text-sm font-semibold">괜찮음 {ok.length}개 · 안전 보증 아님</summary>
                  <div className="mt-3 space-y-3">{ok.map((card) => <CardView key={card.criterion_id + card.title} card={card} />)}</div>
                </details>
              )}
              {report.ok_hidden > 0 && <p className="text-xs text-muted">괜찮음 {report.ok_hidden}개는 화면에 다 싣지 않았어요.</p>}
            </div>
          </div>
          {report.questions.length > 0 && <Questions questions={report.questions} />}
        </>
      )}

      <section className="rounded-xl border border-line bg-surface p-4">
        <h2 className="font-bold">이 앱이 확인하지 않는 것</h2>
        <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm leading-relaxed">{NOT_CHECKED.map((t) => <li key={t}>{t}</li>)}</ul>
      </section>

      {!report.unreadable && !report.not_interpreted && (
        <details className="rounded-lg bg-surface px-4 py-3 text-sm">
          <summary className="cursor-pointer font-semibold">어떻게 판단했나</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li>근거가 기준 목록에서 붙은 카드 {report.evidence_count[0]}/{report.evidence_count[1]}</li>
            <li>규칙 때문에 등급이 바뀐 카드 {report.changed_count}개</li>
            {report.fee?.formula && <li>관리비 계산식 {report.fee.formula}</li>}
            <li>AI는 조항을 읽고 기준을 고르기까지만 하고, 등급 상한·근거·관리비 판정은 코드가 해요.</li>
          </ul>
        </details>
      )}
      <p className="text-xs text-muted">{footerText(meta)}</p>
    </div>
  );
}
