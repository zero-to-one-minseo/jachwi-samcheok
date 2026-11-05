"""POST /api/chat: 챗봇 '매물 비교'. 다른 곳에서 본 매물 글(붙여넣기)이나 캡처 사진을 받아 시세와 비교한다.

요청 본문은 {"text": str, "image_b64": str | 없음}. 사진은 화면에서 줄인 JPEG다.
Claude는 칸 읽기만 하고(_engine/compare.extract), 비교·판단은 코드가 한다(_engine/compare.judge).
받은 글과 사진은 저장하지 않는다. 로그에는 상태와 걸린 시간만 남긴다.
"""

import base64
import binascii
import json
import sys
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

_API_DIR = str(Path(__file__).resolve().parent)
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

import threading  # noqa: E402
from datetime import date, datetime  # noqa: E402

from _engine import agent, compare, settings  # noqa: E402

MAX_BODY_BYTES = 4 * 1024 * 1024
DAILY_LIMIT = 300
MSG_DAILY_LIMIT = "오늘 비교 횟수를 다 썼어요. 내일 다시 와 주세요."
# Vercel은 함수마다 따로 묶어 배포해서 analyze.py를 불러올 수 없다. 상태 이름은 _engine/contract_ai와 같다.
STATUS_TO_CODE = {"timeout": ("timeout", 504), "network": ("network", 502), "server_error": ("server_error", 503),
                  "rate_limited": ("rate_limited", 429), "no_key": ("no_key", 503), "refused": ("refused", 422),
                  "credit": ("credit", 503), "spend_limit": ("credit", 503), "billing": ("credit", 503), "auth": ("auth", 503)}


class _Counter:
    """프로세스 하나 안의 KST 하루 호출 수(느슨한 상한)."""

    def __init__(self, limit: int) -> None:
        self.limit, self._lock, self._day, self._n = limit, threading.Lock(), None, 0

    def try_take(self) -> bool:
        today: date = datetime.now(settings.KST).date()
        with self._lock:
            if self._day != today:
                self._day, self._n = today, 0
            if self._n >= self.limit:
                return False
            self._n += 1
            return True


COUNTER = _Counter(DAILY_LIMIT)
MAX_TEXT = 4000
MSG_EMPTY = "비교할 매물 글을 붙여넣거나 캡처 사진을 올려 주세요."
MSG_FAIL = "매물 정보를 읽지 못했어요. 잠시 뒤 다시 시도해 주세요."
MSG_NOT_LISTING = "매물 정보가 보이지 않아요. 가격·보증금·위치가 적힌 글이나 캡처를 올려 주세요."
MSG_CONTRACT = "계약서로 보여요. 계약서는 '계약서 검사'에서 조항까지 확인할 수 있어요."


def _err(status: int, code: str, message: str) -> tuple[int, dict[str, Any]]:
    return status, {"ok": False, "code": code, "message": message}


def process(body: bytes) -> tuple[int, dict[str, Any]]:
    if len(body) > MAX_BODY_BYTES:
        return _err(413, "too_large", "사진이 너무 커요. 더 작은 캡처로 올려 주세요.")
    try:
        req = json.loads(body or b"{}")
        text = str(req.get("text") or "").strip()[:MAX_TEXT]
        image = base64.b64decode(req["image_b64"], validate=True) if req.get("image_b64") else None
    except (ValueError, binascii.Error, TypeError):
        return _err(400, "bad_request", MSG_EMPTY)
    if not text and not image:
        return _err(400, "bad_request", MSG_EMPTY)
    if not COUNTER.try_take():
        return _err(429, "limit_reached", MSG_DAILY_LIMIT)

    run = agent.run(text, image)
    if run.get("status") == "ok":
        if run["kind"] == "listing":
            return 200, {"ok": True, "kind": "listing", "result": run["result"], "steps": run["steps"], "summary": run["summary"]}
        if run["kind"] == "contract":
            return 200, {"ok": True, "kind": "contract", "message": MSG_CONTRACT}
    # 에이전트가 실패하거나 비교까지 못 가면, 한 번 읽고 코드로 비교하는 기본 길로 간다.
    status, listing = compare.extract(text, image)
    if status != "ok" or listing is None:
        code, http = STATUS_TO_CODE.get(status, ("api_error", 502))
        return _err(http, code, MSG_FAIL)
    if listing.input_kind == "계약서":
        return 200, {"ok": True, "kind": "contract", "message": MSG_CONTRACT}
    if listing.input_kind != "매물 정보":
        return 200, {"ok": True, "kind": "other", "message": MSG_NOT_LISTING}
    return 200, {"ok": True, "kind": "listing", "result": compare.judge(listing)}


class handler(BaseHTTPRequestHandler):  # noqa: N801  Vercel이 이 이름을 찾는다.
    server_version = "chat"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        self._send_json(200, {"ok": True, "status": "ready"})

    def do_POST(self) -> None:  # noqa: N802
        started = time.monotonic()
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY_BYTES:
            status, payload = _err(413, "too_large", "사진이 너무 커요. 더 작은 캡처로 올려 주세요.")
            self.close_connection = True
        else:
            try:
                status, payload = process(self.rfile.read(length))
            except Exception as error:  # noqa: BLE001
                print(f"[chat] unexpected {type(error).__name__}", file=sys.stderr)
                status, payload = _err(500, "internal_error", MSG_FAIL)
        print(f"[chat] http={status} code={payload.get('code', 'ok')} {time.monotonic() - started:.1f}s", file=sys.stderr)
        self._send_json(status, payload)
