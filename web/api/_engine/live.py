"""에이전트가 그 자리에서 부르는 공공데이터 조회: 도로명주소 검색 API와 건축HUB 건축물대장(표제부·층별개요).

열쇠는 환경 변수 JUSO_SEARCH_KEY, DATA_GO_KR_KEY. 없으면 조회하지 않고 이유를 돌려준다.
삼척시 주소만 다룬다. 결과는 저장하지 않는다.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from typing import Any

JUSO_URL = "https://business.juso.go.kr/addrlink/addrLinkApi.do"
TITLE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
FLOOR_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrFlrOulnInfo"
TIMEOUT_S = 8


def _get_json(url: str, params: dict[str, str]) -> Any:
    with urllib.request.urlopen(f"{url}?{urllib.parse.urlencode(params)}", timeout=TIMEOUT_S) as r:
        return json.load(r)


def search_address(keyword: str, limit: int = 8) -> dict[str, Any]:
    """삼척시 안에서 건물 이름이나 도로명으로 주소를 찾는다."""
    key = os.environ.get("JUSO_SEARCH_KEY", "").strip()
    if not key:
        return {"ok": False, "error": "주소 검색 열쇠가 없어요"}
    kw = keyword if "삼척" in keyword else f"삼척시 {keyword}"
    try:
        res = _get_json(JUSO_URL, {"confmKey": key, "currentPage": "1", "countPerPage": str(limit),
                                    "keyword": kw, "resultType": "json"})["results"]
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"주소 검색 실패({type(e).__name__})"}
    if res["common"].get("errorCode") != "0":
        return {"ok": False, "error": res["common"].get("errorMessage", "주소 검색 오류")}
    items = [i for i in (res.get("juso") or []) if "삼척시" in i.get("roadAddrPart1", "")]
    return {"ok": True, "results": [{
        "address": i["roadAddrPart1"], "building_name": i.get("bdNm", ""), "road": i.get("rn", ""), "dong": i.get("emdNm", ""),
        "lot": f"{i.get('lnbrMnnm')}-{i.get('lnbrSlno')}",
        "key": f"{i['admCd']}|{i.get('mtYn', '0')}|{i.get('lnbrMnnm')}|{i.get('lnbrSlno')}",
    } for i in items]}


def _register(url: str, key_str: str, service_key: str) -> list[dict]:
    adm, mt, mn, sl = key_str.split("|")
    body = _get_json(url, {"serviceKey": service_key, "sigunguCd": adm[:5], "bjdongCd": adm[5:],
                           "platGbCd": "1" if mt == "1" else "0", "bun": str(mn).zfill(4), "ji": str(sl).zfill(4),
                           "_type": "json", "numOfRows": "30", "pageNo": "1"})["response"]["body"]
    items = (body.get("items") or {}).get("item") or []
    return items if isinstance(items, list) else [items]


def building_register(key_str: str) -> dict[str, Any]:
    """search_address가 준 key로 건축물대장 표제부와 층별개요를 읽어 건물 정보로 정리한다."""
    service_key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not service_key:
        return {"ok": False, "error": "건축물대장 열쇠가 없어요"}
    if not re.fullmatch(r"\d{10}\|[01]\|\d+\|\d+", key_str or ""):
        return {"ok": False, "error": "주소 key 모양이 아니에요. search_address 결과의 key를 그대로 넣어 주세요"}
    try:
        titles = _register(TITLE_URL, key_str, service_key)
        floors = _register(FLOOR_URL, key_str, service_key)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"건축물대장 조회 실패({type(e).__name__})"}
    if not titles:
        return {"ok": True, "found": False}
    t = max(titles, key=lambda x: float(x.get("totArea") or 0))
    units = []
    for f in floors:
        m = re.search(r"(\d+)\s*(가구|세대)", f.get("etcPurps") or "")
        if m and f.get("area") and int(m.group(1)) > 0:
            units.append(round(float(f["area"]) / int(m.group(1)), 1))
    year = str(t.get("useAprDay") or "")[:4]
    return {"ok": True, "found": True, "building": {
        "name": (t.get("bldNm") or "").strip(), "purpose": t.get("mainPurpsCdNm"),
        "built": int(year) if year.isdigit() else None, "floors": t.get("grndFlrCnt"),
        "households": (t.get("fmlyCnt") or 0) + (t.get("hhldCnt") or 0), "area_total": t.get("totArea"),
        "parking": (t.get("indrMechUtcnt") or 0) + (t.get("oudrMechUtcnt") or 0) + (t.get("indrAutoUtcnt") or 0) + (t.get("oudrAutoUtcnt") or 0),
        "unit_sizes_m2": sorted(set(units)),
    }}
