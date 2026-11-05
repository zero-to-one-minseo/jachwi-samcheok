"""계약서 점검 Claude 호출(기술_확인.md 2·3장).

- 결과 형식은 parse 대신 create + output_config로 받고 stop_reason부터 본다.
- SDK 재시도는 끄고(max_retries=0), 연결 오류·5xx·짧은 retry-after 429만 앱이 1회 다시 보낸다.
- 로그에는 오류 클래스 이름, request_id, 걸린 시간만 남긴다. 계약서 글과 예외 메시지는 찍지 않는다.
"""

import base64
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Literal

import anthropic
import pydantic
import streamlit as st

from lib import settings
from lib.schema import AnalysisOutput

Status = Literal[
    "ok",
    "refused",
    "truncated",
    "invalid",
    "timeout",
    "network",
    "server_error",
    "rate_limited",
    "spend_limit",
    "credit",
    "billing",
    "auth",
    "too_large",
    "bad_request",
    "no_key",
    "limit_reached",
    "error",
]
USAGE_LIMIT_STATUSES = ("spend_limit", "credit", "billing")

REQUEST_TEXT = "위 문서를 지시문과 기준 목록에 따라 점검하고, 정해진 형식으로만 답한다."
SHRINK_TEXT = "\n\n출력을 줄여라. 괜찮음 조항은 빼고, 쉬운 설명은 1문장으로 쓴다."

_OUTPUT_SCHEMA = anthropic.transform_schema(AnalysisOutput)
_USAGE_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


@dataclass(frozen=True)
class AnalysisResult:
    status: Status
    parsed: AnalysisOutput | None
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    request_id: str | None = None
    elapsed_s: float = 0.0
    error_kind: str | None = None
    attempts: int = 0
    stop_reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _log(event: str, *, kind: str | None = None, request_id: str | None = None, elapsed: float | None = None) -> None:
    parts = [f"[contract_ai] {event}"]
    if kind:
        parts.append(f"kind={kind}")
    if request_id:
        parts.append(f"request_id={request_id}")
    if elapsed is not None:
        parts.append(f"elapsed={elapsed:.1f}s")
    print(" ".join(parts), flush=True)


def _read_api_key() -> str | None:
    try:
        key = st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        return None
    key = str(key).strip()
    return key or None


@st.cache_resource(show_spinner=False)
def _make_client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key, timeout=settings.TIMEOUT_S, max_retries=settings.MAX_RETRIES)


def get_client() -> anthropic.Anthropic | None:
    """키가 없거나 비었으면 None. '확인하기'를 누른 뒤에만 부른다."""
    key = _read_api_key()
    if key is None:
        return None
    return _make_client(key)


def load_instructions(path: Path | str | None = None) -> str:
    """지시문을 매 실행 읽는다. 없으면 빈 글(부르는 쪽이 막는다)."""
    path = Path(path) if path is not None else settings.INSTRUCTIONS_PATH
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def build_request(
    file_bytes: bytes,
    kind: Literal["image", "pdf"],
    criteria_text: str,
    instructions_text: str,
    *,
    shrink: bool = False,
) -> dict[str, Any]:
    """messages.create에 넘길 인자. 재시도 때도 system과 format은 그대로 두고 user 글 끝만 바꾼다(캐시)."""
    data = base64.standard_b64encode(file_bytes).decode("ascii")
    if kind == "image":
        file_block = {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}
    elif kind == "pdf":
        file_block = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}}
    else:
        raise ValueError("kind must be 'image' or 'pdf'")

    request_text = REQUEST_TEXT + (SHRINK_TEXT if shrink else "")
    params: dict[str, Any] = {
        "model": settings.MODEL,
        "max_tokens": settings.MAX_TOKENS,
        "system": [
            {"type": "text", "text": instructions_text},
            {"type": "text", "text": criteria_text, "cache_control": {"type": "ephemeral"}},
        ],
        "messages": [{"role": "user", "content": [file_block, {"type": "text", "text": request_text}]}],
        "output_config": {
            "effort": settings.EFFORT,
            "format": {"type": "json_schema", "schema": _OUTPUT_SCHEMA},
        },
    }
    if settings.USE_FALLBACK:
        params["betas"] = [settings.FALLBACK_BETA]
        params["fallbacks"] = "default"
    return params


def _send(client: anthropic.Anthropic, params: dict[str, Any]) -> Any:
    if settings.USE_FALLBACK:
        return client.beta.messages.create(**params)
    return client.messages.create(**params)


def _retry_after_s(error: anthropic.APIStatusError) -> float | None:
    headers = error.response.headers
    ms = headers.get("retry-after-ms")
    if ms:
        try:
            return float(ms) / 1000
        except ValueError:
            pass
    value = headers.get("retry-after")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    try:
        return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
    except Exception:
        return None


def _has_credit_phrase(error: anthropic.APIStatusError) -> bool:
    text = f"{error.api_message or ''} {error.message or ''}".lower()
    return "credit balance" in text


def _classify(error: Exception) -> tuple[Status, float | None]:
    """예외를 상태로 바꾼다. 두 번째 값은 다시 보낼 때 기다릴 초(다시 보내지 않으면 None).

    잡는 순서는 기술_확인.md 3장: 하위 종류부터.
    """
    if isinstance(error, anthropic.APIStatusError) and _has_credit_phrase(error):
        return "credit", None
    if isinstance(error, anthropic.EnforcedSpendLimitReachedError):
        return "spend_limit", None
    if isinstance(error, anthropic.RateLimitError):
        wait = _retry_after_s(error)
        if wait is not None and wait <= settings.RETRY_AFTER_MAX_S:
            return "rate_limited", wait
        return "rate_limited", None
    if isinstance(error, anthropic.APITimeoutError):
        return "timeout", None
    if isinstance(error, anthropic.APIConnectionError):
        return "network", settings.RETRY_DELAY_S
    if isinstance(error, anthropic.InternalServerError):
        wait = _retry_after_s(error)
        if wait is not None and wait > settings.RETRY_AFTER_MAX_S:
            return "server_error", None
        return "server_error", wait if wait is not None else settings.RETRY_DELAY_S
    if isinstance(error, anthropic.BadRequestError):
        message = error.api_message or error.message or ""
        if message.startswith("You have reached your specified"):
            return "spend_limit", None
        return "bad_request", None
    if isinstance(error, anthropic.APIStatusError):
        if error.status_code == 402:
            return "billing", None
        if error.status_code in (401, 403):
            return "auth", None
        if error.status_code == 408:
            return "timeout", None
        if error.status_code == 413:
            return "too_large", None
        return "error", None
    return "error", None


def _add_usage(total: dict[str, int], response: Any) -> None:
    usage = getattr(response, "usage", None)
    for key in _USAGE_KEYS:
        value = getattr(usage, key, None) if usage is not None else None
        if isinstance(value, int):
            total[key] = total.get(key, 0) + value


def _text_of(response: Any) -> str | None:
    texts = [block.text for block in (response.content or []) if getattr(block, "type", None) == "text"]
    return "".join(texts) if texts else None


def analyze(
    file_bytes: bytes,
    kind: Literal["image", "pdf"],
    criteria_text: str,
    instructions_text: str,
    *,
    client: anthropic.Anthropic | None = None,
    on_call: Callable[[], bool] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> AnalysisResult:
    """계약서 1건을 분석한다. 예외를 밖으로 내보내지 않고 status로 돌려준다.

    on_call: 실제 API 호출(다시 보내기 포함) 직전마다 부른다. False를 돌려주면 호출하지 않고
    'limit_reached'로 끝낸다. 세션·하루 상한 카운터를 여기에 건다.
    """
    started = time.monotonic()
    usage: dict[str, int] = {}
    attempts = 0
    model = settings.MODEL
    request_id: str | None = None
    stop_reason: str | None = None

    def finish(status: Status, parsed: AnalysisOutput | None = None, error_kind: str | None = None) -> AnalysisResult:
        elapsed = time.monotonic() - started
        _log(f"done status={status} attempts={attempts}", kind=error_kind, request_id=request_id, elapsed=elapsed)
        return AnalysisResult(
            status=status,
            parsed=parsed,
            model=model,
            usage=usage,
            request_id=request_id,
            elapsed_s=elapsed,
            error_kind=error_kind,
            attempts=attempts,
            stop_reason=stop_reason,
        )

    if not criteria_text.strip() or not instructions_text.strip():
        return finish("error", error_kind="EmptyPrompt")

    if client is None:
        client = get_client()
        if client is None:
            return finish("no_key", error_kind="NoApiKey")

    shrink = False
    # 오류 재시도와 줄인 요청을 합쳐 한 분석에서 다시 보내기는 1번뿐이다(설계 4장).
    retried = False
    while True:
        if on_call is not None and not on_call():
            return finish("limit_reached", error_kind="AppLimit")
        attempts += 1
        params = build_request(file_bytes, kind, criteria_text, instructions_text, shrink=shrink)
        call_started = time.monotonic()
        try:
            response = _send(client, params)
        except Exception as error:
            request_id = getattr(error, "request_id", None) or request_id
            status, wait = _classify(error)
            _log("api_error", kind=type(error).__name__, request_id=request_id, elapsed=time.monotonic() - call_started)
            if wait is not None and not retried:
                retried = True
                sleep(wait)
                continue
            return finish(status, error_kind=type(error).__name__)

        request_id = getattr(response, "_request_id", None) or request_id
        model = getattr(response, "model", None) or model
        stop_reason = getattr(response, "stop_reason", None)
        _add_usage(usage, response)
        _log(f"response stop={stop_reason}", request_id=request_id, elapsed=time.monotonic() - call_started)

        if stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) if details is not None else None
            return finish("refused", error_kind=f"refusal:{category}" if category else "refusal")

        if stop_reason == "max_tokens":
            failure: tuple[Status, str] = ("truncated", "max_tokens")
        else:
            text = _text_of(response)
            if text is None:
                failure = ("invalid", "NoTextBlock")
            else:
                try:
                    return finish("ok", parsed=AnalysisOutput.model_validate_json(text))
                except pydantic.ValidationError:
                    failure = ("invalid", "ValidationError")

        if not retried:
            retried = True
            shrink = True
            continue
        return finish(failure[0], error_kind=failure[1])


STATUS_MESSAGES: dict[str, str] = {
    "refused": "이 문서는 분석하지 못했어요. 저장된 결과로 둘러볼 수 있어요.",
    "truncated": "결과가 너무 길어 끝까지 받지 못했어요. 계약서 쪽을 나눠서 다시 올려 주세요.",
    "invalid": "결과를 정해진 형식으로 받지 못했어요. 잠시 뒤 다시 시도해 주세요.",
    "timeout": "분석이 너무 오래 걸려 멈췄어요. 다시 시도해 주세요.",
    "network": "연결이 잠시 끊겼어요. 잠시 뒤 다시 시도해 주세요.",
    "server_error": "AI 서버가 잠시 바빠요. 잠시 뒤 다시 시도해 주세요.",
    "rate_limited": "지금 사용하는 사람이 많아요. 잠시 뒤 다시 시도해 주세요.",
    "spend_limit": "사용 한도에 닿았어요. 저장된 결과로 보여 드릴게요.",
    "credit": "사용 한도에 닿았어요. 저장된 결과로 보여 드릴게요.",
    "billing": "사용 한도에 닿았어요. 저장된 결과로 보여 드릴게요.",
    "auth": "AI 연결 설정에 문제가 있어요. 저장된 결과로 둘러볼 수 있어요.",
    "too_large": "파일이 너무 커요. 계약서 쪽만 골라 올리거나 사진으로 올려 주세요.",
    "bad_request": "이 파일은 분석하지 못했어요. 다른 사진으로 다시 올려 주세요.",
    "no_key": "AI 연결 키가 없어요. 저장된 결과로 둘러볼 수 있어요.",
    "limit_reached": "오늘 분석 횟수를 다 썼어요. 저장된 결과로 둘러볼 수 있어요.",
    "error": "분석 중 문제가 생겼어요. 다시 시도해 주세요.",
}
MSG_BAD_PDF = "암호가 걸렸거나 열 수 없는 PDF예요. 계약서 쪽만 사진으로 올려 주세요."


def user_message(result: AnalysisResult, kind: Literal["image", "pdf"]) -> str:
    """실패 결과를 화면에 띄울 한 문장으로. 예외 메시지는 쓰지 않는다."""
    if result.status == "bad_request" and kind == "pdf":
        return MSG_BAD_PDF
    return STATUS_MESSAGES.get(result.status, STATUS_MESSAGES["error"])
