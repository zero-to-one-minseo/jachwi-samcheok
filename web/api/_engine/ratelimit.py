"""접속 주소(IP)마다 일정 시간 안의 호출 수를 센다. 서버(함수 인스턴스) 하나 안에서만 세는 느슨한 상한이다.

대회장처럼 같은 와이파이의 여러 사람이 한 IP로 보일 수 있어 상한은 넉넉하게 잡는다.
IP는 기록하지 않고 메모리에만 잠깐 둔다.
"""

from __future__ import annotations

import threading
import time
from collections import deque


class IpLimiter:
    def __init__(self, limit: int, window_s: float) -> None:
        self.limit = limit
        self.window_s = window_s
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}

    def allow(self, ip: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits.setdefault(ip, deque())
            while q and now - q[0] > self.window_s:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            if len(self._hits) > 5000:
                self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] <= self.window_s}
            return True


def client_ip(headers, fallback: str) -> str:
    """Vercel은 x-forwarded-for 맨 앞에 실제 접속 주소를 넣는다."""
    forwarded = (headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return forwarded or headers.get("x-real-ip") or fallback
