"""
키움증권 REST API OAuth2 인증 및 세션 관리 모듈:
TR 명세(tr_docs/au10001.json)를 기반으로 모의투자 및 실전투자용 접근토큰을 발급받고,
프로그램 실행 동안 세션(토큰, 토큰타입, 만료일시, 투자 구분)을 유지 및 보관합니다.
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# .env 환경 변수 로드
load_dotenv()

# 프로젝트 루트 경로를 sys.path에 추가
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from api.http_queue import http_client
from config.config import (
    paper_host_url,
    paper_app_key,
    paper_app_secret,
    real_host_url,
    real_app_key,
    real_app_secret,
)

# au10001 TR 명세 상수
TR_ID_AU10001 = "au10001"


def parse_expires_dt(dt_str: str | None) -> datetime | None:
    """
    키움 API 응답의 14자리 만료일시 문자열('YYYYMMDDHHMMSS', 예: '20241107083713')을
    datetime 객체로 변환합니다.
    """
    if not dt_str or len(dt_str) != 14:
        return None
    try:
        return datetime.strptime(dt_str, "%Y%m%d%H%M%S")
    except ValueError:
        return None


def request_access_token(host: str, app_key: str, app_secret: str) -> dict:
    """
    키움 REST API OAuth2 접근토큰(/oauth2/token, TR ID: au10001) 발급을 요청합니다.

    :param host: 키움 API 호스트 URL
    :param app_key: 앱 키
    :param app_secret: 앱 시크릿 키
    :return: 발급 결과 딕셔너리
             {
                 'success': bool,
                 'token': str | None,
                 'token_type': str | None,
                 'expires_dt': datetime | None,
                 'expires_dt_raw': str | None,
                 'return_code': int | str | None,
                 'return_msg': str | None,
                 'error': str | None,
                 'data': dict
             }
    """
    endpoint = "/oauth2/token"
    url = f"{host}{endpoint}"

    headers = {
        "Content-Type": "application/json;charset=UTF-8",
    }

    params = {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "secretkey": app_secret,
    }

    try:
        response = http_client.post(url, headers=headers, json=params, timeout=10)
        body = response.json()

        token = body.get("token")
        return_code = body.get("return_code")
        return_msg = body.get("return_msg", "")

        # 키움 TR 표준 성공 판정: HTTP 200, return_code == 0, token 값 존재
        is_success = (response.status_code == 200) and (str(return_code) == "0") and bool(token)

        if is_success:
            expires_dt_raw = body.get("expires_dt")
            expires_dt = parse_expires_dt(expires_dt_raw)
            token_type = body.get("token_type", "bearer")

            return {
                "success": True,
                "token": token,
                "token_type": token_type,
                "expires_dt": expires_dt,
                "expires_dt_raw": expires_dt_raw,
                "return_code": return_code,
                "return_msg": return_msg,
                "error": None,
                "data": body,
            }
        else:
            error_detail = return_msg or body.get("error_description") or str(body)
            return {
                "success": False,
                "token": None,
                "token_type": None,
                "expires_dt": None,
                "expires_dt_raw": None,
                "return_code": return_code,
                "return_msg": return_msg,
                "error": f"[코드 {return_code}] {error_detail}" if return_code is not None else error_detail,
                "data": body,
            }
    except Exception as e:
        return {
            "success": False,
            "token": None,
            "token_type": None,
            "expires_dt": None,
            "expires_dt_raw": None,
            "return_code": None,
            "return_msg": None,
            "error": f"네트워크 또는 요청 오류: {str(e)}",
            "data": {},
        }


class SessionManager:
    """
    프로그램 실행 중 발급된 토큰 및 투자 구분(paper/real), 만료일시를 보관하는 세션 관리자
    """

    def __init__(self):
        self._mode: str | None = None                 # 'paper' 또는 'real'
        self._token: str | None = None                # 발급받은 Access Token
        self._token_type: str | None = None           # 'bearer'
        self._expires_dt: datetime | None = None      # 토큰 만료 일시 (datetime)
        self._expires_dt_raw: str | None = None       # 14자리 원본 문자열 ('YYYYMMDDHHMMSS')
        self._host: str | None = None                 # 현재 대상 호스트 URL
        self._last_chat_id: int | str | None = None   # 마지막 로그인 요청한 텔레그램 채팅방 ID

    @property
    def mode(self) -> str | None:
        return self._mode

    @property
    def token(self) -> str | None:
        return self._token

    @property
    def token_type(self) -> str | None:
        return self._token_type

    @property
    def expires_dt(self) -> datetime | None:
        return self._expires_dt

    @property
    def expires_dt_raw(self) -> str | None:
        return self._expires_dt_raw

    @property
    def host(self) -> str | None:
        return self._host

    @property
    def last_chat_id(self) -> int | str | None:
        return self._last_chat_id

    @last_chat_id.setter
    def last_chat_id(self, chat_id: int | str | None):
        self._last_chat_id = chat_id

    @property
    def authorization_header(self) -> str | None:
        """API 호출 시 사용할 Authorization 헤더 문자열 (예: 'Bearer {token}')"""
        if not self._token:
            return None
        prefix = (self._token_type or "Bearer").capitalize()
        return f"{prefix} {self._token}"

    def is_authenticated(self) -> bool:
        """현재 토큰이 발급되어 있고 만료되지 않았는지 확인합니다."""
        return bool(self._token) and not self.is_token_expired()

    def is_token_expired(self) -> bool:
        """만료일시(expires_dt)와 현재 시각을 비교하여 만료 여부를 판정합니다."""
        if not self._token:
            return True
        if self._expires_dt is None:
            return False
        return datetime.now() >= self._expires_dt

    def get_remaining_time_str(self) -> str:
        """토큰 만료까지 남은 시간을 사람이 읽기 쉬운 문자열로 반환합니다."""
        if not self._token or not self._expires_dt:
            return "정보 없음"

        diff = self._expires_dt - datetime.now()
        total_seconds = int(diff.total_seconds())

        if total_seconds <= 0:
            return "만료됨"

        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)

        if hours > 0:
            return f"{hours}시간 {minutes}분 남음"
        else:
            return f"{minutes}분 남음"

    def login(self, mode: str) -> tuple[bool, str, str | None]:
        """
        지정된 모드('paper' 또는 'real')에 따라 au10001 TR을 호출하여
        토큰 및 세션 정보를 갱신합니다.

        :param mode: 'paper' (모의투자) 또는 'real' (실전투자)
        :return: (성공 여부 bool, 안내 메시지 str, 발급된 토큰 str | None)
        """
        normalized_mode = mode.strip().lower()

        if normalized_mode == "paper":
            host = paper_host_url
            app_key = paper_app_key
            app_secret = paper_app_secret
            mode_name = "모의투자(Paper)"
        elif normalized_mode == "real":
            host = real_host_url
            app_key = real_app_key
            app_secret = real_app_secret
            mode_name = "실전투자(Real)"
        else:
            return False, f"지원하지 않는 투자 구분입니다: '{mode}'. 'paper' 또는 'real'을 입력하세요.", None

        if not app_key or not app_secret:
            return False, f"[{mode_name}] 설정 파일에 앱 키 또는 시크릿 키가 설정되어 있지 않습니다.", None

        result = request_access_token(host=host, app_key=app_key, app_secret=app_secret)

        if result["success"]:
            self._mode = normalized_mode
            self._token = result["token"]
            self._token_type = result["token_type"]
            self._expires_dt = result["expires_dt"]
            self._expires_dt_raw = result["expires_dt_raw"]
            self._host = host

            exp_str = self._expires_dt.strftime("%Y-%m-%d %H:%M:%S") if self._expires_dt else "미지정"
            msg = f"[{mode_name}] 로그인 성공! (만료예정: {exp_str})"
            return True, msg, self._token
        else:
            msg = f"[{mode_name}] 로그인 실패: {result['error']}"
            return False, msg, None

    def renew(self) -> tuple[bool, str, str | None]:
        """
        현재 세션에 설정된 투자 구분(paper/real)을 바탕으로 토큰을 재발급(갱신)받습니다.

        :return: (성공 여부 bool, 안내 메시지 str, 갱신된 토큰 str | None)
        """
        if not self._mode:
            return False, "현재 로그인된 세션이 없습니다. 먼저 'login paper' 또는 'login real'로 로그인해 주세요.", None
        return self.login(self._mode)

    def logout(self):
        """현재 세션을 초기화합니다."""
        self._mode = None
        self._token = None
        self._token_type = None
        self._expires_dt = None
        self._expires_dt_raw = None
        self._host = None
        self._last_chat_id = None


# 프로그램 전역에서 공유되는 세션 싱글톤 인스턴스
session_manager = SessionManager()
