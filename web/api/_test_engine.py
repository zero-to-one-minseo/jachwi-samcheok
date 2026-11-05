"""/api/analyze 시험. 진짜 Anthropic API는 부르지 않는다(가짜 클라이언트).

    app/.venv/bin/python -m unittest web/api/_test_engine.py
"""

import base64
import contextlib
import io
import json
import os
import re
import sys
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PIL import Image

API_DIR = Path(__file__).resolve().parent
WEB_DIR = API_DIR.parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

import analyze  # noqa: E402
from _engine import contract_ai, settings  # noqa: E402

SAVED_FAKE = WEB_DIR.parent / "samples" / "saved_fake.json"
SAMPLE_REPORT = WEB_DIR / "public" / "data" / "sample_report.json"
REPORT_TS = WEB_DIR / "lib" / "report.ts"
FAKE_KEY = "sk-ant-test-not-real-0000"


def fake_output_text() -> str:
    return json.dumps(json.loads(SAVED_FAKE.read_text(encoding="utf-8"))["output"], ensure_ascii=False)


def response(stop_reason="end_turn", text=None, category=None):
    content = [SimpleNamespace(type="thinking", thinking="")]
    if text is not None:
        content.append(SimpleNamespace(type="text", text=text))
    return SimpleNamespace(
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(type="refusal", category=category) if stop_reason == "refusal" else None,
        content=content,
        model=settings.MODEL,
        usage=SimpleNamespace(input_tokens=100, output_tokens=50, cache_creation_input_tokens=0,
                              cache_read_input_tokens=0),
        _request_id="req_test",
    )


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
        self.beta = SimpleNamespace(messages=self.messages)


def jpeg_bytes() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (64, 48), (240, 240, 240)).save(out, format="JPEG")
    return out.getvalue()


def body_for(data: bytes, filename: str = "contract.jpg") -> bytes:
    return json.dumps({"file_b64": base64.b64encode(data).decode("ascii"), "filename": filename}).encode("utf-8")


@contextlib.contextmanager
def fake_api(*outcomes, key: str | None = FAKE_KEY):
    """키 환경 변수와 가짜 클라이언트를 건다. key=None이면 키가 없는 상태."""
    client = FakeClient(*outcomes)
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    if key is not None:
        env["ANTHROPIC_API_KEY"] = key
    with mock.patch.dict(os.environ, env, clear=True), \
            mock.patch.object(contract_ai, "_make_client", return_value=client) as make:
        yield client, make


def run_process(body: bytes, counter=None):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        status, payload = analyze.process(body, counter=counter or analyze.DailyCounter())
    json.dumps(payload, ensure_ascii=False)  # JSON으로 바뀌어야 한다
    return status, payload, out.getvalue()


def ts_fields(interface: str) -> set[str]:
    text = REPORT_TS.read_text(encoding="utf-8")
    match = re.search(r"export interface " + interface + r" \{(.*?)\n\}", text, re.S)
    assert match, interface
    return set(re.findall(r"^\s+\"?([\w가-힣 ]+?)\"?\??:", match.group(1), re.M))


REPORT_KEYS = {"doc_type", "contract_type", "read_state", "read_note", "hidden_instruction", "banners", "fee",
               "cards", "ok_hidden", "questions", "unreadable", "not_interpreted", "changed_count",
               "evidence_count", "answer_lines", "counts"}
CARD_KEYS = {"criterion_id", "title", "grade", "ai_grade", "quote", "location", "text_kind", "explanation",
             "question", "in_list", "evidence", "tags", "grade_notes", "rewritten", "by_code", "grade_changed"}
FEE_KEYS = {"criterion_id", "grade", "label", "summary", "formula", "amount_text", "source_text", "items",
            "question", "evidence", "notes", "by_code"}
EVIDENCE_KEYS = {"basis", "limits", "source_name", "source_link"}
META_KEYS = {"model", "effort", "elapsed_s", "criteria_version", "criteria_count", "kind", "source"}


class SuccessTest(unittest.TestCase):
    def test_success_json_shape(self):
        with fake_api(response(text=fake_output_text())) as (client, _):
            status, payload, log = run_process(body_for(jpeg_bytes()))
        self.assertEqual(status, 200)
        self.assertEqual(set(payload), {"ok", "report", "meta"})
        self.assertIs(payload["ok"], True)
        report, meta = payload["report"], payload["meta"]
        self.assertEqual(set(report), REPORT_KEYS)
        self.assertTrue(report["cards"])
        for card in report["cards"]:
            self.assertEqual(set(card), CARD_KEYS)
            if card["evidence"] is not None:
                self.assertEqual(set(card["evidence"]), EVIDENCE_KEYS)
        self.assertEqual(set(report["fee"]), FEE_KEYS)
        self.assertIsInstance(report["evidence_count"], list)
        self.assertEqual(len(report["evidence_count"]), 2)
        self.assertEqual(set(report["counts"]), {"주의", "확인 필요", "괜찮음"})
        self.assertEqual(set(meta), META_KEYS)
        self.assertEqual(meta["kind"], "image")
        self.assertEqual(meta["source"], "live")
        self.assertEqual(meta["effort"], settings.EFFORT)
        self.assertEqual(len(client.messages.calls), 1)
        self.assertNotIn(FAKE_KEY, log)
        self.assertNotIn("contract.jpg", log)

    def test_pdf_kind_and_data_url_prefix(self):
        pdf = b"%PDF-1.4\n%fake\n"
        body = json.dumps({"file_b64": "data:application/pdf;base64," + base64.b64encode(pdf).decode(),
                           "filename": "a.pdf"}).encode()
        with fake_api(response(text=fake_output_text())) as (client, _):
            status, payload, _ = run_process(body)
        self.assertEqual(status, 200)
        self.assertEqual(payload["meta"]["kind"], "pdf")
        self.assertEqual(client.messages.calls[0]["messages"][0]["content"][0]["type"], "document")


class ErrorTest(unittest.TestCase):
    def assert_error(self, status, payload, code, http):
        self.assertEqual(status, http)
        self.assertEqual(set(payload), {"ok", "code", "message", "retryable"})
        self.assertIs(payload["ok"], False)
        self.assertEqual(payload["code"], code)
        self.assertTrue(payload["message"])

    def test_bad_base64(self):
        with fake_api() as (client, _):
            status, payload, _ = run_process(json.dumps({"file_b64": "%%%not base64%%%", "filename": "a.jpg"}).encode())
        self.assert_error(status, payload, "bad_file", 422)
        self.assertEqual(client.messages.calls, [])

    def test_undecodable_image(self):
        with fake_api() as (client, _):
            status, payload, _ = run_process(body_for(b"not an image at all", "a.jpg"))
        self.assert_error(status, payload, "bad_file", 422)
        self.assertEqual(client.messages.calls, [])

    def test_bad_json_and_missing_file(self):
        for body in (b"{not json", b"[]", json.dumps({"filename": "a.jpg"}).encode()):
            status, payload, _ = run_process(body)
            self.assert_error(status, payload, "bad_request", 400)

    def test_too_large_body(self):
        status, payload, _ = run_process(b"x" * (analyze.MAX_BODY_BYTES + 1))
        self.assert_error(status, payload, "too_large", 413)

    def test_missing_key(self):
        with fake_api(key=None) as (client, make):
            status, payload, _ = run_process(body_for(jpeg_bytes()))
        self.assert_error(status, payload, "no_key", 503)
        self.assertEqual(payload["message"], contract_ai.STATUS_MESSAGES["no_key"])
        make.assert_not_called()

    def test_refusal(self):
        with fake_api(response(stop_reason="refusal", category="cyber")) as (client, _):
            status, payload, _ = run_process(body_for(jpeg_bytes()))
        self.assert_error(status, payload, "refused", 422)
        self.assertEqual(payload["message"], contract_ai.STATUS_MESSAGES["refused"])
        self.assertFalse(payload["retryable"])
        self.assertEqual(len(client.messages.calls), 1)

    def test_daily_cap(self):
        with fake_api(response(text=fake_output_text())) as (client, _):
            status, payload, _ = run_process(body_for(jpeg_bytes()), counter=analyze.DailyCounter(limit=0))
        self.assert_error(status, payload, "limit_reached", 429)
        self.assertEqual(client.messages.calls, [])


class HttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), analyze.handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, method, body=None, headers=None):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request(method, "/api/analyze", body=body, headers=headers or {})
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        return resp, raw

    def test_get_ready_without_key(self):
        with fake_api(key=None) as (_, make):
            resp, raw = self.request("GET")
        self.assertEqual(resp.status, 200)
        self.assertEqual(json.loads(raw), {"ok": True, "status": "ready"})
        make.assert_not_called()

    def test_options(self):
        resp, _ = self.request("OPTIONS")
        self.assertEqual(resp.status, 204)
        self.assertIn("POST", resp.getheader("Allow"))

    def test_post_success_over_http(self):
        out = io.StringIO()
        with fake_api(response(text=fake_output_text())), contextlib.redirect_stdout(out):
            resp, raw = self.request("POST", body_for(jpeg_bytes()), {"Content-Type": "application/json"})
        self.assertEqual(resp.status, 200)
        self.assertTrue(resp.getheader("Content-Type").startswith("application/json"))
        self.assertIs(json.loads(raw)["ok"], True)

    def test_post_too_large_header_is_rejected_without_reading(self):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest("POST", "/api/analyze")
        conn.putheader("Content-Length", str(analyze.MAX_BODY_BYTES + 1))
        conn.endheaders()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            resp = conn.getresponse()
            payload = json.loads(resp.read())
        conn.close()
        self.assertEqual(resp.status, 413)
        self.assertEqual(payload["code"], "too_large")


class ContractFilesTest(unittest.TestCase):
    """sample_report.json, report.ts, 실제 응답이 같은 칸 이름을 쓰는지."""

    def test_sample_report_matches_live_shape(self):
        sample = json.loads(SAMPLE_REPORT.read_text(encoding="utf-8"))
        self.assertIs(sample["ok"], True)
        self.assertEqual(set(sample["report"]), REPORT_KEYS)
        for card in sample["report"]["cards"]:
            self.assertEqual(set(card), CARD_KEYS)
        self.assertEqual(set(sample["report"]["fee"]), FEE_KEYS)
        self.assertTrue(META_KEYS <= set(sample["meta"]))
        self.assertEqual(sample["meta"]["source"], "saved")

    def test_sample_report_is_current(self):
        import _make_sample

        self.assertEqual(json.loads(SAMPLE_REPORT.read_text(encoding="utf-8")), _make_sample.build())

    def test_report_ts_fields_match(self):
        self.assertEqual(ts_fields("Report"), REPORT_KEYS)
        self.assertEqual(ts_fields("Card"), CARD_KEYS)
        self.assertEqual(ts_fields("FeeCard"), FEE_KEYS)
        self.assertEqual(ts_fields("Evidence"), EVIDENCE_KEYS)
        self.assertEqual(ts_fields("Banner"), {"level", "text"})
        self.assertEqual(ts_fields("GradeCounts"), {"주의", "확인 필요", "괜찮음"})
        self.assertEqual(ts_fields("ReportMeta"), META_KEYS | {"label", "saved_at", "fake"})
        self.assertEqual(ts_fields("AnalyzeError"), {"ok", "code", "message", "retryable"})

    def test_error_codes_listed_in_ts(self):
        text = REPORT_TS.read_text(encoding="utf-8")
        block = re.search(r"export type AnalyzeErrorCode =(.*?);", text, re.S).group(1)
        ts_codes = set(re.findall(r'"(\w+)"', block))
        py_codes = {code for code, _ in analyze.STATUS_TO_CODE.values()}
        py_codes |= {"bad_request", "bad_file", "too_large", "internal_error", "method_not_allowed"}
        self.assertEqual(ts_codes, py_codes)

    def test_engine_criteria_and_prompt_are_copies(self):
        app_root = WEB_DIR.parent
        self.assertEqual((API_DIR / "_engine" / "criteria.csv").read_bytes(), (app_root / "criteria.csv").read_bytes())
        self.assertEqual((API_DIR / "_engine" / "prompts" / "instructions.txt").read_bytes(),
                         (app_root / "prompts" / "instructions.txt").read_bytes())

    def test_no_ui_framework_under_api(self):
        banned = "stream" + "lit"  # 이 파일도 grep에 걸리지 않게 나눠 쓴다.
        for path in API_DIR.rglob("*"):
            if path.is_file() and path.suffix in (".py", ".md", ".txt", ".csv"):
                self.assertNotIn(banned, path.read_text(encoding="utf-8").lower(), path.name)


if __name__ == "__main__":
    unittest.main()
