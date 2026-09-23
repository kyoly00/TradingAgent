"""
동적 런타임 설정 관리 모듈:
config/data/settings.json 파일을 읽고 쓰며,
기본값은 config/data/settings-default.json에서 참조합니다.
"""

import os
import json
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH = os.path.join(PROJECT_ROOT, "config", "data", "settings.json")
DEFAULT_SETTINGS_PATH = os.path.join(PROJECT_ROOT, "config", "data", "settings-default.json")


def load_settings() -> dict:
    """
    settings.json 파일을 로드하며, 파일이 없거나 오류 발생 시 settings-default.json을 로드합니다.
    """
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    if os.path.exists(DEFAULT_SETTINGS_PATH):
        try:
            with open(DEFAULT_SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return {
        "token_renewal_time": "08:55",
        "market_start_time": "09:00",
        "market_end_time": "15:30",
    }


def save_settings(data: dict) -> bool:
    """
    설정 딕셔너리를 config/data/settings.json에 저장합니다.
    """
    try:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"⚠️ 설정 파일 저장 실패: {e}")
        return False


def get_all_settings() -> dict:
    """settings.json의 전체 설정 딕셔너리를 반환합니다."""
    return load_settings()


def get_setting(key: str, default=None):
    """지정된 설정 키의 값을 가져옵니다."""
    settings = load_settings()
    return settings.get(key, default)


def set_setting(key: str, value) -> bool:
    """지정된 설정 키의 값을 업데이트하고 저장합니다."""
    settings = load_settings()
    settings[key] = value
    return save_settings(settings)


def validate_and_normalize_time(time_str: str) -> tuple[bool, str]:
    """
    24시간제 시간 문자열(예: '9:30', '09:30', '15:00')을 검증하고 'HH:MM' 형태로 정규화합니다.

    :param time_str: 검증할 시간 문자열
    :return: (유효 여부 bool, 정규화된 시간 'HH:MM' 또는 에러 메시지 str)
    """
    cleaned = time_str.strip()
    match = re.match(r"^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$", cleaned)
    if not match:
        return False, f"올바르지 않은 시간 형식: '{time_str}'. 24시간제 'HH:MM' (예: 9:30, 15:30) 형식으로 입력해 주세요."

    hour = int(match.group(1))
    minute = int(match.group(2))
    return True, f"{hour:02d}:{minute:02d}"


def get_token_renewal_time() -> str:
    """현재 설정된 토큰 갱신 시간 (HH:MM 형식)을 반환합니다. 기본값: '08:55'"""
    return get_setting("token_renewal_time", "08:55")


def set_token_renewal_time(time_str: str) -> tuple[bool, str]:
    """
    토큰 자동 갱신 시간을 검증 및 저장합니다.
    """
    valid, norm_time = validate_and_normalize_time(time_str)
    if not valid:
        return False, norm_time

    if set_setting("token_renewal_time", norm_time):
        return True, norm_time
    else:
        return False, "설정 파일 저장 중 오류가 발생했습니다."


def get_market_hours() -> tuple[str, str]:
    """
    현재 설정된 정규 장 운영 시작시간 및 종료시간(HH:MM)을 반환합니다.
    기본값: ('09:00', '15:30')
    """
    start_time = get_setting("market_start_time", "09:00")
    end_time = get_setting("market_end_time", "15:30")
    return start_time, end_time


def set_market_hours(start_str: str, end_str: str) -> tuple[bool, str]:
    """
    장 운영 시작 시간과 종료 시간을 24시간제로 검증하고 config/data/settings.json에 저장합니다.

    :param start_str: 시작 시간 (예: '9:30', '09:00')
    :param end_str: 종료 시간 (예: '15:00', '15:30')
    :return: (성공 여부 bool, 안내 메시지 str)
    """
    valid_start, norm_start = validate_and_normalize_time(start_str)
    if not valid_start:
        return False, f"시작 시간 오류: {norm_start}"

    valid_end, norm_end = validate_and_normalize_time(end_str)
    if not valid_end:
        return False, f"종료 시간 오류: {norm_end}"

    if norm_start >= norm_end:
        return False, f"시작 시간({norm_start})은 종료 시간({norm_end})보다 앞서야 합니다."

    settings = load_settings()
    settings["market_start_time"] = norm_start
    settings["market_end_time"] = norm_end

    if save_settings(settings):
        return True, f"{norm_start} ~ {norm_end}"
    else:
        return False, "설정 파일 저장 중 오류가 발생했습니다."


def get_reservations() -> list[dict]:
    """현재 등록된 예약 명령 목록을 반환합니다."""
    return get_setting("reservations", [])


def add_reservation(
    time_str: str,
    command_str: str,
    rsv_type: str = "daily",
) -> tuple[bool, str, dict | None]:
    """
    새로운 예약 명령을 등록하고 settings.json에 저장합니다.

    :param time_str: 실행 시각 문자열 (24시간제, 예: '10:00', '9:30')
    :param command_str: 실행할 텔레그램 명령어 문자열 (예: 'buy 005930 5')
    :param rsv_type: 예약 구분 ('daily': 매일 평일 반복, 'once': 1회성)
    :return: (성공 여부 bool, 메시지 str, 등록된 예약 객체 dict | None)
    """
    valid, norm_time = validate_and_normalize_time(time_str)
    if not valid:
        return False, f"시간 형식 오류: {norm_time}", None

    clean_cmd = command_str.strip()
    if not clean_cmd:
        return False, "예약할 명령어를 입력해 주세요.", None

    settings = load_settings()
    reservations: list[dict] = settings.get("reservations", [])

    # 일련번호(ID) 자동 채번 (기존 최대 ID + 1)
    existing_ids = [r.get("id", 0) for r in reservations if isinstance(r.get("id"), int)]
    new_id = max(existing_ids, default=0) + 1

    new_item = {
        "id": new_id,
        "time": norm_time,
        "command": clean_cmd,
        "type": rsv_type,  # 'daily' 또는 'once'
        "last_run": None,
    }

    reservations.append(new_item)
    settings["reservations"] = reservations

    if save_settings(settings):
        return True, "예약이 성공적으로 등록되었습니다.", new_item
    else:
        return False, "설정 파일 저장 실패로 예약 등록에 실패했습니다.", None


def remove_reservation(rsv_id: int) -> tuple[bool, str, dict | None]:
    """
    지정된 일련번호(ID)의 예약 명령을 삭제합니다.

    :param rsv_id: 삭제할 예약 일련번호
    :return: (성공 여부 bool, 메시지 str, 삭제된 예약 객체 dict | None)
    """
    settings = load_settings()
    reservations: list[dict] = settings.get("reservations", [])

    target_item = None
    new_list = []
    for r in reservations:
        if r.get("id") == rsv_id:
            target_item = r
        else:
            new_list.append(r)

    if target_item is None:
        return False, f"일련번호 [{rsv_id}]에 해당하는 예약 명령이 존재하지 않습니다.", None

    settings["reservations"] = new_list
    if save_settings(settings):
        return True, f"예약 [{rsv_id}] '{target_item.get('command')}' 항목이 삭제되었습니다.", target_item
    else:
        return False, "설정 파일 저장 중 오류가 발생했습니다.", None


def remove_all_reservations() -> tuple[bool, str, int]:
    """
    등록된 모든 예약 명령을 일괄 삭제합니다.

    :return: (성공 여부 bool, 메시지 str, 삭제된 건수 int)
    """
    settings = load_settings()
    reservations: list[dict] = settings.get("reservations", [])
    count = len(reservations)

    settings["reservations"] = []
    if save_settings(settings):
        return True, f"모든 예약 명령(총 {count}건)이 삭제되었습니다.", count
    else:
        return False, "설정 파일 저장 중 오류가 발생했습니다.", 0


