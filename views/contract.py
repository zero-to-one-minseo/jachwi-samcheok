"""계약서 점검 화면(설계_구현방법.md 6·10장, 기술_확인.md 4장 '다시 실행과 분석 중 화면').

분석 순서: '확인하기' on_click 깃발 → 값 있는 위젯은 disabled로 그리고 단추 자리는 비움
→ 호출 직전 깃발 소비·'분석 시작' 표시(횟수는 analyze의 on_call이 실제 호출마다 셈)
→ st.spinner(show_time=True) → 결과를 session_state에 넣고 st.rerun.
사용자 파일과 결과는 session_state에만 둔다. 저장본 경로는 st.secrets를 건드리지 않는다.
"""

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pydantic
import streamlit as st

from lib import contract_ai, limits, render, rules, settings
from lib.criteria import CriteriaLoad, build_criteria_text, load_criteria
from lib.image_prep import PreparedFile, prepare_upload
from lib.render import escape_md
from lib.schema import AnalysisOutput

DEV = os.environ.get("APP_DEV") == "1"
SAMPLES_DIR = settings.APP_ROOT / "samples"
SAVED_GLOB = "saved_*.json"

K_GEN = "contract_uploader_gen"
K_FILE_ID = "contract_file_id"
K_FILE_NAME = "contract_file_name"
K_PREPARED = "contract_prepared"
K_REQUESTED = "contract_analyze_requested"
K_STARTED = "contract_analysis_started"
K_RESULT = "contract_result"
K_VIEW = "contract_view"
K_SAVED_IMAGES = "contract_saved_images"
FILE_KEYS = (K_FILE_ID, K_FILE_NAME, K_PREPARED, K_RESULT, limits.LIMIT_REASON_KEY)

UPLOAD_HINT = (
    f"JPG·PNG·PDF, 최대 {settings.UPLOAD_MAX_MB}MB(PDF는 {settings.PDF_MAX_MB}MB), "
    "HEIC는 스크린샷이나 JPG로 바꿔 올려 주세요."
)
UPLOAD_LABEL = f"계약서 사진 1장이나 PDF 1개 (JPG·PNG·PDF, 최대 {settings.UPLOAD_MAX_MB}MB)"
UPLOAD_HELP = UPLOAD_HINT + " 형식이나 크기가 맞지 않으면 칸 안에 영어 안내가 뜰 수 있어요."
MASK_NOTICE = "주민번호·연락처·계좌는 가리고 올려 주세요."
DATA_NOTICE = (
    "사진은 Streamlit Community Cloud(미국 서버)를 거쳐 분석을 위해 Anthropic API로 보내요. "
    "이 앱은 사진과 결과를 저장하지 않아요. Anthropic은 받은 내용을 AI 학습에 쓰지 않고 30일 안에 지워요. "
    "단, 안전 점검에 걸리면 최대 2년, 법에 따라 필요하면 더 오래 보관될 수 있어요."
)
DATA_LINKS = (
    ("보관 기간", "https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data"),
    ("학습", "https://privacy.claude.com/en/articles/7996868-is-my-data-used-for-model-training"),
    ("개발자 문서", "https://platform.claude.com/docs/en/manage-claude/api-and-data-retention"),
)
MSG_INTERRUPTED = "분석이 중간에 끊겼어요. 다시 눌러 주세요."
MSG_NO_FILE = "올린 파일이 없어요. 파일을 다시 올려 주세요."
MSG_PAGE_ERROR = "화면을 그리다 문제가 생겼어요. 새로고침하거나 '샘플로 해 보기'로 저장된 결과를 둘러봐 주세요."
RETRYABLE = {"timeout", "network", "server_error", "rate_limited", "invalid", "truncated", "error"}


# ---------- 작은 도우미 ----------


def _fmt_man(value: Any) -> str:
    try:
        number = round(float(value), 1)
    except (TypeError, ValueError):
        return str(value)
    return f"{int(number):,}" if number.is_integer() else f"{number:,.1f}"


def room_line(room: Any) -> str | None:
    """현황판에서 넘어온 방을 한 줄로. 값이 없으면 None."""
    if not isinstance(room, dict) or not (room.get("name") or room.get("area")):
        return None
    name = room.get("name") or "이름 없는 방"
    head = f"{name}({room['area']})" if room.get("area") else name
    ctype = room.get("contract_type") or "모름"
    deposit, monthly = room.get("deposit"), room.get("monthly")
    money: list[str] = []
    if ctype == "전세":
        money.append(f"전세 {_fmt_man(deposit)}만 원" if deposit is not None else "전세")
    else:
        if deposit is not None:
            money.append(f"보증금 {_fmt_man(deposit)}만 원")
        if monthly is not None:
            label = "월세" if ctype in ("월세", "모름") else f"{ctype} 월 환산"
            money.append(f"{label} {_fmt_man(monthly)}만 원")
        elif ctype != "모름":
            money.append(ctype)
    fee = str(room.get("fee_text") or "")
    included = [str(item) for item in room.get("included") or [] if item]
    if included:
        fee = f"{fee}({'·'.join(included)} 포함)" if fee else f"{'·'.join(included)} 포함"
    if fee:
        money.append(fee)
    parts = [head]
    if money:
        parts.append(" / ".join(money))
    origin = [bit for bit in (room.get("source"), room.get("surveyed") and f"조사 {room['surveyed']}") if bit]
    if origin:
        parts.append(" · ".join(str(bit) for bit in origin))
    return "점검 중인 방: " + " · ".join(parts)


def short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def _when_text(iso: str) -> str:
    try:
        moment = datetime.fromisoformat(iso).astimezone(settings.KST)
    except (TypeError, ValueError):
        return "날짜 미상"
    return f"{moment.month}월 {moment.day}일 {moment.hour}시 {moment.minute:02d}분"


# ---------- 저장본 ----------


@dataclass(frozen=True)
class SavedResult:
    name: str
    label: str
    saved_at: str
    model: str
    effort: str
    elapsed_s: float | None
    criteria_version: str
    instructions_version: str
    sample: str
    fake: bool
    output: AnalysisOutput


def saved_names(directory: Path = SAMPLES_DIR, wanted: str = "") -> list[str]:
    """보여 줄 저장본 이름. wanted('fake' 등)가 있으면 saved_<wanted>.json 하나만.

    실제 분석 저장본이 하나라도 있으면 시험용 가짜(saved_fake.json)는 빼서 방문자에게 보이지 않게 한다.
    """
    if wanted and re.fullmatch(r"[\w-]+", wanted) and (directory / f"saved_{wanted}.json").is_file():
        return [f"saved_{wanted}.json"]
    names = sorted(p.name for p in directory.glob(SAVED_GLOB))
    real = [n for n in names if n != "saved_fake.json"]
    return real or names


def load_saved(name: str, directory: Path = SAMPLES_DIR) -> SavedResult | None:
    """저장본 하나를 읽는다. 형식이 맞지 않으면 None(옛 형식 저장본은 다시 만들어야 한다)."""
    try:
        raw = json.loads((directory / name).read_text(encoding="utf-8"))
        output = AnalysisOutput.model_validate(raw["output"])
        elapsed = raw.get("elapsed_s")
        return SavedResult(
            name=name,
            label=str(raw.get("label") or Path(name).stem),
            saved_at=str(raw.get("saved_at") or ""),
            model=str(raw.get("model") or "알 수 없음"),
            effort=str(raw.get("effort") or "알 수 없음"),
            elapsed_s=float(elapsed) if isinstance(elapsed, (int, float)) else None,
            criteria_version=str(raw.get("criteria_version") or ""),
            instructions_version=str(raw.get("instructions_version") or ""),
            sample=str(raw.get("sample") or ""),
            fake=bool(raw.get("fake")),
            output=output,
        )
    except (OSError, ValueError, KeyError, TypeError, pydantic.ValidationError):
        return None


def saved_payload(result: contract_ai.AnalysisResult, meta: dict[str, Any]) -> dict[str, Any]:
    """'결과 파일 내려받기'로 받는 저장본. AI의 원래 결과와 모델·effort·시각·버전을 넣는다."""
    file_name = str(meta.get("file_name") or "")
    return {
        "format": 1,
        "label": f"{file_name} 분석" if file_name else "저장된 분석",
        "saved_at": meta.get("analyzed_at", ""),
        "model": result.model,
        "effort": settings.EFFORT,
        "elapsed_s": round(result.elapsed_s, 1),
        "criteria_version": meta.get("criteria_version", ""),
        "instructions_version": meta.get("instructions_version", ""),
        "sample": file_name,
        "fake": False,
        "usage": dict(result.usage),
        "output": result.parsed.model_dump(mode="json") if result.parsed is not None else None,
    }


def _saved_photo(sample: str) -> tuple[bytes | None, str | None]:
    """저장본의 대조 사진. 같은 준비 함수를 거친 JPEG을 이 세션에만 둔다."""
    if not sample:
        return None, None
    path = SAMPLES_DIR / Path(sample).name
    if path.suffix.lower() == ".pdf":
        return None, path.name
    if not path.is_file():
        return None, None
    images = st.session_state.setdefault(K_SAVED_IMAGES, {})
    if path.name not in images:
        prepared = prepare_upload(path.read_bytes(), path.name)
        images[path.name] = prepared.data if prepared.ok and prepared.kind == "image" else None
    return images[path.name], None


# ---------- 콜백 ----------


def _on_file_change() -> None:
    state = st.session_state
    for key in FILE_KEYS:
        state.pop(key, None)
    state[K_VIEW] = "own"


def _request_analysis() -> None:
    st.session_state[K_REQUESTED] = True
    st.session_state[K_VIEW] = "own"


def _show_saved() -> None:
    st.session_state[K_VIEW] = "saved"


def _show_own() -> None:
    st.session_state[K_VIEW] = "own"


def _clear_all() -> None:
    _on_file_change()
    st.session_state[K_GEN] = st.session_state.get(K_GEN, 0) + 1


# ---------- 화면 조각 ----------


def _render_notices() -> None:
    st.caption(UPLOAD_HINT)
    st.markdown(f"**{MASK_NOTICE}**")
    links = " · ".join(f"[{title}]({url})" for title, url in DATA_LINKS)
    st.caption(f"{escape_md(DATA_NOTICE)} 자세히: {links}")


def _prepare_if_new(uploaded: Any) -> None:
    """새 file_id일 때 한 번만 사진을 준비해 session_state에 둔다. 원본 바이트는 들고 있지 않는다."""
    if uploaded is None:
        return
    state = st.session_state
    if uploaded.file_id == state.get(K_FILE_ID):
        return
    state[K_PREPARED] = prepare_upload(uploaded.getvalue(), uploaded.name)
    state[K_FILE_ID] = uploaded.file_id
    state[K_FILE_NAME] = uploaded.name
    state.pop(K_RESULT, None)


def _render_preview(prepared: PreparedFile | None) -> None:
    if prepared is None:
        return
    if not prepared.ok:
        st.warning(escape_md(prepared.message))
    elif prepared.kind == "image" and prepared.data:
        st.image(prepared.data, width=160, caption="올린 사진(줄이고 사진 정보를 뺀 사본)")
    else:
        st.caption(f"PDF: {escape_md(st.session_state.get(K_FILE_NAME) or '')}")


def _render_waiting() -> None:
    st.markdown("**분석 중이에요.** 분석이 끝날 때까지 이 화면을 켜 두세요. 다른 앱으로 가거나 화면이 꺼지면 결과가 사라질 수 있어요.")
    ai_col, code_col = st.columns(2)
    with ai_col, st.container(border=True):
        st.markdown("**AI가 하는 일**")
        st.markdown("- 글자 읽기\n- 기준 번호 고르기\n- 원문 그대로 인용하기\n- 쉬운 설명과 질문 쓰기")
    with code_col, st.container(border=True):
        st.markdown("**코드가 하는 일**")
        st.markdown(
            "- 사람이 확인한 근거 붙이기\n- 원문 없는 빨강·초록 막기\n"
            "- 관리비 10만 원 판정(계산식)\n- 법 표현 문장 바꾸기\n- 개인정보 가리기"
        )


def _run_analysis(prepared: PreparedFile, crit: CriteriaLoad, instructions: str) -> dict[str, Any]:
    state = st.session_state
    try:
        result = contract_ai.analyze(
            prepared.data,
            prepared.kind,
            build_criteria_text(crit.rows),
            instructions,
            on_call=limits.make_on_call(state),
        )
    except Exception as error:
        print(f"[contract_view] analyze_error kind={type(error).__name__}", flush=True)
        result = contract_ai.AnalysisResult(status="error", parsed=None, model=settings.MODEL,
                                            error_kind=type(error).__name__)
    meta = {
        "analyzed_at": datetime.now(settings.KST).isoformat(timespec="seconds"),
        "criteria_version": crit.version,
        "criteria_count": len(crit.rows),
        "instructions_version": short_hash(instructions),
        "kind": prepared.kind,
        "file_name": state.get(K_FILE_NAME) or "",
    }
    return {"result": result, "meta": meta}


def _report_meta(model: str, effort: str, elapsed: float | None, crit: CriteriaLoad) -> render.ReportMeta:
    return render.ReportMeta(model=model, effort=effort, elapsed_s=elapsed,
                             criteria_count=len(crit.rows), criteria_version=crit.version)


def _render_own_result(outcome: dict[str, Any], crit: CriteriaLoad, dev: bool) -> None:
    state = st.session_state
    result: contract_ai.AnalysisResult = outcome["result"]
    meta: dict[str, Any] = outcome["meta"]
    kind = meta.get("kind") or "image"

    if not result.ok or result.parsed is None:
        if result.status == "limit_reached":
            message = limits.limit_message(state.get(limits.LIMIT_REASON_KEY))
        else:
            message = contract_ai.user_message(result, kind)
        st.warning(escape_md(message))
        with st.container(horizontal=True):
            if result.status in RETRYABLE and limits.session_left(state) > 0:
                st.button("다시 시도", key="contract_retry", on_click=_request_analysis)
            st.button("저장된 결과 보기", key="contract_failed_saved", on_click=_show_saved)
        return

    report = rules.apply_rules(result.parsed, crit.by_id)
    prepared: PreparedFile | None = state.get(K_PREPARED)
    photo = prepared.data if prepared is not None and prepared.ok and prepared.kind == "image" else None
    pdf_name = (meta.get("file_name") or "PDF") if kind == "pdf" else None
    render.render_report(report, _report_meta(result.model, settings.EFFORT, result.elapsed_s, crit),
                         photo=photo, pdf_name=pdf_name)
    with st.container(horizontal=True):
        st.button("결과 지우기", key="contract_clear", on_click=_clear_all)
        if dev:
            stem = re.sub(r"[^\w-]", "_", Path(str(meta.get("file_name") or "result")).stem) or "result"
            st.download_button(
                "결과 파일 내려받기",
                data=json.dumps(saved_payload(result, meta), ensure_ascii=False, indent=2),
                file_name=f"saved_{stem}.json",
                mime="application/json",
                on_click="ignore",
                key="contract_download",
            )


def _render_saved(crit: CriteriaLoad, has_own_result: bool, wanted: str = "") -> None:
    names = saved_names(wanted=wanted)
    if not names:
        st.info("아직 저장된 결과가 없어요.")
        return
    loaded = {n: load_saved(n) for n in names}
    name = names[0]
    if len(names) > 1:
        name = st.selectbox("저장된 결과", names, key="contract_saved_pick",
                            format_func=lambda n: loaded[n].label if loaded[n] else n)
    saved = loaded[name]
    if saved is None:
        st.warning("저장된 결과 파일을 읽지 못했어요. 결과 형식이 바뀌었으면 저장본을 다시 만들어 주세요.")
        return

    if saved.fake:
        st.info("저장된 결과 · 시험용 가짜 결과예요. 실제 분석이 아니에요.")
    else:
        st.info(f"저장된 결과({_when_text(saved.saved_at)} 실제 분석) · 지금 올린 파일의 결과가 아니에요.")
    version_note = f"분석 때 기준 목록 버전 {saved.criteria_version or '미상'}, 지시문 버전 {saved.instructions_version or '미상'}"
    if saved.criteria_version and saved.criteria_version != crit.version:
        version_note += " · 그 뒤 기준 목록이 바뀌었어요"
    st.caption(escape_md(version_note))

    photo, pdf_name = _saved_photo(saved.sample)
    report = rules.apply_rules(saved.output, crit.by_id)
    render.render_report(report, _report_meta(saved.model, saved.effort, saved.elapsed_s, crit),
                         photo=photo, pdf_name=pdf_name)
    if has_own_result:
        st.button("내 파일 결과로 돌아가기", key="contract_back_own", on_click=_show_own)


# ---------- 화면 ----------


def page() -> None:
    state = st.session_state
    saved_value = st.query_params.get("saved") or ""
    saved_param = bool(saved_value) and saved_value != "0"
    dev = st.query_params.get("dev") == "1"
    state.setdefault(K_GEN, 0)
    state.setdefault(K_VIEW, "saved" if saved_param else "own")

    st.title("계약서 점검")
    st.caption(f"{render.DISCLAIMER} 사진을 올리면 AI가 조항을 읽고, 근거와 규칙은 코드가 붙여요.")
    line = room_line(state.get("selected_room"))
    if line:
        st.info(escape_md(line))

    crit = load_criteria()
    if crit.errors:
        st.error("기준 목록 파일에 문제가 있어 분석을 할 수 없어요.\n\n" + "\n".join(f"- {escape_md(e)}" for e in crit.errors))
    instructions = contract_ai.load_instructions()
    if not instructions:
        st.error("지시문 파일이 없어 분석을 할 수 없어요.")

    requested = bool(state.get(K_REQUESTED))
    uploaded = st.file_uploader(
        UPLOAD_LABEL,
        type=list(settings.UPLOAD_TYPES),
        key=f"contract_upload_{state[K_GEN]}",
        help=UPLOAD_HELP,
        on_change=_on_file_change,
        max_upload_size=settings.UPLOAD_MAX_MB,
        disabled=requested,
    )
    _render_notices()
    _prepare_if_new(uploaded)
    prepared: PreparedFile | None = state.get(K_PREPARED)
    _render_preview(prepared)

    left = limits.session_left(state)
    ready = prepared is not None and prepared.ok and crit.ok and bool(instructions) and left > 0
    button_slot = st.empty()
    if requested:
        button_slot.empty()
    else:
        with button_slot.container():
            with st.container(horizontal=True):
                st.button("확인하기", type="primary", key="contract_check", on_click=_request_analysis,
                          disabled=not ready)
                st.button("샘플로 해 보기", key="contract_sample", on_click=_show_saved)
            if left > 0:
                st.caption(f"이 화면에서 남은 분석 {left}회")
            else:
                st.caption(limits.MSG_SESSION_LIMIT)

    if state.get(K_STARTED) and not requested:
        state.pop(K_STARTED, None)
        st.warning(MSG_INTERRUPTED)

    result_slot = st.empty()
    if requested:
        state[K_REQUESTED] = False
        if prepared is None or not prepared.ok or not prepared.data:
            with result_slot.container():
                st.warning(MSG_NO_FILE)
            return
        state[K_STARTED] = True
        state.pop(K_RESULT, None)
        state.pop(limits.LIMIT_REASON_KEY, None)
        with result_slot.container():
            _render_waiting()
            with st.spinner("계약서를 읽고 있어요.", show_time=True):
                outcome = _run_analysis(prepared, crit, instructions)
                # 스피너를 닫는 순간도 다시 실행 요청을 확인하는 지점이라, 그 전에 결과를 저장한다.
                state[K_RESULT] = outcome
                state.pop(K_STARTED, None)
        st.rerun()

    with result_slot.container():
        outcome = state.get(K_RESULT)
        if state.get(K_VIEW) == "saved":
            _render_saved(crit, has_own_result=outcome is not None,
                          wanted="" if saved_value == "1" else saved_value)
        elif outcome is not None:
            _render_own_result(outcome, crit, dev)


try:
    page()
except Exception as error:
    # st.rerun·st.stop은 BaseException 계열이라 여기서 잡히지 않는다.
    print(f"[contract_view] page_error kind={type(error).__name__}", flush=True)
    if DEV:
        raise
    st.error(MSG_PAGE_ERROR)
