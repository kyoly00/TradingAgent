"""자연어에 포함된 국내주식 종목명 후보를 로컬 종목표에서 찾습니다."""

import csv
import re
from functools import lru_cache
from pathlib import Path


_STOCK_DATA_DIR = Path(__file__).resolve().parents[1] / "config" / "data" / "stock_info"
_IGNORED_TOKENS = {
    "가격", "거래", "걸어", "걸어놔", "금액", "만원", "매도", "매수", "보유",
    "시장가", "얼마", "전량", "종목", "주문", "주식", "지정가", "현재가",
}


def _normalize(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", str(value).lower())


@lru_cache(maxsize=1)
def _load_stock_names() -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    """KRX CSV를 한 번 읽어 (코드, 표시명, 검색 별칭) 튜플로 캐시합니다."""
    stocks: list[tuple[str, str, tuple[str, ...]]] = []
    for csv_path in sorted(_STOCK_DATA_DIR.glob("KRX_*.csv")):
        rows = None
        for encoding in ("cp949", "utf-8-sig"):
            try:
                with csv_path.open(encoding=encoding, newline="") as file_handle:
                    rows = list(csv.reader(file_handle))
                break
            except UnicodeDecodeError:
                continue
        if not rows:
            continue

        for row in rows[1:]:
            if len(row) < 5:
                continue
            code = row[1].strip()
            if len(code) != 6 or not code.isdigit():
                continue
            names = tuple(name.strip() for name in row[2:5] if name.strip())
            if not names:
                continue
            display_name = row[3].strip() or row[2].strip()
            stocks.append((code, display_name, names))
    return tuple(stocks)


def find_stock_name_candidates(text: str, limit: int = 5) -> list[dict[str, str]]:
    """문장 토큰과 부분 일치하는 종목명 후보를 점수순으로 반환합니다."""
    normalized_text = _normalize(text)
    tokens = {
        token
        for token in re.findall(r"[0-9A-Za-z가-힣]{2,}", str(text).lower())
        if token not in _IGNORED_TOKENS and not token.isdigit()
    }
    matches: list[tuple[int, str, str]] = []

    for code, display_name, names in _load_stock_names():
        normalized_names = tuple(_normalize(name) for name in names)
        score = 0
        if code in str(text):
            score = 1000
        for name in normalized_names:
            if name and name in normalized_text:
                score = max(score, 500 + len(name))
            for token in tokens:
                normalized_token = _normalize(token)
                if len(normalized_token) >= 2 and normalized_token in name:
                    score = max(score, 100 + len(normalized_token))
        if score:
            matches.append((score, code, display_name))

    matches.sort(key=lambda item: (-item[0], item[2], item[1]))
    return [
        {"stock_code": code, "stock_name": name}
        for _, code, name in matches[:max(1, limit)]
    ]
