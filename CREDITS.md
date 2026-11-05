# 쓴 오픈소스와 데이터

| 이름 | 라이선스 | 쓴 곳 |
|---|---|---|
| [Streamlit](https://github.com/streamlit/streamlit) | Apache-2.0 | 앱 전체 화면 |
| [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) | MIT | 계약서 점검의 Claude 호출 |
| [Pydantic](https://github.com/pydantic/pydantic) | MIT | AI 결과 형식 검사 |
| [Pillow](https://github.com/python-pillow/Pillow) | MIT-CMU(HPND) | 사진 준비(회전, 줄이기, EXIF 지우기) |
| [folium](https://github.com/python-visualization/folium) | MIT | 현황판 지도와 가격 말풍선 |
| [streamlit-folium](https://github.com/randyzwitch/streamlit-folium) | MIT | 지도를 Streamlit에 넣고 누른 방을 돌려받기 |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) | ODbL(지도 데이터) | 바탕 지도. 화면에 출처를 표시한다 |
| OSM Nominatim | ODbL | 조사 단계에서 길 이름을 대략 좌표로 바꿀 때(앱은 부르지 않음) |

시세 자료는 팀이 강원대 홈페이지 게시판, 당근부동산, 에브리타임, 집품, 피터팬의좋은방구하기의 공개 글과 전화 조사에서 숫자와 조건만 옮겨 적은 것이다. 글 원문, 작성자, 연락처는 싣지 않는다.

공공데이터 기준선(`data/baseline_molit.csv`)은 [국토교통부 실거래가 공개시스템](https://rt.molit.go.kr)의 '조건별 자료제공'에서 받은 강원특별자치도 삼척시 전월세 실거래(단독/다가구, 연립/다세대, 오피스텔, 계약일 2025-11-06~2026-11-05)다. 필요한 칸만 남기고 번지와 건물번호는 뺐다. 화면의 기준선은 이 중 40㎡ 이하 월세 계약의 가운데 값이다.
