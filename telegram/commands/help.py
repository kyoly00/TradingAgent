"""
도움말 및 명령어 안내 처리 모듈:
'/help', '/command', '/commands' 등 사용자의 명령어 안내 요청을 처리하며,
전체 명령어 목록 및 개별 명령어('help buy', 'help srch' 등) 상세 사용법을 안내합니다.
"""


def get_general_help_text() -> str:
    """전체 명령어 안내 텍스트를 반환합니다."""
    return (
        "🤖 [트레이딩 에이전트 봇 명령어 안내]\n\n"
        "📈 **1. 계좌 자산 및 잔고**\n"
        "• `report` 또는 `r` (`/report`, `/r`)\n"
        "  └ 예탁자산, 총매입/평가금액, 손익, 보유 종목 목록 조회\n\n"
        "📊 **2. 종목 시세 및 정보**\n"
        "• `srch {종목코드}` 또는 `/srch {종목코드}`\n"
        "  └ 예: `srch 005930` (삼성전자 현재가, 거래량, 전일대비 등 조회)\n\n"
        "🛒 **3. 주식 주문 (매수 / 매도)**\n"
        "• `buy {종목코드} {수량} [지정가]` (시장가/지정가 매수)\n"
        "  └ 예: `buy 005930 10` (시장가), `buy 005930 10 70000` (지정가)\n"
        "• `sell {종목코드} {수량} [지정가]` (시장가/지정가 매도)\n"
        "  └ 예: `sell 005930 10` (시장가), `sell 005930 10 72000` (지정가)\n\n"
        "⏰ **4. 명령어 예약 실행 (rsv)**\n"
        "• `rsv {시간} {명령어}` : 매일 평일 반복 예약 (예: `rsv 10:00 buy 005930 5`)\n"
        "• `rsv once {시간} {명령어}` : 1회성 예약 (예: `rsv once 10:30 srch 005930`)\n"
        "• `rsv list` : 예약 목록 확인\n"
        "• `rsv remove {번호}` (특정 삭제) | `rsv remove all` (전체 삭제)\n\n"
        "🔑 **5. 로그인 및 세션 관리**\n"
        "• `login paper` : 모의투자 로그인 및 토큰 발급\n"
        "• `login real` : 실전투자 로그인 및 토큰 발급\n"
        "• `login renewal {시간}` : 토큰 자동 갱신 시간 설정 (예: `login renewal 8:50`)\n\n"
        "⚙️ **6. 장 시간 및 시스템 설정**\n"
        "• `mkhr {시작} {종료}` : 장 운영 시간 설정 (기본: 09:00 ~ 15:30, 예: `mkhr 9:30 15:00`)\n"
        "• `stts` : 현재 settings.json의 모든 설정값 확인\n\n"
        "ℹ️ **7. 시스템 상태 및 관리**\n"
        "• `status` : 현재 로그인 모드, 토큰 유효 시간, 스케줄러 상태 확인\n"
        "• `help {명령어}` : 특정 명령어의 상세 설명 보기 (예: `help rsv`, `help buy`)\n"
        "• `power off` : 트레이딩 에이전트 프로그램 안전 종료\n\n"
        "💡 모든 명령어는 `/` 접두사(예: `/help`, `/rsv`, `/r`, `/mkhr`, `/stts`)를 붙이거나 생략해도 동일하게 동작합니다."
    )


def get_command_detail_help(target: str) -> str:
    """특정 명령어의 상세 사용법을 반환합니다."""
    cmd = target.strip().lower()
    if cmd.startswith("/"):
        cmd = cmd[1:]

    if cmd in ("rsv", "예약"):
        return (
            "⏰ [명령어 예약 (rsv) 상세 사용법]\n\n"
            "• 1. 매일 반복 예약 (주말 제외):\n"
            "  형식: `rsv {시간(24시간제)} {명령어}`\n"
            "  예시: `rsv 10:00 buy 005930 5` (매일 평일 10시에 삼성전자 5주 매수)\n\n"
            "• 2. 1회성 예약 (1회 실행 후 자동 삭제):\n"
            "  형식: `rsv once {시간(24시간제)} {명령어}`\n"
            "  예시: `rsv once 14:30 srch 005930`\n\n"
            "• 3. 예약 목록 조회:\n"
            "  형식: `rsv list`\n\n"
            "• 4. 예약 삭제:\n"
            "  특정 삭제: `rsv remove {일련번호}` (예: `rsv remove 1`)\n"
            "  전체 삭제: `rsv remove all`"
        )
    elif cmd in ("report", "r", "리포트", "잔고", "자산"):
        return (
            "📈 [계좌 자산 및 보유 종목 조회 (report/r) 상세 사용법]\n\n"
            "• 기본 형식: `report` 또는 `r`\n"
            "• 슬래시 지원: `/report`, `/r`\n"
            "• 표시 정보:\n"
            "  1. 전체 자금 현황: 추정예탁자산, 총매입금액, 총평가금액, 총평가손익, 총수익률\n"
            "  2. 보유 종목 리스트: 종목번호, 종목명, 보유수량, 매입가, 현재가, 수익률"
        )
    elif cmd in ("srch", "search", "조회"):
        return (
            "🔍 [종목 정보 조회 (srch) 상세 사용법]\n\n"
            "• 기본 형식: `srch {종목코드}`\n"
            "• 사용 예시:\n"
            "  - `srch 005930` (삼성전자 조회)\n"
            "  - `srch 035720` (카카오 조회)\n"
            "• 표시 정보: 현재가, 전일대비(등락율), 거래량, 시가, 고가, 저가"
        )
    elif cmd in ("buy", "매수"):
        return (
            "🛒 [주식 매수 주문 (buy) 상세 사용법]\n\n"
            "• 1. 시장가 매수:\n"
            "  형식: `buy {종목코드} {수량}`\n"
            "  예시: `buy 005930 10` (삼성전자 10주 시장가 매수)\n\n"
            "• 2. 지정가 매수:\n"
            "  형식: `buy {종목코드} {수량} {단가}`\n"
            "  예시: `buy 005930 10 70000` (삼성전자 10주 70,000원 지정가 매수)"
        )
    elif cmd in ("sell", "매도"):
        return (
            "💰 [주식 매도 주문 (sell) 상세 사용법]\n\n"
            "• 1. 시장가 매도:\n"
            "  형식: `sell {종목코드} {수량}`\n"
            "  예시: `sell 005930 10` (삼성전자 10주 시장가 매도)\n\n"
            "• 2. 지정가 매도:\n"
            "  형식: `sell {종목코드} {수량} {단가}`\n"
            "  예시: `sell 005930 10 72000` (삼성전자 10주 72,000원 지정가 매도)"
        )
    elif cmd in ("login", "로그인"):
        return (
            "🔑 [로그인 및 세션 관리 (login) 상세 사용법]\n\n"
            "• 모의투자 로그인: `login paper`\n"
            "• 실전투자 로그인: `login real`\n"
            "• 토큰 정기 갱신 시간 설정: `login renewal {HH:MM}`\n"
            "  예: `login renewal 08:50` (매일 오전 8시 50분에 토큰 자동 갱신)"
        )
    elif cmd in ("status", "상태"):
        return (
            "ℹ️ [시스템 상태 확인 (status) 상세 사용법]\n\n"
            "• 형식: `status` 또는 `/status`\n"
            "• 표시 정보: 현재 로그인 모드(paper/real), 토큰 만료 일시 및 잔여 시간, 스케줄러 가동 여부"
        )
    elif cmd in ("mkhr", "장시간"):
        return (
            "🕒 [장 운영 시간 설정 (mkhr) 상세 사용법]\n\n"
            "• 형식: `mkhr {시작시간} {종료시간}` (24시간제)\n"
            "• 예시: `mkhr 9:30 15:00`\n"
            "• 현재 설정 조회: `mkhr` 단독 입력\n"
            "• 기본값: 09:00 ~ 15:30 (한국 주식 시장 정규 거래 시간)\n"
            "• 저장 위치: `config/data/settings.json`"
        )
    elif cmd in ("stts", "settings", "설정"):
        return (
            "⚙️ [전체 설정값 확인 (stts) 상세 사용법]\n\n"
            "• 형식: `stts` 또는 `/stts`\n"
            "• 설명: `config/data/settings.json`에 저장된 모든 설정값(장 시간, 토큰 갱신 시간 등)을 요약 및 원본 JSON으로 확인합니다."
        )
    elif cmd in ("power", "종료"):
        return (
            "🛑 [시스템 종료 (power off) 상세 사용법]\n\n"
            "• 형식: `power off`\n"
            "• 설명: 백그라운드 스케줄러와 텔레그램 수신 루프를 정리하고 안전하게 프로그램을 종료합니다."
        )
    else:
        return (
            f"❓ '{target}' 명령어에 대한 상세 안내가 없습니다.\n\n"
            "전체 명령어 안내를 보시려면 `/help` 또는 `/command`를 입력하세요."
        )


def handle_help_command(args: list[str]) -> str:
    """
    도움말 명령어를 처리합니다.
    인자가 없으면 전체 안내, 인자가 있으면 해당 명령어의 세부 안내를 회신합니다.
    """
    if not args:
        return get_general_help_text()
    return get_command_detail_help(args[0])
