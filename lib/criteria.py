"""확인 기준 목록(criteria.csv) 읽기와 AI에게 줄 기준 목록 글 만들기.

캐시 함수나 모듈 전역에 담지 않고 매 실행 읽는다. 기준 담당이 고쳐 push해도
Streamlit은 CSV가 바뀐 것을 모르기 때문이다(기술_확인.md 6장).
"""

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from lib import settings

BASE_COLUMNS = (
    "번호",
    "이름",
    "분류",
    "줄 종류",
    "판정 주체",
    "확인할 것",
    "주의 신호",
    "괜찮은 모습",
    "검수된 쉬운 설명",
    "근거 문장",
    "이 근거가 말하지 않는 것",
    "확인 날짜",
    "기본 질문",
)
# 설계 7장: 출처 이름과 링크는 한 칸이어도 되고 두 칸으로 나눠도 된다.
SOURCE_ONE = "출처 이름·링크"
SOURCE_TWO = ("출처 이름", "출처 링크")

EVIDENCE_ROW = "근거 줄"
QUESTION_ROW = "질문 전용 줄"

_URL = re.compile(r"https?://\S+")


@dataclass(frozen=True)
class Criterion:
    id: str
    name: str
    category: str
    row_kind: str
    judge: str
    check: str
    warn_signs: str
    ok_looks: str
    plain_explanation: str
    basis: str
    basis_limits: str
    source_name: str
    source_link: str
    checked_date: str
    default_question: str

    @property
    def judged_by_ai(self) -> bool:
        return self.judge.strip().upper() == "AI"

    @property
    def is_evidence_row(self) -> bool:
        """주의·괜찮음까지 낼 수 있는 줄. 근거 줄이라도 출처 링크나 확인 날짜가 비면 질문 전용으로 본다."""
        return self.row_kind == EVIDENCE_ROW and bool(self.source_link) and bool(self.checked_date)


@dataclass
class CriteriaLoad:
    rows: list[Criterion] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    version: str = ""

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def by_id(self) -> dict[str, Criterion]:
        return {row.id: row for row in self.rows}

    @property
    def ai_rows(self) -> list[Criterion]:
        return [row for row in self.rows if row.judged_by_ai]


def load_criteria(path: Path | str | None = None) -> CriteriaLoad:
    path = Path(path) if path is not None else settings.CRITERIA_PATH
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return CriteriaLoad(errors=[f"기준 목록 파일이 없어요: {path.name}"])
    except OSError:
        return CriteriaLoad(errors=[f"기준 목록 파일을 열지 못했어요: {path.name}"])
    return parse_criteria(raw)


def parse_criteria(raw: bytes) -> CriteriaLoad:
    version = hashlib.sha256(raw).hexdigest()[:8]
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return CriteriaLoad(
            errors=["기준 목록을 UTF-8로 읽지 못했어요. 구글 시트에서 CSV로 다시 내려받아 주세요(엑셀로 저장하지 마세요)."],
            version=version,
        )

    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = [cell.strip() for cell in next(reader)]
    except StopIteration:
        return CriteriaLoad(errors=["기준 목록 파일이 비어 있어요."], version=version)

    errors: list[str] = []
    missing = [name for name in BASE_COLUMNS if name not in header]
    has_one = SOURCE_ONE in header
    has_two = all(name in header for name in SOURCE_TWO)
    if not (has_one or has_two):
        missing.append(f"{SOURCE_ONE} (또는 {SOURCE_TWO[0]}·{SOURCE_TWO[1]})")
    duplicated_headers = sorted({name for name in header if name and header.count(name) > 1})
    if duplicated_headers:
        errors.append(f"칸 이름이 두 번 나와요: {', '.join(duplicated_headers)}")
    if missing:
        errors.append(f"칸 이름이 빠졌거나 달라요: {', '.join(missing)}")
        return CriteriaLoad(errors=errors, version=version)

    index = {name: header.index(name) for name in header if name}
    rows: list[Criterion] = []
    seen: dict[str, int] = {}
    for line_no, cells in enumerate(reader, start=2):
        if not any(cell.strip() for cell in cells):
            continue

        def get(name: str) -> str:
            i = index[name]
            return cells[i].strip() if i < len(cells) else ""

        crit_id = get("번호")
        if not crit_id:
            errors.append(f"{line_no}번째 줄의 번호가 비어 있어요.")
            continue
        if crit_id in seen:
            errors.append(f"번호 '{crit_id}'가 {seen[crit_id]}번째 줄과 {line_no}번째 줄에 두 번 나와요.")
            continue
        seen[crit_id] = line_no

        if has_two:
            source_name, source_link = get(SOURCE_TWO[0]), get(SOURCE_TWO[1])
        else:
            source_name = get(SOURCE_ONE)
            match = _URL.search(source_name)
            source_link = match.group(0) if match else ""

        rows.append(
            Criterion(
                id=crit_id,
                name=get("이름"),
                category=get("분류"),
                row_kind=get("줄 종류"),
                judge=get("판정 주체"),
                check=get("확인할 것"),
                warn_signs=get("주의 신호"),
                ok_looks=get("괜찮은 모습"),
                plain_explanation=get("검수된 쉬운 설명"),
                basis=get("근거 문장"),
                basis_limits=get("이 근거가 말하지 않는 것"),
                source_name=source_name,
                source_link=source_link,
                checked_date=get("확인 날짜"),
                default_question=get("기본 질문"),
            )
        )

    if not rows and not errors:
        errors.append("기준 목록에 줄이 하나도 없어요.")
    return CriteriaLoad(rows=rows, errors=errors, version=version)


def _one_line(text: str) -> str:
    return " / ".join(part.strip() for part in text.splitlines() if part.strip())


def build_criteria_text(rows: list[Criterion]) -> str:
    """AI 판정 줄만 글 목록으로 만든다. 같은 입력이면 글자 하나 다르지 않다(프롬프트 캐시).

    화면용 칸(근거 문장, 출처, 기본 질문, 검수된 쉬운 설명)은 넣지 않는다.
    """
    lines = ["# 기준 목록", "기준 번호는 아래 대괄호 안의 것만 쓴다. 맞는 번호가 없으면 '기타'로 쓴다.", ""]
    for row in rows:
        if not row.judged_by_ai:
            continue
        cap = "" if row.is_evidence_row else " · 질문 전용: 등급은 확인 필요까지만"
        lines.append(f"[{row.id}] {_one_line(row.name)} ({_one_line(row.category)}{cap})")
        lines.append(f"- 확인할 것: {_one_line(row.check)}")
        if row.warn_signs:
            lines.append(f"- 주의 신호: {_one_line(row.warn_signs)}")
        if row.ok_looks:
            lines.append(f"- 괜찮은 모습: {_one_line(row.ok_looks)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
