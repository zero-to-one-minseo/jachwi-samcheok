"""POST /api/analyze: 계약서 사진·PDF 1개를 점검해 보고서 JSON을 돌려준다(Vercel Python 함수).

순서는 기존 앱 화면(app/views/contract.py)과 같다: prepare_upload → contract_ai.analyze → rules.apply_rules.
요청 본문은 {"file_b64": str, "filename": str}. 응답 모양은 README.md와 web/lib/report.ts에 있다.
로그에는 상태·코드·걸린 시간만 남긴다. 파일 내용, 파일 이름, 키는 찍지 않는다.
"""

import base64
import binascii
import dataclasses
import enum
import json
import sys
import threading
import time
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

# Vercel이 이 파일을 어떤 작업 폴더에서 불러도 옆의 _engine을 찾게 한다.
_API_DIR = str(Path(__file__).resolve().parent)
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

from _engine import contract_ai, image_prep, rules, settings  # noqa: E402
from _engine.criteria import build_criteria_text, load_criteria  # noqa: E402

# Vercel 함수 요청 본문 상한(4.5MB)과 별개로, 이 함수가 스스로 막는 선.
MAX_BODY_BYTES = 14 * 1024 * 1024

MSG_NO_FILE = "올린 파일이 없어요. 파일을 다시 올려 주세요."
MSG_DAILY_LIMIT = "오늘 앱 전체의 분석 횟수를 다 썼어요. 내일 다시 오거나 저장된 결과로 둘러볼 수 있어요."
MSG_CRITERIA_BROKEN = "기준 목록 파일에 문제가 있어 분석을 할 수 없어요."
MSG_NO_INSTRUCTIONS = "지시문 파일이 없어 분석을 할 수 없어요."
MSG_INTERNAL = "분석 중 문제가 생겼어요. 다시 시도해 주세요."
MSG_METHOD = "이 주소는 POST로만 분석해요."

# contract_ai의 status → (응답 code, HTTP 상태). 'ok'와 'limit_reached'는 따로 다룬다.
STATUS_TO_CODE: dict[str, tuple[str, int]] = {
    "refused": ("refused", 422),
    "truncated": ("truncated", 502),
    "invalid": ("invalid", 502),
    "timeout": ("timeout", 504),
    "network": ("network", 502),
    "server_error": ("server_error", 503),
    "rate_limited": ("rate_limited", 429),
    "spend_limit": ("credit", 503),
    "credit": ("credit", 503),
    "billing": ("credit", 503),
    "auth": ("auth", 503),
    "too_large": ("too_large", 413),
    "bad_request": ("bad_file", 422),
    "no_key": ("no_key", 503),
    "limit_reached": ("limit_reached", 429),
    "error": ("api_error", 502),
}
# 기존 앱 화면이 '다시 시도' 단추를 보여 주는 경우와 같다(views/contract.py RETRYABLE).
RETRYABLE_CODES = {"timeout", "network", "server_error", "rate_limited", "invalid", "truncated", "api_error",
                   "internal_error"}


class DailyCounter:
    """프로세스 하나 안의 KST 하루 호출 수. 인스턴스가 여러 개 뜨면 각자 세는 느슨한 상한이다."""

    def __init__(self, limit: int = settings.DAILY_LIMIT) -> None:
        self.limit = limit
        self._lock = threading.Lock()
        self._day: date | None = None
        self._count = 0

    def try_take(self, today: date | None = None) -> bool:
        today = today or datetime.now(settings.KST).date()
        with self._lock:
            if self._day != today:
                self._day = today
                self._count = 0
            if self._count >= self.limit:
                return False
            self._count += 1
            return True


COUNTER = DailyCounter()


def _log(event: str, **fields: Any) -> None:
    bits = [f"[analyze] {event}"] + [f"{k}={v}" for k, v in fields.items() if v is not None]
    print(" ".join(bits), flush=True)


def _json_safe(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return _json_safe(value.value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def report_to_json(report: rules.Report) -> dict[str, Any]:
    """Report를 JSON용 dict로. asdict가 빼는 계산 속성(counts, grade_changed)도 넣는다."""
    data = dataclasses.asdict(report)
    data["counts"] = report.counts
    for card_json, card in zip(data["cards"], report.cards):
        card_json["grade_changed"] = card.grade_changed
    return _json_safe(data)


def error_body(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "code": code, "message": message, "retryable": code in RETRYABLE_CODES}


class _Reject(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(code)
        self.status = status
        self.body = error_body(code, message)


def _decode_request(body: bytes) -> tuple[bytes, str]:
    """본문 JSON에서 파일 바이트와 파일 이름을 꺼낸다. 맞지 않으면 _Reject."""
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise _Reject(400, "bad_request", MSG_NO_FILE) from None
    if not isinstance(payload, dict):
        raise _Reject(400, "bad_request", MSG_NO_FILE)
    file_b64 = payload.get("file_b64")
    filename = payload.get("filename")
    if not isinstance(file_b64, str) or not file_b64.strip():
        raise _Reject(400, "bad_request", MSG_NO_FILE)
    if filename is not None and not isinstance(filename, str):
        raise _Reject(400, "bad_request", MSG_NO_FILE)
    text = file_b64.strip()
    if text.startswith("data:") and "," in text:
        text = text.split(",", 1)[1]
    try:
        data = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise _Reject(422, "bad_file", image_prep.MSG_CANNOT_OPEN) from None
    if not data:
        raise _Reject(400, "bad_request", MSG_NO_FILE)
    return data, filename or ""


def process(body: bytes, *, counter: DailyCounter | None = None) -> tuple[int, dict[str, Any]]:
    """요청 본문 하나를 처리해 (HTTP 상태, 응답 dict)를 돌려준다. 예외를 밖으로 내보내지 않는다."""
    counter = counter or COUNTER
    if len(body) > MAX_BODY_BYTES:
        return 413, error_body("too_large", image_prep.MSG_TOO_BIG_FILE)

    try:
        data, filename = _decode_request(body)
    except _Reject as reject:
        return reject.status, reject.body

    prepared = image_prep.prepare_upload(data, filename)
    del data
    if not prepared.ok or prepared.data is None or prepared.kind is None:
        if prepared.error_kind == "너무 큼":
            return 413, error_body("too_large", prepared.message)
        return 422, error_body("bad_file", prepared.message)

    crit = load_criteria()
    if crit.errors:
        _log("criteria_error", count=len(crit.errors))
        return 500, error_body("internal_error", MSG_CRITERIA_BROKEN)
    instructions = contract_ai.load_instructions()
    if not instructions:
        return 500, error_body("internal_error", MSG_NO_INSTRUCTIONS)

    result = contract_ai.analyze(
        prepared.data,
        prepared.kind,
        build_criteria_text(crit.rows),
        instructions,
        on_call=counter.try_take,
    )

    if not result.ok or result.parsed is None:
        code, status = STATUS_TO_CODE.get(result.status, ("api_error", 502))
        if result.status == "limit_reached":
            message = MSG_DAILY_LIMIT
        else:
            message = contract_ai.user_message(result, prepared.kind)
        return status, error_body(code, message)

    report = rules.apply_rules(result.parsed, crit.by_id)
    meta = {
        "model": result.model,
        "effort": settings.EFFORT,
        "elapsed_s": round(result.elapsed_s, 1),
        "criteria_version": crit.version,
        "criteria_count": len(crit.rows),
        "kind": prepared.kind,
        "source": "live",
    }
    return 200, {"ok": True, "report": report_to_json(report), "meta": meta}


class handler(BaseHTTPRequestHandler):  # noqa: N801  Vercel이 이 이름을 찾는다.
    server_version = "analyze"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # 기본 로그는 요청 줄 전체를 찍는다. 경로·상태만 남긴다.
        return

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        # 같은 출처에서만 쓴다. 다른 사이트용 CORS 허용 헤더는 일부러 내지 않는다.
        self.send_response(204)
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        self._send_json(200, {"ok": True, "status": "ready"})

    def do_PUT(self) -> None:  # noqa: N802
        self._send_json(405, error_body("method_not_allowed", MSG_METHOD))

    do_DELETE = do_PUT
    do_PATCH = do_PUT

    def do_POST(self) -> None:  # noqa: N802
        started = time.monotonic()
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0:
            status, payload = 400, error_body("bad_request", MSG_NO_FILE)
        elif length > MAX_BODY_BYTES:
            # 본문을 읽지 않고 끊는다.
            status, payload = 413, error_body("too_large", image_prep.MSG_TOO_BIG_FILE)
            self.close_connection = True
        else:
            try:
                status, payload = process(self.rfile.read(length))
            except Exception as error:
                _log("unexpected", kind=type(error).__name__)
                status, payload = 500, error_body("internal_error", MSG_INTERNAL)
        _log("done", http=status, code=payload.get("code", "ok"), elapsed=f"{time.monotonic() - started:.1f}s")
        self._send_json(status, payload)
