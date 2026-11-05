"""계약서 점검 화면 연기 시험. 실제 API는 부르지 않는다(analyze를 가짜로 바꾼다)."""

import json
import unittest
from pathlib import Path
from unittest import mock

from streamlit.testing.v1 import AppTest

from lib import contract_ai, limits, settings
from lib.schema import AnalysisOutput

APP_DIR = Path(__file__).resolve().parent.parent
APP = str(APP_DIR / "app.py")
PAGE = "views/contract.py"
FAKE = json.loads((APP_DIR / "samples" / "saved_fake.json").read_text(encoding="utf-8"))
SAMPLE_A = (APP_DIR / "samples" / "sample_a.jpg").read_bytes()
_ENV = mock.patch.dict("os.environ", {"APP_DEV": "1"})


def setUpModule():
    # 개발 스위치를 켜야 화면이 예외를 일반 문장으로 덮지 않고 at.exception으로 올린다.
    _ENV.start()


def tearDownModule():
    _ENV.stop()


def open_page(query=None, state=None):
    at = AppTest.from_file(APP, default_timeout=30)
    for key, value in (query or {}).items():
        at.query_params[key] = value
    for key, value in (state or {}).items():
        at.session_state[key] = value
    at.run()
    at.switch_page(PAGE)
    at.run()
    return at


def texts(elements):
    return [element.value for element in elements]


def fake_analyze(status="ok"):
    calls = []

    def analyze(file_bytes, kind, criteria_text, instructions_text, *, on_call=None, **_):
        calls.append((len(file_bytes), kind, len(criteria_text) > 0, len(instructions_text) > 0))
        if on_call is not None and not on_call():
            return contract_ai.AnalysisResult(status="limit_reached", parsed=None, model=settings.MODEL)
        parsed = AnalysisOutput.model_validate(FAKE["output"]) if status == "ok" else None
        return contract_ai.AnalysisResult(status=status, parsed=parsed, model="claude-opus-5-5", elapsed_s=12.3,
                                          attempts=1)

    return analyze, calls


class BeforeUploadTest(unittest.TestCase):
    def test_page_renders(self):
        with mock.patch.object(contract_ai, "_read_api_key", side_effect=AssertionError("secrets read")) as read_key:
            at = open_page()
        self.assertFalse(at.exception)
        self.assertEqual(texts(at.title), ["계약서 점검"])
        uploader = at.file_uploader[0]
        self.assertEqual(uploader.allowed_type, [".jpg", ".jpeg", ".png", ".pdf"])
        self.assertIn("HEIC", uploader.help)
        captions = " ".join(texts(at.caption))
        self.assertIn("HEIC는 스크린샷이나 JPG로", captions)
        self.assertIn("미국 서버", captions)
        self.assertIn("**주민번호·연락처·계좌는 가리고 올려 주세요.**", texts(at.markdown))
        buttons = {b.label: b.disabled for b in at.button}
        self.assertTrue(buttons["확인하기"])
        self.assertFalse(buttons["샘플로 해 보기"])
        self.assertEqual(len(at.info), 0)
        read_key.assert_not_called()

    def test_room_line(self):
        room = {"name": "교동 원룸", "area": "교동", "contract_type": "월세", "deposit": 300, "monthly": 30,
                "fee_text": "관리비 5만 원", "included": ["수도", "인터넷"], "source": "에타", "surveyed": "2026-11-05"}
        at = open_page(state={"selected_room": room})
        self.assertFalse(at.exception)
        line = at.info[0].value
        self.assertIn("점검 중인 방: 교동 원룸(교동)", line)
        self.assertIn("보증금 300만 원 / 월세 30만 원 / 관리비 5만 원(수도·인터넷 포함)", line)

    def test_interrupted_notice(self):
        at = open_page(state={"contract_analysis_started": True})
        self.assertIn("분석이 중간에 끊겼어요. 다시 눌러 주세요.", texts(at.warning))
        at.run()
        self.assertNotIn("분석이 중간에 끊겼어요. 다시 눌러 주세요.", texts(at.warning))


class SavedViewTest(unittest.TestCase):
    def test_saved_param_shows_saved_result_without_secrets(self):
        with mock.patch.object(contract_ai, "_read_api_key", side_effect=AssertionError("secrets read")) as read_key:
            at = open_page(query={"saved": "1"})
        self.assertFalse(at.exception)
        read_key.assert_not_called()
        self.assertTrue(any("저장된 결과" in v for v in texts(at.info)))
        self.assertTrue(any(v.startswith("**주의 ") for v in texts(at.markdown)))
        self.assertEqual(len(at.download_button), 0)

    def test_fake_saved_result_content(self):
        # 실제 저장본이 생겨도 이 시험은 saved_fake.json을 직접 연다.
        at = open_page(query={"saved": "fake"})
        self.assertFalse(at.exception)
        self.assertIn("저장된 결과 · 시험용 가짜 결과예요. 실제 분석이 아니에요.", texts(at.info))
        self.assertEqual(len(at.image), 1)  # 대조 사진(samples/sample_a.jpg를 준비 함수로 줄인 것)
        self.assertIn("**주의 2 · 확인 필요 4 · 괜찮음 3** · 괜찮음 = 안전 보증 아님", texts(at.markdown))
        codes = texts(at.code)
        self.assertIn("120,000 ≥ 100,000", codes)
        joined = "\n".join(codes)
        self.assertNotIn("010-0000-0000", joined)
        self.assertNotIn("000000-0000000", joined)
        self.assertNotIn("000-00-000000", joined)
        self.assertIn("1~2개월", joined)
        self.assertTrue(any(v.startswith("관리-01:확인 필요\n퇴실-01:주의") for v in codes))
        self.assertTrue(any("1\\~2개월" in v for v in texts(at.markdown)))
        self.assertEqual(len(at.download_button), 0)

    def test_sample_button_shows_saved(self):
        at = open_page()
        next(b for b in at.button if b.label == "샘플로 해 보기").click()
        at.run()
        self.assertFalse(at.exception)
        self.assertTrue(any("저장된 결과" in v for v in texts(at.info)))


class AnalyzeFlowTest(unittest.TestCase):
    def upload(self, at, name="sample_a.jpg", data=SAMPLE_A, mime="image/jpeg"):
        at.file_uploader[0].set_value((name, data, mime))
        at.run()
        return at

    def test_upload_then_check(self):
        analyze, calls = fake_analyze()
        with mock.patch.object(contract_ai, "analyze", analyze), \
                mock.patch.object(limits, "daily_counter", return_value=limits.DailyCounter()):
            at = self.upload(open_page(query={"dev": "1"}))
            self.assertFalse(at.exception)
            self.assertEqual(len(at.image), 1)
            check = next(b for b in at.button if b.label == "확인하기")
            self.assertFalse(check.disabled)
            check.click()
            at.run()
        self.assertFalse(at.exception)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1:], ("image", True, True))
        self.assertLess(calls[0][0], len(SAMPLE_A) * 2)
        self.assertEqual(at.session_state[limits.SESSION_COUNT_KEY], 1)
        self.assertFalse(at.session_state["contract_analyze_requested"])
        self.assertNotIn("contract_analysis_started", at.session_state)
        self.assertIn("**주의 2 · 확인 필요 4 · 괜찮음 3** · 괜찮음 = 안전 보증 아님", texts(at.markdown))
        self.assertFalse(any("저장된 결과" in v for v in texts(at.info)))
        self.assertEqual(len(at.download_button), 1)
        self.assertTrue(any("걸린 시간 12.3초" in v for v in texts(at.caption)))
        # 다시 실행해도 분석을 다시 부르지 않는다.
        at.run()
        self.assertEqual(len(calls), 1)

    def test_failure_shows_message_and_buttons(self):
        analyze, calls = fake_analyze(status="timeout")
        with mock.patch.object(contract_ai, "analyze", analyze), \
                mock.patch.object(limits, "daily_counter", return_value=limits.DailyCounter()):
            at = self.upload(open_page())
            next(b for b in at.button if b.label == "확인하기").click()
            at.run()
        self.assertFalse(at.exception)
        self.assertIn(contract_ai.STATUS_MESSAGES["timeout"], texts(at.warning))
        labels = [b.label for b in at.button]
        self.assertIn("다시 시도", labels)
        self.assertIn("저장된 결과 보기", labels)
        next(b for b in at.button if b.label == "저장된 결과 보기").click()
        at.run()
        self.assertTrue(any("저장된 결과" in v for v in texts(at.info)))

    def test_session_limit_blocks_call(self):
        analyze, calls = fake_analyze()
        with mock.patch.object(contract_ai, "analyze", analyze):
            at = self.upload(open_page(state={limits.SESSION_COUNT_KEY: settings.SESSION_LIMIT}))
        self.assertFalse(at.exception)
        self.assertTrue(next(b for b in at.button if b.label == "확인하기").disabled)
        self.assertIn(limits.MSG_SESSION_LIMIT, texts(at.caption))
        self.assertEqual(calls, [])

    def test_bad_file_message(self):
        at = self.upload(open_page(), name="broken.jpg", data=b"not an image", mime="image/jpeg")
        self.assertFalse(at.exception)
        self.assertTrue(any("열 수 없어요" in v for v in texts(at.warning)))
        self.assertTrue(next(b for b in at.button if b.label == "확인하기").disabled)

    def test_pdf_shows_compare_notice(self):
        analyze, _ = fake_analyze()
        pdf = (APP_DIR / "samples" / "sample_b.pdf").read_bytes()
        with mock.patch.object(contract_ai, "analyze", analyze), \
                mock.patch.object(limits, "daily_counter", return_value=limits.DailyCounter()):
            at = self.upload(open_page(), name="sample_b.pdf", data=pdf, mime="application/pdf")
            next(b for b in at.button if b.label == "확인하기").click()
            at.run()
        self.assertFalse(at.exception)
        self.assertIn("원본 PDF를 내 기기에서 열어 대조해 주세요.", texts(at.info))


if __name__ == "__main__":
    unittest.main()
