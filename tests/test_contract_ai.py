import contextlib
import io
import json
import unittest
from types import SimpleNamespace
from unittest import mock

import anthropic
import httpx2
import pydantic

from lib import contract_ai, settings
from lib.criteria import BASE_COLUMNS, SOURCE_ONE, SOURCE_TWO, build_criteria_text, parse_criteria
from lib.schema import AnalysisOutput

SECRET_QUOTE = "임차인 홍길동 010-1234-5678 은 퇴실 시 청소비 30만원을 낸다"
INSTRUCTIONS = "지시문"
CRITERIA = "# 기준 목록\n[퇴실-01] 청소비\n"
URL = "https://api.anthropic.com/v1/messages"


def valid_payload(quote: str = "퇴실 시 청소비 [개인정보]") -> dict:
    return {
        "doc_type": "계약서",
        "contract_type": "선세",
        "read_state": "잘 읽힘",
        "read_note": "",
        "hidden_instruction": "없음",
        "clauses": [
            {
                "criterion_id": "퇴실-01",
                "title": "퇴실 청소비",
                "grade": "주의",
                "quote": quote,
                "location": "1쪽 특약 2번",
                "text_kind": "인쇄 글자",
                "explanation": "나갈 때 청소비를 따로 내야 해요.",
                "question": "청소비는 얼마인지 미리 알려 주실 수 있을까요?",
            }
        ],
        "management_fee": {
            "mention": "금액 있음",
            "amount_text": "12만원",
            "monthly_won": 120000,
            "billing": "정액",
            "itemized": "없음",
            "items": [],
            "source_text": "관리비 월 12만원",
        },
    }


def response(stop_reason="end_turn", text=None, *, model=settings.MODEL, request_id="req_ok", category=None):
    content = [SimpleNamespace(type="thinking", thinking="")]
    if text is not None:
        content.append(SimpleNamespace(type="text", text=text))
    return SimpleNamespace(
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(type="refusal", category=category) if stop_reason == "refusal" else None,
        content=content,
        model=model,
        usage=SimpleNamespace(
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=10,
            cache_read_input_tokens=5,
        ),
        _request_id=request_id,
    )


def ok_response(**kwargs):
    return response(text=json.dumps(valid_payload(), ensure_ascii=False), **kwargs)


def status_error(cls, status, message="error", headers=None, body=None):
    request = httpx2.Request("POST", URL)
    body = body or {"type": "error", "error": {"type": "error", "message": message}}
    resp = httpx2.Response(status, request=request, headers={"request-id": "req_err", **(headers or {})}, json=body)
    return cls(message, response=resp, body=body)


class FakeMessages:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeClient:
    def __init__(self, *outcomes):
        self.messages = FakeMessages(outcomes)
        self.beta = SimpleNamespace(messages=FakeMessages(outcomes))


def run(client, kind="image", **kwargs):
    sleeps = []
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = contract_ai.analyze(
            b"\xff\xd8fake-jpeg",
            kind,
            CRITERIA,
            INSTRUCTIONS,
            client=client,
            sleep=sleeps.append,
            **kwargs,
        )
    return result, sleeps, out.getvalue()


class RequestShapeTest(unittest.TestCase):
    def test_request_has_cache_and_output_config_and_no_sampling_or_thinking(self):
        client = FakeClient(ok_response())
        result, _, _ = run(client)
        self.assertEqual(result.status, "ok")
        params = client.messages.calls[0]

        for banned in ("temperature", "top_p", "top_k", "thinking", "cache_control", "tool_choice", "output_format"):
            self.assertNotIn(banned, params)
        self.assertNotIn("betas", params)
        self.assertNotIn("fallbacks", params)

        self.assertEqual(params["model"], "claude-opus-5-5")
        self.assertEqual(params["max_tokens"], 16000)
        system = params["system"]
        self.assertEqual(len(system), 2)
        self.assertEqual(system[0]["text"], INSTRUCTIONS)
        self.assertNotIn("cache_control", system[0])
        self.assertEqual(system[1]["text"], CRITERIA)
        self.assertEqual(system[1]["cache_control"], {"type": "ephemeral"})

        self.assertEqual(params["output_config"]["effort"], "medium")
        fmt = params["output_config"]["format"]
        self.assertEqual(fmt["type"], "json_schema")
        self.assertEqual(fmt["schema"], anthropic.transform_schema(AnalysisOutput))

        messages = params["messages"]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "user")
        content = messages[0]["content"]
        self.assertEqual(content[0]["type"], "image")
        self.assertEqual(content[0]["source"]["media_type"], "image/jpeg")
        self.assertEqual(content[1]["type"], "text")
        self.assertEqual(content[1]["text"], contract_ai.REQUEST_TEXT)

    def test_pdf_goes_as_document_before_text(self):
        client = FakeClient(ok_response())
        run(client, kind="pdf")
        content = client.messages.calls[0]["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "document")
        self.assertEqual(content[0]["source"]["media_type"], "application/pdf")
        self.assertEqual(content[1]["type"], "text")

    def test_schema_has_no_reasoning_like_names_and_all_required(self):
        schema = anthropic.transform_schema(AnalysisOutput)
        dumped = json.dumps(schema)
        for word in ("reasoning", "thinking", "trace"):
            self.assertNotIn(word, dumped)
        objects = [schema, *schema.get("$defs", {}).values()]
        for obj in objects:
            self.assertEqual(sorted(obj["required"]), sorted(obj["properties"]))
            for prop in obj["properties"].values():
                self.assertNotIn("default", prop)
                if "enum" in prop:
                    self.assertGreaterEqual(len(prop["enum"]), 2)
        contract_types = schema["properties"]["contract_type"]["enum"]
        self.assertIn("연세", contract_types)
        self.assertIn("선세", contract_types)

    def test_fallback_switch_uses_beta_client(self):
        client = FakeClient(ok_response())
        with mock.patch.object(settings, "USE_FALLBACK", True):
            result, _, _ = run(client)
        self.assertEqual(result.status, "ok")
        self.assertEqual(client.messages.calls, [])
        params = client.beta.messages.calls[0]
        self.assertEqual(params["betas"], ["server-side-fallback-2026-07-01"])
        self.assertEqual(params["fallbacks"], "default")


class ResponsePathTest(unittest.TestCase):
    def test_ok(self):
        client = FakeClient(ok_response(model="claude-opus-5-5", request_id="req_1"))
        result, sleeps, _ = run(client)
        self.assertEqual(result.status, "ok")
        self.assertIsInstance(result.parsed, AnalysisOutput)
        self.assertEqual(result.parsed.clauses[0].criterion_id, "퇴실-01")
        self.assertEqual(result.parsed.management_fee.monthly_won, 120000)
        self.assertEqual(result.model, "claude-opus-5-5")
        self.assertEqual(result.request_id, "req_1")
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.usage["input_tokens"], 100)
        self.assertEqual(result.usage["cache_read_input_tokens"], 5)
        self.assertGreaterEqual(result.elapsed_s, 0)
        self.assertEqual(sleeps, [])

    def test_refusal_is_not_retried(self):
        client = FakeClient(response("refusal", None, category="cyber"))
        result, _, _ = run(client)
        self.assertEqual(result.status, "refused")
        self.assertIsNone(result.parsed)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.error_kind, "refusal:cyber")

    def test_truncation_retries_once_with_shrink_text(self):
        client = FakeClient(response("max_tokens", '{"doc_type": "계'), ok_response())
        result, sleeps, _ = run(client)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.attempts, 2)
        self.assertEqual(sleeps, [])
        first, second = client.messages.calls
        self.assertEqual(first["system"], second["system"])
        self.assertEqual(first["output_config"], second["output_config"])
        self.assertEqual(second["messages"][0]["content"][1]["text"], contract_ai.REQUEST_TEXT + contract_ai.SHRINK_TEXT)
        self.assertIn("괜찮음", contract_ai.SHRINK_TEXT)
        self.assertIn("1문장", contract_ai.SHRINK_TEXT)
        self.assertEqual(result.usage["output_tokens"], 100)

    def test_truncation_twice_gives_truncated(self):
        client = FakeClient(response("max_tokens", None), response("max_tokens", None))
        result, _, _ = run(client)
        self.assertEqual(result.status, "truncated")
        self.assertEqual(result.attempts, 2)

    def test_invalid_format_retries_then_reports_without_leaking(self):
        bad = json.dumps({**valid_payload(SECRET_QUOTE), "read_state": "READ OK"}, ensure_ascii=False)
        client = FakeClient(response(text=bad), response(text="not json " + SECRET_QUOTE))
        result, _, logs = run(client)
        self.assertEqual(result.status, "invalid")
        self.assertEqual(result.error_kind, "ValidationError")
        self.assertEqual(result.attempts, 2)
        self.assertNotIn(SECRET_QUOTE, logs)
        self.assertNotIn("홍길동", logs)

    def test_no_text_block_is_invalid(self):
        client = FakeClient(response(text=None), response(text=None))
        result, _, _ = run(client)
        self.assertEqual(result.status, "invalid")
        self.assertEqual(result.error_kind, "NoTextBlock")

    def test_validation_error_hides_input(self):
        bad = json.dumps({**valid_payload(SECRET_QUOTE), "read_state": "READ OK"}, ensure_ascii=False)
        with self.assertRaises(pydantic.ValidationError) as ctx:
            AnalysisOutput.model_validate_json(bad)
        self.assertNotIn("READ OK", str(ctx.exception))
        nested = valid_payload(SECRET_QUOTE)
        nested["clauses"][0]["grade"] = SECRET_QUOTE
        with self.assertRaises(pydantic.ValidationError) as ctx:
            AnalysisOutput.model_validate(nested)
        self.assertNotIn("홍길동", str(ctx.exception))


class ErrorPathTest(unittest.TestCase):
    def test_timeout_is_not_retried(self):
        client = FakeClient(anthropic.APITimeoutError(request=httpx2.Request("POST", URL)))
        result, sleeps, _ = run(client)
        self.assertEqual(result.status, "timeout")
        self.assertEqual(result.attempts, 1)
        self.assertEqual(sleeps, [])
        self.assertEqual(result.error_kind, "APITimeoutError")

    def test_connection_error_retries_once(self):
        err = anthropic.APIConnectionError(request=httpx2.Request("POST", URL))
        client = FakeClient(err, ok_response())
        result, sleeps, _ = run(client)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.attempts, 2)
        self.assertEqual(len(sleeps), 1)

    def test_connection_error_twice_gives_network(self):
        req = httpx2.Request("POST", URL)
        client = FakeClient(anthropic.APIConnectionError(request=req), anthropic.APIConnectionError(request=req))
        result, sleeps, _ = run(client)
        self.assertEqual(result.status, "network")
        self.assertEqual(result.attempts, 2)
        self.assertEqual(len(sleeps), 1)

    def test_overloaded_retries_once(self):
        client = FakeClient(status_error(anthropic.OverloadedError, 529, "Overloaded"), ok_response())
        result, sleeps, _ = run(client)
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(sleeps), 1)

    def test_server_error_twice(self):
        client = FakeClient(
            status_error(anthropic.InternalServerError, 500),
            status_error(anthropic.InternalServerError, 500),
        )
        result, _, _ = run(client)
        self.assertEqual(result.status, "server_error")
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.request_id, "req_err")

    def test_rate_limit_short_retry_after_retries(self):
        client = FakeClient(status_error(anthropic.RateLimitError, 429, headers={"retry-after": "2"}), ok_response())
        result, sleeps, _ = run(client)
        self.assertEqual(result.status, "ok")
        self.assertEqual(sleeps, [2.0])

    def test_rate_limit_long_or_missing_retry_after_is_not_retried(self):
        for headers in ({"retry-after": "60"}, {}):
            client = FakeClient(status_error(anthropic.RateLimitError, 429, headers=headers))
            result, sleeps, _ = run(client)
            self.assertEqual(result.status, "rate_limited")
            self.assertEqual(result.attempts, 1)
            self.assertEqual(sleeps, [])

    def test_enforced_spend_limit_is_not_retried(self):
        client = FakeClient(
            status_error(anthropic.EnforcedSpendLimitReachedError, 429, "limit", headers={"retry-after": "1"})
        )
        result, sleeps, _ = run(client)
        self.assertEqual(result.status, "spend_limit")
        self.assertEqual(sleeps, [])

    def test_usage_limit_400_and_credit_and_billing(self):
        cases = [
            (anthropic.BadRequestError, 400, "You have reached your specified workspace API usage limits.", "spend_limit"),
            (anthropic.BadRequestError, 400, "Your credit balance is too low to access the Anthropic API.", "credit"),
            (anthropic.APIStatusError, 402, "billing problem", "billing"),
            (anthropic.BadRequestError, 400, "Could not process PDF", "bad_request"),
            (anthropic.AuthenticationError, 401, "invalid x-api-key", "auth"),
        ]
        for cls, status, message, expected in cases:
            with self.subTest(expected=expected):
                client = FakeClient(status_error(cls, status, message))
                result, sleeps, logs = run(client)
                self.assertEqual(result.status, expected)
                self.assertEqual(result.attempts, 1)
                self.assertEqual(sleeps, [])
                self.assertNotIn(message, logs)
                self.assertIn(cls.__name__, logs)

    def test_bad_pdf_message(self):
        client = FakeClient(status_error(anthropic.BadRequestError, 400, "Could not process PDF"))
        result, _, _ = run(client, kind="pdf")
        self.assertIn("PDF", contract_ai.user_message(result, "pdf"))
        self.assertIn(contract_ai.user_message(result, "image"), contract_ai.STATUS_MESSAGES.values())

    def test_no_key(self):
        with mock.patch.object(contract_ai, "_read_api_key", return_value=None):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                result = contract_ai.analyze(b"x", "image", CRITERIA, INSTRUCTIONS)
        self.assertEqual(result.status, "no_key")
        self.assertEqual(result.attempts, 0)

    def test_empty_prompt_does_not_call(self):
        client = FakeClient()
        result, _, _ = run_with(client, criteria="  ")
        self.assertEqual(result.status, "error")
        self.assertEqual(client.messages.calls, [])

    def test_on_call_counts_every_call_and_can_stop(self):
        calls = []

        def allow():
            calls.append(1)
            return len(calls) <= 1

        client = FakeClient(response("max_tokens", None), ok_response())
        result, _, _ = run(client, on_call=allow)
        self.assertEqual(result.status, "limit_reached")
        self.assertEqual(len(client.messages.calls), 1)
        self.assertEqual(len(calls), 2)

    def test_client_settings(self):
        client = contract_ai._make_client("sk-ant-test-not-real")
        self.assertEqual(client.max_retries, 0)
        self.assertEqual(client.timeout, 120)


def run_with(client, criteria):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = contract_ai.analyze(b"x", "image", criteria, INSTRUCTIONS, client=client)
    return result, [], out.getvalue()


def csv_bytes(header, rows, bom=True):
    buf = io.StringIO()
    import csv

    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    text = buf.getvalue()
    return ("﻿" + text if bom else text).encode("utf-8")


HEADER = list(BASE_COLUMNS[:11]) + [SOURCE_ONE] + list(BASE_COLUMNS[11:])


def row(crit_id, judge="AI", kind="근거 줄", source="법제처 https://law.go.kr/x", date="2026-11-05"):
    values = {
        "번호": crit_id,
        "이름": "퇴실 청소비",
        "분류": "퇴실·원상복구",
        "줄 종류": kind,
        "판정 주체": judge,
        "확인할 것": "청소비를\n따로 받는지",
        "주의 신호": "청소비 30만원",
        "괜찮은 모습": "청소비 없음",
        "검수된 쉬운 설명": "검수 설명",
        "근거 문장": "근거",
        "이 근거가 말하지 않는 것": "범위",
        SOURCE_ONE: source,
        "확인 날짜": date,
        "기본 질문": "청소비가 있나요?",
    }
    return [values[name] for name in HEADER]


class CriteriaTest(unittest.TestCase):
    def test_reads_bom_and_builds_stable_text(self):
        raw = csv_bytes(HEADER, [row("퇴실-01"), row("관리비-01", judge="코드"), row("생활-01", kind="질문 전용 줄")])
        loaded = parse_criteria(raw)
        self.assertEqual(loaded.errors, [])
        self.assertEqual(len(loaded.rows), 3)
        self.assertEqual(loaded.rows[0].id, "퇴실-01")
        self.assertEqual(loaded.rows[0].source_link, "https://law.go.kr/x")
        self.assertTrue(loaded.rows[0].is_evidence_row)
        self.assertFalse(loaded.by_id["생활-01"].is_evidence_row)
        self.assertEqual([r.id for r in loaded.ai_rows], ["퇴실-01", "생활-01"])

        text = build_criteria_text(loaded.rows)
        self.assertEqual(text, build_criteria_text(parse_criteria(raw).rows))
        self.assertIn("[퇴실-01]", text)
        self.assertNotIn("[관리비-01]", text)
        self.assertIn("질문 전용", text)
        self.assertIn("청소비를 / 따로 받는지", text)
        for screen_only in ("검수 설명", "청소비가 있나요?", "law.go.kr"):
            self.assertNotIn(screen_only, text)
        self.assertEqual(parse_criteria(csv_bytes(HEADER, [row("퇴실-01")], bom=False)).errors, [])

    def test_evidence_row_without_link_or_date_is_question_only(self):
        loaded = parse_criteria(csv_bytes(HEADER, [row("a", source="이름만"), row("b", date="")]))
        self.assertFalse(loaded.by_id["a"].is_evidence_row)
        self.assertFalse(loaded.by_id["b"].is_evidence_row)

    def test_two_source_columns_are_accepted(self):
        header = list(BASE_COLUMNS) + list(SOURCE_TWO)
        values = row("퇴실-01")
        by_name = dict(zip(HEADER, values))
        by_name["출처 이름"], by_name["출처 링크"] = "법제처", "https://law.go.kr/y"
        loaded = parse_criteria(csv_bytes(header, [[by_name[name] for name in header]]))
        self.assertEqual(loaded.errors, [])
        self.assertEqual(loaded.rows[0].source_link, "https://law.go.kr/y")

    def test_errors(self):
        missing = parse_criteria(csv_bytes([h for h in HEADER if h != "판정 주체"], []))
        self.assertTrue(any("판정 주체" in e for e in missing.errors))

        dup = parse_criteria(csv_bytes(HEADER, [row("퇴실-01"), row("퇴실-01")]))
        self.assertTrue(any("두 번" in e for e in dup.errors))
        self.assertEqual(len(dup.rows), 1)

        empty = parse_criteria(csv_bytes(HEADER, [row(""), ["" for _ in HEADER]]))
        self.assertEqual(len(empty.errors), 1)
        self.assertTrue(any("2번째 줄" in e for e in empty.errors))

        self.assertTrue(parse_criteria("번호,이름".encode("cp949")).errors)
        self.assertTrue(parse_criteria("가".encode("cp949")).errors)
        self.assertTrue(parse_criteria(b"").errors)


class StreamlitSmokeTest(unittest.TestCase):
    def test_get_client_reads_secrets_only_when_called(self):
        from streamlit.testing.v1 import AppTest

        def script():
            import streamlit as st

            from lib import contract_ai

            st.text("client" if contract_ai.get_client() is not None else "none")

        at = AppTest.from_function(script)
        at.secrets["ANTHROPIC_API_KEY"] = ""
        at.run()
        self.assertFalse(at.exception)
        self.assertEqual(at.text[0].value, "none")

        at = AppTest.from_function(script)
        at.secrets["ANTHROPIC_API_KEY"] = "sk-ant-test-not-real"
        at.run()
        self.assertFalse(at.exception)
        self.assertEqual(at.text[0].value, "client")


if __name__ == "__main__":
    unittest.main()
