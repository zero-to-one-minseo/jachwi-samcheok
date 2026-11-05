"""두 화면을 잇는 통합 시험. 실제 API는 부르지 않는다."""

import ast
import os
import re
import unittest
from pathlib import Path
from unittest import mock

from streamlit.testing.v1 import AppTest

from lib import contract_ai
from lib import rooms_data as rd

APP_DIR = Path(__file__).resolve().parent.parent
APP = str(APP_DIR / "app.py")
ROOMS = "views/rooms.py"
CONTRACT = "views/contract.py"
PII_PATTERN = r"01[016789]-?\d{3,4}-?\d{4}|\d{6}-[1-4]\d{6}"


def _room_line_func():
    # views/contract.py를 import하면 화면 본문이 바로 돌아가므로 room_line과 그 도우미만 떼어 낸다.
    tree = ast.parse((APP_DIR / CONTRACT).read_text(encoding="utf-8"))
    wanted = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("_fmt_man", "room_line")]
    namespace: dict = {"Any": object}
    exec(compile(ast.Module(body=wanted, type_ignores=[]), CONTRACT, "exec"), namespace)
    return namespace["room_line"]


def _all_text(at) -> str:
    parts = [e.value for e in at.markdown] + [e.value for e in at.caption] + [e.value for e in at.info]
    parts += [e.value for e in at.warning] + [e.value for e in at.title]
    return "\n".join(str(p) for p in parts)


def _metric(at, label):
    return next(m.value for m in at.metric if m.label == label)


class ProductionModeTest(unittest.TestCase):
    """배포처럼 APP_DEV 없이 돌린다. 화면 예외가 일반 문장으로 덮이므로 st.error가 없어야 정상이다."""

    def setUp(self):
        env = {k: v for k, v in os.environ.items() if k != "APP_DEV"}
        patcher = mock.patch.dict("os.environ", env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_both_pages_render_without_error(self):
        at = AppTest.from_file(APP, default_timeout=30).run()
        self.assertFalse(at.exception)
        self.assertFalse(at.error)
        self.assertEqual(at.title[0].value, "삼척 자취방 시세")
        at.switch_page(CONTRACT).run()
        self.assertFalse(at.exception)
        self.assertFalse(at.error)
        self.assertEqual(at.title[0].value, "계약서 점검")
        self.assertIsNone(next((i for i in at.info if "점검 중인 방" in i.value), None))
        at.switch_page(ROOMS).run()
        self.assertFalse(at.exception)
        self.assertEqual(at.title[0].value, "삼척 자취방 시세")

    def test_saved_view_without_key(self):
        with mock.patch.object(contract_ai, "_read_api_key", side_effect=AssertionError("secrets read")):
            at = AppTest.from_file(APP, default_timeout=30)
            at.query_params["saved"] = "1"
            at.run()
            at.switch_page(CONTRACT).run()
        self.assertFalse(at.exception)
        self.assertFalse(at.error)
        text = _all_text(at)
        self.assertIn("저장된 결과", text)
        self.assertIn("시험용 가짜 결과", text)
        self.assertNotRegex(text, PII_PATTERN)


class HandoffTest(unittest.TestCase):
    """현황판 단추 → 계약서 화면. 개발 스위치를 켜서 예외가 그대로 올라오게 한다."""

    def setUp(self):
        patcher = mock.patch.dict("os.environ", {"APP_DEV": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.rooms = {r["id"]: r for r in rd.read_rooms(rd.ROOMS_CSV)}
        self.at = AppTest.from_file(APP, default_timeout=30).run()

    def _info_line(self):
        return next(i.value for i in self.at.info if "점검 중인 방" in i.value)

    def test_transfer_room_line_and_back_keeps_filters(self):
        at = self.at
        at.pills(key="rooms_kind").select("양도").run()
        count = _metric(at, "조건에 맞는 방")
        room_id = next(b.key for b in at.button if b.key and b.key.startswith("pick_")).removeprefix("pick_")
        room = self.rooms[room_id]
        self.assertEqual(room["kind"], "양도")
        at.button(key=f"pick_{room_id}").click().run()
        at.button(key=f"check_{room_id}").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.title[0].value, "계약서 점검")
        self.assertEqual(at.session_state["selected_room"], rd.to_selected_room(room))
        line = self._info_line()
        self.assertIn(rd.fmt_man(room["monthly"]), line)
        self.assertIn("월 환산", line)
        self.assertIn(room["area"], line)

        at.switch_page(ROOMS).run()
        self.assertFalse(at.exception)
        self.assertEqual(_metric(at, "조건에 맞는 방"), count)
        self.assertEqual(at.pills(key="rooms_kind").value, ["양도"])

    def test_unknown_price_room_hands_over(self):
        at = self.at
        at.checkbox(key="rooms_unknown").check().run()
        keys = [b.key.removeprefix("pick_") for b in at.button if b.key and b.key.startswith("pick_")]
        no_price = [k for k in keys if self.rooms[k].get("monthly") is None]
        self.assertTrue(no_price, "가격 없는 방이 하나는 있어야 한다")
        at.button(key=f"pick_{no_price[0]}").click().run()
        at.button(key=f"check_{no_price[0]}").click().run()
        self.assertFalse(at.exception)
        self.assertIsNone(at.session_state["selected_room"]["monthly"])
        self.assertIn(self.rooms[no_price[0]]["area"], self._info_line())

    def test_sample_after_handoff_keeps_room_line(self):
        at = self.at
        first = next(b.key for b in at.button if b.key and b.key.startswith("pick_")).removeprefix("pick_")
        at.button(key=f"pick_{first}").click().run()
        at.button(key=f"check_{first}").click().run()
        at.button(key="contract_sample").click().run()
        self.assertFalse(at.exception)
        self.assertIn("점검 중인 방", "\n".join(i.value for i in at.info))
        self.assertIn("시험용 가짜 결과", _all_text(at))


class RoomLineForEveryRoomTest(unittest.TestCase):
    def test_every_visible_room_makes_a_line(self):
        room_line = _room_line_func()
        rooms = rd.visible_rooms(rd.read_rooms(rd.ROOMS_CSV))
        self.assertGreater(len(rooms), 50)
        for room in rooms:
            sel = rd.to_selected_room(room)
            line = room_line(sel)
            self.assertTrue(line and line.startswith("점검 중인 방: "), room["id"])
            self.assertNotIn("None", line, room["id"])
            self.assertNotIn("nan", line, room["id"])
            self.assertNotRegex(line, PII_PATTERN + r"|https?://", room["id"])
            if sel["monthly"] is not None and sel["contract_type"] != "전세":
                self.assertIn(rd.fmt_man(sel["monthly"]), line, room["id"])

    def test_empty_or_bad_selection_gives_none(self):
        room_line = _room_line_func()
        for value in (None, {}, "방", {"name": "", "area": ""}):
            self.assertIsNone(room_line(value))


class RequirementsTest(unittest.TestCase):
    def test_core_packages_pinned(self):
        text = (APP_DIR / "requirements.txt").read_text(encoding="utf-8")
        for name in ("streamlit", "anthropic", "pydantic", "pillow"):
            self.assertRegex(text, rf"(?im)^{name}==\d", name)
        self.assertNotRegex(text, r"(?m)^[^#\s].*(>=|~=|\s@\s|file://)")


if __name__ == "__main__":
    unittest.main()
