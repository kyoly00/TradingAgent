"""
동적 런타임 설정 관리 모듈:
config/data/settings.json 파일을 읽고 쓰며,
기본값은 config/data/settings-default.json에서 참조합니다.
"""

import os
import json
import math
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
        "reservations": [],
        "take_profit_rate": 5.0,
        "stop_loss_rate": -10.0,
        "trailing_stop_drop_rate": 3.5,
        "trailing_stop_min_profit_rate": 5.0,
        "trailing_stop_auto_trade_enabled": False,
        "golden_cross_short_interval": 5,
        "golden_cross_long_interval": 20,
        "golden_cross_stocks": [],
        "golden_cross_auto_trade_enabled": False,
        "dead_cross_auto_trade_enabled": False,
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


def get_golden_cross_intervals() -> tuple[int, int]:
    """골든/데드크로스 계산에 사용할 단기·장기 분봉값을 반환합니다."""
    settings = load_settings()
    short_interval = settings.get("golden_cross_short_interval", 5)
    long_interval = settings.get("golden_cross_long_interval", 20)

    try:
        if isinstance(short_interval, bool) or not re.fullmatch(
            r"[+-]?\d+", str(short_interval).strip()
        ):
            raise ValueError
        short_value = int(short_interval)
        if not 1 <= short_value <= 60:
            short_value = 5
    except (TypeError, ValueError):
        short_value = 5

    try:
        if isinstance(long_interval, bool) or not re.fullmatch(
            r"[+-]?\d+", str(long_interval).strip()
        ):
            raise ValueError
        long_value = int(long_interval)
        if not 1 <= long_value <= 60:
            long_value = 20
    except (TypeError, ValueError):
        long_value = 20

    return short_value, long_value


def set_golden_cross_intervals(
    short_interval: str | int,
    long_interval: str | int,
) -> tuple[bool, int, int, str]:
    """
    골든/데드크로스 계산용 단기·장기 분봉값을 검증하고 함께 저장합니다.

    두 값은 각각 1~60 사이의 정수여야 합니다.
    """
    try:
        if isinstance(short_interval, bool) or not re.fullmatch(
            r"[+-]?\d+", str(short_interval).strip()
        ):
            raise ValueError
        short_value = int(short_interval)
    except (TypeError, ValueError):
        return False, 0, 0, f"단기 분봉값은 1~60 사이의 정수여야 합니다: '{short_interval}'"

    try:
        if isinstance(long_interval, bool) or not re.fullmatch(
            r"[+-]?\d+", str(long_interval).strip()
        ):
            raise ValueError
        long_value = int(long_interval)
    except (TypeError, ValueError):
        return False, 0, 0, f"장기 분봉값은 1~60 사이의 정수여야 합니다: '{long_interval}'"

    if not 1 <= short_value <= 60:
        return False, 0, 0, f"단기 분봉값은 1~60 사이여야 합니다: {short_value}"
    if not 1 <= long_value <= 60:
        return False, 0, 0, f"장기 분봉값은 1~60 사이여야 합니다: {long_value}"

    settings = load_settings()
    settings["golden_cross_short_interval"] = short_value
    settings["golden_cross_long_interval"] = long_value

    if save_settings(settings):
        return True, short_value, long_value, "설정이 저장되었습니다."
    return False, short_value, long_value, "설정 파일 저장 중 오류가 발생했습니다."


def _normalize_golden_cross_stocks(stocks: object) -> list[dict]:
    """설정에서 읽은 골든크로스 종목 목록을 검증·정규화합니다."""
    if not isinstance(stocks, list):
        return []

    normalized_stocks = []
    for item in stocks:
        if not isinstance(item, dict):
            continue
        stock_code = str(item.get("stock_code", "")).strip()
        amount = item.get("amount")
        if not stock_code.isdigit() or len(stock_code) != 6:
            continue
        if isinstance(amount, bool):
            continue
        try:
            amount_value = int(amount)
        except (TypeError, ValueError):
            continue
        if amount_value <= 0:
            continue
        normalized_stocks.append({"stock_code": stock_code, "amount": amount_value})

    return normalized_stocks


def get_golden_cross_stocks() -> list[dict]:
    """등록 순서를 유지한 골든크로스 대상 종목 목록을 반환합니다."""
    settings = load_settings()
    return _normalize_golden_cross_stocks(settings.get("golden_cross_stocks", []))


def get_golden_cross_auto_trade_enabled() -> bool:
    """골든크로스 자동매수 활성화 설정을 반환합니다."""
    return bool(get_setting("golden_cross_auto_trade_enabled", False))


def set_golden_cross_auto_trade_enabled(enabled: bool) -> bool:
    """골든크로스 자동매수 활성화 설정을 저장합니다."""
    return set_setting("golden_cross_auto_trade_enabled", bool(enabled))


def get_dead_cross_auto_trade_enabled() -> bool:
    """데드크로스 자동매도 활성화 설정을 반환합니다."""
    return bool(get_setting("dead_cross_auto_trade_enabled", False))


def set_dead_cross_auto_trade_enabled(enabled: bool) -> bool:
    """데드크로스 자동매도 활성화 설정을 저장합니다."""
    return set_setting("dead_cross_auto_trade_enabled", bool(enabled))


def add_golden_cross_stock(
    stock_code: str,
    amount: str | int,
) -> tuple[bool, dict | None, str]:
    """골든크로스 대상 종목과 매수 금액을 목록 끝에 추가합니다."""
    clean_code = str(stock_code).strip()
    if not clean_code.isdigit() or len(clean_code) != 6:
        return False, None, "종목코드는 6자리 숫자로 입력해 주세요."

    if isinstance(amount, bool):
        return False, None, "금액은 0원보다 큰 정수로 입력해 주세요."

    clean_amount = str(amount).strip()
    if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)", clean_amount):
        return False, None, "금액은 0원보다 큰 정수로 입력해 주세요."

    amount_value = int(clean_amount.replace(",", ""))
    if amount_value <= 0:
        return False, None, "금액은 0원보다 큰 정수로 입력해 주세요."

    settings = load_settings()
    stocks = _normalize_golden_cross_stocks(settings.get("golden_cross_stocks", []))
    if any(item["stock_code"] == clean_code for item in stocks):
        return False, None, f"이미 등록된 종목입니다: {clean_code}"
    new_item = {"stock_code": clean_code, "amount": amount_value}
    stocks.append(new_item)
    settings["golden_cross_stocks"] = stocks

    if save_settings(settings):
        return True, new_item, "종목이 추가되었습니다."
    return False, None, "설정 파일 저장 중 오류가 발생했습니다."


def remove_golden_cross_stock(list_number: str | int) -> tuple[bool, dict | None, str]:
    """조회 목록의 1부터 시작하는 번호에 해당하는 종목을 삭제합니다."""
    if isinstance(list_number, bool) or not re.fullmatch(
        r"\d+", str(list_number).strip()
    ):
        return False, None, "삭제할 번호는 1 이상의 정수로 입력해 주세요."

    number = int(list_number)
    settings = load_settings()
    stocks = _normalize_golden_cross_stocks(settings.get("golden_cross_stocks", []))
    if not stocks:
        return False, None, "목록에 등록된 종목이 없습니다."
    if number < 1 or number > len(stocks):
        return False, None, f"목록 번호는 1~{len(stocks)} 사이여야 합니다."

    removed_item = stocks.pop(number - 1)
    settings["golden_cross_stocks"] = stocks

    if save_settings(settings):
        return True, removed_item, "종목이 삭제되었습니다."
    return False, None, "설정 파일 저장 중 오류가 발생했습니다."


def clear_golden_cross_stocks() -> tuple[bool, int, str]:
    """골든크로스 대상 종목 목록을 모두 삭제합니다."""
    settings = load_settings()
    stocks = _normalize_golden_cross_stocks(settings.get("golden_cross_stocks", []))
    removed_count = len(stocks)
    settings["golden_cross_stocks"] = []

    if save_settings(settings):
        return True, removed_count, "종목 목록을 비웠습니다."
    return False, removed_count, "설정 파일 저장 중 오류가 발생했습니다."


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


def get_trailing_stop_settings() -> tuple[float, float]:
    """트레일링 스탑의 고점 대비 하락률과 최소 발동 수익률을 반환합니다."""
    settings = load_settings()

    def normalize(value: object, default: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        if not math.isfinite(number) or number <= 0:
            return default
        return number

    drop_rate = normalize(settings.get("trailing_stop_drop_rate"), 3.5)
    min_profit_rate = normalize(
        settings.get("trailing_stop_min_profit_rate"),
        5.0,
    )
    return drop_rate, min_profit_rate


def set_trailing_stop_settings(
    drop_rate_input: float | str,
    min_profit_rate_input: float | str,
) -> tuple[bool, float, float, str]:
    """트레일링 스탑의 두 퍼센트 설정을 검증하고 원자적으로 저장합니다."""

    def parse_positive_rate(value: float | str, label: str) -> tuple[float | None, str]:
        if isinstance(value, bool):
            return None, f"{label}은 0보다 큰 숫자로 입력해 주세요."
        try:
            number = float(str(value).strip())
        except (TypeError, ValueError):
            return None, f"{label}은 0보다 큰 숫자로 입력해 주세요: '{value}'"
        if not math.isfinite(number) or number <= 0:
            return None, f"{label}은 0보다 큰 유한한 숫자여야 합니다."
        rounded = round(number, 2)
        if rounded <= 0:
            return None, f"{label}은 소수점 둘째 자리 기준으로 0보다 커야 합니다."
        return rounded, ""

    drop_rate, error = parse_positive_rate(drop_rate_input, "고점 대비 하락률")
    if drop_rate is None:
        return False, 0.0, 0.0, error

    min_profit_rate, error = parse_positive_rate(
        min_profit_rate_input,
        "최소 발동 수익률",
    )
    if min_profit_rate is None:
        return False, 0.0, 0.0, error

    settings = load_settings()
    settings["trailing_stop_drop_rate"] = drop_rate
    settings["trailing_stop_min_profit_rate"] = min_profit_rate
    if save_settings(settings):
        return True, drop_rate, min_profit_rate, "설정이 저장되었습니다."
    return False, drop_rate, min_profit_rate, "설정 파일 저장 중 오류가 발생했습니다."


def get_trailing_stop_auto_trade_enabled() -> bool:
    """트레일링 스탑 자동매도 활성화 설정을 반환합니다."""
    return bool(get_setting("trailing_stop_auto_trade_enabled", False))


def set_trailing_stop_auto_trade_enabled(enabled: bool) -> bool:
    """트레일링 스탑 자동매도 활성화 설정을 저장합니다."""
    return set_setting("trailing_stop_auto_trade_enabled", bool(enabled))


def get_take_profit_rate() -> float:
    """설정된 익절 기준 수익률(%)을 반환합니다. 기본값: 5.0"""
    val = get_setting("take_profit_rate", 5.0)
    try:
        return float(val)
    except (ValueError, TypeError):
        return 5.0


def set_take_profit_rate(rate_input: float | str) -> tuple[bool, float, str]:
    """
    익절 기준(%)을 설정하고 config/data/settings.json에 저장합니다.
    양수/음수 입력에 상관없이 항상 양수(+)로 변환하여 저장합니다.

    :param rate_input: 익절 기준 퍼센티지 (예: 5, '5', '-5', '5%')
    :return: (성공 여부 bool, 설정된 익절률 float, 안내 메시지 str)
    """
    try:
        if isinstance(rate_input, str):
            cleaned = rate_input.strip().replace("%", "")
            val = float(cleaned)
        else:
            val = float(rate_input)
    except (ValueError, TypeError):
        return False, 0.0, f"올바른 숫자를 입력해 주세요: '{rate_input}'"

    abs_rate = round(abs(val), 2)
    if abs_rate == 0:
        return False, 0.0, "익절 기준은 0%보다 커야 합니다."

    if set_setting("take_profit_rate", abs_rate):
        return True, abs_rate, f"+{abs_rate:g}%"
    else:
        return False, abs_rate, "설정 파일 저장 중 오류가 발생했습니다."


def get_stop_loss_rate() -> float:
    """설정된 손절 기준 수익률(%)을 반환합니다. 기본값: -10.0"""
    val = get_setting("stop_loss_rate", -10.0)
    try:
        return float(val)
    except (ValueError, TypeError):
        return -10.0


def set_stop_loss_rate(rate_input: float | str) -> tuple[bool, float, str]:
    """
    손절 기준(%)을 설정하고 config/data/settings.json에 저장합니다.
    양수/음수 입력에 상관없이 항상 음수(-)로 변환하여 저장합니다.

    :param rate_input: 손절 기준 퍼센티지 (예: 10, '10', '-10', '10%')
    :return: (성공 여부 bool, 설정된 손절률 float, 안내 메시지 str)
    """
    try:
        if isinstance(rate_input, str):
            cleaned = rate_input.strip().replace("%", "")
            val = float(cleaned)
        else:
            val = float(rate_input)
    except (ValueError, TypeError):
        return False, 0.0, f"올바른 숫자를 입력해 주세요: '{rate_input}'"

    abs_rate = round(abs(val), 2)
    if abs_rate == 0:
        return False, 0.0, "손절 기준은 0%보다 커야 합니다 (예: 10 또는 -10 입력 시 -10%로 설정)."

    neg_rate = -abs_rate
    if set_setting("stop_loss_rate", neg_rate):
        return True, neg_rate, f"{neg_rate:g}%"
    else:
        return False, neg_rate, "설정 파일 저장 중 오류가 발생했습니다."
