import csv
import re
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CRITERIA = ROOT / "criteria.csv"
SAMPLES = ROOT / "samples"

COLUMNS = ["번호", "이름", "분류", "줄 종류", "판정 주체", "확인할 것", "주의 신호", "괜찮은 모습",
           "검수된 쉬운 설명", "근거 문장", "이 근거가 말하지 않는 것", "출처 이름·링크", "확인 날짜", "기본 질문"]
CATEGORIES = {"보증금·월세", "관리비", "퇴실·원상복구", "수리·하자", "계약 기간·갱신",
              "전입·확정일자", "공과금·생활", "기본 정보"}
ROW_KINDS = {"근거 줄", "질문 전용 줄"}
JUDGES = {"AI", "코드"}
# 설계_구현방법.md 7장: 제10조는 이 법이 직접 정한 사항의 줄에만 붙인다.
ARTICLE_10_ROWS = {"기간-01", "기간-02", "기간-03", "전입-02"}
# 규칙 적용 3단계가 AI 문장을 바꿀 때 쓰는 칸이라, 바꾼 뒤 문장이 다시 걸리면 안 된다.
LEGAL_WORDS = re.compile(
    r"불법|위법|무효|사기|소송|처벌|효력이 없|법에 어긋|돌려받을 수 있|안 지켜도 되|"
    r"주택임대차보호법|민법|공인중개사법|주민등록법|제\s*\d+\s*조"
)
OVERCLAIM = re.compile(r"무효|불법|위반|공제 금지|판례상")


def load_rows():
    with open(CRITERIA, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


class CriteriaTest(unittest.TestCase):
    def setUp(self):
        self.columns, self.rows = load_rows()

    def test_columns(self):
        self.assertEqual(self.columns, COLUMNS)

    def test_ids(self):
        ids = [r["번호"].strip() for r in self.rows]
        self.assertTrue(all(ids), "빈 번호가 있어요")
        self.assertEqual(len(ids), len(set(ids)), "번호가 겹쳐요")
        for i in ids:
            self.assertRegex(i, r"^[가-힣]{2}-\d{2}$")

    def test_size(self):
        self.assertGreaterEqual(len(self.rows), 15)

    def test_allowed_values(self):
        for r in self.rows:
            self.assertIn(r["분류"], CATEGORIES, r["번호"])
            self.assertIn(r["줄 종류"], ROW_KINDS, r["번호"])
            self.assertIn(r["판정 주체"], JUDGES, r["번호"])

    def test_only_fee_row_is_code(self):
        code = [r["번호"] for r in self.rows if r["판정 주체"] == "코드"]
        self.assertEqual(code, ["관리-01"])

    def test_required_text(self):
        for r in self.rows:
            for col in ("이름", "확인할 것", "주의 신호", "괜찮은 모습", "검수된 쉬운 설명", "근거 문장", "기본 질문"):
                self.assertTrue(r[col].strip(), f"{r['번호']} {col}")
            self.assertTrue(r["기본 질문"].endswith("?"), r["번호"])

    def test_question_only_rows_have_no_source(self):
        for r in self.rows:
            if r["줄 종류"] == "질문 전용 줄":
                self.assertEqual(r["출처 이름·링크"], "", r["번호"])
                self.assertEqual(r["확인 날짜"], "", r["번호"])
                self.assertTrue(r["근거 문장"].startswith("법 근거 아님"), r["번호"])

    def test_evidence_rows_have_source(self):
        for r in self.rows:
            if r["줄 종류"] == "근거 줄":
                self.assertIn("](https://", r["출처 이름·링크"], r["번호"])
                if r["확인 날짜"]:
                    self.assertRegex(r["확인 날짜"], r"^\d{4}-\d{2}-\d{2}$")

    def test_replacement_text_has_no_legal_words(self):
        for r in self.rows:
            for col in ("검수된 쉬운 설명", "기본 질문"):
                self.assertIsNone(LEGAL_WORDS.search(r[col]), f"{r['번호']} {col}")

    def test_evidence_does_not_overclaim(self):
        for r in self.rows:
            self.assertIsNone(OVERCLAIM.search(r["근거 문장"]), r["번호"])

    def test_article_10_only_where_allowed(self):
        for r in self.rows:
            if "제10조" in r["근거 문장"]:
                self.assertIn(r["번호"], ARTICLE_10_ROWS)


class SamplesTest(unittest.TestCase):
    def test_images(self):
        for name in ("sample_a.jpg", "sample_y.jpg"):
            with Image.open(SAMPLES / name) as im:
                self.assertEqual(im.format, "JPEG")
                self.assertEqual(im.size, (1240, 1754))
                self.assertEqual(im.mode, "RGB")

    def test_pdf(self):
        data = (SAMPLES / "sample_b.pdf").read_bytes()
        self.assertTrue(data.startswith(b"%PDF-"))
        self.assertIn(b"/Count 2", data)
        self.assertLess(len(data), 20 * 1024 * 1024)

    def test_answers_use_known_ids(self):
        _, rows = load_rows()
        known = {r["번호"] for r in rows}
        text = (SAMPLES / "answers.md").read_text(encoding="utf-8")
        used = set(re.findall(r"^([가-힣]{2}-\d{2}) : ", text, re.M))
        self.assertTrue(used)
        self.assertEqual(used - known, set())


if __name__ == "__main__":
    unittest.main()
