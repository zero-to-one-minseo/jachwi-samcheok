import unittest
from datetime import date, datetime, timedelta, timezone

from lib import limits, rules
from lib.criteria import Criterion
from lib.render import escape_md, footer_text, questions_copy_text, source_markdown, ReportMeta
from lib.schema import AnalysisOutput, Clause, FeeItem, ManagementFee


def crit(cid, *, kind="근거 줄", judge="AI", link="https://example.org/x", checked="2026-11-05", name=None,
         category="퇴실·원상복구"):
    return Criterion(
        id=cid, name=name or f"{cid} 이름", category=category, row_kind=kind, judge=judge, check="", warn_signs="",
        ok_looks="", plain_explanation=f"{cid} 검수된 설명이에요.", basis=f"{cid} 근거 문장이에요. 6개월~2개월 전",
        basis_limits=f"{cid} 한계", source_name=f"[출처]({link})" if link else "", source_link=link,
        checked_date=checked, default_question=f"{cid} 기본 질문을 여쭤봐도 될까요?",
    )


BY_ID = {
    "퇴실-01": crit("퇴실-01"),
    "수리-01": crit("수리-01", category="수리·하자"),
    "기간-01": crit("기간-01", category="계약 기간·갱신"),
    "기간-04": crit("기간-04", checked=""),
    "기간-05": crit("기간-05", kind="질문 전용 줄", link=""),
    "보증-01": crit("보증-01", kind="질문 전용 줄", link=""),
    "관리-01": crit("관리-01", judge="코드", category="관리비"),
}
for i in range(1, 9):
    BY_ID[f"좋음-0{i}"] = crit(f"좋음-0{i}")
    BY_ID[f"질문-0{i}"] = crit(f"질문-0{i}")


def clause(cid="퇴실-01", grade="주의", quote="퇴실 시 청소비 10만 원을 공제한다.", text_kind="인쇄 글자",
           explanation="청소비가 빠져요.", question="청소 범위를 알려 주실 수 있을까요?", title="AI 제목", location=""):
    return Clause(criterion_id=cid, title=title, grade=grade, quote=quote, location=location, text_kind=text_kind,
                  explanation=explanation, question=question)


def fee(mention="금액 있음", won=120000, billing="정액", itemized="없음", items=(), source="관리비 월 120,000원 (정액)",
        amount="120,000원"):
    return ManagementFee(mention=mention, amount_text=amount, monthly_won=won, billing=billing, itemized=itemized,
                         items=[FeeItem(name=n, amount_text=a) for n, a in items], source_text=source)


def output(clauses=(), management_fee=None, doc_type="계약서", contract_type="월세", read_state="잘 읽힘",
           hidden="없음", read_note=""):
    return AnalysisOutput(doc_type=doc_type, contract_type=contract_type, read_state=read_state, read_note=read_note,
                          hidden_instruction=hidden, clauses=list(clauses),
                          management_fee=management_fee or fee(mention="언급 없음", won=0, source="", amount=""))


class FeeTableTest(unittest.TestCase):
    def judge(self, f, doc_type="계약서"):
        return rules.judge_fee(f, doc_type, BY_ID)

    def test_fixed_over_threshold_no_items(self):
        card = self.judge(fee())
        self.assertEqual(card.grade, rules.CHECK)
        self.assertEqual(card.label, "항목별 금액을 찾지 못함")
        self.assertEqual(card.formula, "120,000 ≥ 100,000")
        self.assertEqual(card.summary, "관리비 월 120,000원 · 정액 · 항목별 금액 없음")
        self.assertEqual(card.question, BY_ID["관리-01"].default_question)
        self.assertTrue(card.evidence.basis.endswith(rules.FEE_NOT_FOUND_SUFFIX))
        self.assertEqual(card.criterion_id, "관리-01")

    def test_boundary_values(self):
        self.assertEqual(self.judge(fee(won=100000)).grade, rules.CHECK)
        self.assertEqual(self.judge(fee(won=100000)).formula, "100,000 ≥ 100,000")
        low = self.judge(fee(won=99999))
        self.assertEqual((low.grade, low.label, low.formula), (rules.NOTE, "포함 항목 확인", "99,999 < 100,000"))
        self.assertIsNone(low.evidence)

    def test_partial_items(self):
        card = self.judge(fee(itemized="일부", items=[("수도료", "20,000원"), ("인터넷", "")]))
        self.assertEqual((card.grade, card.label), (rules.CHECK, "항목별 금액 확인"))
        self.assertEqual(card.items, [("수도료", "20,000원"), ("인터넷", "")])

    def test_full_items_is_ok_with_table(self):
        items = [("일반(공용)관리비", "50,000"), ("수도료", "20,000"), ("인터넷 사용료", "20,000"),
                 ("TV 사용료", "10,000"), ("기타관리비", "20,000")]
        card = self.judge(fee(itemized="있음", items=items))
        self.assertEqual(card.grade, rules.OK)
        self.assertEqual(len(card.items), 5)
        self.assertEqual(card.question, "")
        self.assertFalse(card.evidence.basis.endswith(rules.FEE_NOT_FOUND_SUFFIX))

    def test_full_items_without_source_text_is_not_green(self):
        card = self.judge(fee(itemized="있음", items=[("수도료", "20,000")], source="", amount=""))
        self.assertEqual(card.grade, rules.CHECK)

    def test_usage_and_mixed(self):
        for billing in ("사용량", "섞임"):
            card = self.judge(fee(billing=billing, won=80000))
            self.assertEqual((card.grade, card.label), (rules.CHECK, "월 평균 금액과 포함 항목 물어보기"))
            self.assertEqual(card.question, rules.FEE_Q_USAGE)

    def test_not_mentioned_or_unreadable(self):
        none = self.judge(fee(mention="언급 없음", won=0, source="", amount=""))
        self.assertEqual((none.grade, none.label), (rules.CHECK, "관리비 칸 직접 확인"))
        self.assertEqual(none.formula, "")
        # 금액 못 읽음이면 AI가 숫자를 줘도 금액으로 판정하지 않는다.
        unread = self.judge(fee(mention="금액 못 읽음", won=120000))
        self.assertEqual((unread.grade, unread.label, unread.formula), (rules.CHECK, "관리비 칸 직접 확인", ""))
        zero = self.judge(fee(won=0))
        self.assertEqual(zero.label, "관리비 칸 직접 확인")

    def test_suspicious_amount(self):
        card = self.judge(fee(won=600000))
        self.assertEqual((card.grade, card.label), (rules.CHECK, "월세나 보증금을 잘못 읽었을 수 있음"))
        self.assertEqual(card.formula, "600,000 > 500,000")
        self.assertEqual(self.judge(fee(won=500000)).label, "항목별 금액을 찾지 못함")

    def test_unknown_billing(self):
        card = self.judge(fee(billing="알 수 없음"))
        self.assertEqual(card.grade, rules.CHECK)
        self.assertEqual(self.judge(fee(billing="알 수 없음", won=50000)).grade, rules.NOTE)

    def test_fixed_guessed_without_word(self):
        card = self.judge(fee(source="관리비 매달 120,000원", amount="120,000원"))
        self.assertIn("정액으로 보임", card.summary)

    def test_bill_document_has_no_threshold_rule(self):
        bill = self.judge(fee(itemized="없음"), doc_type="관리비 내역")
        self.assertEqual((bill.grade, bill.label), (rules.CHECK, "관리인에게 내역을 요청해 보세요"))
        self.assertIsNone(bill.evidence)
        self.assertEqual(bill.formula, "")
        listed = self.judge(fee(itemized="있음", items=[("수도료", "1")]), doc_type="관리비 내역")
        self.assertEqual(listed.grade, rules.NOTE)
        self.assertIsNone(listed.evidence)

    def test_other_documents_have_no_fee_card(self):
        for doc_type in ("등기부", "확인설명서", "기타"):
            self.assertIsNone(self.judge(fee(), doc_type=doc_type))

    def test_fee_card_pinned_and_question_after_warnings(self):
        report = rules.apply_rules(output([clause("보증-01", "확인 필요", quote=""), clause()], fee()), BY_ID)
        self.assertEqual(report.answer_lines[0], "관리-01:확인 필요")
        self.assertEqual(report.questions[0], "청소 범위를 알려 주실 수 있을까요?")
        self.assertEqual(report.questions[1], BY_ID["관리-01"].default_question)

    def test_fee_clause_from_ai_is_dropped(self):
        report = rules.apply_rules(output([clause("관리-01", "주의")], fee()), BY_ID)
        self.assertEqual([c.criterion_id for c in report.cards], [])
        self.assertEqual(report.fee.criterion_id, "관리-01")


class GradeCapTest(unittest.TestCase):
    def card(self, **kw):
        return rules.build_card(clause(**kw), BY_ID)

    def test_evidence_row_keeps_warning_with_quote(self):
        card = self.card()
        self.assertEqual(card.grade, rules.WARN)
        self.assertEqual(card.title, "퇴실-01 이름")
        self.assertIsNotNone(card.evidence)
        self.assertFalse(card.grade_changed)

    def test_other_and_unknown_ids(self):
        for cid in ("기타", "없는-99"):
            card = self.card(cid=cid, title="AI가 만든 제목")
            self.assertEqual(card.criterion_id, rules.OTHER_ID)
            self.assertEqual(card.grade, rules.CHECK)
            self.assertIn(rules.TAG_AI_OPINION, card.tags)
            self.assertIsNone(card.evidence)
            self.assertEqual(card.title, "AI가 만든 제목")
            self.assertEqual(card.question, "청소 범위를 알려 주실 수 있을까요?")

    def test_bracketed_id_is_matched(self):
        self.assertEqual(self.card(cid="[퇴실-01]").criterion_id, "퇴실-01")

    def test_question_only_rows_cap(self):
        for grade in ("주의", "괜찮음"):
            card = self.card(cid="기간-05", grade=grade)
            self.assertEqual(card.grade, rules.CHECK)
            self.assertIn(rules.NOTE_QUESTION_ROW, card.grade_notes)
            self.assertIsNone(card.evidence)
        # 근거 줄이어도 확인 날짜가 비면 질문 전용으로 본다.
        self.assertEqual(self.card(cid="기간-04").grade, rules.CHECK)

    def test_no_quote_lowers_red_and_green(self):
        for grade in ("주의", "괜찮음"):
            card = self.card(grade=grade, quote="  ")
            self.assertEqual(card.grade, rules.CHECK)
            self.assertIn(rules.NOTE_NO_QUOTE, card.grade_notes)
        self.assertEqual(self.card(grade="확인 필요", quote="").grade, rules.CHECK)

    def test_handwriting_or_blur_cannot_be_green(self):
        for kind in ("손글씨", "흐려서 불확실"):
            card = self.card(grade="괜찮음", text_kind=kind, quote="반려동물 금지")
            self.assertEqual(card.grade, rules.CHECK)
            self.assertIn(rules.NOTE_HANDWRITING, card.grade_notes)
        self.assertEqual(self.card(grade="주의", text_kind="손글씨").grade, rules.WARN)

    def test_handwritten_number_tag_and_question(self):
        card = self.card(text_kind="손글씨", quote="청소비 10만 원", question="청소비 10만 원은 언제 내나요?")
        self.assertIn(rules.TAG_READ_VALUE, card.tags)
        self.assertEqual(card.question, BY_ID["퇴실-01"].default_question)
        printed = self.card(quote="청소비 10만 원", question="청소비 10만 원은 언제 내나요?")
        self.assertNotIn(rules.TAG_READ_VALUE, printed.tags)

    def test_ok_card_has_no_question_and_empty_question_filled(self):
        self.assertEqual(self.card(grade="괜찮음", question="물어볼까요?").question, "")
        self.assertEqual(self.card(question="").question, BY_ID["퇴실-01"].default_question)

    def test_explanation_cut_to_two_sentences(self):
        card = self.card(explanation="하나예요. 둘이에요. 셋이에요.")
        self.assertEqual(card.explanation, "하나예요. 둘이에요.")
        self.assertEqual(self.card(explanation="").explanation, BY_ID["퇴실-01"].plain_explanation)


class LegalRewriteTest(unittest.TestCase):
    def test_detection(self):
        for text in ("이 특약은 무효예요.", "불법이에요", "효력이 없어요", "법에 어긋나요", "돌려받을 수 있어요",
                     "안 지켜도 돼요", "주택임대차보호법에 따라", "민법상", "제10조에 따라", "제 7 조", "소송을 걸 수"):
            self.assertTrue(rules.has_legal_expression(text), text)
        for text in ("방법을 알려 주세요", "보증금 1~2개월", "법인 계좌", ""):
            self.assertFalse(rules.has_legal_expression(text), text)

    def test_sentence_replaced_grade_kept(self):
        card = rules.build_card(clause(explanation="이런 특약은 무효예요. 큰 고장도 내가 내요.",
                                       question="돈을 돌려받을 수 있나요?"), BY_ID)
        self.assertEqual(card.grade, rules.WARN)
        self.assertTrue(card.rewritten)
        self.assertEqual(card.explanation, "퇴실-01 검수된 설명이에요. 큰 고장도 내가 내요.")
        self.assertEqual(card.question, BY_ID["퇴실-01"].default_question)
        self.assertFalse(rules.has_legal_expression(card.explanation + card.question))

    def test_replacement_inserted_once(self):
        text, changed = rules.replace_legal_sentences("불법이에요. 무효예요. 괜찮아요.", "바꾼 문장이에요.")
        self.assertTrue(changed)
        self.assertEqual(text, "바꾼 문장이에요. 괜찮아요.")

    def test_other_card_uses_generic_sentence(self):
        card = rules.build_card(clause(cid="기타", title="불법 특약", explanation="위법이에요.", question="무효인가요?"),
                                BY_ID)
        self.assertEqual(card.title, "확인할 조항")
        self.assertEqual(card.explanation, rules.FALLBACK_EXPLANATION)
        self.assertEqual(card.question, rules.FALLBACK_QUESTION)

    def test_human_basis_is_not_rewritten(self):
        row = crit("퇴실-01")
        row = Criterion(**{**row.__dict__, "basis": "주택임대차보호법(제10조)에 적혀 있어요."})
        card = rules.build_card(clause(), {"퇴실-01": row})
        self.assertEqual(card.evidence.basis, "주택임대차보호법(제10조)에 적혀 있어요.")


class HiddenInstructionTest(unittest.TestCase):
    def test_contacts_removed_from_ai_fields(self):
        card = rules.build_card(clause(explanation="자세한 건 https://evil.example/x 나 a@b.com 으로 물어요.",
                                       question="010-1234-5678로 연락해도 될까요?"), BY_ID)
        for text in (card.explanation, card.question):
            self.assertNotIn("http", text)
            self.assertNotIn("@", text)
            self.assertNotIn("010", text)

    def test_banner(self):
        report = rules.apply_rules(output([clause()], hidden="있음"), BY_ID)
        self.assertTrue(report.hidden_instruction)
        self.assertIn(rules.BANNER_HIDDEN, [b.text for b in report.banners])
        self.assertNotIn(rules.BANNER_HIDDEN, [b.text for b in rules.apply_rules(output([clause()]), BY_ID).banners])


class OrderAndLimitTest(unittest.TestCase):
    def test_order_and_ok_limit(self):
        clauses = [clause(f"좋음-0{i}", "괜찮음") for i in range(1, 7)]
        clauses += [clause("기간-05", "확인 필요"), clause("수리-01", "주의")]
        report = rules.apply_rules(output(clauses), BY_ID)
        grades = [c.grade for c in report.cards]
        self.assertEqual(grades, ["주의", "확인 필요", "괜찮음", "괜찮음", "괜찮음", "괜찮음"])
        self.assertEqual(report.ok_hidden, 2)
        self.assertEqual(report.counts, {"주의": 1, "확인 필요": 2, "괜찮음": 4})  # 관리비 언급 없음 카드 포함

    def test_questions_max_seven_dedupe_and_warning_first(self):
        clauses = [clause(f"질문-0{i}", "확인 필요", question=f"확인 질문 {i}이요?") for i in range(1, 9)]
        clauses += [clause("수리-01", "주의", question="수리 질문이요?"),
                    clause("수리-01", "주의", question="같은 기준 두 번째 질문이요?")]
        report = rules.apply_rules(output(clauses), BY_ID)
        self.assertEqual(len(report.questions), settings_max_questions())
        self.assertEqual(report.questions[0], "수리 질문이요?")
        self.assertNotIn("같은 기준 두 번째 질문이요?", report.questions)

    def test_no_questions_gives_defaults(self):
        self.assertEqual(rules.build_questions([], None), list(rules.DEFAULT_QUESTIONS))

    def test_other_questions_not_merged_by_id(self):
        cards = [rules.build_card(clause("기타", "확인 필요", question=f"기타 질문 {i}이요?"), BY_ID) for i in range(3)]
        self.assertEqual(len(rules.build_questions(cards, None)), 3)

    def test_jeonse_hides_ok_cards(self):
        report = rules.apply_rules(output([clause("좋음-01", "괜찮음"), clause()], contract_type="전세"), BY_ID)
        self.assertEqual([c.grade for c in report.cards], ["주의"])
        self.assertEqual(report.ok_hidden, 1)
        self.assertIn(rules.BANNER_JEONSE, [b.text for b in report.banners])

    def test_unreadable_and_not_interpreted(self):
        unreadable = rules.apply_rules(output([clause()], fee(), read_state="읽기 어려움"), BY_ID)
        self.assertTrue(unreadable.unreadable)
        self.assertEqual((unreadable.cards, unreadable.fee, unreadable.questions), ([], None, []))
        registry = rules.apply_rules(output([clause()], fee(), doc_type="등기부"), BY_ID)
        self.assertTrue(registry.not_interpreted)
        self.assertEqual((registry.cards, registry.fee), ([], None))
        other = rules.apply_rules(output([clause()], doc_type="기타"), BY_ID)
        self.assertIn(rules.BANNER_NOT_CONTRACT, [b.text for b in other.banners])

    def test_blurry_banner_and_note_masked(self):
        report = rules.apply_rules(output([clause()], read_state="일부 흐림", read_note="010-1111-2222 옆이 흐림"), BY_ID)
        self.assertIn(rules.BANNER_BLURRY, [b.text for b in report.banners])
        self.assertNotIn("1111", report.read_note)


def settings_max_questions():
    from lib import settings
    return settings.MAX_QUESTIONS


class PiiMaskTest(unittest.TestCase):
    def test_masks(self):
        cases = {
            "주민번호 000000-0000000": "000000",
            "주민 990101-1234567 이다": "1234567",
            "전화 010-0000-0000": "0000-0000",
            "전화 01012345678": "01012345678",
            "전화 010 1234 5678": "1234 5678",
            "사무실 033-570-6000": "570-6000",
            "계좌 000-00-000000": "000-00-000000",
            "농협 3021234567891": "3021234567891",
            "국민은행 123456-01-234567": "234567",
            "예금주 확인 계좌번호 1002 345 678901": "678901",
        }
        for text, secret in cases.items():
            masked = rules.mask_pii(text)
            self.assertNotIn(secret, masked, text)
            self.assertIn(rules.MASK, masked, text)

    def test_keeps_dates_and_money(self):
        for text in ("2026-03-01", "2027년 3월 1일부터 2028년 2월 29일까지", "2026.03.01", "관리비 120,000원",
                     "선세 3300000원", "보증금 300만 원", "1~2개월", "제2조 3항", "우리 집 보증금 3000000원"):
            self.assertEqual(rules.mask_pii(text), text)

    def test_report_masks_quotes_fee_and_questions(self):
        clauses = [clause("기타", "확인 필요", quote="임대인 연락처 010-9999-8888", question="010-9999-8888로 보내도 될까요?")]
        f = fee(source="관리비 월 120,000원, 입금 계좌 000-00-000000", items=[("관리비 계좌 000-11-222222", "120,000원")])
        report = rules.apply_rules(output(clauses, f), BY_ID)
        text = " ".join([report.cards[0].quote, report.cards[0].question, report.fee.source_text,
                         report.fee.items[0][0]] + report.questions)
        for secret in ("9999-8888", "000-00-000000", "222222"):
            self.assertNotIn(secret, text)
        self.assertIn("120,000원", report.fee.source_text)


class EscapeTest(unittest.TestCase):
    def test_markdown_symbols(self):
        self.assertEqual(escape_md("1~2개월"), "1\\~2개월")
        self.assertEqual(escape_md("$5와 $6"), "\\$5와 \\$6")
        self.assertEqual(escape_md("[개인정보]"), "\\[개인정보\\]")
        self.assertEqual(escape_md("**굵게** _기울임_ `코드`"), "\\*\\*굵게\\*\\* \\_기울임\\_ \\`코드\\`")
        self.assertNotIn(":red[", escape_md(":red[계좌]"))
        self.assertNotIn(":smile:", escape_md(":smile:"))
        self.assertEqual(escape_md("특약:수리:").replace("​", ""), "특약:수리:")
        self.assertEqual(escape_md("- 목록"), "\\- 목록")
        self.assertEqual(escape_md("1. 첫째"), "1\\. 첫째")
        self.assertEqual(escape_md("# 제목"), "\\# 제목")
        self.assertEqual(escape_md(None), "")

    def test_source_markdown(self):
        md = source_markdown("[민법](https://law.example/a) · [대법원](https://law.example/b)", "https://law.example/a")
        self.assertEqual(md, "[민법](https://law.example/a) · [대법원](https://law.example/b)")
        self.assertEqual(source_markdown("민법 https://law.example/a", "https://law.example/a"),
                         "[민법](https://law.example/a)")
        self.assertEqual(source_markdown("이름만~", ""), "이름만\\~")

    def test_copy_text_and_footer(self):
        text = questions_copy_text(["질문 하나요?", "질문 둘이요?"])
        self.assertTrue(text.endswith("1. 질문 하나요?\n2. 질문 둘이요?"))
        footer = footer_text(ReportMeta("claude-opus-5-5", "medium", 41.25, 15, "26c91e55"))
        self.assertEqual(footer, "답한 모델 claude-opus-5-5 · effort medium · 걸린 시간 41.2초 · 기준 목록 15개(버전 26c91e55)")


class LimitsTest(unittest.TestCase):
    def test_daily_counter(self):
        counter = limits.DailyCounter()
        day = date(2026, 11, 5)
        self.assertTrue(counter.try_take(2, day))
        self.assertTrue(counter.try_take(2, day))
        self.assertFalse(counter.try_take(2, day))
        self.assertEqual(counter.used(day), 2)
        self.assertTrue(counter.try_take(2, date(2026, 11, 6)))
        self.assertEqual(counter.used(day), 0)

    def test_kst_date(self):
        utc_evening = datetime(2026, 11, 5, 15, 30, tzinfo=timezone.utc)
        self.assertEqual(limits.kst_today(utc_evening), date(2026, 11, 6))
        self.assertEqual(limits.kst_today(utc_evening - timedelta(hours=1)), date(2026, 11, 5))

    def test_session_then_daily(self):
        state, counter, day = {}, limits.DailyCounter(), date(2026, 11, 5)
        for _ in range(2):
            self.assertEqual(limits.try_take_call(state, counter, session_limit=2, daily_limit=5, today=day),
                             (True, None))
        self.assertEqual(limits.try_take_call(state, counter, session_limit=2, daily_limit=5, today=day),
                         (False, "session"))
        self.assertEqual(counter.used(day), 2)
        other = {}
        self.assertEqual(limits.try_take_call(other, counter, session_limit=9, daily_limit=2, today=day),
                         (False, "daily"))
        self.assertEqual(limits.session_used(other), 0)
        self.assertEqual(limits.session_left(state, 10), 8)

    def test_on_call_records_reason(self):
        state = {limits.SESSION_COUNT_KEY: 3}
        on_call = limits.make_on_call(state, limits.DailyCounter(), session_limit=3)
        self.assertFalse(on_call())
        self.assertEqual(state[limits.LIMIT_REASON_KEY], "session")
        self.assertIn("저장된 결과", limits.limit_message("session"))
        self.assertIn("오늘", limits.limit_message("daily"))


if __name__ == "__main__":
    unittest.main()
