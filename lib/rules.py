"""AI 결과에 코드 규칙을 적용해 화면에 그릴 보고서를 만든다(설계_구현방법.md 5장 순서).

입력은 schema.AnalysisOutput과 기준 목록(번호 → Criterion)이다. 화면·세션·API를 모른다.
그래서 실제 분석과 저장본 화면이 같은 함수를 거친다.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from lib import settings
from lib.criteria import Criterion
from lib.schema import AnalysisOutput, Clause, ManagementFee

WARN = "주의"
CHECK = "확인 필요"
OK = "괜찮음"
NOTE = "참고"
GRADE_ORDER = {WARN: 0, CHECK: 1, NOTE: 2, OK: 3}

OTHER_ID = "기타"
PRINTED = "인쇄 글자"
MASK = "[개인정보]"

TAG_AI_OPINION = "AI 참고 의견"
TAG_READ_VALUE = "사진에서 읽은 값, 원본 확인"

NOTE_OTHER = "기준 목록 밖이라 확인 필요까지만 표시해요."
NOTE_QUESTION_ROW = "검증된 근거가 없는 기준이라 확인 필요까지만 표시해요."
NOTE_NO_QUOTE = "원문 인용이 없어 확인 필요로 낮췄어요."
NOTE_HANDWRITING = "손글씨이거나 흐린 글자라 괜찮음 대신 확인 필요로 뒀어요."

FALLBACK_EXPLANATION = "이 조항이 나에게 어떤 뜻인지 집주인에게 직접 확인해 보세요."
FALLBACK_QUESTION = "이 조항이 구체적으로 어떤 뜻인지 조금 더 설명해 주실 수 있을까요?"

DEFAULT_QUESTIONS = (
    "관리비에는 어떤 항목이 포함되어 있는지 알려 주실 수 있을까요?",
    "퇴실할 때 보증금은 언제, 어떤 방법으로 정산해 주시는지 알려 주실 수 있을까요?",
)

BANNER_HIDDEN = "이 문서에 AI에게 하는 말이 들어 있어요. 결과를 그대로 믿지 마세요."
BANNER_BLURRY = "사진 일부가 흐려요. 흐린 곳은 원본과 꼭 대조해 주세요."
BANNER_NOT_CONTRACT = "계약서가 아닌 것 같아요. 임대차 계약서 쪽을 올렸는지 확인해 주세요."
BANNER_NOT_INTERPRETED = "이 앱은 이 문서(등기부·확인설명서)를 해석하지 않아요. 계약서 쪽을 올려 주세요."
BANNER_JEONSE = (
    "전세·반전세 계약은 보증금이 커서 더 조심해야 해요. 괜찮음 카드는 숨겼어요. "
    "입주한 날 전입신고를 하고 확정일자를 받아 두세요. 등기부에 나보다 먼저 잡힌 근저당이 있는지도 확인하세요."
)

RETAKE_TIPS = (
    "밝은 곳에서 찍어 주세요.",
    "그림자가 지지 않게 찍어 주세요.",
    "한 번에 한 쪽씩 찍어 주세요.",
    "글자가 화면을 가득 채우게 가까이 찍어 주세요.",
)
NO_CARDS = "올린 쪽에서 기준에 맞는 조항을 찾지 못했어요. 문서 전체가 찍혔는지 확인해 주세요."

FEE_ID_DEFAULT = "관리-01"
FEE_NOT_FOUND_SUFFIX = "이 계약서에서는 항목별 금액을 찾지 못했어요."
FEE_Q_ITEMS = "관리비에 어떤 항목이 들어 있고 항목별로 얼마인지 알려 주실 수 있을까요?"
FEE_Q_USAGE = "관리비가 한 달 평균 얼마쯤 나오고 어떤 항목이 들어가는지 알려 주실 수 있을까요?"
FEE_Q_NONE = "관리비가 따로 있는지, 있다면 매달 얼마이고 어떤 항목이 들어가는지 알려 주실 수 있을까요?"
FEE_Q_INCLUDED = "관리비에 어떤 항목이 포함되어 있는지 알려 주실 수 있을까요?"
FEE_Q_BILL = "관리비 항목별로 얼마씩인지 내역을 받아 볼 수 있을까요?"
FEE_BROKER_TIP = "중개사를 끼고 계약하면 관리비 금액과 산출내역을 중개사에게 설명해 달라고 요청해 보세요."
FEE_READ_NOTE = "AI가 읽은 금액으로 코드가 판정했어요. 금액이 맞는지 원본과 꼭 대조해 주세요."

# 설계 5장 3단계. 사람이 쓴 근거 칸에는 쓰지 않고 AI가 쓴 칸(제목, 설명, 질문)에만 쓴다.
LEGAL_PATTERN = re.compile(
    r"불법|위법|무효|사기|소송|처벌|효력이\s*없|법에\s*어긋|돌려받을\s*수\s*있|안\s*지켜도\s*[되돼]|"
    r"주택\s*임대차\s*보호법|상가\s*건물\s*임대차\s*보호법|임대차\s*보호법|민법|공인중개사법|주민등록법|"
    r"민사집행법|전세사기\s*피해자\s*지원|시행령|시행규칙|"
    r"제\s*\d+\s*조"
)

_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_RRN = re.compile(r"(?<!\d)\d{6}\s?-\s?\d{7}(?!\d)")
_MOBILE = re.compile(r"(?<!\d)01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)")
_LANDLINE = re.compile(r"(?<!\d)0\d{1,2}[-.)\s]\s?\d{3,4}[-.\s]\d{4}(?!\d)")
# 날짜(2026-03-01, 8자리)는 남기고 계좌 꼴(10자리 이상)만 가린다.
_DASHED_NUMBER = re.compile(r"(?<!\d)\d{2,6}(?:-\d{1,7}){2,3}(?!\d)")
_LONG_DIGITS = re.compile(r"(?<!\d)\d{10,16}(?!\d)")
# '우리'·'하나'처럼 흔한 낱말 뒤의 금액까지 가려지지 않게, 은행을 뜻하는 낱말만 둔다.
_ACCOUNT_WORD = re.compile(
    r"((?:계좌|은행|예금주|농협|신협|수협|우체국|새마을금고|뱅크)"
    r"[^\d\n]{0,12})(\d[\d\s-]{5,}\d)"
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。])\s+")
_ID_CLEAN = re.compile(r"^[\[\(（]\s*|\s*[\]\)）]$")


@dataclass
class Evidence:
    basis: str
    limits: str
    source_name: str
    source_link: str


@dataclass
class Card:
    criterion_id: str
    title: str
    grade: str
    ai_grade: str
    quote: str
    location: str
    text_kind: str
    explanation: str
    question: str
    in_list: bool
    evidence: Evidence | None = None
    tags: list[str] = field(default_factory=list)
    grade_notes: list[str] = field(default_factory=list)
    rewritten: bool = False
    by_code: bool = False

    @property
    def grade_changed(self) -> bool:
        return self.grade != self.ai_grade


@dataclass
class FeeCard:
    criterion_id: str
    grade: str
    label: str
    summary: str
    formula: str
    amount_text: str
    source_text: str
    items: list[tuple[str, str]]
    question: str
    evidence: Evidence | None = None
    notes: list[str] = field(default_factory=list)
    by_code: bool = True


@dataclass
class Banner:
    level: str  # "warning" 또는 "info"
    text: str


@dataclass
class Report:
    doc_type: str
    contract_type: str
    read_state: str
    read_note: str
    hidden_instruction: bool
    banners: list[Banner]
    fee: FeeCard | None
    cards: list[Card]
    ok_hidden: int
    questions: list[str]
    unreadable: bool
    not_interpreted: bool
    changed_count: int
    evidence_count: tuple[int, int]
    answer_lines: list[str]

    @property
    def counts(self) -> dict[str, int]:
        counts = {WARN: 0, CHECK: 0, OK: 0}
        graded = [card.grade for card in self.cards]
        if self.fee is not None:
            graded.append(self.fee.grade)
        for grade in graded:
            if grade in counts:
                counts[grade] += 1
        return counts


# ---------- 작은 도우미 ----------


def mask_pii(text: str) -> str:
    """주민번호·전화번호·계좌 꼴 숫자를 가린다. 날짜와 금액은 남긴다(설계 5장 8단계)."""
    if not text:
        return text
    text = _RRN.sub(MASK, text)
    text = _MOBILE.sub(MASK, text)
    text = _LANDLINE.sub(MASK, text)
    def account(match: re.Match[str]) -> str:
        number = match.group(2)
        after = match.string[match.end():match.end() + 2].lstrip()
        digits = sum(ch.isdigit() for ch in number)
        if after[:1] in ("원", "만", "년", "월", "일") or (digits < 10 and "-" not in number):
            return match.group(0)
        return match.group(1) + MASK

    text = _ACCOUNT_WORD.sub(account, text)

    def dashed(match: re.Match[str]) -> str:
        digits = sum(ch.isdigit() for ch in match.group(0))
        return MASK if digits >= 10 else match.group(0)

    text = _DASHED_NUMBER.sub(dashed, text)
    text = _LONG_DIGITS.sub(MASK, text)
    return text


def has_legal_expression(text: str) -> bool:
    return bool(text) and bool(LEGAL_PATTERN.search(text))


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_SPLIT.split(text.strip()) if part.strip()]


def replace_legal_sentences(text: str, replacement: str) -> tuple[str, bool]:
    """법 표현이 든 문장을 replacement로 바꾼다. 여러 문장이 걸려도 replacement는 한 번만 넣는다."""
    if not has_legal_expression(text):
        return text, False
    out: list[str] = []
    replaced = False
    for sentence in split_sentences(text):
        if has_legal_expression(sentence):
            if not replaced:
                out.append(replacement)
                replaced = True
        else:
            out.append(sentence)
    return " ".join(out).strip(), True


def strip_contacts(text: str) -> str:
    """AI가 쓴 칸에서 링크·이메일·전화·계좌 꼴을 지운다(숨은 지시 대비, 설계 5장 4단계)."""
    if not text:
        return text
    text = _URL.sub("", text)
    text = _EMAIL.sub("", text)
    text = _RRN.sub("", text)
    text = _MOBILE.sub("", text)
    text = _LANDLINE.sub("", text)
    text = _ACCOUNT_WORD.sub(lambda m: m.group(1), text)
    text = _DASHED_NUMBER.sub(lambda m: "" if sum(c.isdigit() for c in m.group(0)) >= 10 else m.group(0), text)
    text = _LONG_DIGITS.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def first_sentences(text: str, limit: int = 2) -> str:
    parts = split_sentences(text)
    return " ".join(parts[:limit]) if parts else ""


def normalize_id(raw: str) -> str:
    return _ID_CLEAN.sub("", (raw or "").strip()).strip()


def _evidence_of(row: Criterion) -> Evidence | None:
    if not row.basis:
        return None
    return Evidence(row.basis, row.basis_limits, row.source_name, row.source_link)


def _won(value: int) -> str:
    return f"{value:,}"


# ---------- 조항 카드 ----------


def build_card(clause: Clause, by_id: Mapping[str, Criterion]) -> Card | None:
    """조항 하나에 1~5단계 규칙을 적용한다. 코드가 판정하는 줄(관리비)이면 None(관리비 카드가 맡는다)."""
    raw_id = normalize_id(clause.criterion_id)
    row = by_id.get(raw_id)
    if row is not None and not row.judged_by_ai:
        return None
    in_list = row is not None
    card = Card(
        criterion_id=raw_id if in_list else OTHER_ID,
        title=clause.title.strip(),
        grade=clause.grade,
        ai_grade=clause.grade,
        quote=clause.quote.strip(),
        location=clause.location.strip(),
        text_kind=clause.text_kind,
        explanation=clause.explanation.strip(),
        question=clause.question.strip(),
        in_list=in_list,
    )

    # 1. 근거 붙이기
    if row is not None:
        card.title = row.name or card.title
        if row.is_evidence_row:
            card.evidence = _evidence_of(row)
    else:
        card.tags.append(TAG_AI_OPINION)

    # 2. 등급 상한
    def cap(note: str) -> None:
        if card.grade != CHECK:
            card.grade = CHECK
            card.grade_notes.append(note)

    if not in_list:
        cap(NOTE_OTHER)
    elif not row.is_evidence_row:
        cap(NOTE_QUESTION_ROW)
    if card.grade in (WARN, OK) and not card.quote:
        cap(NOTE_NO_QUOTE)
    if card.grade == OK and card.text_kind != PRINTED:
        cap(NOTE_HANDWRITING)

    # 3. 법 표현 문장 바꾸기(등급은 그대로)
    explanation_fallback = (row.plain_explanation if row else "") or FALLBACK_EXPLANATION
    question_fallback = (row.default_question if row else "") or FALLBACK_QUESTION
    title_fallback = (row.name if row else "") or "확인할 조항"
    card.title, changed_title = replace_legal_sentences(card.title, title_fallback)
    card.explanation, changed_expl = replace_legal_sentences(card.explanation, explanation_fallback)
    card.question, changed_q = replace_legal_sentences(card.question, question_fallback)
    card.rewritten = changed_title or changed_expl or changed_q

    # 4. 숨은 지시 대비: AI가 쓴 칸의 링크·연락처 지우기
    card.title = strip_contacts(card.title) or title_fallback
    card.explanation = strip_contacts(card.explanation)
    card.question = strip_contacts(card.question)

    # 5. 손글씨·흐린 글자에서 읽은 숫자
    if card.text_kind != PRINTED and re.search(r"\d", card.quote):
        card.tags.append(TAG_READ_VALUE)
        if re.search(r"\d", card.question):
            card.question = question_fallback

    card.explanation = first_sentences(card.explanation) or explanation_fallback
    if card.grade in (WARN, CHECK) and not card.question:
        card.question = question_fallback
    if card.grade == OK:
        card.question = ""
    return card


# ---------- 관리비 ----------


def _find_fee_row(by_id: Mapping[str, Criterion]) -> Criterion | None:
    row = by_id.get(FEE_ID_DEFAULT)
    if row is not None:
        return row
    for candidate in by_id.values():
        if not candidate.judged_by_ai and candidate.category == "관리비":
            return candidate
    return None


def _billing_label(fee: ManagementFee) -> str:
    if fee.billing == "정액" and "정액" not in f"{fee.amount_text} {fee.source_text}":
        return "정액으로 보임"
    return fee.billing


def judge_fee(fee: ManagementFee, doc_type: str, by_id: Mapping[str, Criterion]) -> FeeCard | None:
    """관리비 규칙표(설계 6장 기능 4). 금액 판정은 언급 여부가 '금액 있음'일 때만 한다."""
    if doc_type not in ("계약서", "관리비 내역"):
        return None
    row = _find_fee_row(by_id)
    fee_id = row.id if row is not None else FEE_ID_DEFAULT
    items = [(item.name.strip(), item.amount_text.strip()) for item in fee.items if item.name.strip()]
    won = fee.monthly_won if fee.mention == "금액 있음" else 0
    has_amount = won > 0
    itemized_label = f"항목별 금액 {fee.itemized}"

    def card(grade: str, label: str, summary: str, formula: str = "", question: str = "",
             evidence: Evidence | None = None, notes: list[str] | None = None) -> FeeCard:
        return FeeCard(
            criterion_id=fee_id,
            grade=grade,
            label=label,
            summary=summary,
            formula=formula,
            amount_text=fee.amount_text.strip(),
            source_text=fee.source_text.strip(),
            items=items,
            question=question,
            evidence=evidence,
            notes=notes or [],
        )

    read_notes = [FEE_READ_NOTE] if has_amount else []

    if doc_type == "관리비 내역":
        # 고지서 표시 방법을 정한 근거는 검증하지 못해 10만 원 규칙과 근거를 쓰지 않는다.
        if fee.itemized == "없음" or not has_amount:
            return card(CHECK, "관리인에게 내역을 요청해 보세요", "올린 고지서에서 항목별 금액을 찾지 못했어요.",
                        question=FEE_Q_BILL)
        return card(NOTE, "관리비 내역", f"관리비 월 {_won(won)}원 · {itemized_label}", notes=read_notes)

    if fee.mention == "언급 없음":
        return card(CHECK, "관리비 칸 직접 확인", "올린 쪽에서 관리비를 찾지 못했어요.", question=FEE_Q_NONE,
                    notes=[FEE_BROKER_TIP])
    if not has_amount:
        return card(CHECK, "관리비 칸 직접 확인", "관리비 금액을 읽지 못했어요. 원본에서 직접 확인해 주세요.",
                    question=FEE_Q_NONE, notes=[FEE_BROKER_TIP])

    summary = f"관리비 월 {_won(won)}원 · {_billing_label(fee)} · {itemized_label}"
    threshold = settings.FEE_THRESHOLD_WON
    suspicious = settings.FEE_SUSPICIOUS_WON
    notes = read_notes + [FEE_BROKER_TIP]

    if won > suspicious:
        return card(CHECK, "월세나 보증금을 잘못 읽었을 수 있음", summary, f"{_won(won)} > {_won(suspicious)}",
                    notes=[FEE_READ_NOTE])
    if fee.billing in ("사용량", "섞임"):
        return card(CHECK, "월 평균 금액과 포함 항목 물어보기", summary, question=FEE_Q_USAGE, notes=notes)
    if won < threshold:
        return card(NOTE, "포함 항목 확인", summary, f"{_won(won)} < {_won(threshold)}", question=FEE_Q_INCLUDED,
                    notes=notes)

    formula = f"{_won(won)} ≥ {_won(threshold)}"
    question = (row.default_question if row else "") or FEE_Q_ITEMS
    evidence = _evidence_of(row) if row is not None else None
    if fee.billing == "알 수 없음":
        return card(CHECK, "부과 방식과 항목별 금액 확인", summary, formula, question, evidence, notes)
    if fee.itemized == "없음":
        if evidence is not None:
            evidence = Evidence(f"{evidence.basis} {FEE_NOT_FOUND_SUFFIX}".strip(), evidence.limits,
                                evidence.source_name, evidence.source_link)
        return card(CHECK, "항목별 금액을 찾지 못함", summary, formula, question, evidence, notes)
    if fee.itemized == "일부":
        return card(CHECK, "항목별 금액 확인", summary, formula, question, evidence, notes)
    if not (fee.source_text.strip() or fee.amount_text.strip()) or not any(
        item.amount_text.strip() for item in fee.items
    ):
        # 원문과 항목별 금액 없이는 초록이 없다(설계 8장).
        return card(CHECK, "항목별 금액 원문 확인", summary, formula, question, evidence, notes)
    return card(OK, "항목별 금액이 적혀 있어요", summary, formula, evidence=evidence, notes=notes)


# ---------- 질문 ----------


def build_questions(cards: list[Card], fee: FeeCard | None, limit: int | None = None) -> list[str]:
    """주의 질문을 앞에, 같은 기준 번호는 하나만, 최대 limit개. 0개면 기본 질문 2개."""
    limit = settings.MAX_QUESTIONS if limit is None else limit
    ordered: list[tuple[str, str]] = []
    ordered += [(c.criterion_id, c.question) for c in cards if c.grade == WARN]
    if fee is not None and fee.grade == CHECK:
        ordered.append((fee.criterion_id, fee.question))
    ordered += [(c.criterion_id, c.question) for c in cards if c.grade == CHECK]
    if fee is not None and fee.grade == NOTE:
        ordered.append((fee.criterion_id, fee.question))

    questions: list[str] = []
    seen_ids: set[str] = set()
    seen_text: set[str] = set()
    for crit_id, text in ordered:
        text = text.strip()
        if not text or text in seen_text:
            continue
        if crit_id != OTHER_ID and crit_id in seen_ids:
            continue
        seen_ids.add(crit_id)
        seen_text.add(text)
        questions.append(text)
        if len(questions) >= limit:
            break
    return questions or list(DEFAULT_QUESTIONS)


# ---------- 전체 ----------


def _mask_card(card: Card) -> None:
    card.title = mask_pii(card.title)
    card.quote = mask_pii(card.quote)
    card.location = mask_pii(card.location)
    card.explanation = mask_pii(card.explanation)
    card.question = mask_pii(card.question)


def _mask_fee(fee: FeeCard) -> None:
    fee.amount_text = mask_pii(fee.amount_text)
    fee.source_text = mask_pii(fee.source_text)
    fee.items = [(mask_pii(name), mask_pii(amount)) for name, amount in fee.items]


def apply_rules(output: AnalysisOutput, by_id: Mapping[str, Criterion]) -> Report:
    banners: list[Banner] = []
    hidden = output.hidden_instruction == "있음"
    if hidden:
        banners.append(Banner("warning", BANNER_HIDDEN))
    if output.read_state == "일부 흐림":
        banners.append(Banner("warning", BANNER_BLURRY))

    unreadable = output.read_state == "읽기 어려움"
    not_interpreted = output.doc_type in ("등기부", "확인설명서")
    if not_interpreted:
        banners.append(Banner("info", BANNER_NOT_INTERPRETED))
    elif output.doc_type == "기타":
        banners.append(Banner("info", BANNER_NOT_CONTRACT))

    cards: list[Card] = []
    fee: FeeCard | None = None
    if not (unreadable or not_interpreted):
        for clause in output.clauses:
            card = build_card(clause, by_id)
            if card is not None:
                cards.append(card)
        fee = judge_fee(output.management_fee, output.doc_type, by_id)

    jeonse = output.contract_type in ("전세", "반전세")
    if jeonse and not (unreadable or not_interpreted):
        banners.append(Banner("info", BANNER_JEONSE))

    cards.sort(key=lambda c: GRADE_ORDER.get(c.grade, 9))
    ok_cards = [c for c in cards if c.grade == OK]
    shown_ok = [] if jeonse else ok_cards[: settings.MAX_OK_CARDS]
    ok_hidden = len(ok_cards) - len(shown_ok)
    shown = [c for c in cards if c.grade != OK] + shown_ok

    questions = [] if (unreadable or not_interpreted) else build_questions(shown, fee)

    # 8. 개인정보 가리기는 화면에 내보내기 직전, 모든 판정이 끝난 뒤에 한다.
    for card in shown:
        _mask_card(card)
    if fee is not None:
        _mask_fee(fee)
    questions = [mask_pii(q) for q in questions]
    read_note = mask_pii(output.read_note.strip())

    answer_lines = [f"{c.criterion_id}:{c.grade}" for c in shown]
    if fee is not None:
        answer_lines.insert(0, f"{fee.criterion_id}:{fee.grade}")

    with_evidence = sum(1 for c in shown if c.evidence is not None) + (1 if fee and fee.evidence else 0)
    total = len(shown) + (1 if fee else 0)
    return Report(
        doc_type=output.doc_type,
        contract_type=output.contract_type,
        read_state=output.read_state,
        read_note=read_note,
        hidden_instruction=hidden,
        banners=banners,
        fee=fee,
        cards=shown,
        ok_hidden=ok_hidden,
        questions=questions,
        unreadable=unreadable,
        not_interpreted=not_interpreted,
        changed_count=sum(1 for c in shown if c.grade_changed),
        evidence_count=(with_evidence, total),
        answer_lines=answer_lines,
    )
