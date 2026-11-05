import csv
import re
import tempfile
import unittest
from pathlib import Path

from lib import rooms_data as rd
from tools import build_rooms as br

APP_DIR = Path(__file__).resolve().parent.parent


def raw(**kw):
    row = {c: "" for c in br.RAW_COLUMNS}
    row.update({"조사 날짜": "2026-11-05", "출처": "에브리타임 삼척도계캠 장터게시판"})
    for k, v in kw.items():
        row[{"name": "건물명/대략 주소", "dong": "동네", "deposit": "보증금", "monthly": "월세",
             "fee": "관리비", "inc": "관리비 포함 항목", "memo": "메모", "kind": "자료 종류",
             "size": "평수", "dist": "학교까지 거리", "url": "출처 주소"}.get(k, k)] = v
    return row


class NormalizeTest(unittest.TestCase):
    def test_prepaid_300_over_10_months(self):
        r = br.normalize_row(raw(name="당저동 원룸", dong="당저동", deposit="30", memo="10개월 선세 300만"))
        self.assertEqual(r["contract_type"], "선세")
        self.assertEqual(r["monthly"], "30")
        self.assertEqual((r["prepaid_total"], r["prepaid_months"]), ("300", "10"))

    def test_prepaid_total_typed_in_monthly_column(self):
        r = br.normalize_row(raw(dong="교동(후문)", monthly="300", memo="선세, 10개월 계약"))
        self.assertEqual(r["monthly"], "30")

    def test_prepaid_given_as_monthly_kept(self):
        r = br.normalize_row(raw(dong="당저동", monthly="25(1년 선세 250만, 3~12월)"))
        self.assertEqual(r["monthly"], "25")
        self.assertEqual(r["prepaid_months"], "10")

    def test_yearly_without_months_gives_range(self):
        r = br.normalize_row(raw(dong="마달동", memo="연세 300만, 기간 글에 없음"))
        self.assertEqual(r["contract_type"], "연세")
        self.assertEqual((r["monthly_low"], r["monthly_high"], r["monthly"]), ("25", "30", "27.5"))

    def test_transfer_post(self):
        r = br.normalize_row(raw(
            name="후문 원룸", dong="교동(후문)", monthly="35", kind="양도",
            memo="원래 금액 480(약 1년). 6개월 210(월 35), 4개월 200으로 내려서 양도",
        ))
        self.assertEqual((r["kind"], r["contract_type"], r["show"]), ("양도", "양도", "1"))
        self.assertEqual(r["monthly"], "35")
        self.assertEqual((r["prepaid_total"], r["prepaid_months"], r["orig_total"]), ("210", "6", "480"))

    def test_transfer_from_memo_only(self):
        r = br.normalize_row(raw(dong="교동(정문)", monthly="33", memo="세입자 양도 글, 12월까지 선세"))
        self.assertEqual(r["kind"], "양도")

    def test_transfer_without_period_has_no_monthly(self):
        r = br.normalize_row(raw(dong="당저동", deposit="0", kind="양도", memo="선세 70, 기간 미기재"))
        self.assertEqual(r["monthly"], "")
        self.assertEqual(r["prepaid_total"], "70")

    def test_seek_post_hidden_but_landlord_offer_shown(self):
        seek = br.normalize_row(raw(dong="교동", kind="구함", memo="겨울방학 동안 비는 자취방 구합니다"))
        self.assertEqual((seek["kind"], seek["show"]), ("구함", "0"))
        offer = br.normalize_row(raw(dong="마달동", monthly="27.5", kind="신규 입주자 구함", memo="연세 330"))
        self.assertEqual((offer["kind"], offer["show"]), ("신규 매물", "1"))

    def test_guide_and_dogye_hidden(self):
        self.assertEqual(br.normalize_row(raw(dong="교동", monthly="35~45만", kind="시세 범위(안내문)"))["show"], "0")
        self.assertEqual(br.normalize_row(raw(name="황조길 66 일대(도계읍)", dong="도계읍", monthly="29"))["show"], "0")

    def test_jeonse(self):
        r = br.normalize_row(raw(dong="당저동", deposit="5500", memo="전세", kind="매물 게시 기록(전세)"))
        self.assertEqual((r["contract_type"], r["monthly"], r["deposit"]), ("전세", "", "5500"))

    def test_jeonse_mention_with_monthly_stays_monthly(self):
        r = br.normalize_row(raw(dong="마달동", deposit="200", monthly="30", memo="전세 1,600만도 있다고 적힘"))
        self.assertEqual(r["contract_type"], "월세")

    def test_options_list_is_unknown_type(self):
        r = br.normalize_row(raw(dong="남양동 추정", memo="선세·반전세·전세·월세 가능"))
        self.assertEqual(r["contract_type"], "모름")

    def test_area_classification(self):
        cases = [
            (("교동(후문)", "후문 원룸"), "후문"),
            (("교동(교동택지)", "코아루타워 건너편 원룸단지"), "교동택지"),
            (("교동", "청석로 7-29 일대"), "교동택지"),
            (("교동(정문)", "장기재길 34 일대(정문 쪽)"), "정문"),
            (("교동(신정문) 추정", "대학교 신정문 앞 원룸"), "정문"),
            (("마달동(학교 옆)", "누가아파트(마달1길 75)"), "마달동"),
            (("당저동", "정문~홈플러스 쪽 원룸"), "당저동"),
            (("당저동 추정", "월드마트 부근 원룸"), "당저동"),
            (("남양동 추정", "로얄원룸(대학로 94, 시청 앞)"), "시내"),
            (("정상동", "정라사거리길 29 일대"), "시내"),
            (("사직동", "금빛하우스B"), "시내"),
            (("근덕면", "덕산해변길 34 일대"), "기타"),
            (("위치 글에 없음", "하늘새원룸"), "기타"),
        ]
        for (dong, name), want in cases:
            with self.subTest(dong=dong, name=name):
                self.assertEqual(br.classify_area(dong, name), want)

    def test_area_column_override(self):
        r = br.normalize_row({**raw(dong="교동", name="늘푸른원룸"), "생활권": "정문"})
        self.assertEqual(r["area"], "정문")

    def test_included_items(self):
        cases = [
            ("수도·인터넷·TV·난방비 포함", ["수도", "인터넷", "난방"]),
            ("심야전기 난방, 인터넷 무료(설명글)", ["인터넷"]),
            ("인터넷·난방·수도·온수·가스·공용전기 주인 부담, 방 전기만 세입자", ["수도", "인터넷", "난방", "가스"]),
            ("전기·가스 별도", []),
            ("수도 연 5만, 가스·전기 세입자", []),
            ("관리비·인터넷 포함", ["인터넷", "관리비"]),
            ("전기·수도·TV·인터넷·와이파이 포함", ["수도", "인터넷", "전기"]),
        ]
        for text, want in cases:
            with self.subTest(text=text):
                self.assertEqual(br.included_items(text), want)
        self.assertEqual(br.included_items("", "6만(인터넷 포함)"), ["인터넷"])

    def test_fee(self):
        for text, want in [("6만원", 6.0), ("1만", 1.0), ("10만원 안팎", 10.0), ("0", 0.0), ("월세에 포함", 0.0),
                           ("없음(설명글)", 0.0), ("적힌 금액 없음", None), ("별도", None), ("협의", None), ("", None)]:
            with self.subTest(text=text):
                self.assertEqual(br.parse_fee(text), want)

    def test_size(self):
        self.assertEqual(br.parse_size_m2("9평(29.8㎡)"), 29.8)
        self.assertEqual(br.parse_size_m2("20.89㎡(6.3평)"), 20.89)
        self.assertAlmostEqual(br.parse_size_m2("17평(공급 기준 추정)"), 56.2, places=1)
        self.assertIsNone(br.parse_size_m2("면적 미기재"))

    def test_sanitize_removes_contacts_units_urls(self):
        t = br.sanitize("○○원룸 302호, 연락 010-1234-5678, 카톡 아이디 abc, https://everytime.kr/123 참고")
        self.assertNotIn("302호", t)
        self.assertNotIn("010", t)
        self.assertNotIn("abc", t)
        self.assertNotIn("everytime", t)
        self.assertIn("○○원룸", t)
        self.assertEqual(br.sanitize("2026-11-05"), "2026-11-05")
        self.assertEqual(br.sanitize("1호선 근처"), "1호선 근처")

    def test_source_url_and_phone_not_in_output(self):
        r = br.normalize_row(raw(name="원룸 201호", memo="문의 010 9876 5432", url="https://everytime.kr/x/1"))
        joined = " ".join(r.values())
        self.assertNotIn("everytime.kr", joined)
        self.assertNotIn("9876", joined)
        self.assertNotIn("201호", joined)
        self.assertEqual(r["source"], "에브리타임 장터게시판")


class BuildTest(unittest.TestCase):
    def test_build_real_raw_files(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "rooms.csv"
            rooms = br.build(APP_DIR / "data" / "raw", out)
            self.assertGreater(len(rooms), 50)
            text = out.read_text(encoding="utf-8-sig")
            self.assertNotRegex(text, r"https?://")
            self.assertNotRegex(text, r"01[016789][-\s]?\d{3,4}[-\s]?\d{4}")
            header = next(csv.reader(text.splitlines()))
            self.assertEqual(header, br.ROOM_FIELDS)
            self.assertTrue(all(r["area"] in br.AREAS for r in rooms))
            self.assertTrue(all(r["contract_type"] in br.CONTRACT_TYPES for r in rooms))

    def test_missing_columns_is_clear_error(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "bad.csv").write_text("조사 날짜,출처\n2026-11-05,에타\n", encoding="utf-8-sig")
            with self.assertRaises(ValueError) as cm:
                br.build(Path(d), Path(d) / "out.csv")
            self.assertIn("동네", str(cm.exception))


def room(**kw):
    base = {"id": "r1", "show": True, "area": "후문", "kind": "신규 매물", "contract_type": "월세",
            "monthly": 30.0, "monthly_low": 30.0, "monthly_high": 30.0, "included": [], "size_m2": None,
            "deposit": 100.0, "name": "방", "source": "당근부동산", "surveyed": "2026-11-05",
            "fee": None, "fee_text": ""}
    base.update(kw)
    return base


class RoomsDataTest(unittest.TestCase):
    def setUp(self):
        self.rooms = [
            room(id="a", area="후문", monthly=30.0, monthly_low=30.0, monthly_high=30.0, included=["인터넷", "수도"]),
            room(id="b", area="후문", monthly=40.0, monthly_low=40.0, monthly_high=40.0, kind="양도", contract_type="양도"),
            room(id="c", area="당저동", monthly=27.5, monthly_low=25.0, monthly_high=30.0, contract_type="연세"),
            room(id="d", area="당저동", monthly=None, monthly_low=None, monthly_high=None, contract_type="전세"),
            room(id="e", area="시내", show=False),
        ]

    def ids(self, rooms):
        return [r["id"] for r in rooms]

    def test_filter_defaults_hide_unknown_and_hidden(self):
        self.assertEqual(self.ids(rd.filter_rooms(self.rooms)), ["a", "b", "c"])
        self.assertEqual(self.ids(rd.filter_rooms(self.rooms, include_unknown_price=True)), ["a", "b", "c", "d"])

    def test_filter_by_each_condition(self):
        self.assertEqual(self.ids(rd.filter_rooms(self.rooms, areas=["당저동"])), ["c"])
        self.assertEqual(self.ids(rd.filter_rooms(self.rooms, monthly_range=(0, 26))), ["c"])
        self.assertEqual(self.ids(rd.filter_rooms(self.rooms, monthly_range=(31, 45))), ["b"])
        self.assertEqual(self.ids(rd.filter_rooms(self.rooms, contract_types=["양도"])), ["b"])
        self.assertEqual(self.ids(rd.filter_rooms(self.rooms, kinds=["신규 매물"])), ["a", "c"])
        self.assertEqual(self.ids(rd.filter_rooms(self.rooms, required_items=["인터넷", "수도"])), ["a"])
        self.assertEqual(self.ids(rd.filter_rooms(self.rooms, required_items=["인터넷", "난방"])), [])

    def test_sort_puts_unknown_last(self):
        self.assertEqual(self.ids(rd.sort_rooms(self.rooms[:4])), ["c", "a", "b", "d"])

    def test_area_medians_exclude_transfer_and_large(self):
        rooms = [room(id=str(i), monthly=float(v)) for i, v in enumerate([30, 34, 40])]
        rooms += [room(id="t", monthly=10.0, kind="양도"), room(id="big", monthly=90.0, size_m2=80.0)]
        m = rd.area_medians(rooms)
        self.assertEqual(m["후문"], {"median": 34.0, "count": 3})
        cmp = rd.compare_to_area(room(monthly=40.0), m)
        self.assertEqual(cmp["diff"], 6.0)
        self.assertEqual(rd.compare_text(cmp), "생활권 가운데 값(34만 원)보다 6만 원 비싸요")
        self.assertIn("싸요", rd.compare_text(rd.compare_to_area(room(monthly=30.0), m)))
        self.assertIsNone(rd.compare_to_area(room(area="당저동"), m))
        self.assertIsNone(rd.compare_to_area(room(area="기타"), {"기타": {"median": 30, "count": 9}}))

    def test_selected_room_contract(self):
        sel = rd.to_selected_room(room(fee=5.0, included=["수도"]))
        self.assertEqual(
            set(sel),
            {"name", "area", "contract_type", "deposit", "monthly", "fee_text", "included", "source", "surveyed", "kind"},
        )
        self.assertEqual(sel["fee_text"], "관리비 5만 원")
        self.assertEqual(sel["included"], ["수도"])
        self.assertIn(sel["contract_type"], rd.CONTRACT_TYPES)

    def test_fmt(self):
        self.assertEqual(rd.fmt_man(27.5), "27.5")
        self.assertEqual(rd.fmt_man(30.0), "30")
        self.assertEqual(rd.fmt_man(5500), "5,500")
        self.assertEqual(rd.monthly_text(self.rooms[2]), "25~30만 원")

    def test_read_generated_rooms_csv(self):
        rooms = rd.read_rooms(APP_DIR / "data" / "rooms.csv")
        self.assertTrue(rooms)
        self.assertTrue(all(isinstance(r["show"], bool) for r in rooms))
        self.assertTrue(all(isinstance(r["included"], list) for r in rooms))

    def test_baseline_missing_is_none(self):
        self.assertIsNone(rd.load_baseline(APP_DIR / "data" / "no_such_file.csv"))
        self.assertIsNone(rd.baseline_summary(None))

    def test_baseline_molit_export(self):
        text = (
            "□ 본 서비스에서 제공하는 정보는 법적인 효력이 없으므로 참고용으로만 활용하시기 바랍니다.\n"
            "\n"
            "NO,시군구,도로조건,계약면적(㎡),전월세구분,계약년월,계약일,보증금(만원),월세금(만원),건축년도\n"
            '1,강원특별자치도 삼척시 교동,8m미만,30.5,월세,202607,3,"300",40,2010\n'
            "2,강원특별자치도 삼척시 교동,8m미만,25,월세,202608,9,200,30,2012\n"
            "3,강원특별자치도 삼척시 교동,8m미만,85,월세,202608,9,1000,70,2012\n"
            '4,강원특별자치도 삼척시 남양동,8m미만,33,전세,202609,1,"5,000",0,2001\n'
            "5,강원특별자치도 삼척시 남양동,8m미만,20,월세,202609,1,100,25,2001\n"
        )
        b = rd.parse_baseline_text(text)
        self.assertEqual(b["count"], 3)
        self.assertEqual(b["by_dong"]["교동"]["monthly_median"], 35)
        self.assertEqual(b["period"], "202607~202609")
        self.assertEqual(rd.baseline_summary(b, ["후문"])["monthly_median"], 35)
        self.assertEqual(rd.baseline_summary(b)["label"], "삼척시 전체")
        self.assertIsNone(rd.baseline_summary(b, ["기타"]))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "baseline_molit.csv"
            p.write_bytes(text.encode("cp949"))
            self.assertEqual(rd.load_baseline(p)["count"], 3)


class RoomsPageTest(unittest.TestCase):
    def setUp(self):
        from streamlit.testing.v1 import AppTest

        self.at = AppTest.from_file(str(APP_DIR / "app.py"), default_timeout=30).run()

    def metric(self, label):
        return next(m.value for m in self.at.metric if m.label == label)

    def test_page_renders_without_exception(self):
        at = self.at
        self.assertFalse(at.exception)
        self.assertEqual(at.title[0].value, "삼척 자취방 시세")
        self.assertFalse(at.error)
        self.assertGreater(len(at.button), 10)
        self.assertEqual(self.metric("공공데이터 기준선"), "월 40만 원")
        texts = " ".join(m.value for m in at.markdown)
        self.assertIn("실제 매물 여부는 연락해서 확인하세요", texts)
        self.assertNotRegex(texts, r"https?://|01[016789]-\d{3,4}-\d{4}")
        at.pills(key="rooms_kind").select("양도").run()
        transfer = next(b.key for b in at.button if b.key and b.key.startswith("pick_"))
        at.button(key=transfer).click().run()
        self.assertIn("집주인 동의 확인", " ".join(m.value for m in at.markdown))

    def test_filters_change_results(self):
        at = self.at
        total = int(re.sub(r"\D", "", self.metric("조건에 맞는 방")))
        at.pills(key="rooms_area").select("마달동").run()
        mad = int(re.sub(r"\D", "", self.metric("조건에 맞는 방")))
        self.assertLess(mad, total)
        self.assertEqual(len(at.button), mad)
        at.slider(key="rooms_monthly").set_value((0, 28)).run()
        self.assertLess(int(re.sub(r"\D", "", self.metric("조건에 맞는 방"))), mad)
        at.pills(key="rooms_area").unselect("마달동").run()
        at.slider(key="rooms_monthly").set_value((0, 60)).run()
        at.pills(key="rooms_items").select("인터넷").run()
        self.assertLess(int(re.sub(r"\D", "", self.metric("조건에 맞는 방"))), total)
        at.checkbox(key="rooms_unknown").check().run()
        self.assertFalse(at.exception)

    def test_check_button_hands_over_selected_room(self):
        at = self.at
        first = next(b.key for b in at.button if b.key and b.key.startswith("pick_")).removeprefix("pick_")
        at.button(key=f"pick_{first}").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["room_selected_id"], first)
        at.button(key=f"check_{first}").click().run()
        self.assertFalse(at.exception)
        sel = at.session_state["selected_room"]
        for key in ("name", "area", "contract_type", "deposit", "monthly", "fee_text", "included", "source", "surveyed"):
            self.assertIn(key, sel)
        self.assertEqual(at.title[0].value, "계약서 점검")


if __name__ == "__main__":
    unittest.main()
