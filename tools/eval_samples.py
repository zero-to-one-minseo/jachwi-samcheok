"""가상 샘플 계약서를 배포된 분석 API에 보내고, samples/answers.md의 정답표와 대조한다.

    .venv/bin/python tools/eval_samples.py                  # 7개 모두
    .venv/bin/python tools/eval_samples.py c d e            # 고른 샘플만
    .venv/bin/python tools/eval_samples.py --url http://127.0.0.1:8822/api/analyze

실제 Claude를 부르므로 샘플 하나에 약 0.13달러가 든다. 결과 원본은 --save 폴더에 JSON으로 남는다.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
SAMPLES = APP_DIR / "samples"
ANSWERS = SAMPLES / "answers.md"
DEFAULT_URL = "https://jachwi-samcheok.vercel.app/api/analyze"
FILES = {"a": "sample_a.jpg", "y": "sample_y.jpg", "b": "sample_b.pdf", "c": "sample_c.jpg",
         "d": "sample_d.jpg", "e": "sample_e.jpg", "f": "sample_f.jpg"}
BANNER_WORDS = {"e": "AI에게 하는 말", "f": "계약서가 아닌"}


def parse_answers(text: str) -> dict[str, dict[str, set[str]]]:
    """샘플별 {'must': {'기준:등급'}, 'ok': {...}}. 각 절의 첫 코드 블록이 '꼭 나와야 함', 다음이 '나와도 됨'이다."""
    out: dict[str, dict[str, set[str]]] = {}
    for sec in re.split(r"^## ", text, flags=re.M)[1:]:
        m = re.match(r"샘플 ([A-Z])", sec)
        if not m:
            continue
        key = m.group(1).lower()
        parts = re.split(r"\*\*나와도 됨\*\*", sec, maxsplit=1)
        grab = lambda s: {re.sub(r"\s*:\s*", ":", line.strip()) for b in re.findall(r"```\n(.*?)```", s, flags=re.S) for line in b.splitlines() if ":" in line}  # noqa: E731
        must_part = parts[0].split("**괜찮음 또는 카드 없음**")[0]
        maybe_part = (parts[0].split("**괜찮음 또는 카드 없음**")[1] if "**괜찮음 또는 카드 없음**" in parts[0] else "") + (parts[1] if len(parts) > 1 else "")
        out[key] = {"must": grab(must_part), "ok": grab(maybe_part)}
    return out


def call(url: str, path: Path) -> tuple[dict, float]:
    body = json.dumps({"file_b64": base64.b64encode(path.read_bytes()).decode(), "filename": path.name}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "jachwi-eval/1.0"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=310) as r:
            return json.load(r), time.time() - t
    except urllib.error.HTTPError as e:
        try:
            return json.load(e), time.time() - t
        except Exception:
            return {"ok": False, "code": f"http_{e.code}", "message": ""}, time.time() - t


def grade(key: str, resp: dict, ans: dict[str, set[str]]) -> dict:
    if not resp.get("ok"):
        return {"error": f"{resp.get('code')} {resp.get('message', '')}"}
    rep = resp["report"]
    got = set(rep["answer_lines"])
    must, maybe = ans.get("must", set()), ans.get("ok", set())
    missed = sorted(must - got)
    warns = sorted(x for x in got if x.endswith(":주의"))
    false_alarms = sorted(x for x in warns if x not in must)
    banners = [b["text"] for b in rep["banners"]]
    banner_ok = None
    if key in BANNER_WORDS:
        banner_ok = any(BANNER_WORDS[key] in b for b in banners)
    return {
        "must": len(must), "hit": len(must) - len(missed), "missed": missed, "false_alarms": false_alarms,
        "extra": sorted(got - must - maybe), "banners": banners, "banner_ok": banner_ok,
        "doc": rep["doc_type"], "contract": rep["contract_type"], "read": rep["read_state"],
        "hidden": rep["hidden_instruction"], "elapsed": resp["meta"].get("elapsed_s"),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("keys", nargs="*", default=list(FILES))
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--save", type=Path, help="응답 원본 JSON을 남길 폴더")
    args = ap.parse_args(argv)
    answers = parse_answers(ANSWERS.read_text(encoding="utf-8"))
    total_must = total_hit = total_fa = 0
    for key in args.keys:
        path = SAMPLES / FILES[key]
        resp, took = call(args.url, path)
        if args.save:
            args.save.mkdir(parents=True, exist_ok=True)
            (args.save / f"{key}.json").write_text(json.dumps(resp, ensure_ascii=False, indent=1), encoding="utf-8")
        g = grade(key, resp, answers.get(key, {}))
        print(f"\n[{key.upper()}] {FILES[key]} · {took:.0f}초")
        if "error" in g:
            print("  실패:", g["error"])
            continue
        total_must += g["must"]
        total_hit += g["hit"]
        total_fa += len(g["false_alarms"])
        print(f"  꼭 나와야 함 {g['hit']}/{g['must']} · 헛경보 주의 {len(g['false_alarms'])}개")
        print(f"  문서 {g['doc']} · 계약 {g['contract']} · 읽기 {g['read']} · 숨은 지시 {g['hidden']}")
        if g["missed"]:
            print("  놓침:", ", ".join(g["missed"]))
        if g["false_alarms"]:
            print("  헛경보:", ", ".join(g["false_alarms"]))
        if g["extra"]:
            print("  정답표에 없는 결과:", ", ".join(g["extra"]))
        if g["banner_ok"] is not None:
            print("  기대한 띠:", "떴음" if g["banner_ok"] else "안 떴음")
        for b in g["banners"]:
            print("  띠:", b)
    if total_must:
        print(f"\n합계: 꼭 나와야 함 {total_hit}/{total_must} ({total_hit / total_must:.0%}) · 헛경보 주의 {total_fa}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
