# 쓴 오픈소스와 데이터

| 이름 | 라이선스 | 쓴 곳 |
|---|---|---|
| [Next.js](https://github.com/vercel/next.js) · [React](https://github.com/facebook/react) | MIT | 주 사이트 화면(`web/`) |
| [Tailwind CSS](https://github.com/tailwindlabs/tailwindcss) | MIT | 주 사이트 스타일 |
| [Leaflet](https://github.com/Leaflet/Leaflet) · [Leaflet.markercluster](https://github.com/Leaflet/Leaflet.markercluster) | BSD-2-Clause · MIT | 주 사이트 지도 |
| [Streamlit](https://github.com/streamlit/streamlit) | Apache-2.0 | 비상용 Streamlit 판 화면 |
| [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) | MIT | 계약서 점검과 매물 분석 에이전트의 Claude 호출 |
| [Pydantic](https://github.com/pydantic/pydantic) | MIT | AI 결과 형식 검사 |
| [Pillow](https://github.com/python-pillow/Pillow) | MIT-CMU(HPND) | 사진 준비(회전, 줄이기, EXIF 지우기) |
| [folium](https://github.com/python-visualization/folium) | MIT | 현황판 지도와 가격 말풍선 |
| [streamlit-folium](https://github.com/randyzwitch/streamlit-folium) | MIT | 지도를 Streamlit에 넣고 누른 방을 돌려받기 |
| [OpenStreetMap](https://www.openstreetmap.org/copyright) | ODbL(지도 데이터) | 바탕 지도. 화면에 출처를 표시한다 |
| OSM Nominatim | ODbL | 조사 단계에서 길 이름을 대략 좌표로 바꿀 때(앱은 부르지 않음) |
| OpenStreetMap 데이터(Overpass API) | ODbL | 바탕 지도의 길·건물·강·공원·이름표. `tools/build_basemap.py`로 받아 `data/basemap.geojson`에 두고 앱이 직접 칠한다 |
| 네이버 지역 검색 API(NAVER API HUB) | 네이버 클라우드 이용 약관 | 학생 조사 방 33곳의 건물 위치를 한 번 찾아 `data/coords.csv`에 적음. 검색 결과 저장 제한 때문에 행정안전부 도로명주소 좌표로 바꾸는 중(`tools/geocode_juso.py`, 좌표제공 API 승인 대기). 화면은 네이버 지도 검색 링크만 연다 |
| [행정안전부 도로명주소 검색 API](https://business.juso.go.kr) | 이용허락범위 제한 없음 | 길별 건물 목록·지번(`tools/build_buildings.py`), 에이전트의 건물 찾기(`web/api/_engine/live.py`) |
| [국토교통부 건축HUB 건축물대장정보](https://www.data.go.kr/data/15134735/openapi.do) | 이용허락범위 제한 없음 | 건물 용도·사용승인 연도·층수·가구 수·층별 면적(`data/buildings.csv`), 에이전트의 대장 조회 |
| [SUIT 글꼴](https://github.com/sun-typeface/SUIT) | OFL-1.1 | 앱 전체 글꼴(jsDelivr에서 불러옴) |

시세 자료는 팀이 강원대 홈페이지 게시판, 당근부동산, 에브리타임, 집품, 피터팬의좋은방구하기의 공개 글과 전화 조사에서 숫자와 조건만 옮겨 적은 것이다. 글 원문, 작성자, 연락처는 싣지 않는다.

국토부 실거래(`data/molit_rent.csv`)는 [국토교통부 실거래가 공개시스템](https://rt.molit.go.kr)의 '조건별 자료제공'에서 받은 강원특별자치도 삼척시 전월세 실거래(아파트, 단독/다가구, 연립/다세대, 오피스텔, 계약일 2023-11-06~2026-11-05, 2,111건)다. 필요한 칸만 남겼고, 국토부가 가린 단독다가구 번지는 가린 그대로 둔다. 공공데이터 기준선(`data/baseline_molit.csv`)은 이 중 아파트를 뺀 것이고, 화면의 기준선은 40㎡ 이하 월세 계약의 가운데 값이다.
