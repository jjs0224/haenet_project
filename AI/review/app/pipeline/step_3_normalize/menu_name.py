from __future__ import annotations
import re
from typing import List

PRICE_RE = re.compile(r"\d{1,3}(?:,\d{3})+|\d{4,}")

START_KEYWORDS = ["메뉴", "단가", "금액", "수량", "품명", "리뷰", "상품"]
STOP_KEYWORDS = ["소 계","소계","부가세", "합계", "결제", "신용", "카드", "총액", "판매", "금 액", "현금", "공급"]

BANNED_MENU = set(START_KEYWORDS + STOP_KEYWORDS)

# "포함되면 무조건 제외" (라벨류는 여기로)
BLOCK_CONTAINS = [
    "층","가세", "과세", "상품명", "품명", "메뉴", "수량", "단가", "금액",  # 컬럼 라벨
]

REMOVE_GAE_RE = re.compile(r"\b개\b")
REMOVE_QTY_GAE_RE = re.compile(r"\d+\s*개")

CUT_TAIL_KEYWORDS = [
    "리뷰", "진동", "주문", "영수증", "작성", "작성시", "이벤트", "쿠폰", "증정", "할인", "적립", "서비스",
]

def _clean_menu_name(s: str) -> str:
    s = REMOVE_QTY_GAE_RE.sub("", s)
    s = REMOVE_GAE_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"개$", "", s).strip()

    for kw in CUT_TAIL_KEYWORDS:
        idx = s.find(kw)
        if idx != -1:
            s = s[:idx].strip()
            break
    return s.strip()

def _blocked_by_contains(s: str) -> bool:
    # 공백 제거한 버전도 같이 검사(예: "수량 단가 금액")
    s_nospace = s.replace(" ", "")
    return any(kw in s or kw in s_nospace for kw in BLOCK_CONTAINS)

def extract_menu_items(lines: List[str]) -> List[str]:
    menu_items: List[str] = []
    started = False

    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue

        # START 1회
        if not started and any(k in line for k in START_KEYWORDS):
            started = True
            continue
        if not started:
            continue

        # STOP
        if any(k in line for k in STOP_KEYWORDS):
            break

        # 라벨/헤더/컬럼 포함 줄은 무조건 제외 (포함이면 빼기)
        if _blocked_by_contains(line):
            continue

        # 가격 포함된 줄
        if PRICE_RE.search(line):
            name = re.sub(PRICE_RE, "", line)
            name = re.sub(r"\d+", "", name)
            name = re.sub(r"[^가-힣 ]", "", name).strip()
            name = _clean_menu_name(name)

            # name도 포함필터 한번 더
            if name and not _blocked_by_contains(name) and name not in BANNED_MENU and re.search(r"[가-힣]{2,}", name):
                menu_items.append(name)
                continue

            # 이전 줄 fallback
            if i > 0:
                prev = re.sub(r"[^가-힣 ]", "", lines[i - 1]).strip()
                prev = _clean_menu_name(prev)

                # prev도 포함필터 적용 (여기가 핵심)
                if prev and not _blocked_by_contains(prev) and prev not in BANNED_MENU and re.search(r"[가-힣]{2,}", prev):
                    menu_items.append(prev)
            continue

        # 가격 없는 줄 (메뉴 후보)
        name_tokens = re.sub(r"[^가-힣 ]", "", line).strip()
        name_tokens = _clean_menu_name(name_tokens)

        # name_tokens도 포함필터
        if name_tokens and not _blocked_by_contains(name_tokens) and name_tokens not in BANNED_MENU and re.search(r"[가-힣]{2,}", name_tokens):
            menu_items.append(name_tokens)

    # 중복 제거(순서 유지)
    out: List[str] = []
    for m in menu_items:
        if m not in out:
            out.append(m)

    return out




