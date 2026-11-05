"""계약서 점검 결과 그리기. 실제 분석과 저장본 화면이 같은 함수를 쓴다.

- 원문 인용은 마크다운을 해석하지 않는 st.code(language=None, wrap_lines=True)로 보인다.
- AI 설명과 사람이 쓴 근거 문장을 마크다운으로 그릴 때는 escape_md를 거친다
  ('1~2개월'의 물결표가 취소선이 되는 것 등, 기술_확인.md 4장).
"""

import re
from dataclasses import dataclass

import streamlit as st

from lib import rules
from lib.rules import CHECK, NOTE, OK, WARN, Card, FeeCard, Report

BADGE_COLORS = {WARN: "red", CHECK: "yellow", OK: "green", NOTE: "gray"}

DISCLAIMER = "법률 자문이 아닌 확인 체크리스트예요."
OK_NOT_SAFE = "괜찮음 = 안전 보증 아님"
GRADE_MEANINGS = (
    ("주의", "학생에게 불리할 수 있는 내용이 적혀 있어요. 원문 인용이 있고, 검증된 근거가 있는 기준에서만 나와요."),
    ("확인 필요", "있어야 할 내용이 보이지 않거나, 애매하거나, 흐리거나, 근거가 없는 기준이에요."),
    ("괜찮음", "기준 목록의 '괜찮은 모습'대로 적혀 있어요. 기준에 걸리는 것이 없다는 뜻이지 안전 보증이 아니에요."),
)
NOT_CHECKED_TITLE = "이 앱이 확인하지 않는 것"
NOT_CHECKED = (
    "입주한 날 전입신고를 하고 확정일자를 받아 두세요. 등기부에 나보다 먼저 잡힌 근저당이 있는지도 확인하세요.",
    "집주인은 계약할 때 이 집의 확정일자·보증금 정보와 납세증명서를 보여 줘야 해요. "
    "보증금이 1천만 원을 넘으면 계약 뒤 입주일 전까지 집주인 동의 없이도 밀린 세금 열람을 신청할 수 있어요.",
    "계약서에 \"전입신고 금지\" 같은 문구가 있으면 서명 전에 멈추고 상담 창구에 먼저 물어보세요.",
)
QUESTION_GREETING = "안녕하세요. 계약하기 전에 몇 가지 여쭤보고 싶어요."
COPY_HINT = "휴대폰에서는 상자를 길게 눌러 복사하세요."
SEND_YOURSELF = "보내기는 직접 하세요. 집주인의 답은 문자 등 기록으로 받아 두세요."
BY_AI = "AI가 읽고 판단"
BY_CODE = "코드 규칙으로 표시"
PDF_COMPARE = "원본 PDF를 내 기기에서 열어 대조해 주세요."

_MD_SPECIAL = re.compile(r"([\\`*_~$\[\]#<>|])")
_BULLET_MARKER = re.compile(r"^(\s*)([-+])", re.MULTILINE)
_NUMBER_MARKER = re.compile(r"^(\s*\d+)\.", re.MULTILINE)
_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_URL = re.compile(r"https?://\S+")


def escape_md(text: object) -> str:
    """마크다운 기호(~, $, [], :이름:, * 등)를 글자 그대로 보이게 바꾼다."""
    text = _MD_SPECIAL.sub(r"\\\1", str(text or ""))
    # ':이름:' 아이콘·':red[...]' 색 지시는 백슬래시로 막히지 않아 콜론 뒤에 폭 없는 공백을 넣는다.
    text = re.sub(r":(?=\S)", ":​", text)
    text = _BULLET_MARKER.sub(lambda m: m.group(1) + "\\" + m.group(2), text)
    return _NUMBER_MARKER.sub(lambda m: m.group(1) + "\\.", text)


def source_markdown(name: str, link: str) -> str:
    """출처 칸을 링크 마크다운으로. 칸 안의 '[이름](주소)'는 그대로 링크로 살린다."""
    pairs = _MD_LINK.findall(name or "")
    if pairs:
        return " · ".join(f"[{escape_md(title)}]({url})" for title, url in pairs)
    label = _URL.sub("", name or "").strip(" ·") or "출처"
    if link:
        return f"[{escape_md(label)}]({link})"
    return escape_md(name)


@dataclass(frozen=True)
class ReportMeta:
    model: str
    effort: str
    elapsed_s: float | None
    criteria_count: int
    criteria_version: str


def footer_text(meta: ReportMeta) -> str:
    bits = [f"답한 모델 {meta.model}", f"effort {meta.effort}"]
    if meta.elapsed_s is not None:
        bits.append(f"걸린 시간 {meta.elapsed_s:.1f}초")
    bits.append(f"기준 목록 {meta.criteria_count}개(버전 {meta.criteria_version or '알 수 없음'})")
    return " · ".join(bits)


def summary_text(report: Report) -> str:
    counts = report.counts
    return f"주의 {counts[WARN]} · 확인 필요 {counts[CHECK]} · 괜찮음 {counts[OK]}"


def questions_copy_text(questions: list[str]) -> str:
    lines = [QUESTION_GREETING, ""] + [f"{i}. {q}" for i, q in enumerate(questions, start=1)]
    return "\n".join(lines)


# ---------- 부품 ----------


def grade_badge(grade: str) -> None:
    st.badge(grade, color=BADGE_COLORS.get(grade, "gray"))


def _quote_box(text: str) -> None:
    st.code(text, language=None, wrap_lines=True)


def _evidence_body(evidence: rules.Evidence | None, *, by_code: bool) -> None:
    if evidence is None:
        if by_code:
            st.caption("근거 없이 코드 규칙으로만 표시했어요.")
        else:
            st.caption("이 카드에는 검증된 근거가 붙어 있지 않아요. 집주인에게 직접 확인해 보세요.")
        return
    st.markdown(escape_md(evidence.basis))
    if evidence.limits:
        st.markdown(f"**이 근거가 말하지 않는 것:** {escape_md(evidence.limits)}")
    if evidence.source_name or evidence.source_link:
        st.markdown(f"**출처:** {source_markdown(evidence.source_name, evidence.source_link)}")


def render_card(card: Card, *, fold_evidence: bool = True) -> None:
    """조항 카드 하나. fold_evidence=False면 근거를 접지 않고 보인다(접기 상자 안에 그릴 때. 접기는 겹칠 수 없다)."""
    with st.container(border=True):
        with st.container(horizontal=True, gap="small"):
            grade_badge(card.grade)
            if rules.TAG_AI_OPINION in card.tags:
                st.badge(rules.TAG_AI_OPINION, color="gray")
            if card.text_kind != rules.PRINTED:
                st.badge(card.text_kind, color="violet")
            if rules.TAG_READ_VALUE in card.tags:
                st.badge(rules.TAG_READ_VALUE, color="orange")
        st.markdown(f"**{escape_md(card.title)}**")
        if card.quote:
            st.caption("원문 그대로")
            _quote_box(card.quote)
        else:
            st.caption("원문 인용 없음 · 올린 쪽에서 찾지 못했어요")
        if card.location:
            st.caption(f"위치: {escape_md(card.location)}")
        st.markdown(escape_md(card.explanation))
        for note in card.grade_notes:
            st.caption(escape_md(note))
        origin = BY_CODE if card.by_code else BY_AI
        if card.rewritten:
            origin += " · 법 표현이 있어 코드가 문장을 바꿨어요"
        st.caption(origin)
        if fold_evidence:
            with st.expander("근거 보기"):
                _evidence_body(card.evidence, by_code=card.by_code)
        else:
            st.caption("근거")
            _evidence_body(card.evidence, by_code=card.by_code)


def render_fee_card(fee: FeeCard) -> None:
    with st.container(border=True):
        with st.container(horizontal=True, gap="small"):
            grade_badge(fee.grade)
            st.badge(BY_CODE, color="gray")
        st.markdown(f"**관리비 · {escape_md(fee.label)}**")
        st.markdown(escape_md(fee.summary))
        if fee.formula:
            st.caption("계산식")
            st.code(fee.formula, language=None, wrap_lines=True)
        if fee.items:
            st.caption("AI가 읽은 항목")
            # st.table은 칸 글을 마크다운으로 그린다.
            rows = [{"항목": escape_md(name), "금액": escape_md(amount) or "금액 없음"} for name, amount in fee.items]
            st.table(rows, hide_index=True)
        original = fee.source_text or fee.amount_text
        if original:
            st.caption("AI가 읽은 원문")
            _quote_box(original)
        for note in fee.notes:
            st.caption(escape_md(note))
        with st.expander("근거 보기"):
            _evidence_body(fee.evidence, by_code=True)


def render_questions(questions: list[str]) -> None:
    st.subheader("집주인에게 이렇게 물어보세요")
    st.caption(f"전체 복사 · {COPY_HINT}")
    st.code(questions_copy_text(questions), language=None, wrap_lines=True)
    with st.expander("질문 하나씩 복사"):
        st.caption(COPY_HINT)
        for question in questions:
            st.code(question, language=None, wrap_lines=True)
    st.caption(SEND_YOURSELF)


def render_not_checked() -> None:
    with st.container(border=True):
        st.markdown(f"**{NOT_CHECKED_TITLE}**")
        st.markdown("\n".join(f"- {escape_md(line)}" for line in NOT_CHECKED))


def render_grade_meanings() -> None:
    with st.expander(f"등급 뜻 · {OK_NOT_SAFE}"):
        for name, meaning in GRADE_MEANINGS:
            st.markdown(f"**{name}:** {escape_md(meaning)}")


def render_how_judged(report: Report, meta: ReportMeta) -> None:
    with st.expander("어떻게 판단했나"):
        with_evidence, total = report.evidence_count
        lines = [
            f"근거가 기준 목록에서 붙은 카드 {with_evidence}/{total}",
            f"규칙 때문에 등급이 바뀐 카드 {report.changed_count}개",
        ]
        if report.fee is not None and report.fee.formula:
            lines.append(f"관리비 계산식 {report.fee.formula}")
        lines.append(footer_text(meta))
        st.markdown("\n".join(f"- {escape_md(line)}" for line in lines))
        if report.answer_lines:
            st.caption("정답표용 기준번호:등급")
            st.code("\n".join(report.answer_lines), language=None, wrap_lines=True)


def render_retake_tips() -> None:
    with st.container(border=True):
        st.markdown("**글자를 읽기 어려워요. 이렇게 다시 찍어 주세요.**")
        st.markdown("\n".join(f"- {tip}" for tip in rules.RETAKE_TIPS))


def render_compare_column(photo: bytes | None, pdf_name: str | None) -> None:
    if photo:
        st.caption("AI가 읽은 사진(원문 대조용)")
        st.image(photo, width="stretch")
    elif pdf_name is not None:
        st.info(PDF_COMPARE)
        st.caption(f"파일: {escape_md(pdf_name)}")
    else:
        st.caption("대조할 사진이 없어요.")


def render_report(report: Report, meta: ReportMeta, *, photo: bytes | None = None, pdf_name: str | None = None) -> None:
    """결과 화면 전체(설계 10장 순서). 띠 → 요약 → 관리비 → 사진·카드 → 질문 → 확인하지 않는 것 → 판단 → 아래 글."""
    for banner in report.banners:
        text = escape_md(banner.text)
        if banner.level == "warning":
            st.warning(text)
        else:
            st.info(text)
    if report.read_state == "일부 흐림" and report.read_note:
        st.caption(f"흐린 곳: {escape_md(report.read_note)}")

    if report.unreadable:
        render_retake_tips()
    elif not report.not_interpreted:
        st.markdown(f"**{summary_text(report)}** · {OK_NOT_SAFE}")
        render_grade_meanings()
        if report.fee is not None:
            render_fee_card(report.fee)

        left, right = st.columns([2, 3])
        with left:
            render_compare_column(photo, pdf_name)
        with right:
            main_cards = [card for card in report.cards if card.grade != OK]
            ok_cards = [card for card in report.cards if card.grade == OK]
            if not report.cards and report.fee is None:
                st.info(rules.NO_CARDS)
            for card in main_cards:
                render_card(card)
            if ok_cards:
                with st.expander(f"괜찮음 {len(ok_cards)}개 · 안전 보증 아님"):
                    for card in ok_cards:
                        render_card(card, fold_evidence=False)
            if report.ok_hidden:
                st.caption(f"괜찮음 {report.ok_hidden}개는 화면에 다 싣지 않았어요.")

        render_questions(report.questions)

    render_not_checked()
    if not report.unreadable and not report.not_interpreted:
        render_how_judged(report, meta)
    st.caption(footer_text(meta))
