"""로컬 개발용: analyze.handler를 http://127.0.0.1:8822/api/analyze 에서 띄운다(표준 라이브러리만).

Next.js 개발 서버가 /api/analyze 를 여기로 넘긴다. 이름이 _로 시작해 Vercel 함수로 배포되지 않는다.
키는 환경 변수 ANTHROPIC_API_KEY, 없으면 web/.env.local 의 ANTHROPIC_API_KEY= 줄에서 읽는다.

    app/.venv/bin/python web/api/_dev_server.py [--port 8822]
"""

import argparse
import os
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
WEB_DIR = API_DIR.parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from analyze import handler  # noqa: E402
from chat import handler as chat_handler  # noqa: E402

ROUTE = "/api/analyze"
CHAT_ROUTE = "/api/chat"
DEFAULT_PORT = 8822  # 해커톤 프로젝트 구간 8820–8829


def _load_env_local(path: Path = WEB_DIR / ".env.local") -> None:
    if os.environ.get("ANTHROPIC_API_KEY") or not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        name, sep, value = line.strip().partition("=")
        if sep and name.strip() == "ANTHROPIC_API_KEY":
            os.environ["ANTHROPIC_API_KEY"] = value.strip().strip("'\"")
            return


class DevHandler(handler):
    def _route_ok(self) -> bool:
        if self.path.split("?", 1)[0].rstrip("/") == ROUTE:
            return True
        self._send_json(404, {"ok": False, "code": "not_found", "message": "없는 주소예요.", "retryable": False})
        return False

    def do_GET(self) -> None:  # noqa: N802
        if self._route_ok():
            super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0].rstrip("/") == CHAT_ROUTE:
            chat_handler.do_POST(self)
        elif self._route_ok():
            super().do_POST()

    def do_OPTIONS(self) -> None:  # noqa: N802
        if self._route_ok():
            super().do_OPTIONS()


def main() -> None:
    parser = argparse.ArgumentParser(description="계약서 점검 API 로컬 서버")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    _load_env_local()
    key_state = "있음" if os.environ.get("ANTHROPIC_API_KEY", "").strip() else "없음(분석은 no_key로 끝남)"
    server = ThreadingHTTPServer(("127.0.0.1", args.port), DevHandler)
    print(f"[dev_server] http://127.0.0.1:{args.port}{ROUTE} · 키 {key_state}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
