"""web/public/data/sample_report.json 만들기(API 호출 없음).

app/samples/saved_fake.json 의 output 에 지금 기준 목록으로 apply_rules 를 적용해
/api/analyze 성공 응답과 같은 모양으로 쓴다. 기준 목록이 바뀌면 다시 돌린다.

    app/.venv/bin/python web/api/_make_sample.py
"""

import json
import sys
from pathlib import Path
from typing import Any

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from _engine import rules, settings  # noqa: E402
from _engine.criteria import load_criteria  # noqa: E402
from _engine.schema import AnalysisOutput  # noqa: E402
from analyze import report_to_json  # noqa: E402

SAVED = API_DIR.parent.parent / "samples" / "saved_fake.json"
OUT = API_DIR.parent / "public" / "data" / "sample_report.json"


def build(saved_path: Path = SAVED) -> dict[str, Any]:
    raw = json.loads(saved_path.read_text(encoding="utf-8"))
    output = AnalysisOutput.model_validate(raw["output"])
    crit = load_criteria()
    if crit.errors:
        raise SystemExit("기준 목록 오류: " + "; ".join(crit.errors))
    report = rules.apply_rules(output, crit.by_id)
    sample = str(raw.get("sample") or "")
    meta = {
        "model": str(raw.get("model") or settings.MODEL),
        "effort": str(raw.get("effort") or settings.EFFORT),
        "elapsed_s": float(raw.get("elapsed_s") or 0.0),
        "criteria_version": crit.version,
        "criteria_count": len(crit.rows),
        "kind": "pdf" if sample.lower().endswith(".pdf") else "image",
        "source": "saved",
        "label": str(raw.get("label") or ""),
        "saved_at": str(raw.get("saved_at") or ""),
        "fake": bool(raw.get("fake")),
    }
    return {"ok": True, "report": report_to_json(report), "meta": meta}


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
