// /api/analyze 응답과 public/data/sample_report.json 의 타입.
// api/_engine/rules.py 의 dataclass(Report, Card, FeeCard, Banner, Evidence)를 dataclasses.asdict로 바꾼 모양이다.
// 칸 이름을 바꾸면 api/analyze.py, api/_test_engine.py 도 함께 바꾼다(시험이 이 파일과 JSON을 대조한다).

export type CardGrade = "주의" | "확인 필요" | "괜찮음";
export type FeeGrade = "확인 필요" | "참고" | "괜찮음";
export type DocType = "계약서" | "관리비 내역" | "등기부" | "확인설명서" | "기타";
export type ContractType = "월세" | "전세" | "반전세" | "연세" | "선세" | "알 수 없음";
export type ReadState = "잘 읽힘" | "일부 흐림" | "읽기 어려움";
export type TextKind = "인쇄 글자" | "손글씨" | "흐려서 불확실";

export interface Evidence {
  basis: string;
  limits: string;
  source_name: string;
  source_link: string;
}

export interface Card {
  criterion_id: string;
  title: string;
  grade: CardGrade;
  ai_grade: CardGrade;
  quote: string;
  location: string;
  text_kind: TextKind;
  explanation: string;
  question: string;
  in_list: boolean;
  evidence: Evidence | null;
  tags: string[];
  grade_notes: string[];
  rewritten: boolean;
  by_code: boolean;
  grade_changed: boolean;
}

export interface FeeCard {
  criterion_id: string;
  grade: FeeGrade;
  label: string;
  summary: string;
  formula: string;
  amount_text: string;
  source_text: string;
  /** [항목 이름, 금액 글자] */
  items: [string, string][];
  question: string;
  evidence: Evidence | null;
  notes: string[];
  by_code: boolean;
}

export interface Banner {
  level: "warning" | "info";
  text: string;
}

export interface GradeCounts {
  주의: number;
  "확인 필요": number;
  괜찮음: number;
}

export interface Report {
  doc_type: DocType;
  contract_type: ContractType;
  read_state: ReadState;
  read_note: string;
  hidden_instruction: boolean;
  banners: Banner[];
  fee: FeeCard | null;
  cards: Card[];
  ok_hidden: number;
  questions: string[];
  unreadable: boolean;
  not_interpreted: boolean;
  changed_count: number;
  /** [근거가 붙은 카드 수, 전체 카드 수(관리비 포함)] */
  evidence_count: [number, number];
  answer_lines: string[];
  counts: GradeCounts;
}

export interface ReportMeta {
  model: string;
  effort: string;
  elapsed_s: number;
  criteria_version: string;
  criteria_count: number;
  kind: "image" | "pdf";
  source: "live" | "saved";
  /** source가 "saved"(저장본)일 때만 */
  label?: string;
  saved_at?: string;
  fake?: boolean;
}

export type AnalyzeErrorCode =
  | "bad_request"
  | "bad_file"
  | "too_large"
  | "no_key"
  | "refused"
  | "truncated"
  | "invalid"
  | "timeout"
  | "network"
  | "server_error"
  | "rate_limited"
  | "limit_reached"
  | "credit"
  | "auth"
  | "api_error"
  | "internal_error"
  | "method_not_allowed";

export interface AnalyzeRequest {
  file_b64: string;
  filename: string;
}

export interface AnalyzeSuccess {
  ok: true;
  report: Report;
  meta: ReportMeta;
}

export interface AnalyzeError {
  ok: false;
  code: AnalyzeErrorCode;
  /** 화면에 그대로 띄울 한국어 한 문장 */
  message: string;
  /** '다시 시도' 단추를 보여 줄지 */
  retryable: boolean;
}

export type AnalyzeResponse = AnalyzeSuccess | AnalyzeError;

export interface AnalyzeReady {
  ok: true;
  status: "ready";
}

/** api/analyze.py MAX_BODY_BYTES 와 같은 값(JSON 본문 전체 기준). */
export const ANALYZE_MAX_BODY_BYTES = 14 * 1024 * 1024;
