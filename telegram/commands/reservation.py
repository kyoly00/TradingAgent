"""
텔레그램 명령어 예약 처리 모듈:
'rsv {시간} {명령어}' : 매일(주말 제외) 해당 시각에 명령어 예약 실행
'rsv once {시간} {명령어}' : 1회성 명령어 예약 실행
'rsv list' : 예약된 명령어 목록 조회
'rsv remove {일련번호}' : 특정 예약 삭제
'rsv remove all' : 모든 예약 삭제
"""

from utils.settings import (
    get_reservations,
    add_reservation,
    remove_reservation,
    remove_all_reservations,
)


def handle_rsv_command(args: list[str]) -> str:
    """
    'rsv' 명령어를 파싱하여 예약 등록, 조회, 삭제를 수행합니다.

    :param args: 명령어 뒤에 오는 인자 목록
    :return: 텔레그램 회신 메시지 문자열
    """
    if not args:
        return (
            "ℹ️ [명령어 예약 (rsv) 사용법]\n\n"
            "• 매일 반복 예약 (주말 제외):\n"
            "  `rsv {시간} {명령어}`\n"
            "  예: `rsv 10:00 buy 005930 5`\n\n"
            "• 1회성 예약:\n"
            "  `rsv once {시간} {명령어}`\n"
            "  예: `rsv once 10:30 srch 005930`\n\n"
            "• 예약 목록 확인:\n"
            "  `rsv list`\n\n"
            "• 특정 예약 삭제:\n"
            "  `rsv remove {일련번호}` (예: `rsv remove 1`)\n\n"
            "• 전체 예약 삭제:\n"
            "  `rsv remove all`"
        )

    sub_cmd = args[0].strip().lower()

    # 1. 예약 목록 조회 ('rsv list')
    if sub_cmd == "list":
        reservations = get_reservations()
        if not reservations:
            return "ℹ️ 현재 등록된 예약 명령이 없습니다."

        lines = [f"📋 [예약 명령어 목록] (총 {len(reservations)}건)\n"]
        for r in reservations:
            r_id = r.get("id")
            r_time = r.get("time")
            r_cmd = r.get("command")
            r_type = r.get("type", "daily")
            type_label = "🎯 1회성" if r_type == "once" else "🔄 매일(평일)"

            lines.append(f"• [{r_id}] ⏰ {r_time} | {type_label} | `{r_cmd}`")

        lines.append("\n💡 삭제: `rsv remove {번호}` | 전체 삭제: `rsv remove all`")
        return "\n".join(lines)

    # 2. 예약 삭제 ('rsv remove ...')
    if sub_cmd in ("remove", "delete", "del", "rm"):
        if len(args) < 2:
            return "⚠️ 삭제할 예약 번호를 입력해 주세요. (예: `rsv remove 1` 또는 `rsv remove all`)"

        target = args[1].strip().lower()

        # 전체 삭제 ('rsv remove all')
        if target == "all":
            success, msg, count = remove_all_reservations()
            if success:
                return f"🗑️ 등록된 모든 예약 명령({count}건)이 삭제되었습니다."
            else:
                return f"⚠️ {msg}"

        # 개별 삭제 ('rsv remove {번호}')
        try:
            r_id = int(target)
        except ValueError:
            return f"⚠️ 올바른 예약 번호(숫자)를 입력해 주세요: '{args[1]}'"

        success, msg, deleted_item = remove_reservation(r_id)
        if success and deleted_item:
            return f"🗑️ 예약 [{r_id}]이(가) 삭제되었습니다.\n• 대상 명령: `{deleted_item.get('command')}`"
        else:
            return f"⚠️ {msg}"

    # 3. 1회성 예약 등록 ('rsv once {시간} {명령어...}')
    if sub_cmd == "once":
        if len(args) < 3:
            return (
                "⚠️ 1회성 예약 형식이 올바르지 않습니다.\n"
                "• 형식: `rsv once {시간} {명령어}`\n"
                "• 예시: `rsv once 10:30 srch 005930`\n"
                "• 예시: `rsv once 14:00 buy 005930 10`"
            )

        time_str = args[1].strip()
        command_str = " ".join(args[2:]).strip()

        success, msg, new_item = add_reservation(time_str=time_str, command_str=command_str, rsv_type="once")
        if success and new_item:
            return (
                "🎯 [1회성 명령어 예약 완료]\n\n"
                f"• 예약 번호: [{new_item['id']}]\n"
                f"• 실행 시각: {new_item['time']} (24시간제)\n"
                f"• 실행 명령: `{new_item['command']}`\n"
                "• 해당 시각에 1회 실행된 후 자동으로 목록에서 삭제됩니다."
            )
        else:
            return f"⚠️ [예약 등록 실패] {msg}"

    # 4. 매일 반복 예약 등록 ('rsv {시간} {명령어...}')
    time_str = args[0].strip()
    if len(args) < 2:
        return (
            "⚠️ 예약 형식이 올바르지 않습니다.\n"
            "• 형식: `rsv {시간} {명령어}` (매일 평일 반복)\n"
            "• 예시: `rsv 10:00 buy 005930 5`\n"
            "• 1회성: `rsv once 10:00 buy 005930 5`"
        )

    command_str = " ".join(args[1:]).strip()
    success, msg, new_item = add_reservation(time_str=time_str, command_str=command_str, rsv_type="daily")
    if success and new_item:
        return (
            "⏰ [반복 명령어 예약 완료]\n\n"
            f"• 예약 번호: [{new_item['id']}]\n"
            f"• 실행 시각: 매일 {new_item['time']} (주말 제외)\n"
            f"• 실행 명령: `{new_item['command']}`\n"
            "• 매일(토/일 제외) 해당 시각에 명령이 자동으로 실행됩니다."
        )
    else:
        return f"⚠️ [예약 등록 실패] {msg}"
