# 계약서 점검 API (`/api/analyze`)

Vercel Python 함수 하나. 순서는 기존 앱과 같다: `prepare_upload` → `contract_ai.analyze`(Claude 1회) → `rules.apply_rules`.

## 파일

| 파일 | 하는 일 |
|---|---|
| `analyze.py` | Vercel 함수(`handler` 클래스, 표준 라이브러리 `BaseHTTPRequestHandler`) |
| `_engine/` | `app/lib` 엔진 사본(schema, criteria, rules, image_prep, settings, contract_ai)과 `criteria.csv`, `prompts/instructions.txt` 사본 |
| `_dev_server.py` | 로컬 개발 서버 `http://127.0.0.1:8822/api/analyze` |
| `_test_engine.py` | 시험(가짜 Anthropic 클라이언트, 실제 API 안 부름) |
| `_make_sample.py` | `public/data/sample_report.json` 다시 만들기(API 안 부름) |

`_`로 시작하는 파일·폴더는 Vercel 함수가 되지 않는다. `app/lib`, `app/criteria.csv`, `app/prompts/instructions.txt`를 고치면 `_engine/`에도 같이 반영한다(시험이 기준 목록·지시문 사본이 같은지 확인한다).

## 요청

`POST /api/analyze`, `Content-Type: application/json`

```json
{ "file_b64": "<파일 base64, data:...;base64, 앞머리 있어도 됨>", "filename": "contract.jpg" }
```

- JSON 본문 전체가 14MB를 넘으면 `too_large`로 바로 거절한다.
- **Vercel 함수 요청 본문 상한은 4.5MB다.** base64는 원본보다 약 1.33배 커서 원본 약 3.3MB를 넘으면 Vercel이 먼저 413으로 끊는다(이때 본문은 이 JSON 모양이 아니다). 화면 쪽에서 사진을 줄여 보내는 것이 안전하다.
- `GET` → `{"ok": true, "status": "ready"}` (키를 건드리지 않음). `OPTIONS` → 204.

## 성공 응답 (200)

```json
{
  "ok": true,
  "report": {
    "doc_type", "contract_type", "read_state", "read_note", "hidden_instruction",
    "banners": [{"level": "warning|info", "text"}],
    "fee": null | {"criterion_id", "grade", "label", "summary", "formula", "amount_text", "source_text",
                   "items": [["이름", "금액"]], "question", "evidence", "notes", "by_code"},
    "cards": [{"criterion_id", "title", "grade", "ai_grade", "quote", "location", "text_kind", "explanation",
               "question", "in_list", "evidence": null | {"basis", "limits", "source_name", "source_link"},
               "tags", "grade_notes", "rewritten", "by_code", "grade_changed"}],
    "ok_hidden", "questions", "unreadable", "not_interpreted", "changed_count",
    "evidence_count": [근거 붙은 수, 전체 수], "answer_lines",
    "counts": {"주의", "확인 필요", "괜찮음"}
  },
  "meta": {"model", "effort", "elapsed_s", "criteria_version", "criteria_count", "kind": "image|pdf",
           "source": "live|saved", "label?", "saved_at?", "fake?"}
}
```

정확한 타입은 `web/lib/report.ts`. 무료 시연용 저장본은 `web/public/data/sample_report.json`(같은 모양, `meta.source = "saved"`, `meta.fake = true`).

## 실패 응답

```json
{ "ok": false, "code": "<코드>", "message": "<화면에 띄울 한국어 한 문장>", "retryable": true }
```

`message`는 기존 앱이 같은 경우에 띄우는 문장과 같다. `retryable`이 true면 '다시 시도' 단추를 보여 준다.

| code | HTTP | 언제 |
|---|---|---|
| `bad_request` | 400 | JSON이 아니거나 `file_b64`가 없음 |
| `bad_file` | 422 | base64가 깨짐, 열 수 없는 사진, HEIC, 지원 안 하는 형식, API가 파일을 못 읽음(PDF면 PDF 전용 문장) |
| `too_large` | 413 | 본문 14MB 초과, 파일 20MB 초과, PDF 10MB 초과, 사진 화소 초과 |
| `no_key` | 503 | `ANTHROPIC_API_KEY` 환경 변수가 없음 |
| `refused` | 422 | 모델이 거절 |
| `truncated` | 502 | 출력이 잘림(줄인 요청으로 1번 다시 보낸 뒤) |
| `invalid` | 502 | 결과 형식이 맞지 않음 |
| `timeout` | 504 | 120초 시간 초과 |
| `network` | 502 | 연결 끊김 |
| `server_error` | 503 | Anthropic 서버 5xx·과부하 |
| `rate_limited` | 429 | Anthropic 429 |
| `limit_reached` | 429 | 이 프로세스의 KST 하루 150회 상한(인스턴스마다 따로 세는 느슨한 상한) |
| `credit` | 503 | 크레딧 부족, 지출 한도, 결제 문제 |
| `auth` | 503 | 키가 틀림(401·403) |
| `api_error` | 502 | 그 밖의 API 오류 |
| `internal_error` | 500 | 이 함수 안의 예외, 기준 목록·지시문 파일 문제 |
| `method_not_allowed` | 405 | PUT·DELETE·PATCH |

로그에는 HTTP 상태, code, 걸린 시간, request_id만 남는다. 파일 내용, 파일 이름, 키는 찍지 않는다.

## 키

Vercel 프로젝트 설정 → Environment Variables에 `ANTHROPIC_API_KEY`를 넣는다. 저장소에는 넣지 않는다.

## 로컬에서 돌리기 (`app/` 폴더에서)

```bash
# 개발 서버 (키는 환경 변수, 없으면 web/.env.local 의 ANTHROPIC_API_KEY= 줄)
.venv/bin/python web/api/_dev_server.py          # http://127.0.0.1:8822/api/analyze
curl http://127.0.0.1:8822/api/analyze           # {"ok": true, "status": "ready"}

# 시험 (API 안 부름)
.venv/bin/python -m unittest web/api/_test_engine.py

# 저장본 다시 만들기 (기준 목록을 바꿨을 때)
.venv/bin/python web/api/_make_sample.py
```

키를 넣고 실제 파일을 POST하면 Claude가 불려 크레딧이 나간다.
