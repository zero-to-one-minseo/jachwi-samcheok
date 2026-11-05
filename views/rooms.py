import math
import os
import re

import streamlit as st

from lib import map_view
from lib import rooms_data as rd

DEV = os.environ.get("APP_DEV") == "1"
SEL_KEY = "room_selected_id"
CENTER_KEY = "rooms_map_center"
CONTRACT_PAGE = "views/contract.py"
ALWAYS_CHECK = "실제 매물 여부는 연락해서 확인하세요."

_MD_SPECIAL = re.compile(r"([\\`*_~$\[\]#<>|])")


def md(text) -> str:
    """조사 글을 마크다운으로 그릴 때 ~ $ [ ] 같은 기호가 서식으로 바뀌지 않게 한다."""
    return _MD_SPECIAL.sub(r"\\\1", str(text or ""))


def price_line(room: dict) -> str:
    dep = room.get("deposit")
    dep_txt = f"보증금 **{rd.fmt_man(dep)}만 원**" if dep is not None else "보증금 글에 없음"
    ctype = room.get("contract_type")
    if ctype == "전세":
        return f"전세 **{rd.fmt_man(dep)}만 원**" if dep is not None else "전세 · 금액 글에 없음"
    if room.get("monthly") is None:
        if room.get("prepaid_total"):
            return f"{dep_txt} · 선세 {rd.fmt_man(room['prepaid_total'])}만 원(기간이 안 적혀 월 환산을 못 해요)"
        return f"{dep_txt} · 월 금액이 글에 없어요"
    monthly = md(rd.monthly_text(room))
    total = room.get("prepaid_total")
    if ctype in ("선세", "연세", "양도") and total:
        months = room.get("prepaid_months")
        period = f"{rd.fmt_man(months)}개월 " if months else ""
        word = "연세" if ctype == "연세" else "선세"
        line = f"{dep_txt} · {period}{word} {rd.fmt_man(total)}만 원 · 월 환산 **{monthly}**"
        if not months and room.get("monthly_low") != room.get("monthly_high"):
            line += " (기간이 안 적혀 10\\~12개월로 나눴어요)"
        return line
    if ctype in ("선세", "연세"):
        return f"{dep_txt} · 월 환산 **{monthly}**"
    return f"{dep_txt} · 월세 **{monthly}**"


def included_line(room: dict) -> str:
    items = room.get("included") or []
    fee = rd.fee_summary(room)
    parts = [md(fee)] if fee else []
    parts.append(f"포함: {'·'.join(items)}" if items else "포함 항목이 안 적혀 있어요")
    return " · ".join(parts)


def detail_line(room: dict) -> str:
    bits = [room.get("structure"), room.get("size"), room.get("options"), room.get("distance")]
    return " · ".join(md(b) for b in bits if b)


def source_line(room: dict) -> str:
    bits = [f"출처 {room.get('source') or '미상'}", f"조사 {room.get('surveyed') or '미상'}"]
    if room.get("posted"):
        bits.append(f"게시·거래 {room['posted']}")
    return md(" · ".join(bits))


def go_check(room: dict) -> None:
    st.session_state["selected_room"] = rd.to_selected_room(room)
    st.switch_page(CONTRACT_PAGE)


def room_card(room: dict, medians: dict) -> None:
    with st.container(border=True):
        st.markdown(f"**{md(room.get('name') or '이름 없는 방')}**")
        badges = [f":blue-badge[{room['area']}]", f":gray-badge[{room['contract_type']}]"]
        if room.get("kind") == "양도":
            badges.append(":orange-badge[양도 글]")
        elif room.get("kind") == "실거래":
            badges.append(":violet-badge[실거래]")
        st.markdown(" ".join(badges))
        st.markdown(price_line(room))
        st.markdown(included_line(room))
        detail = detail_line(room)
        if detail:
            st.caption(detail)
        cmp_txt = rd.compare_text(rd.compare_to_area(room, medians))
        if cmp_txt:
            color = "orange" if "비싸요" in cmp_txt else "green" if "싸요" in cmp_txt else "gray"
            st.markdown(f":{color}[{md(cmp_txt)}]")
        if room.get("kind") == "양도":
            orig = room.get("orig_total")
            orig_txt = f" 원래 계약은 {rd.fmt_man(orig)}만 원이었다고 적혀 있어요." if orig else ""
            st.markdown(
                ":orange[**집주인 동의 확인:** 양도(남은 기간 넘겨받기)는 집주인이 동의해야 해요(민법 제629조). "
                "집주인에게 직접 확인하고, 계약서를 새로 쓰거나 동의 내용을 적어 두세요."
                f"{orig_txt}]"
            )
        st.caption(source_line(room))
        if st.button("계약 전에 계약서 점검하기", key=f"check_{room['id']}", width="stretch"):
            go_check(room)


def summary(filtered: list, areas: list, baseline) -> None:
    priced = [r["monthly"] for r in filtered if r.get("monthly") is not None]
    mid = rd.median(priced)
    base = rd.baseline_summary(baseline, areas)
    c1, c2, c3 = st.columns(3)
    c1.metric("조건에 맞는 방", f"{len(filtered)}곳")
    c2.metric("가운데 월 환산", f"{rd.fmt_man(mid)}만 원" if mid is not None else "없음")
    if base:
        c3.metric("공공데이터 기준선", f"월 {rd.fmt_man(base['monthly_median'])}만 원")
        c3.caption(md(f"국토교통부 전월세 실거래 {base['count']}건 · {base['label']} · {base['period']}"))
    else:
        c3.metric("공공데이터 기준선", "준비 중")
        c3.caption("국토교통부 전월세 실거래가를 넣는 중이에요." if baseline is None else "고른 생활권의 실거래가 없어요.")
    if any(r.get("kind") == "양도" for r in filtered):
        st.caption("양도 글은 남은 기간을 깎아 넘기는 값이 섞여 있어서, 생활권 가운데 값 계산에서는 뺐어요.")


def footer(rooms: list) -> None:
    st.divider()
    dates = sorted({r["surveyed"] for r in rooms if r.get("surveyed")})
    when = dates[0] if len(dates) == 1 else (f"{dates[0]}~{dates[-1]}" if dates else "미상")
    sources = sorted({r["source"] for r in rooms if r.get("source")})
    st.caption(md(f"조사 시점: {when} · 출처: {', '.join(sources)}"))
    st.caption(
        "팀원이 글을 직접 읽고 숫자와 조건만 옮겼어요. 연락처, 호수, 글 주소는 싣지 않았어요. "
        "선세·연세는 개월 수로 나눈 월 환산으로 비교해요."
    )
    st.markdown(f"**{ALWAYS_CHECK}**")


def main() -> None:
    st.title("삼척 자취방 시세")
    st.caption("직방에 안 뜨는 삼척 자취방, 학생들이 직접 모은 시세예요.")

    rooms = rd.load_rooms()
    if not rooms:
        st.info("조사 자료를 준비하고 있어요. 조금 뒤에 다시 열어 주세요.")
        st.markdown(f"**{ALWAYS_CHECK}**")
        return
    shown = rd.visible_rooms(rooms)
    baseline = rd.load_baseline()
    medians = rd.area_medians(shown)

    present = lambda key, order: [o for o in order if any(r.get(key) == o for r in shown)]  # noqa: E731
    max_monthly = max((r["monthly_high"] for r in shown if r.get("monthly") is not None), default=60)
    top = int(math.ceil(max_monthly / 5.0) * 5)

    with st.expander("조건 고르기", expanded=True):
        areas = st.pills(
            "생활권", present("area", rd.AREAS), selection_mode="multi", key="rooms_area",
            persist_state="session", help="고르지 않으면 전체예요.",
        )
        lo, hi = st.slider(
            "월 환산(만 원)", 0, top, (0, top), step=1, key="rooms_monthly", persist_state="session",
            help="선세·연세는 총액을 개월 수로 나눈 값이에요.",
        )
        col_a, col_b = st.columns(2)
        with col_a:
            ctypes = st.pills(
                "계약 방식", present("contract_type", rd.CONTRACT_TYPES), selection_mode="multi",
                key="rooms_contract", persist_state="session",
            )
            kinds = st.pills(
                "자료 종류", present("kind", rd.KINDS), selection_mode="multi",
                key="rooms_kind", persist_state="session",
                help="양도는 남은 기간을 넘기는 글이에요. 실거래는 신고된 계약 기록이에요.",
            )
        with col_b:
            items = st.pills(
                "포함 항목(모두 포함)", rd.INCLUDED_ITEMS, selection_mode="multi",
                key="rooms_items", persist_state="session",
                help="월세·관리비에 들어 있어 따로 안 내도 된다고 적힌 항목이에요.",
            )
            unknown = st.checkbox(
                "가격이 안 적힌 방도 보기", key="rooms_unknown", persist_state="session",
                help="전세나 '가격 협의' 글처럼 월 환산을 못 한 방이에요.",
            )

    filtered = rd.sort_rooms(rd.filter_rooms(
        shown, areas=areas, monthly_range=(lo, hi), contract_types=ctypes, kinds=kinds,
        required_items=items, include_unknown_price=unknown,
    ))
    summary(filtered, areas or [], baseline)

    if not filtered:
        st.info("조건에 맞는 방이 없어요. 조건을 줄여 보세요.")
    map_and_list(filtered, medians)
    footer(shown)


def pick(room: dict) -> None:
    st.session_state[SEL_KEY] = room["id"]
    st.session_state[CENTER_KEY] = (room["lat"], room["lon"])


def map_and_list(filtered: list, medians: dict) -> None:
    centers = map_view.load_centers()
    placed = map_view.attach_coords(filtered, map_view.load_coords(), centers)
    by_id = {r["id"]: r for r in placed}
    selected = st.session_state.get(SEL_KEY)
    if selected not in by_id:
        selected = None
        st.session_state.pop(SEL_KEY, None)
        st.session_state.pop(CENTER_KEY, None)
    center = st.session_state.get(CENTER_KEY)

    left, right = st.columns([3, 2])
    with left:
        clicked = map_view.render_map(
            placed, medians, centers, selected_id=selected, center=center,
            zoom=map_view.SELECTED_ZOOM if center else None, height=480,
        )
        st.caption(
            "말풍선 숫자는 월 환산(만 원)이에요. 초록은 생활권 가운데 값보다 3만 원 넘게 싸고, 주황은 비싸요. "
            "점선 테두리는 양도 글이에요."
        )
        st.caption("점 위치는 길 단위로 뭉갠 대략 위치예요. 정확한 건물이 아니에요. 지도 © OpenStreetMap 기여자")
    if clicked and clicked in by_id and clicked != selected:
        pick(by_id[clicked])
        st.rerun()

    with right:
        if selected:
            room_card(by_id[selected], medians)
        else:
            st.info("지도의 가격 말풍선이나 아래 목록의 '보기'를 누르면 방 정보가 여기에 떠요.")
        st.markdown(f"**목록 {len(placed)}곳**")
        with st.container(height=420):
            for r in placed:
                name_col, btn_col = st.columns([4, 1], vertical_alignment="center")
                price = map_view.price_label(r)
                price_txt = f"월 {price}만" if price != "?" else "가격 모름"
                mark = "▶ " if r["id"] == selected else ""
                name_col.markdown(
                    f"{mark}**{price_txt}** · {md(r.get('name') or '이름 없는 방')}  \n"
                    f":gray[{md(r.get('area', ''))} · {md(r.get('contract_type', ''))}]"
                )
                btn_col.button("보기", key=f"pick_{r['id']}", on_click=pick, args=(r,))


try:
    main()
except Exception as e:
    print(f"[rooms] {type(e).__name__}", flush=True)
    if DEV:
        raise
    st.error("현황판을 그리다가 문제가 생겼어요. 새로고침해 주세요.")
