"""19:45 리뷰 지적을 고친 동작을 지키는 시험."""

import unittest

import anthropic
import httpx2

from lib import rules
from tests.test_contract_ai import URL, FakeClient, response, run
from tests.test_rules import BY_ID, fee
from tools.build_rooms import sanitize, vague_place


class AccountMaskTest(unittest.TestCase):
    def test_amounts_and_dates_next_to_bank_words_stay(self):
        for text in ("월세는 농협 계좌로 매월 1000000원", "은행 송금, 보증금 5000000원", "계좌이체 2026 03 01 까지"):
            self.assertEqual(rules.mask_pii(text), text)

    def test_account_numbers_are_still_masked(self):
        self.assertIn(rules.MASK, rules.mask_pii("농협 계좌 3021234567891"))
        self.assertIn(rules.MASK, rules.mask_pii("입금 계좌: 신한은행 110-123-456789"))


class FeeGreenNeedsItemAmountsTest(unittest.TestCase):
    def test_itemized_without_any_item_amount_is_not_green(self):
        card = rules.judge_fee(fee(itemized="있음", items=[("수도", ""), ("인터넷", "")]), "계약서", BY_ID)
        self.assertEqual(card.grade, rules.CHECK)
        self.assertEqual(card.label, "항목별 금액 원문 확인")

    def test_itemized_with_amounts_is_green(self):
        card = rules.judge_fee(fee(itemized="있음", items=[("수도", "20,000원"), ("인터넷", "30,000원")]), "계약서", BY_ID)
        self.assertEqual(card.grade, rules.OK)


class SingleRetryTest(unittest.TestCase):
    def test_connection_error_then_truncation_sends_only_twice(self):
        err = anthropic.APIConnectionError(request=httpx2.Request("POST", URL))
        client = FakeClient(err, response(stop_reason="max_tokens", text='{"doc'))
        result, _, _ = run(client)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.status, "truncated")


class VaguePlaceTest(unittest.TestCase):
    def test_lot_numbers_and_floors_are_removed(self):
        self.assertEqual(vague_place("당저동1길 51-3 일대 2층"), "당저동1길 일대")
        self.assertEqual(vague_place("당저동 125-3"), "당저동")
        self.assertEqual(vague_place("학사빌라(마달길 103-16)"), "학사빌라(마달길)")
        self.assertEqual(vague_place("○○원룸"), "○○원룸")

    def test_hosil_is_removed(self):
        self.assertNotIn("302", sanitize("후문 원룸 302호실 양도"))


if __name__ == "__main__":
    unittest.main()
