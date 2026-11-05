# 자취학과

삼척 학생용 웹앱. 두 기능이 한 흐름으로 이어진다.

1. **삼척 자취방 시세 현황판**: 팀이 모은 방 정보를 생활권·월 환산·계약 방식으로 걸러 본다.
2. **계약서 점검**: 방 카드의 '계약 전에 계약서 점검하기'를 누르면 넘어온다. 계약서 사진이나 PDF를 올리면 Claude가 조항을 읽고, 코드가 기준 목록의 근거와 규칙을 붙여 주의/확인 필요/괜찮음 카드와 집주인에게 물을 질문을 만든다.

법률 자문이 아니라 확인 체크리스트다.

- **배포 주소:** https://jachwi-samcheok.streamlit.app (공개, Streamlit Community Cloud, `main`의 `app.py`)
- **외부 데이터:** 국토교통부 삼척시 전월세 실거래 1년치(`data/baseline_molit.csv`). 현황판의 '공공데이터 기준선'이 된다.

## 실행 (로컬)

이 폴더(저장소 루트)에서 실행한다. Community Cloud도 저장소 루트에서 실행하므로 경로를 맞춘다.

```sh
APP_DEV=1 .venv/bin/streamlit run app.py --server.headless true --server.port 8820
```

- 주소: http://localhost:8820 (현황판), http://localhost:8820/contract (계약서 점검)
- `APP_DEV=1`: 개발 스위치. 켜면 화면 예외의 traceback이 보인다. 배포에서는 켜지 않는다.
- `--server.headless true`: macOS에서 첫 실행 때 이메일 입력을 기다리거나 브라우저를 저절로 여는 것을 막는다.
- 가상환경은 Python 3.12(uv가 관리하는 3.12.13)이고 판은 `requirements.txt`에 모두 고정돼 있다. 새로 만들 때만 `uv venv --python 3.12` 뒤 `uv pip install -r requirements.txt`를 한다.

### 주소 옵션 (계약서 점검 화면)

| 옵션 | 하는 일 |
|---|---|
| `?saved=1` | 저장된 결과를 연다. 실제 저장본이 있으면 그것을, 없으면 시험용 가짜(`samples/saved_fake.json`)를 보인다. API 키를 읽지 않는다. |
| `?saved=<이름>` | `samples/saved_<이름>.json` 하나를 연다. 예: `?saved=fake` |
| `?dev=1` | 가상 샘플(sample_a·sample_y)을 바로 실제 분석하는 단추와, 분석 뒤 '결과 파일 내려받기' 단추를 보인다. 리허설과 저장본 만들기에 쓴다. 샘플 분석도 API 크레딧을 쓰고 횟수 상한에 들어간다. |

## 비밀값 (API 키)

- 로컬: `.streamlit/secrets.toml`의 맨 윗단(섹션 없이)에 넣는다.

  ```toml
  ANTHROPIC_API_KEY = "sk-ant-..."
  ```

  이 파일은 `.gitignore`에 있어 저장소에 올라가지 않는다.
- 배포: Community Cloud의 Secrets 칸에 위와 같은 한 줄을 맨 윗단에 붙여 넣는다.
- 키는 '확인하기'를 누른 뒤에만 읽는다. 키가 없어도 현황판과 `?saved=1` 화면은 열린다.

## 폴더 구조

```
app.py                  진입점. st.navigation으로 두 화면을 잇고, 개발 스위치가 꺼지면 오류 상세를 숨긴다
views/rooms.py          ① 시세 현황판
views/contract.py       ② 계약서 점검 화면 (올리기 → 확인하기 → 결과, 저장본 보기)
lib/
  settings.py           모델·effort·상한·경로 같은 설정값 한곳
  rooms_data.py         rooms.csv 읽기, 필터·정렬, 생활권 가운데 값, 국토부 기준선, selected_room 만들기
  schema.py             AI 결과 형식(Pydantic). 칸 이름을 바꾸면 저장본과 규칙 코드가 깨진다
  criteria.py           criteria.csv 읽기·검사, AI에게 줄 기준 목록 글
  image_prep.py         사진 줄이기·회전·EXIF 지우기, PDF 크기 확인
  contract_ai.py        Anthropic 호출, 응답·오류 처리, 화면 문장
  rules.py              AI 결과에 근거·등급 상한·법 표현 바꾸기·관리비 규칙·개인정보 가리기 적용
  render.py             카드·관리비·질문 그리기, 마크다운 기호 막기
  limits.py             세션·하루 분석 횟수 상한
  map_view.py           지도: 좌표 붙이기, 가격 핀, 핀 묶기, 누른 방 돌려받기
  basemap.py            바탕 지도를 네이버 지도 같은 밝은 색으로 직접 칠하기
  style.py              두 화면이 같이 쓰는 꾸밈(CSS). 색·글꼴 기본값은 .streamlit/config.toml [theme]
prompts/instructions.txt AI 지시문
criteria.csv            확인 기준 목록(원본. 구글 시트에서 고친 뒤 CSV UTF-8로 받아 덮어쓴다. 엑셀로 열어 저장하지 않는다)
data/raw/*.csv          팀 조사 원자료(16칸)
data/rooms.csv          현황판이 읽는 정리본(tools/build_rooms.py가 만든다)
data/baseline_molit.csv 국토부 전월세 실거래(삼척시, 279건). 기준선은 40㎡ 이하 월세의 가운데 값. 파일이 없으면 '준비 중'
samples/                가상 샘플 계약서(sample_a.jpg, sample_y.jpg, sample_b.pdf), 정답표(answers.md), 저장본(saved_*.json)
tools/build_rooms.py    원자료 → rooms.csv
tools/build_basemap.py  OpenStreetMap에서 삼척 시내 길·건물·강·공원을 받아 data/basemap.geojson으로(바탕 지도)
tools/make_samples.py   가상 샘플 다시 그리기
tests/                  unittest 시험
.streamlit/config.toml  maxUploadSize 20, magicEnabled false
```

두 기능을 잇는 약속: 현황판 단추가 `st.session_state['selected_room']`에 사전(name, area, contract_type, deposit, monthly, fee_text, included, source, surveyed, kind)을 넣고 `st.switch_page('views/contract.py')`로 넘어간다. 계약서 화면은 맨 위에 '점검 중인 방' 한 줄로 보인다.

## 데이터 갱신

1. 팀 시트에서 받은 CSV(16칸, UTF-8)를 `data/raw/`에 넣는다(같은 이름이면 덮어쓴다).
2. 정리본을 다시 만든다.

   ```sh
   .venv/bin/python tools/build_rooms.py            # data/raw → data/rooms.csv
   .venv/bin/python tools/build_rooms.py --raw 다른폴더 --out 다른경로.csv
   ```

   필수 칸이 빠진 CSV가 있으면 빠진 칸 이름을 말하고 종료 코드 1로 끝난다. 전화번호·글 주소·호수·카톡 구절은 정리본에서 지워지고, 출처는 짧은 이름만 남는다.
3. 앱은 rooms.csv의 수정 시각을 보고 알아서 다시 읽는다. 서버를 다시 켤 필요는 없다.
4. 공공데이터 기준선은 `data/baseline_molit.csv`다. 국토부 실거래가 공개시스템(rt.molit.go.kr) '조건별 자료제공'에서 강원특별자치도 삼척시, 전월세, 단독/다가구·연립/다세대·오피스텔을 1년 범위로 받아 필요한 칸만 남겼다(출처와 기간은 파일 맨 위 두 줄). 새로 받으면 같은 칸 이름으로 덮어쓴다. 읽는 쪽은 앞의 설명 줄을 건너뛰고 칸 이름으로 찾으며, UTF-8과 CP949를 모두 읽는다.

기준 목록을 바꾸면 `criteria.csv`만 덮어쓰면 된다. 매 실행 다시 읽고, 칸 이름·번호에 문제가 있으면 계약서 화면이 오류를 띄우고 분석을 막는다.

## 시험

```sh
.venv/bin/python -m unittest discover -s tests
```

실제 Anthropic API는 부르지 않는다(가짜 응답과 `streamlit.testing.v1.AppTest`로 화면을 돌린다). 'missing ScriptRunContext', 'No runtime found' 경고는 런타임 밖에서 캐시 함수를 부를 때 나는 것이라 무시해도 된다.

## 배포 메모 (Streamlit Community Cloud)

- 저장소 루트가 이 폴더다. 진입 파일은 `app.py`.
- **Python 판은 Advanced settings에서 3.12를 직접 고른다.** 기본값을 믿지 않는다. numpy 2.5가 3.12 이상이라 3.11이면 설치가 실패한다. 배포 뒤에는 판을 못 바꾸니(지우고 다시 배포해야 함) 처음에 맞춘다. 빌드 로그에서 실제 판을 확인한다.
- **Secrets 칸 맨 윗단에 `ANTHROPIC_API_KEY = "..."`** 한 줄을 넣는다.
- 의존성 파일은 **`requirements.txt`만** 둔다. `uv.lock`, `pyproject.toml`, `Pipfile`, `runtime.txt`, `.python-version`은 두지 않는다(Cloud가 uv.lock 등을 requirements.txt보다 먼저 쓴다). requirements.txt를 바꾸면 전체 재배포에 몇 분 걸리니 대회 후반에는 바꾸지 않는다.
- 비공개 저장소면 앱도 비공개로 시작한다. 심사위원 QR을 쓰려면 앱 설정 Sharing에서 앱을 공개로 바꾸고, 로그인하지 않은 휴대폰으로 열리는지 확인한다. (지금은 공개로 바꿔 둠)
- 첫 배포 때 막힌 두 가지(같은 조직·비공개 저장소로 다시 배포할 때 참고):
  - Streamlit이 처음엔 공개 저장소만 읽는다. Workspace settings → Linked accounts의 'Private access → Connect here'로 비공개 저장소 권한을 더 준다. 안 주면 Deploy 단추가 아무 말 없이 멈춘다.
  - GitHub 조직은 Deploy keys가 꺼져 있을 수 있다. 조직 Settings → Deploy keys를 Enabled로 바꾼다. 안 바꾸면 "Deploy keys are disabled" 오류가 난다.
- Advanced settings의 Secrets는 Deploy 화면을 떠나면 날아간다. 키 없이 먼저 배포하고 앱 Settings → Secrets에 넣어도 된다(1분 안에 반영).
- Cloud는 `client.showErrorDetails`를 강제로 바꾼다. 앱은 `APP_DEV`가 없으면 실행 중에 none으로 덮어쓰고 두 화면 본문을 try/except로 감싼다. 첫 배포 때 실제로 traceback이 안 보이는지 확인한다.
- 시연 중에는 그 브랜치에 push하지 않는다(runOnSave로 모든 세션이 다시 실행돼 진행 중인 분석이 버려진다).
- 12시간 접속이 없으면 잠든다. 발표 전에 주소를 열어 깨우고 `?saved=1`과 샘플 한 번을 돌린다.
- 서버는 미국에 있다. 시험·시연은 가상 샘플만 쓴다.
