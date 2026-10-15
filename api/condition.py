"""키움 WebSocket ka10171 조건검색 목록조회 API 모듈."""

from api.auth import session_manager
from realtime.engine import realtime_engine
from utils.logger import log_error


def _normalize_condition_items(data: object) -> list[dict[str, str]]:
    """ka10171의 배열/객체 응답을 일련번호와 조건식명으로 정규화합니다."""
    if not isinstance(data, list):
        return []

    conditions = []
    for item in data:
        if isinstance(item, dict):
            seq = item.get("seq")
            name = item.get("name")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            seq, name = item[0], item[1]
        else:
            continue

        normalized_seq = str(seq if seq is not None else "").strip()
        normalized_name = str(name if name is not None else "").strip()
        if not normalized_seq or not normalized_name:
            continue
        conditions.append({"seq": normalized_seq, "name": normalized_name})
    return conditions


def get_condition_list(timeout: float = 15.0) -> dict:
    """공용 WebSocket 엔진으로 ka10171 조건검색식 목록을 조회합니다."""
    if not session_manager.is_authenticated() or not session_manager.token:
        return {
            "success": False,
            "conditions": [],
            "error": "로그인이 필요합니다. 먼저 `login paper` 또는 `login real`을 실행해 주세요.",
        }

    try:
        response = realtime_engine.request(
            payload={"trnm": "CNSRLST"},
            expected_trnm="CNSRLST",
            timeout=timeout,
        )
    except Exception as exc:
        log_error(f"[ka10171 조건검색 목록조회 오류] {exc}")
        return {
            "success": False,
            "conditions": [],
            "error": f"조건검색 목록조회 통신 오류: {exc}",
        }

    return_code = response.get("return_code")
    return_msg = str(response.get("return_msg") or "").strip()
    if str(return_code) != "0":
        error = return_msg or "키움 API가 조건검색 목록조회를 거부했습니다."
        return {
            "success": False,
            "conditions": [],
            "return_code": return_code,
            "error": f"[코드 {return_code}] {error}",
        }

    return {
        "success": True,
        "conditions": _normalize_condition_items(response.get("data")),
        "return_code": return_code,
        "error": None,
    }
