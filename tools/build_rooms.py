"""data/raw/*.csv(조사 16칸)를 합쳐 data/rooms.csv를 만든다.

실행: app 폴더에서 .venv/bin/python tools/build_rooms.py
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = APP_DIR / "data" / "raw"
OUT_PATH = APP_DIR / "data" / "rooms.csv"

RAW_COLUMNS = [
    "조사 날짜", "출처", "건물명/대략 주소", "동네", "보증금", "월세", "관리비",
    "관리비 포함 항목", "구조", "평수", "옵션", "학교까지 거리", "메모", "자료 종류",
    "게시·거래 시점", "출처 주소",
]
# 팀 시트에 나중에 생길 수 있는 칸. 있으면 추정보다 우선한다.
OPTIONAL_COLUMNS = ["생활권", "계약 방식", "선세 금액", "개월 수"]

ROOM_FIELDS = [
    "id", "show", "hide_reason", "surveyed", "source", "posted", "name", "dong",
    "area", "kind", "contract_type", "deposit", "monthly", "monthly_low",
    "monthly_high", "prepaid_total", "prepaid_months", "orig_total", "fee",
    "fee_text", "included", "structure", "size", "size_m2", "options", "distance", "memo",
]

AREAS = ["후문", "정문", "교동택지", "마달동", "당저동", "시내", "기타"]
CONTRACT_TYPES = ["월세", "선세", "연세", "전세", "양도", "모름"]
KINDS = ["신규 매물", "양도", "구함", "실거래", "안내"]
INCLUDED_ITEMS = ["수도", "인터넷", "난방", "전기", "가스", "관리비"]

NUM = r"\d[\d,]*(?:\.\d+)?"

# ---------- 개인정보 지우기 ----------

_PHONE = re.compile(r"(?<!\d)0\d{1,2}[-.\s)]*[\d*xX]{3,4}[-.\s]*[\d*xX]{4}(?!\d)")
_URL = re.compile(r"https?://\S+|www\.\S+", re.I)
_DOMAIN = re.compile(r"\b[\w-]+(?:\.[\w-]+)*\.(?:com|net|org|kr|io|me|co)\b\S*", re.I)
_EMAIL = re.compile(r"\S+@\S+")
_HOSU = re.compile(r"(?<![\d.])\d{2,4}\s*호(?:실)?(?![가-힣])")
# 길·로·동 뒤의 번지와 층은 한 집을 가리킬 수 있어 지운다(설계_시세현황판 2장: 건물명 또는 대략 주소).
_LOT_NUMBER = re.compile(r"(?<=[길로동])\s+\d+(?:-\d+)?(?:\s*번지)?")
_FLOOR = re.compile(r"\s*(?:지하\s*)?\d+\s*층")


def vague_place(name: str) -> str:
    t = _FLOOR.sub("", _LOT_NUMBER.sub("", name or ""))
    t = re.sub(r"\(\s*\)", "", t)
    return re.sub(r"\s{2,}", " ", t).strip()
_CONTACT_CLAUSE = re.compile(r"카톡|카카오|오픈채팅|오픈톡|아이디|텔레그램|인스타|DM", re.I)


def sanitize(text: str | None) -> str:
    """연락처·글 주소·호수를 지운다. rooms.csv에 들어가는 모든 글은 이 함수를 거친다."""
    if not text:
        return ""
    t = str(text)
    t = _URL.sub("", t)
    t = _EMAIL.sub("", t)
    t = _DOMAIN.sub("", t)
    t = _PHONE.sub("", t)
    t = _HOSU.sub("", t)
    parts = [p for p in re.split(r"([,，;]\s*)", t)]
    kept: list[str] = []
    for i in range(0, len(parts), 2):
        clause = parts[i]
        if _CONTACT_CLAUSE.search(clause):
            continue
        kept.append(clause)
    t = ", ".join(c.strip() for c in kept if c.strip())
    t = re.sub(r"\(\s*[,，]?\s*\)", "", t)
    t = re.sub(r"\(\s*[,，]\s*", "(", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip(" ,，")


_SOURCE_NAMES = [
    ("에브리타임", "에브리타임 장터게시판"),
    ("에타", "에브리타임 장터게시판"),
    ("당근", "당근부동산"),
    ("집품", "집품(직방 계열)"),
    ("피터팬", "피터팬의좋은방구하기"),
    ("국제처", "강원대 국제처 숙소 안내"),
    ("KNU광장", "강원대 홈페이지 게시판"),
    ("네이버", "네이버 부동산"),
    ("전화", "중개사무소 전화"),
    ("지인", "지인 수소문"),
]


def short_source(text: str) -> str:
    for key, name in _SOURCE_NAMES:
        if key in (text or ""):
            return name
    return sanitize(text)[:30]


# ---------- 숫자 ----------


def _to_float(s: str) -> float:
    return float(s.replace(",", ""))


def _round(v: float | None) -> float | None:
    return None if v is None else round(v, 1)


def leading_number(text: str) -> tuple[float, float] | None:
    """글 맨 앞의 숫자나 범위('약 25~30', '35~45만')를 (작은 값, 큰 값)으로 읽는다."""
    m = re.match(rf"\s*(?:약\s*)?({NUM})\s*(?:만\s*원?)?\s*(?:[~∼]\s*({NUM}))?", text or "")
    if not m:
        return None
    lo = _to_float(m.group(1))
    hi = _to_float(m.group(2)) if m.group(2) else lo
    return (min(lo, hi), max(lo, hi))


def parse_deposit(text: str) -> float | None:
    v = leading_number(text)
    return None if v is None else v[0]


def parse_fee(text: str) -> float | None:
    t = (text or "").strip()
    if not t or "적힌" in t or "협의" in t:
        return None
    m = re.search(rf"({NUM})\s*만", t)
    if m:
        return _to_float(m.group(1))
    if re.fullmatch(rf"{NUM}", t):
        return _to_float(t)
    if re.search(r"포함|무료|없음|주인 부담", t):
        return 0.0
    return None


PYEONG_M2 = 3.3058


def parse_size_m2(text: str) -> float | None:
    """'9평(29.8㎡)', '20.89㎡(6.3평)', '17평(공급 기준 추정)'에서 ㎡를 읽는다. 범위('5~7평')면 작은 값."""
    t = text or ""
    m = re.search(rf"({NUM})\s*(?:㎡|m2|제곱미터)", t)
    if m:
        return _to_float(m.group(1))
    m = re.search(rf"({NUM})\s*(?:[~∼]\s*{NUM}\s*)?평", t)
    if m:
        return round(_to_float(m.group(1)) * PYEONG_M2, 1)
    return None


def parse_months(text: str) -> int | None:
    """'10개월' > '3~12월' > '1년' 순서로 개월 수를 찾는다. '10~12개월'처럼 범위면 모른다고 본다."""
    t = text or ""
    t = re.sub(r"\d{1,2}\s*[~∼]\s*\d{1,2}\s*개월", " ", t)
    m = re.search(r"(?<![\d.])(\d{1,2})\s*개월", t)
    if m:
        return int(m.group(1))
    m = re.search(r"(?<!\d)(\d{1,2})\s*[~∼]\s*(\d{1,2})\s*월", t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if 1 <= a <= 12 and 1 <= b <= 12:
            return b - a + 1 if b >= a else b + 12 - a + 1
    m = re.search(r"(?<!\d)([1-3])\s*년(?!\d)", t)
    if m:
        return 12 * int(m.group(1))
    return None


def parse_prepaid(text: str) -> tuple[float | None, int | None]:
    """선세·연세 총액과 개월 수. '6개월 210만'처럼 붙어 있으면 그 쌍을 먼저 쓴다."""
    t = text or ""
    m = re.search(rf"(?<![\d.])(\d{{1,2}})\s*개월\s*(?:선세|연세|년세)?\s*({NUM})", t)
    if m:
        months, total = int(m.group(1)), _to_float(m.group(2))
        if total >= months * 5:
            return total, months
    for m in re.finditer(rf"(?:선세|연세|년세)\)?\s*(?:\d+\s*평\s*)?({NUM})", t):
        total = _to_float(m.group(1))
        if total >= 30:
            return total, parse_months(t)
    return None, None


def parse_orig_total(text: str) -> float | None:
    m = re.search(rf"원래\s*(?:금액|계약|선세|연세)?\s*({NUM})", text or "")
    return _to_float(m.group(1)) if m else None


# ---------- 분류 ----------

_SEEK = re.compile(r"구함|구해요|구합니다|찾습니다|찾아요")
_OFFER_SEEK = re.compile(r"(입주자|세입자|룸메이트)\s*구")


def classify_kind(kind_raw: str, memo: str) -> str:
    k = kind_raw or ""
    if "양도" in k or "양도" in (memo or ""):
        return "양도"
    if "안내" in k or "시세 범위" in k:
        return "안내"
    if "실거래" in k:
        return "실거래"
    if _SEEK.search(k) and not _OFFER_SEEK.search(k):
        return "구함"
    return "신규 매물"


def classify_contract(kind: str, monthly_field: str, memo: str, has_monthly: bool) -> str:
    text = f"{monthly_field} {memo}"
    if kind == "양도":
        return "양도"
    if re.search(r"(선세|전세|월세)\s*·\s*(선세|반전세|전세|월세)", text):
        return "모름"
    if "연세" in text or "년세" in text:
        return "연세"
    if "선세" in text or re.search(r"\d\s*개월\s*\d", monthly_field or ""):
        return "선세"
    if re.search(r"(?<!반)전세", text) and not has_monthly:
        return "전세"
    if has_monthly:
        return "월세"
    return "모름"


_AREA_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("기타", re.compile(r"도계|근덕")),
    ("교동택지", re.compile(r"교동택지|코아루|청석로")),
    ("후문", re.compile(r"후문")),
    ("정문", re.compile(r"신정문|정문|장기재길")),
    ("마달동", re.compile(r"마달|누가아파트|혜진아파트|두타관")),
    ("당저동", re.compile(r"당저|월드마트")),
    ("시내", re.compile(r"남양|시청|중앙시장|정상동|정라|사직|성내|성북|터미널|사대")),
]


def classify_area(dong: str, name: str, distance: str = "") -> str:
    """동네 칸을 먼저 보고, 모자라면 건물명·주소, 그다음 학교까지 거리 글을 본다."""
    for text in (dong, name, distance):
        for area, pattern in _AREA_RULES:
            if pattern.search(text or ""):
                return area
    return "기타"


_ITEM_PATTERNS = [
    ("수도", re.compile(r"수도")),
    ("인터넷", re.compile(r"인터넷|와이파이|wi-?fi", re.I)),
    ("난방", re.compile(r"난방|보일러")),
    ("전기", re.compile(r"전기")),
    ("가스", re.compile(r"가스")),
    ("관리비", re.compile(r"관리비")),
]
_POSITIVE = re.compile(r"포함|무료|주인|제공|선납 완료|공짜")
_NEGATIVE = re.compile(r"별도|본인|각자|세입자|개인|실비|개별|따로|사용량|나눠")


def included_items(*texts: str) -> list[str]:
    """'수도·인터넷 포함, 전기 별도' 같은 글에서 따로 안 내도 되는 항목만 고른다."""
    found: set[str] = set()
    for text in texts:
        for clause in re.split(r"[,，;/]", text or ""):
            clause = re.sub(r"공용전기|심야전기|전기레인지", "", clause)
            if not _POSITIVE.search(clause) or _NEGATIVE.search(clause):
                continue
            for item, pattern in _ITEM_PATTERNS:
                if pattern.search(clause):
                    found.add(item)
    return [i for i in INCLUDED_ITEMS if i in found]


# ---------- 한 줄 정규화 ----------


def _fmt(v: float | int | None) -> str:
    if v is None:
        return ""
    v = float(v)
    return str(int(v)) if v.is_integer() else f"{v:.1f}"


def normalize_row(raw: dict[str, str], room_id: str = "") -> dict[str, str]:
    g = lambda k: (raw.get(k) or "").strip()  # noqa: E731
    memo_raw = g("메모")
    monthly_field = g("월세")
    kind = classify_kind(g("자료 종류"), memo_raw)

    given = leading_number(monthly_field)
    text_all = f"{monthly_field} {memo_raw}"
    prepaid_total, prepaid_months = parse_prepaid(text_all)

    contract = classify_contract(kind, monthly_field, memo_raw, given is not None)
    override_contract = g("계약 방식")
    if override_contract in CONTRACT_TYPES:
        contract = override_contract
    if g("선세 금액"):
        prepaid_total = parse_deposit(g("선세 금액"))
        prepaid_months = parse_months(g("개월 수") + "개월") or prepaid_months

    low = high = None
    prepaid_like = contract in ("선세", "연세") or (kind == "양도" and prepaid_total)
    if given is not None and not (prepaid_like and given[0] >= 100 and not prepaid_total):
        low, high = given
    elif given is not None:
        prepaid_total = given[0]
        prepaid_months = prepaid_months or parse_months(memo_raw)
    if low is None and prepaid_total:
        if prepaid_months:
            low = high = prepaid_total / prepaid_months
        elif contract in ("선세", "연세"):
            low, high = prepaid_total / 12, prepaid_total / 10
    if contract == "전세":
        low = high = None
    monthly = None if low is None else (low + high) / 2

    dong = sanitize(g("동네"))
    name = vague_place(sanitize(g("건물명/대략 주소")))
    area = g("생활권") if g("생활권") in AREAS else classify_area(dong, name, g("학교까지 거리"))

    hide_reason = ""
    if kind == "구함":
        hide_reason = "방을 구하는 글"
    elif kind == "안내":
        hide_reason = "시세 안내 글"
    elif re.search(r"도계", f"{dong} {name}"):
        hide_reason = "도계캠퍼스 쪽"

    fee_raw = g("관리비")
    return {
        "id": room_id,
        "show": "0" if hide_reason else "1",
        "hide_reason": hide_reason,
        "surveyed": sanitize(g("조사 날짜")),
        "source": short_source(g("출처")),
        "posted": sanitize(g("게시·거래 시점")),
        "name": name,
        "dong": dong,
        "area": area,
        "kind": kind,
        "contract_type": contract,
        "deposit": _fmt(parse_deposit(g("보증금"))),
        "monthly": _fmt(_round(monthly)),
        "monthly_low": _fmt(_round(low)),
        "monthly_high": _fmt(_round(high)),
        "prepaid_total": _fmt(prepaid_total),
        "prepaid_months": _fmt(prepaid_months),
        "orig_total": _fmt(parse_orig_total(memo_raw)) if kind == "양도" else "",
        "fee": _fmt(parse_fee(fee_raw)),
        "fee_text": sanitize(fee_raw),
        "included": "|".join(included_items(g("관리비 포함 항목"), fee_raw)),
        "structure": sanitize(g("구조")),
        "size": sanitize(g("평수")),
        "size_m2": _fmt(parse_size_m2(g("평수"))),
        "options": sanitize(g("옵션")),
        "distance": sanitize(g("학교까지 거리")),
        "memo": sanitize(memo_raw),
    }


# ---------- 파일 ----------


def read_raw(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = [h.strip() for h in (reader.fieldnames or [])]
        missing = [c for c in RAW_COLUMNS if c not in header]
        if missing:
            raise ValueError(f"{path.name}: 칸이 없어요 → {', '.join(missing)}")
        reader.fieldnames = header
        return [row for row in reader if any((v or "").strip() for v in row.values() if isinstance(v, str))]


def build(raw_dir: Path = RAW_DIR, out_path: Path = OUT_PATH) -> list[dict[str, str]]:
    files = sorted(raw_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"{raw_dir}에 CSV가 없어요")
    rooms: list[dict[str, str]] = []
    for path in files:
        for raw in read_raw(path):
            rooms.append(normalize_row(raw, room_id=f"r{len(rooms) + 1:03d}"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ROOM_FIELDS)
        writer.writeheader()
        writer.writerows(rooms)
    return rooms


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="조사 CSV를 합쳐 rooms.csv를 만든다")
    parser.add_argument("--raw", type=Path, default=RAW_DIR)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args(argv)
    try:
        rooms = build(args.raw, args.out)
    except (OSError, ValueError) as e:
        print(f"실패: {e}", file=sys.stderr)
        return 1
    shown = sum(r["show"] == "1" for r in rooms)
    priced = sum(r["show"] == "1" and r["monthly"] != "" for r in rooms)
    print(f"{args.out} 저장: {len(rooms)}줄 (표시 {shown}, 월 환산 있음 {priced})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
