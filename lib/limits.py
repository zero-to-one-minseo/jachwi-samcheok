"""분석 횟수 상한: 세션당(session_state)과 서버 하루(모든 사용자 공유).

세는 단위는 실제 API 호출이다(다시 보내기 포함, 저장본 보기 제외). contract_ai.analyze의
on_call에 make_on_call(...)을 넘기면 호출 직전마다 센다.
하루 카운터는 메모리에만 있어 앱이 다시 시작되면 0이 되는 느슨한 상한이다(기술_확인.md 4장).
"""

import threading
from collections.abc import Callable, MutableMapping
from datetime import date, datetime
from typing import Any, Literal

import streamlit as st

from lib import settings

SESSION_COUNT_KEY = "analysis_calls"
LIMIT_REASON_KEY = "limit_reason"

LimitReason = Literal["session", "daily"]

MSG_SESSION_LIMIT = "이 화면에서 쓸 수 있는 분석 횟수를 다 썼어요. 저장된 결과로 둘러볼 수 있어요."
MSG_DAILY_LIMIT = "오늘 앱 전체의 분석 횟수를 다 썼어요. 내일 다시 오거나 저장된 결과로 둘러볼 수 있어요."


def kst_today(now: datetime | None = None) -> date:
    now = now or datetime.now(settings.KST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=settings.KST)
    return now.astimezone(settings.KST).date()


class DailyCounter:
    """모든 세션이 함께 쓰는 하루 횟수. 확인과 증가를 잠금 안에서 한 번에 한다."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._day: date | None = None
        self._count = 0

    def try_take(self, limit: int, today: date) -> bool:
        with self._lock:
            if self._day != today:
                self._day = today
                self._count = 0
            if self._count >= limit:
                return False
            self._count += 1
            return True

    def used(self, today: date) -> int:
        with self._lock:
            return self._count if self._day == today else 0


@st.cache_resource(show_spinner=False)
def daily_counter() -> DailyCounter:
    return DailyCounter()


def session_used(state: MutableMapping[str, Any]) -> int:
    return int(state.get(SESSION_COUNT_KEY, 0))


def session_left(state: MutableMapping[str, Any], limit: int | None = None) -> int:
    limit = settings.SESSION_LIMIT if limit is None else limit
    return max(0, limit - session_used(state))


def try_take_call(
    state: MutableMapping[str, Any],
    counter: DailyCounter | None = None,
    *,
    session_limit: int | None = None,
    daily_limit: int | None = None,
    today: date | None = None,
) -> tuple[bool, LimitReason | None]:
    """한 번의 실제 호출을 허락할지. 허락하면 세션·하루 횟수를 1씩 올린다."""
    session_limit = settings.SESSION_LIMIT if session_limit is None else session_limit
    daily_limit = settings.DAILY_LIMIT if daily_limit is None else daily_limit
    if session_used(state) >= session_limit:
        return False, "session"
    counter = counter or daily_counter()
    if not counter.try_take(daily_limit, today or kst_today()):
        return False, "daily"
    state[SESSION_COUNT_KEY] = session_used(state) + 1
    return True, None


def make_on_call(
    state: MutableMapping[str, Any],
    counter: DailyCounter | None = None,
    **limits: Any,
) -> Callable[[], bool]:
    """analyze(on_call=...)에 넘길 함수. 막히면 이유를 state[LIMIT_REASON_KEY]에 남긴다."""

    def on_call() -> bool:
        allowed, reason = try_take_call(state, counter, **limits)
        if not allowed:
            state[LIMIT_REASON_KEY] = reason
        return allowed

    return on_call


def limit_message(reason: str | None) -> str:
    return MSG_DAILY_LIMIT if reason == "daily" else MSG_SESSION_LIMIT
